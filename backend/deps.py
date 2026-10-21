"""Shared pieces used by every endpoint file (main.py and backend/routes/*.py).

AppContext   the O*NET data, the storage (MySQL or memory) and the India/industry settings,
             loaded once at startup (see main.build_context)
get_context  FastAPI dependency that hands the AppContext to an endpoint (tests override it)
current_student  the logged-in student's id from the "Authorization: Bearer <token>" header
"""
import json
import math
import os
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, status
from dotenv import load_dotenv
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.security import read_token
from ml.localise import clean_title, industries_of, load_industries, load_salaries, salary_for
from ml.pathways import load_courses, load_routes
from ml.preferences import load_areas, load_courses as load_study_courses, personalised
from ml.recommender_v2 import field_of, recommend_v2
from ml.recommender_v3 import recommend_v3
from ml.semantic import LazyMatcher, SemanticMatcher

load_dotenv()
# Which engine ranks careers: "v3" (v2 + strength fit; better Hit@k on the survey, see
# docs/results/survey/hit_rate.csv) or "v2". Set ENGINE_VERSION in .env to switch back.
MODEL_VERSION = os.getenv("ENGINE_VERSION", "v3").strip().lower()
if MODEL_VERSION not in ("v2", "v3"):
    raise ValueError(f"ENGINE_VERSION must be v2 or v3, got {MODEL_VERSION!r}")
MIN_JOB_ZONE = 3


def recommend(student, data, top_n=10):
    """Top careers from the quiz answers only, with the engine chosen by ENGINE_VERSION
    (Job Zone >= 3, field diversity on). The app uses personal_recommend below."""
    engine = recommend_v3 if MODEL_VERSION == "v3" else recommend_v2
    return engine(student, data, top_n=top_n, min_job_zone=MIN_JOB_ZONE, diversity=True)


def personal_recommend(ctx, student, top_n=10, hidden_ids=()):
    """Top careers using the student's areas, course, lifestyle and "not for me" choices (ml/preferences.py).
    Returns (DataFrame, info). With ENGINE_VERSION=v2 the extra answers are not used (v2 has no such step)."""
    hidden = {ctx.codes_by_id[i] for i in hidden_ids if i in ctx.codes_by_id}
    if MODEL_VERSION == "v2":
        recs = recommend(student, ctx.data, top_n + len(hidden))
        recs = recs[~recs["code"].isin(hidden)].head(top_n).assign(rank=lambda d: range(1, len(d) + 1))
        return recs.assign(group="all", area_keys=[[]] * len(recs), area_labels=[[]] * len(recs), course_link=False,
                           extra_reasons=[[]] * len(recs)), {"notes": [], "chosen_areas": [], "areas_from": None}
    recs, info = personalised(student, ctx.data, student.get("profile"), top_n=top_n, hidden=hidden,
                              min_job_zone=MIN_JOB_ZONE, areas=ctx.areas, courses=ctx.study_courses,
                              field_model=ctx.field_model)
    info.pop("predicted", None)                   # the note already says it; not part of the API response
    return recs, info


@dataclass
class AppContext:
    data: dict             # the O*NET tables (see ml/baseline_recommender.load_onet)
    repo: object           # SqlRepository or MemoryRepository
    career_ids: dict       # O*NET code -> career_id
    data_source: str       # "mysql" or "files"
    industries: list = field(default_factory=load_industries)     # config/industries.csv
    salaries: list = field(default_factory=load_salaries)         # config/salary_india.csv (cited rows only)
    routes: list = field(default_factory=load_routes)             # config/career_paths.csv (Indian education routes)
    courses: list = field(default_factory=load_courses)           # config/courses.csv (checked courses only)
    areas: object = field(default_factory=load_areas)             # config/areas.csv (areas a student can pick)
    study_courses: object = None                                  # config/course_areas.csv (degree -> areas)
    field_model: object = None     # ml/field_model.py, trained on the survey at startup (None without the file)
    matcher: object = None     # ml/semantic.py matcher (LazyMatcher at startup; built on first use otherwise)

    def __post_init__(self):
        self.codes_by_id = {cid: code for code, cid in self.career_ids.items()}
        if self.study_courses is None:
            self.study_courses = load_study_courses(areas=self.areas)
        self.ranked = set(self.data["codes"])

    # ---- small helpers the endpoints share
    def official_title(self, code):
        return str(self.data["occupations"].loc[code, "Title"])

    def display_title(self, code):
        """Short common title (ml/localise.py); trimmed official title if none was loaded."""
        short = self.data.get("short_title")
        if short is not None and code in short.index:
            return str(short[code])
        return clean_title(self.official_title(code))

    def summary(self, code, max_chars=180):
        """First sentence of the O*NET description: what the job actually involves."""
        text = str(self.data["occupations"].loc[code].get("Description") or "").strip()
        first = text.split(". ")[0].rstrip(".")
        if len(first) > max_chars:
            first = first[:max_chars].rsplit(" ", 1)[0] + "…"
        return first + ("." if first and not first.endswith("…") else "")

    def excluded_reason(self, code):
        return self.data.get("excluded", {}).get(code)

    def industry_ids(self, code):
        return industries_of(code, self.industries)

    def salary(self, code):
        return salary_for(code, self.industry_ids(code), self.salaries)

    def get_matcher(self, timeout=60):
        """The "describe yourself" matcher (Sentence-BERT if installed, else TF-IDF)."""
        if self.matcher is None:
            self.matcher = SemanticMatcher(self.data)
        return self.matcher.get(timeout) if isinstance(self.matcher, LazyMatcher) else self.matcher

    def job_zone(self, code):
        jz = self.data.get("job_zone", {}).get(code) if "job_zone" in self.data else None
        return None if jz is None or (isinstance(jz, float) and math.isnan(jz)) else int(jz)


class _Holder:
    context = None


holder = _Holder()


def get_context() -> AppContext:
    """Dependency used by every endpoint. Tests replace it with app.dependency_overrides."""
    if holder.context is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "O*NET data is not loaded")
    return holder.context


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


def optional_student(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    """The student's id if a valid token was sent, else None (for pages that also work logged out)."""
    if creds is None:
        return None
    try:
        return read_token(creds.credentials)
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------- helpers
def career_brief(ctx, code, matched_title=None):
    """The short career summary used in lists (search, explore, matches for your words, assistant sources)."""
    return {"career_id": ctx.career_ids[code], "code": code, "title": ctx.official_title(code),
            "display_title": ctx.display_title(code), "field": field_of(code), "ranked": code in ctx.ranked,
            "matched_title": matched_title, "excluded_reason": ctx.excluded_reason(code),
            "job_zone": ctx.job_zone(code)}


def num(x, digits=3):
    """float for JSON; NaN -> None."""
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), digits)


def career_code(ctx, career_id, must_be_ranked=False):
    code = ctx.codes_by_id.get(career_id)
    if code is None or code not in ctx.data["occupations"].index:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Career {career_id} not found")
    if must_be_ranked and code not in ctx.ranked:
        reason = ctx.excluded_reason(code)
        raise HTTPException(422,
                            f"Not recommended in India: {reason}" if reason else
                            "O*NET has no interest/skill/knowledge data for this career, so it cannot be scored")
    return code


def own_assessment(ctx, assessment_id, student_id):
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
    student["preferred_location"] = a.get("preferred_location")
    student["about_me"] = a.get("about_me")
    student["profile"] = json.loads(a["profile_json"]) if a.get("profile_json") else {}
    return student
