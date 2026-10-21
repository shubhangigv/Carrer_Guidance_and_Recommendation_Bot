"""Pydantic models: the exact shape of every request and response.

FastAPI uses them to (1) reject bad input with a clear 422 error before our code runs,
(2) build the interactive documentation at /docs.
"""
from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ml.preferences import FURTHER_STUDY, MAX_AREAS, MAX_STRENGTHS, MAX_WEAKNESSES, WORK_SETTINGS
from ml.recommender_v2 import SKILL_MAP_V2, SUBJECT_MAP_V2

SkillRow = Literal[tuple(SKILL_MAP_V2)]          # only the 8 survey rows are accepted
SubjectRow = Literal[tuple(SUBJECT_MAP_V2)]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ---------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=8)
    education_level: Optional[str] = Field(default=None, max_length=50)
    degree: Optional[str] = Field(default=None, max_length=100)
    year_of_study: Optional[int] = Field(default=None, ge=1, le=10)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v):
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def bcrypt_limit(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes (bcrypt limit)")
        return v

    model_config = {"json_schema_extra": {"example": {
        "name": "Test Student", "email": "test@example.com", "password": "a-long-password",
        "education_level": "Undergraduate", "degree": "B.Sc", "year_of_study": 2}}}


class StudentOut(BaseModel):
    student_id: int
    name: str
    email: str


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def lower_email(cls, v):
        return v.strip().lower()

    model_config = {"json_schema_extra": {"example": {"email": "test@example.com", "password": "a-long-password"}}}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


# ---------------------------------------------------------------- assessment
class Rating(BaseModel):
    rating: int = Field(ge=1, le=5, description="1 = never done it / very weak, 3 = can do with help, "
                                                 "5 = can do it well on my own")


SkillAnswer = Union[Rating, Literal["no_experience", "cant_assess"]]
SubjectAnswer = Union[Rating, Literal["not_studied", "cant_assess"]]


class Interests(BaseModel):
    """How much the student enjoys each RIASEC activity type, 1-5 (always answered)."""
    Realistic: int = Field(ge=1, le=5)
    Investigative: int = Field(ge=1, le=5)
    Artistic: int = Field(ge=1, le=5)
    Social: int = Field(ge=1, le=5)
    Enterprising: int = Field(ge=1, le=5)
    Conventional: int = Field(ge=1, le=5)


class Profile(BaseModel):
    """The extra quiz answers (all optional). Area and course keys come from config/areas.csv and
    config/course_areas.csv (GET /quiz/options lists them); they are checked in ml/preferences.clean_profile."""
    areas: list[str] = Field(default_factory=list, max_length=MAX_AREAS, description="up to 3 area keys, e.g. tech")
    course: Optional[str] = Field(default=None, max_length=50, description="course key, e.g. btech_cse")
    strengths: list[SkillRow] = Field(default_factory=list, max_length=MAX_STRENGTHS)
    weaknesses: list[SkillRow] = Field(default_factory=list, max_length=MAX_WEAKNESSES)
    work_setting: Literal[tuple(WORK_SETTINGS)] = "any"
    further_study: Literal[tuple(FURTHER_STUDY)] = "any"


class AssessmentIn(BaseModel):
    interests: Interests
    skills: dict[SkillRow, SkillAnswer] = Field(default_factory=dict,
                                                 description="Missing rows count as cant_assess")
    subjects: dict[SubjectRow, SubjectAnswer] = Field(default_factory=dict,
                                                       description="Missing rows count as cant_assess")
    preferred_location: Optional[str] = Field(default=None, max_length=100,
                                              description="Where the student wants to work, e.g. Pune (job-search links)")
    about_me: Optional[str] = Field(default=None, max_length=1000,
                                    description="Optional free text: what the student enjoys (semantic matching)")
    profile: Optional[Profile] = Field(default=None, description="areas, course, strongest/weakest skills, lifestyle")

    model_config = {"json_schema_extra": {"example": {
        "interests": {"Realistic": 2, "Investigative": 5, "Artistic": 3, "Social": 3,
                      "Enterprising": 2, "Conventional": 3},
        "skills": {"Mathematics": {"rating": 3}, "Programming": {"rating": 3},
                   "Problem Solving": {"rating": 4}, "Research": "cant_assess",
                   "Communication": {"rating": 3}, "Writing": {"rating": 4},
                   "Leadership": "no_experience", "Technical/Practical Skills": {"rating": 3}},
        "subjects": {"Mathematics": {"rating": 3}, "Physics/Chemistry": {"rating": 4},
                     "Biology": {"rating": 5}, "Computer Science": {"rating": 4},
                     "Commerce/Economics": "not_studied", "Languages": {"rating": 3},
                     "Social Sciences": {"rating": 2}, "Arts/Design": {"rating": 3}}}}}


class AssessmentOut(BaseModel):
    assessment_id: int
    rated: int
    no_experience_or_not_studied: int
    cant_assess: int


# ---------------------------------------------------------------- recommendations
class FollowUp(BaseModel):
    category: Literal["skill", "subject"]
    item: str


class RecommendationOut(BaseModel):
    rank: int
    career_id: int
    code: str
    career: str = Field(description="official O*NET title")
    display_title: str = Field(description="short common title shown to students")
    summary: str = Field(default="", description="first sentence of the O*NET description (what the job involves)")
    field: str
    display: Literal["score", "range", "withheld"]
    interest_fit: float
    match_low: Optional[float] = Field(description="null when display is 'withheld'")
    match_high: Optional[float]
    skill_low: Optional[float]
    skill_high: Optional[float]
    subject_low: Optional[float]
    subject_high: Optional[float]
    coverage: float
    critical_unknowns: list[str]
    follow_ups: list[FollowUp]
    reasons: list[str]
    group: Literal["your_areas", "also_consider", "all"] = Field(
        description="your_areas = in the areas the student picked (or linked to their course); also_consider = elsewhere")
    areas: list[str] = Field(default_factory=list, description="labels of the student's areas this career is in")
    course_link: bool = False


class RecommendResponse(BaseModel):
    assessment_id: int
    model_version: str
    chosen_areas: list[str] = Field(default_factory=list)
    areas_from: Optional[Literal["picked", "course"]] = None
    notes: list[str] = Field(default_factory=list, description="filters used, hidden careers ...")
    recommendations: list[RecommendationOut]


class Option(BaseModel):
    key: str
    label: str
    example: str = ""


class QuizOptions(BaseModel):
    areas: list[Option]
    courses: list[Option]
    work_settings: list[Option]
    further_study: list[Option]
    max_areas: int
    max_strengths: int
    max_weaknesses: int


class HiddenOut(BaseModel):
    career_ids: list[int]


# ---------------------------------------------------------------- careers
class CareerBrief(BaseModel):
    career_id: int
    code: str
    title: str
    display_title: str
    excluded_reason: Optional[str] = Field(default=None, description="why it is not recommended in India")
    job_zone: Optional[int] = None
    field: str
    ranked: bool = Field(description="false if O*NET lacks the data to score this career")
    matched_title: Optional[str] = Field(default=None, description="the alternate job title that matched")


class Salary(BaseModel):
    min_lpa: float
    max_lpa: float
    source_name: str
    source_url: Optional[str]
    year: Optional[str]


class CareerDetail(BaseModel):
    career_id: int
    code: str
    title: str
    display_title: str
    excluded_reason: Optional[str] = None
    industries: list[str] = []
    salary: Optional[Salary] = Field(default=None, description="only from a cited source in config/salary_india.csv")
    description: Optional[str]
    field: str
    job_zone: Optional[int]
    ranked: bool


# ---------------------------------------------------------------- target career
class Question(BaseModel):
    category: Literal["skill", "subject"]
    item: str
    elements: list[str]
    max_importance: float


class QuestionsResponse(BaseModel):
    career_id: int
    career: str
    questions: list[Question]


class TargetIn(BaseModel):
    assessment_id: int


class Gap(BaseModel):
    area: str
    survey_row: str
    element: str
    importance: float
    required_level: float
    your_level: Optional[float]
    gap: Optional[float]
    priority: Optional[float]
    note: str


class Alternative(BaseModel):
    career_id: int
    code: str
    career: str
    display_title: str
    field: str
    display: str
    match_low: Optional[float]
    match_high: Optional[float]
    source: str


class InterestCheck(BaseModel):
    value: float
    label: Literal["strong", "moderate", "weak"]
    career_top_types: list[str]
    your_top_types: list[str]


class TargetOut(BaseModel):
    career_id: int
    code: str
    career: str
    display_title: str
    field: str
    job_zone: Optional[int]
    readiness: dict[str, Union[float, str, None]]
    interest_fit: InterestCheck
    reasons: list[str]
    gaps: list[Gap]
    questions_needed: list[Question]
    alternatives: list[Alternative]


class Health(BaseModel):
    status: str
    data_source: str
    storage: str
    careers_total: int
    careers_ranked: int
    checked_at: datetime


# ---------------------------------------------------------------- the logged-in student
class MeOut(BaseModel):
    student_id: int
    name: str
    email: str
    latest_assessment_id: Optional[int]
    preferred_location: Optional[str] = None


# ---------------------------------------------------------------- explore by industry
class Industry(BaseModel):
    id: str
    name: str
    description: str
    careers: int


class IndustryCareers(BaseModel):
    id: str
    name: str
    description: str
    careers: list[CareerBrief]


# ---------------------------------------------------------------- requirements and roadmap
class Requirement(BaseModel):
    element: str
    kind: Literal["skill", "knowledge"]
    importance: float
    required_level: Optional[float]
    your_level: Optional[float]
    gap: Optional[float]
    priority: Optional[float]
    status: Literal["have", "build", "not_assessed", "not_measured"]
    quiz_row: Optional[str]
    start_from_scratch: bool


class RequirementsOut(BaseModel):
    career_id: int
    display_title: str
    requirements: list[Requirement]


class RoadmapStep(BaseModel):
    key: str
    stage: str
    title: str
    detail: str
    items: list[Requirement]
    done: bool


class RoadmapOut(BaseModel):
    career_id: int
    code: str
    display_title: str
    career: str
    job_zone: Optional[int]
    preferred_location: Optional[str]
    steps: list[RoadmapStep]
    done: int
    total: int


class ProgressIn(BaseModel):
    step_key: str = Field(min_length=1, max_length=150)
    done: bool


class RoadmapSummary(BaseModel):
    career_id: int
    display_title: str
    done: int



# ---------------------------------------------------------------- matches for your own words + assistant
class TextMatchIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000,
                      description="What the student enjoys, in their own words")
    top_n: int = Field(default=10, ge=1, le=30)


