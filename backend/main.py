"""Pathfinder API (FastAPI).

Run (PowerShell, project root, .venv active):
    uvicorn backend.main:app --reload
Then open http://127.0.0.1:8000/app/ for the student web app (frontend/app/),
or http://127.0.0.1:8000/docs to try every endpoint in the browser.

At startup the O*NET data is loaded ONCE: from MySQL if it is running and filled
(scripts/load_onet_to_mysql.py), otherwise from the files in data/raw/onet/. Students,
assessments and recommendations are saved in MySQL; without MySQL they are kept in memory
(lost when the server stops). GET /health shows which sources are in use.
"""
import logging
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend import schemas
from backend.db import PROJECT_ROOT, get_engine, update_schema
from backend.repository import EmailTaken, MemoryRepository, SqlRepository
from backend.security import create_token, expire_minutes, hash_password, read_token, verify_password
from ml.recommender_v2 import (add_extras, explain_v2, field_of, load_from_mysql, load_onet_v2,
                               questions_needed, recommend_v2, target_career)

log = logging.getLogger("pathfinder")
MODEL_VERSION = "v2"
MIN_JOB_ZONE = 3
ONET_DIR = Path(os.getenv("PATHFINDER_ONET_DIR", PROJECT_ROOT / "data" / "raw" / "onet"))
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "app"


# ---------------------------------------------------------------- what the endpoints need
@dataclass
class AppContext:
    data: dict             # the O*NET tables (see ml/baseline_recommender.load_onet)
    repo: object           # SqlRepository or MemoryRepository
    career_ids: dict       # O*NET code -> career_id
    data_source: str       # "mysql" or "files"

    def __post_init__(self):
        self.codes_by_id = {cid: code for code, cid in self.career_ids.items()}
        self.ranked = set(self.data["codes"])


_context = None


def build_context():
    """Load O*NET once. MySQL first (if reachable and loaded), else the files + in-memory storage."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            loaded = conn.execute(text("SELECT COUNT(*) FROM career")).scalar()
        if not loaded:
            raise RuntimeError("the career table is empty - run scripts/load_onet_to_mysql.py")
        update_schema(engine)                 # bring a database made with an older schema.sql up to date
        data = load_from_mysql(engine)
        if any(ONET_DIR.rglob("*.txt")):
            add_extras(data, ONET_DIR)        # alternate titles and related occupations come from files
        repo = SqlRepository(engine)
        return AppContext(data, repo, repo.career_ids(data), "mysql")
    except Exception as err:                  # no server, wrong password, tables missing ...
        log.warning("MySQL not used (%s). Loading O*NET files from %s; data is kept in memory.", err, ONET_DIR)
        data = load_onet_v2(ONET_DIR)
        repo = MemoryRepository()
        return AppContext(data, repo, repo.career_ids(data), "files")


def get_context() -> AppContext:
    """Dependency used by every endpoint. Tests replace it with app.dependency_overrides."""
    if _context is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "O*NET data is not loaded")
    return _context


@asynccontextmanager
async def lifespan(app):
    global _context
    try:
        _context = build_context()
        log.info("Loaded %d careers (%d ranked) from %s", len(_context.data["occupations"]),
                 len(_context.ranked), _context.data_source)
    except Exception:
        log.exception("Could not load O*NET data - endpoints will answer 503")
    yield


app = FastAPI(title="Pathfinder API", version=MODEL_VERSION, lifespan=lifespan,
              description="Career recommendations from O*NET 31.0 (CC BY 4.0). "
                          "Click **Authorize** and paste the token from /auth/login to use the locked endpoints.")

# The prototype runs from a file (origin "null") or a local web server (localhost / 127.0.0.1, any port).
app.add_middleware(CORSMiddleware, allow_origins=["null"],
                   allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
                   allow_methods=["*"], allow_headers=["*"])

bearer = HTTPBearer(auto_error=False)


def current_student(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    """The logged-in student's id, from the 'Authorization: Bearer <token>' header."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return read_token(creds.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})


# ---------------------------------------------------------------- helpers
def _num(x, digits=3):
    """float for JSON; NaN -> None."""
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), digits)


def _career_code(ctx, career_id, must_be_ranked=False):
    code = ctx.codes_by_id.get(career_id)
    if code is None or code not in ctx.data["occupations"].index:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Career {career_id} not found")
    if must_be_ranked and code not in ctx.ranked:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "O*NET has no interest/skill/knowledge data for this career, so it cannot be scored")
    return code


