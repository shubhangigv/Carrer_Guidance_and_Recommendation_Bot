"""Shared pieces used by every endpoint file (main.py and backend/routes/*.py).

AppContext   the O*NET data, the storage (MySQL or memory) and the India/industry settings,
             loaded once at startup (see main.build_context)
get_context  FastAPI dependency that hands the AppContext to an endpoint (tests override it)
current_student  the logged-in student's id from the "Authorization: Bearer <token>" header
"""
import math
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.security import read_token
from ml.localise import clean_title, industries_of, load_industries, load_salaries, salary_for
from ml.recommender_v2 import field_of
from ml.semantic import LazyMatcher, SemanticMatcher

MODEL_VERSION = "v2"
MIN_JOB_ZONE = 3


@dataclass
class AppContext:
    data: dict             # the O*NET tables (see ml/baseline_recommender.load_onet)
    repo: object           # SqlRepository or MemoryRepository
    career_ids: dict       # O*NET code -> career_id
    data_source: str       # "mysql" or "files"
    industries: list = field(default_factory=load_industries)     # config/industries.csv
    salaries: list = field(default_factory=load_salaries)         # config/salary_india.csv (cited rows only)
    matcher: object = None     # ml/semantic.py matcher (LazyMatcher at startup; built on first use otherwise)

    def __post_init__(self):
        self.codes_by_id = {cid: code for code, cid in self.career_ids.items()}
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
    return student
