"""Tests for the FastAPI backend (backend/main.py).

The O*NET data is the tiny fake folder and the database is replaced by MemoryRepository through
FastAPI's dependency override, so no MySQL is needed. The last test repeats the main flow with the
real SqlRepository and is skipped when MySQL is not running.
All students here are synthetic test accounts.

Run:  pytest -q tests/test_api.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import AppContext, app, get_context  # noqa: E402
from backend.repository import MemoryRepository, SqlRepository  # noqa: E402
from ml.recommender_v2 import load_onet_v2  # noqa: E402

LAB = "19-0001.00"
FULL_ANSWERS = {
    "interests": {"Realistic": 2, "Investigative": 5, "Artistic": 2, "Social": 2, "Enterprising": 2,
                  "Conventional": 2},
    "skills": {"Mathematics": {"rating": 3}, "Programming": {"rating": 2}, "Problem Solving": {"rating": 5},
               "Research": {"rating": 5}, "Communication": {"rating": 3}, "Writing": {"rating": 5},
               "Leadership": "no_experience", "Technical/Practical Skills": {"rating": 2}},
    "subjects": {"Mathematics": {"rating": 3}, "Physics/Chemistry": {"rating": 5}, "Biology": {"rating": 5},
                 "Computer Science": {"rating": 3}, "Commerce/Economics": "not_studied",
                 "Languages": {"rating": 3}, "Social Sciences": {"rating": 2}, "Arts/Design": {"rating": 2}},
}


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-only-for-pytest-0123456789abcdef")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "5")


def make_client(ctx):
    app.dependency_overrides[get_context] = lambda: ctx
    return TestClient(app)          # not used as "with": the startup loader does not run


@pytest.fixture
def onet(onet_dir):
    pd.DataFrame({"O*NET-SOC Code": [LAB], "Title": ["Lab Scientist"], "Alternate Title": ["Research Chemist"]}) \
        .to_csv(onet_dir / "Alternate Titles.txt", sep="\t", index=False)
    return load_onet_v2(onet_dir)


@pytest.fixture
def ctx(onet):
    repo = MemoryRepository()
    return AppContext(onet, repo, repo.career_ids(onet), "files")


@pytest.fixture
def client(ctx):
    yield make_client(ctx)
    app.dependency_overrides.clear()


def login(client, email="student@example.com", password="correct-horse-1"):
    client.post("/auth/register", json={"name": "Test", "email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def career_id(client, ctx, code=LAB):
    return ctx.career_ids[code]


# ---------------------------------------------------------------- auth
def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["storage"] == "memory" and body["careers_ranked"] == 3


def test_register_and_login(client, ctx):
    r = client.post("/auth/register", json={"name": "A", "email": "A@Example.com", "password": "long-enough"})
    assert r.status_code == 201 and r.json()["email"] == "a@example.com"
    stored = ctx.repo.get_student_by_email("a@example.com")
    assert stored["password_hash"] != "long-enough" and stored["password_hash"].startswith("$2")   # bcrypt hash
    assert client.post("/auth/register", json={"name": "B", "email": "a@example.com",
                                               "password": "long-enough"}).status_code == 409
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-one"}).status_code == 401
    ok = client.post("/auth/login", json={"email": "a@example.com", "password": "long-enough"})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"


def test_register_validation(client):
    assert client.post("/auth/register", json={"name": "A", "email": "not-an-email",
                                               "password": "long-enough"}).status_code == 422
    assert client.post("/auth/register", json={"name": "A", "email": "a@b.co", "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={"name": "A", "email": "a@b.co", "password": "x" * 73}).status_code == 422


def test_protected_routes_need_a_valid_token(client):
    assert client.post("/assessment", json=FULL_ANSWERS).status_code == 401
    assert client.get("/recommend", params={"assessment_id": 1}).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.post("/assessment", json=FULL_ANSWERS, headers=bad).status_code == 401


# ---------------------------------------------------------------- assessment validation
@pytest.mark.parametrize("change", [
    {"skills": {"Research": {"rating": 6}}},              # rating out of range
    {"skills": {"Cooking": {"rating": 3}}},               # not a survey row
    {"skills": {"Research": "not_studied"}},              # that answer is for subjects
    {"subjects": {"Biology": "no_experience"}},           # that answer is for skills
    {"interests": {"Realistic": 3}},                      # interests must have all 6 types
])
def test_assessment_validation(client, change):
    body = {**FULL_ANSWERS, **change}
    assert client.post("/assessment", json=body, headers=login(client)).status_code == 422


# ---------------------------------------------------------------- full flow
def test_assessment_then_recommend(client, ctx):
    headers = login(client)
    r = client.post("/assessment", json=FULL_ANSWERS, headers=headers)
    assert r.status_code == 201
    assert r.json() == {"assessment_id": 1, "rated": 14, "no_experience_or_not_studied": 2, "cant_assess": 0}

    rec = client.get("/recommend", params={"assessment_id": 1, "top_n": 5}, headers=headers)
    assert rec.status_code == 200
    recs = rec.json()["recommendations"]
    assert recs[0]["code"] == LAB and recs[0]["display"] == "score"
    assert recs[0]["match_low"] == recs[0]["match_high"]
    assert any("Investigative" in reason for reason in recs[0]["reasons"])
    assert "Helper" not in [x["career"] for x in recs]            # Job Zone 1 is filtered out
    saved = ctx.repo.recommendations
    assert len(saved) == len(recs) and all(s["model_version"] == "v2" for s in saved)


def test_cant_assess_gives_a_range_and_follow_ups(client):
    headers = login(client)
    body = {**FULL_ANSWERS, "skills": {**FULL_ANSWERS["skills"], "Research": "cant_assess"}}
    aid = client.post("/assessment", json=body, headers=headers).json()["assessment_id"]
    lab = next(x for x in client.get("/recommend", params={"assessment_id": aid}, headers=headers).json()
               ["recommendations"] if x["code"] == LAB)
    assert lab["display"] == "range"
    assert lab["match_low"] < lab["match_high"]
    assert {"category": "skill", "item": "Research"} in lab["follow_ups"]
    assert "Science" in lab["critical_unknowns"]


def test_withheld_hides_the_score(client):
    headers = login(client)
    body = {"interests": FULL_ANSWERS["interests"]}               # no skills or subjects at all
    aid = client.post("/assessment", json=body, headers=headers).json()["assessment_id"]
    recs = client.get("/recommend", params={"assessment_id": aid}, headers=headers).json()["recommendations"]
    assert all(x["display"] == "withheld" and x["match_low"] is None for x in recs)
    assert all(x["interest_fit"] is not None for x in recs)


def test_cannot_read_another_students_assessment(client):
    aid = client.post("/assessment", json=FULL_ANSWERS, headers=login(client)).json()["assessment_id"]
    other = login(client, email="other@example.com")
    assert client.get("/recommend", params={"assessment_id": aid}, headers=other).status_code == 404


# ---------------------------------------------------------------- careers and target
def test_search_by_title_and_alternate_title(client):
    hits = client.get("/careers/search", params={"q": "lab"}).json()
    assert [h["code"] for h in hits] == [LAB]
    alt = client.get("/careers/search", params={"q": "chemist"}).json()
    assert alt[0]["code"] == LAB and alt[0]["matched_title"] == "Research Chemist"
    assert client.get("/careers/search", params={"q": "zzz-nothing"}).json() == []
    assert client.get("/careers/search", params={"q": "a"}).status_code == 422   # too short


def test_career_detail(client, ctx):
    r = client.get(f"/careers/{career_id(client, ctx)}").json()
    assert r["title"] == "Lab Scientist" and r["job_zone"] == 4 and r["ranked"] is True
    assert client.get("/careers/9999").status_code == 404


def test_target_questions_and_target(client, ctx):
    headers = login(client)
    body = {**FULL_ANSWERS, "skills": {k: v for k, v in FULL_ANSWERS["skills"].items() if k != "Writing"}}
    aid = client.post("/assessment", json=body, headers=headers).json()["assessment_id"]
    cid = career_id(client, ctx)
    q = client.get(f"/target/{cid}/questions", params={"assessment_id": aid}, headers=headers).json()
    assert [x["item"] for x in q["questions"]] == ["Writing"]
    t = client.post(f"/target/{cid}", json={"assessment_id": aid}, headers=headers)
    assert t.status_code == 200
    t = t.json()
    assert t["readiness"]["match_low"] < t["readiness"]["match_high"]
    assert t["interest_fit"]["label"] == "strong"
    assert any(g["note"] == "not assessed - answer to check" for g in t["gaps"])
    assert all(a["code"] != LAB for a in t["alternatives"])


# assessment_rating as Phase 1 created it (before migration 002 added answer_status)
PHASE1_ASSESSMENT_RATING = """
    CREATE TABLE assessment_rating (
        assessment_id INT UNSIGNED NOT NULL, category VARCHAR(20) NOT NULL, item VARCHAR(100) NOT NULL,
        rating TINYINT UNSIGNED NOT NULL,
        PRIMARY KEY (assessment_id, category, item),
        CONSTRAINT ck_assessment_rating_range CHECK (rating BETWEEN 1 AND 5),
        CONSTRAINT fk_assessment_rating_assessment FOREIGN KEY (assessment_id)
            REFERENCES assessment (assessment_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""


# ---------------------------------------------------------------- the same flow on real MySQL
@pytest.mark.parametrize("old_database", [False, True], ids=["new-database", "phase1-database"])
def test_flow_with_mysql_repository(onet_dir, onet, old_database):
    """old_database: the tables were made by the Phase 1 schema, then the loader is re-run.
    The loader must apply the migrations, otherwise saving a "cant_assess" answer fails (HTTP 500)."""
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from backend.db import get_engine, run_sql_file
    from load_onet_to_mysql import load
    db = os.getenv("MYSQL_TEST_DATABASE", "career_guidance_test")
    try:
        server = get_engine("")
        with server.begin() as conn:
            conn.execute(sqlalchemy.text(f"DROP DATABASE IF EXISTS `{db}`"))
            conn.execute(sqlalchemy.text(f"CREATE DATABASE `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    except Exception as err:
        pytest.skip(f"MySQL not reachable ({type(err).__name__})")
    engine = get_engine(db)
    try:
        if old_database:
            run_sql_file(engine)
            with engine.begin() as conn:
                conn.execute(sqlalchemy.text("DROP TABLE assessment_rating"))
                conn.execute(sqlalchemy.text(PHASE1_ASSESSMENT_RATING))
        load(engine, onet_dir)
        repo = SqlRepository(engine)
        ctx = AppContext(onet, repo, repo.career_ids(onet), "mysql")
        client = make_client(ctx)
        headers = login(client)
        body = {**FULL_ANSWERS, "skills": {**FULL_ANSWERS["skills"], "Research": "cant_assess"}}
        aid = client.post("/assessment", json=body, headers=headers).json()["assessment_id"]
        recs = client.get("/recommend", params={"assessment_id": aid}, headers=headers).json()["recommendations"]
        assert recs[0]["code"] == LAB
        with engine.connect() as conn:
            stored = conn.execute(sqlalchemy.text(
                "SELECT rating, answer_status FROM assessment_rating WHERE item = 'Research'")).one()
            versions = conn.execute(sqlalchemy.text("SELECT DISTINCT model_version FROM recommendation")).scalars().all()
        assert tuple(stored) == (None, "cant_assess") and versions == ["v2"]
        # roadmap progress and the "me" endpoint are stored in MySQL too
        cid = recs[0]["career_id"]
        r = client.put(f"/roadmap/{cid}/progress", json={"step_key": "education", "done": True}, headers=headers)
        assert r.status_code == 200 and r.json()["done"] == 1
        assert client.get("/roadmaps", headers=headers).json()[0]["career_id"] == cid
        assert client.get("/me", headers=headers).json()["latest_assessment_id"] == aid
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with server.begin() as conn:
            conn.execute(sqlalchemy.text(f"DROP DATABASE IF EXISTS `{db}`"))


# ---------------------------------------------------------------- student web app (frontend/app)
def test_web_app_is_served(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
    page = client.get("/app/")
    assert page.status_code == 200 and "Pathfinder" in page.text
    for name in ("api.js", "core.js", "account.js", "quiz.js", "matches.js", "career.js", "roadmap.js",
                 "explore.js", "assistant.js", "styles.css"):
        assert client.get(f"/app/{name}").status_code == 200, name
        assert f'src="{name}"' in page.text or name == "styles.css", f"{name} is not loaded by index.html"


def test_web_app_questions_match_the_engine():
    """The quiz rows in frontend/app/quiz.js must be exactly the survey rows the API accepts."""
    import re
    from ml.recommender_v2 import SKILL_MAP_V2, SUBJECT_MAP_V2
    js = (ROOT / "frontend" / "app" / "quiz.js").read_text(encoding="utf-8")

    def first_values(const):
        block = re.search(rf"const {const} = \[(.*?)\n\];", js, re.S).group(1)
        return re.findall(r'^\s*\["([^"]+)",', block, re.M)
    assert first_values("SKILL_ROWS") == list(SKILL_MAP_V2)
    assert first_values("SUBJECT_ROWS") == list(SUBJECT_MAP_V2)
    assert first_values("INTEREST_ROWS") == ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]