def _own_assessment(ctx, assessment_id, student_id):
    """The assessment as engine input. 404 if it does not exist OR belongs to another student."""
    a = ctx.repo.get_assessment(assessment_id)
    if a is None or a["student_id"] != student_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Assessment {assessment_id} not found")
    student = {"interests": {}, "skills": {}, "subjects": {}}
    for ans in a["answers"]:
        if ans["category"] == "interest":
            student["interests"][ans["item"]] = ans["rating"]
        else:
            key = "skills" if ans["category"] == "skill" else "subjects"
            student[key][ans["item"]] = ({"rating": ans["rating"]} if ans["answer_status"] == "rated"
                                         else ans["answer_status"])
    return student


def _follow_up(label):
    category, item = label.split(": ", 1)
    return {"category": category, "item": item}


# ---------------------------------------------------------------- endpoints
@app.get("/health", response_model=schemas.Health, tags=["system"])
def health(ctx: AppContext = Depends(get_context)):
    return {"status": "ok", "data_source": ctx.data_source, "storage": ctx.repo.kind,
            "careers_total": len(ctx.data["occupations"]), "careers_ranked": len(ctx.ranked),
            "checked_at": datetime.now(timezone.utc)}


@app.post("/auth/register", response_model=schemas.StudentOut, status_code=201, tags=["auth"])
def register(body: schemas.RegisterIn, ctx: AppContext = Depends(get_context)):
    try:
        student_id = ctx.repo.create_student(body.name, body.email, hash_password(body.password),
                                             body.education_level, body.degree, body.year_of_study)
    except EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already registered")
    return {"student_id": student_id, "name": body.name, "email": body.email}