class TextMatch(CareerBrief):
    similarity: float = Field(description="cosine similarity 0-1 between the text and the career description")


class TextMatchOut(BaseModel):
    method: str = Field(description='"sbert:<model>" (Sentence-BERT) or "tfidf" (word matching)')
    results: list[TextMatch]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    career_id: Optional[int] = Field(default=None, description="the career page the student is looking at")


class ChatOut(BaseModel):
    reply: str
    mode: Literal["gemini", "offline"]
    sources: list[CareerBrief]


class AssistantStatus(BaseModel):
    mode: Literal["gemini", "offline"]
    semantic_method: Optional[str]


# ---------------------------------------------------------------- how to get there (pathway)
class RouteStep(BaseModel):
    stage: str
    text: str
    link_name: Optional[str]
    link_url: Optional[str]


class Route(BaseModel):
    id: str
    name: str
    verified: bool = Field(description="false = drafted, not yet checked by the team on the official site")
    steps: list[RouteStep]


class Stream(BaseModel):
    stream: str
    because: list[str]


class EducationShare(BaseModel):
    level: int
    label: str
    percent: int


class LadderCareer(BaseModel):
    career_id: int
    display_title: str
    job_zone: int
    source: str


class Course(BaseModel):
    element: str
    title: str
    provider: Optional[str]
    url: str
    cost: Optional[str]
    language: Optional[str]
    verified_on: str


class PathwayOut(BaseModel):
    career_id: int
    display_title: str
    job_zone: Optional[int]
    stream: Optional[Stream]
    routes: list[Route]
    education_us: list[EducationShare] = Field(description="O*NET survey (US): share of workers by education level")
    ways_in: list[LadderCareer]
    grow_into: list[LadderCareer]
    courses: dict[str, list[Course]] = Field(description="checked courses per skill/knowledge (config/courses.csv)")