@app.post("/auth/login", response_model=schemas.TokenOut, tags=["auth"])
def login(body: schemas.LoginIn, ctx: AppContext = Depends(get_context)):
    student = ctx.repo.get_student_by_email(body.email)
    if student is None or not verify_password(body.password, student["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")   # same message for both
    return {"access_token": create_token(student["student_id"]), "expires_in_minutes": expire_minutes()}


@app.post("/assessment", response_model=schemas.AssessmentOut, status_code=201, tags=["assessment"])
def save_assessment(body: schemas.AssessmentIn, student_id: int = Depends(current_student),
                    ctx: AppContext = Depends(get_context)):
    answers = [{"category": "interest", "item": t, "rating": r, "answer_status": "rated"}
               for t, r in body.interests.model_dump().items()]
    for category, given in (("skill", body.skills), ("subject", body.subjects)):
        for item, ans in given.items():
            rated = isinstance(ans, schemas.Rating)
            answers.append({"category": category, "item": item, "rating": ans.rating if rated else None,
                            "answer_status": "rated" if rated else ans})
    assessment_id = ctx.repo.create_assessment(student_id, answers)
    statuses = [a["answer_status"] for a in answers if a["category"] != "interest"]
    return {"assessment_id": assessment_id, "rated": statuses.count("rated"),
            "no_experience_or_not_studied": statuses.count("no_experience") + statuses.count("not_studied"),
            "cant_assess": statuses.count("cant_assess")}


@app.get("/recommend", response_model=schemas.RecommendResponse, tags=["recommendations"])
def recommend(assessment_id: int, top_n: int = Query(10, ge=1, le=50),
              student_id: int = Depends(current_student), ctx: AppContext = Depends(get_context)):
    student = _own_assessment(ctx, assessment_id, student_id)
    recs = recommend_v2(student, ctx.data, top_n=top_n, min_job_zone=MIN_JOB_ZONE, diversity=True)
    out, saved = [], []
    for _, r in recs.iterrows():
        reasons, _ = explain_v2(student, ctx.data, r["code"])
        hide = r["display"] == "withheld"            # withheld: show the interest fit only
        out.append({
            "rank": int(r["rank"]), "career_id": ctx.career_ids[r["code"]], "code": r["code"],
            "career": r["career"], "field": r["field"], "display": r["display"],
            "interest_fit": _num(r["interest_fit"]),
            **{k: None if hide else _num(r[k], 1 if k.startswith("match") else 3)
               for k in ("match_low", "match_high", "skill_low", "skill_high", "subject_low", "subject_high")},
            "coverage": _num(r["coverage"]), "critical_unknowns": list(r["critical_unknowns"]),
            "follow_ups": [_follow_up(f) for f in r["follow_ups"]], "reasons": reasons})
        saved.append({"code": r["code"], "match_score": float(r["match_low"]), "reasons": reasons,
                      "model_version": MODEL_VERSION})
    ctx.repo.save_recommendations(student_id, assessment_id, saved, ctx.career_ids)
    return {"assessment_id": assessment_id, "model_version": MODEL_VERSION, "recommendations": out}


@app.get("/careers/search", response_model=list[schemas.CareerBrief], tags=["careers"])
def search_careers(q: str = Query(min_length=2, max_length=100), limit: int = Query(20, ge=1, le=50),
                   ctx: AppContext = Depends(get_context)):
    """Search by job title, including O*NET alternate titles when that file is loaded."""
    needle = q.strip().lower()
    alt = ctx.data.get("alt_titles", {})
    hits = []
    for code, title in ctx.data["occupations"]["Title"].items():
        t = str(title).lower()
        if needle in t:
            hits.append(((0 if t == needle else 1 if t.startswith(needle) else 2), title, code, None))
            continue
        match = next((a for a in alt.get(code, []) if needle in str(a).lower()), None)
        if match is not None:
            hits.append((3, title, code, match))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [{"career_id": ctx.career_ids[code], "code": code, "title": title, "field": field_of(code),
             "ranked": code in ctx.ranked, "matched_title": match}
            for _, title, code, match in hits[:limit] if code in ctx.career_ids]


@app.get("/careers/{career_id}", response_model=schemas.CareerDetail, tags=["careers"])
def get_career(career_id: int, ctx: AppContext = Depends(get_context)):
    code = _career_code(ctx, career_id)
    occ = ctx.data["occupations"].loc[code]
    jz = ctx.data.get("job_zone", {}).get(code) if "job_zone" in ctx.data else None
    return {"career_id": career_id, "code": code, "title": occ["Title"], "description": occ.get("Description"),
            "field": field_of(code), "job_zone": None if jz is None or math.isnan(jz) else int(jz),
            "ranked": code in ctx.ranked}


def _question_fields(questions):
    return [{k: q[k] for k in ("category", "item", "elements", "max_importance")} for q in questions]


@app.get("/target/{career_id}/questions", response_model=schemas.QuestionsResponse, tags=["target career"])
def target_questions(career_id: int, assessment_id: int, student_id: int = Depends(current_student),
                     ctx: AppContext = Depends(get_context)):
    """Survey rows that matter for this career but are unanswered or "cant_assess"."""
    code = _career_code(ctx, career_id, must_be_ranked=True)
    student = _own_assessment(ctx, assessment_id, student_id)
    return {"career_id": career_id, "career": ctx.data["occupations"].loc[code, "Title"],
            "questions": _question_fields(questions_needed(student, ctx.data, code))}


@app.post("/target/{career_id}", response_model=schemas.TargetOut, tags=["target career"])
def target(career_id: int, body: schemas.TargetIn, student_id: int = Depends(current_student),
           ctx: AppContext = Depends(get_context)):
    """Readiness range, gaps, interest check and nearby alternatives for a career the student aims at."""
    code = _career_code(ctx, career_id, must_be_ranked=True)
    student = _own_assessment(ctx, body.assessment_id, student_id)
    t = target_career(student, ctx.data, code, min_job_zone=MIN_JOB_ZONE)
    gaps = [{k: (_num(v, 2) if isinstance(v, float) else v) for k, v in g.items()}
            for g in t["gaps"].to_dict("records")]
    return {**{k: t[k] for k in ("code", "career", "field", "job_zone", "readiness", "interest_fit", "reasons")},
            "career_id": career_id, "gaps": gaps,
            "questions_needed": _question_fields(t["questions_needed"]),
            "alternatives": [{**a, "career_id": ctx.career_ids[a["code"]]}
                             for a in t["alternatives"] if a["code"] in ctx.career_ids]}


# ---------------------------------------------------------------- student web app
# The student app (frontend/app/) is served by this same server at /app/, so the page and the API
# share one address: no CORS problems and only one thing to start. Mounted last so it never hides an endpoint.
@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/")


if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="app")

