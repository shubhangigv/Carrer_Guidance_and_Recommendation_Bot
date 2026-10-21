"""Tests for short titles, the India filter, explore by industry, skills to build and the roadmap.

Fake O*NET folder (tests/fake_onet.py) with two changes made here:
  * the "Designer" career is renamed "Gambling Designers" -> must be excluded for India
  * a Sample of Reported Titles.txt gives Lab Scientist the My Next Move title "Research Scientist"
All students are synthetic test accounts.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import AppContext, app, get_context  # noqa: E402
from backend.repository import MemoryRepository  # noqa: E402
from ml.career_needs import requirements, roadmap  # noqa: E402
from ml.localise import apply_local_rules, clean_title, excluded_careers, pick_short_title  # noqa: E402
from ml.recommender_v2 import load_onet_v2  # noqa: E402

LAB, DESIGN, HELPER = "19-0001.00", "27-0001.00", "47-0001.00"
ANSWERS = {
    "interests": {"Realistic": 2, "Investigative": 5, "Artistic": 2, "Social": 2, "Enterprising": 2, "Conventional": 2},
    "skills": {"Mathematics": {"rating": 3}, "Programming": {"rating": 1}, "Problem Solving": {"rating": 2},
               "Research": {"rating": 2}, "Communication": {"rating": 3}, "Writing": "cant_assess",
               "Leadership": "no_experience", "Technical/Practical Skills": {"rating": 2}},
    "subjects": {"Mathematics": {"rating": 3}, "Physics/Chemistry": {"rating": 5}, "Biology": {"rating": 5},
                 "Computer Science": {"rating": 3}, "Commerce/Economics": "not_studied",
                 "Languages": {"rating": 3}, "Social Sciences": {"rating": 2}, "Arts/Design": {"rating": 2}},
    "preferred_location": "Pune",
}


@pytest.fixture(autouse=True)
def jwt_settings(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-only-for-pytest-0123456789abcdef")


@pytest.fixture
def data(onet_dir):
    occ = pd.read_csv(onet_dir / "Occupation Data.txt", sep="\t", dtype=str)
    occ.loc[occ["O*NET-SOC Code"] == DESIGN, "Title"] = "Gambling Designers"
    occ.to_csv(onet_dir / "Occupation Data.txt", sep="\t", index=False)
    pd.DataFrame({"O*NET-SOC Code": [LAB, LAB], "Title": ["Lab Scientist"] * 2,
                  "Reported Job Title": ["Laboratory Research Technician Lead", "Research Scientist"],
                  "Shown in My Next Move": ["N", "Y"]}) \
        .to_csv(onet_dir / "Sample of Reported Titles.txt", sep="\t", index=False)
    return apply_local_rules(load_onet_v2(onet_dir), onet_dir)


@pytest.fixture
def client(data):
    repo = MemoryRepository()
    ctx = AppContext(data, repo, repo.career_ids(data), "files")
    app.dependency_overrides[get_context] = lambda: ctx
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client):
    client.post("/auth/register", json={"name": "T", "email": "t@example.com", "password": "long-password"})
    token = client.post("/auth/login", json={"email": "t@example.com", "password": "long-password"}).json()
    return {"Authorization": "Bearer " + token["access_token"]}


def career_id(client, code):
    return app.dependency_overrides[get_context]().career_ids[code]


# ---------------------------------------------------------------- short titles and India filter
def test_clean_title_removes_us_category_wording():
    assert clean_title("Entertainment and Recreation Managers, Except Gambling") == "Entertainment and Recreation Managers"
    assert clean_title("Engineers, All Other") == "Engineers"
    assert clean_title("Nurse Anesthetists") == "Nurse Anesthetists"


def test_pick_short_title_prefers_shared_words_then_shortest():
    official = "Entertainment and Recreation Managers, Except Gambling"
    assert pick_short_title(official, ["Club Manager", "Recreation Manager", "Director"]) == "Recreation Manager"
    assert pick_short_title(official, []) == "Entertainment and Recreation Managers"


def test_except_gambling_is_not_excluded(data):
    rules = [{"rule": "title_contains", "value": "gambling", "reason": "r"}]
    fake = {"occupations": pd.DataFrame({"Title": ["Entertainment and Recreation Managers, Except Gambling",
                                                   "Gambling Managers"]}, index=["11-9072.00", "11-9071.00"])}
    assert excluded_careers(fake, rules) == {"11-9071.00": "r"}


def test_short_title_from_my_next_move_and_exclusion(data):
    assert data["short_title"][LAB] == "Research Scientist"          # the "Y" title, not the "N" one
    assert DESIGN in data["excluded"] and DESIGN not in data["codes"]


def test_api_never_recommends_excluded_and_explains_why(client):
    headers = login(client)
    aid = client.post("/assessment", json=ANSWERS, headers=headers).json()["assessment_id"]
    recs = client.get("/recommend", params={"assessment_id": aid}, headers=headers).json()["recommendations"]
    assert DESIGN not in [r["code"] for r in recs]
    lab = next(r for r in recs if r["code"] == LAB)
    assert lab["display_title"] == "Research Scientist" and lab["career"] == "Lab Scientist"
    hit = client.get("/careers/search", params={"q": "gambl"}).json()[0]
    assert hit["code"] == DESIGN and "gambling" in hit["excluded_reason"].lower()
    r = client.post(f"/target/{hit['career_id']}", json={"assessment_id": aid}, headers=headers)
    assert r.status_code == 422 and "India" in r.json()["detail"]


def test_search_finds_short_title(client):
    assert client.get("/careers/search", params={"q": "research sci"}).json()[0]["code"] == LAB


# ---------------------------------------------------------------- explore by industry
def test_industries(client):
    industries = {i["id"]: i for i in client.get("/industries").json()}
    assert industries["science"]["careers"] == 1                      # 19-0001.00
    assert industries["art-design"]["careers"] == 0                   # 27-0001.00 is excluded
    body = client.get("/industries/science").json()
    assert [c["code"] for c in body["careers"]] == [LAB]
    assert client.get("/industries/nope").status_code == 404


# ---------------------------------------------------------------- skills to build and roadmap
def test_requirements_cover_all_important_elements(data):
    student = {k: v for k, v in ANSWERS.items() if k != "preferred_location"}
    rows = requirements(student, data, LAB)
    im = data["skill_importance"].loc[LAB]
    assert {r["element"] for r in rows if r["kind"] == "skill"} == set(im[im >= 3].index)
    by = {r["element"]: r for r in rows}
    assert by["Science"]["status"] == "build"                          # Research rated 2, needed high
    assert by["Writing"]["status"] == "not_assessed"                   # Writing = cant_assess
    assert all(r["importance"] >= 3 for r in rows)
    assert [r["importance"] for r in rows] == sorted((r["importance"] for r in rows), reverse=True)


def test_roadmap_orders_skills_by_priority(data):
    student = {k: v for k, v in ANSWERS.items() if k != "preferred_location"}
    plan = roadmap(student, data, LAB, job_zone=4)
    keys = [s["key"] for s in plan["steps"]]
    assert keys[:2] == ["stream", "education"] and "bachelor" in plan["steps"][1]["detail"]
    assert "Biology" in plan["steps"][0]["detail"] or "Chemistry" in plan["steps"][0]["detail"]
    build = [s["items"][0]["priority"] for s in plan["steps"] if s["key"].startswith("build:")]
    assert build and build == sorted(build, reverse=True)
    assert [s["key"] for s in plan["steps"]][-2:] == ["experience", "apply"]


def test_roadmap_api_progress(client):
    headers = login(client)
    client.post("/assessment", json=ANSWERS, headers=headers)
    cid = career_id(client, LAB)
    plan = client.get(f"/roadmap/{cid}", headers=headers).json()
    assert plan["done"] == 0 and plan["preferred_location"] == "Pune"
    step = next(s["key"] for s in plan["steps"] if s["key"].startswith("build:"))
    after = client.put(f"/roadmap/{cid}/progress", json={"step_key": step, "done": True}, headers=headers).json()
    assert after["done"] == 1 and next(s for s in after["steps"] if s["key"] == step)["done"]
    assert client.get("/roadmaps", headers=headers).json() == [{"career_id": cid, "display_title": "Research Scientist", "done": 1}]
    undo = client.put(f"/roadmap/{cid}/progress", json={"step_key": step, "done": False}, headers=headers).json()
    assert undo["done"] == 0
    bad = client.put(f"/roadmap/{cid}/progress", json={"step_key": "made-up", "done": True}, headers=headers)
    assert bad.status_code == 422
    assert client.get(f"/roadmap/{cid}").status_code == 401


def test_requirements_logged_out_and_in(client):
    cid = career_id(client, LAB)
    out = client.get(f"/careers/{cid}/requirements").json()["requirements"]
    assert out and all(r["your_level"] is None for r in out)
    headers = login(client)
    client.post("/assessment", json=ANSWERS, headers=headers)
    mine = client.get(f"/careers/{cid}/requirements", headers=headers).json()["requirements"]
    assert any(r["status"] == "build" for r in mine)


def test_me_returns_latest_assessment(client):
    headers = login(client)
    assert client.get("/me", headers=headers).json()["latest_assessment_id"] is None
    aid = client.post("/assessment", json=ANSWERS, headers=headers).json()["assessment_id"]
    me = client.get("/me", headers=headers).json()
    assert me["latest_assessment_id"] == aid and me["preferred_location"] == "Pune" and me["name"] == "T"


def test_career_detail_has_industries_and_no_invented_salary(client):
    cid = career_id(client, LAB)
    d = client.get(f"/careers/{cid}").json()
    assert d["display_title"] == "Research Scientist" and "science" in d["industries"]
    assert d["salary"] is None                     # config/salary_india.csv has no cited rows


# ---------------------------------------------------------------- how to get there (pathway)
from ml.pathways import career_ladder, courses_for, load_courses, load_education, load_routes, routes_for, suggested_stream  # noqa: E402


def test_routes_file_is_well_formed():
    routes = load_routes(include_unverified=True)
    assert len(routes) >= 20
    for r in routes:
        assert r["name"] and r["prefixes"] and r["steps"]
        for st in r["steps"]:
            assert st["stage"] and st["text"]
            assert st["link_url"] is None or st["link_url"].startswith("https://")
    assert [r["id"] for r in routes_for("29-1215.00", routes)] == ["doctor"]
    assert [r["id"] for r in routes_for("17-2051.00", routes)] == ["engineer"]
    assert routes_for("99-9999.00", routes) == []


def test_route_is_verified_only_if_every_step_is(tmp_path, monkeypatch):
    f = tmp_path / "paths.csv"
    f.write_text("route_id,route_name,applies_to,verified,stage,text,link_name,link_url\n"
                 "a,Route A,29,yes,Step 1,Do this,,\na,Route A,29,no,Step 2,Then this,,\n"
                 "b,Route B,17,yes,Step 1,Do that,,\n", encoding="utf-8")
    routes = {r["id"]: r for r in load_routes(f, include_unverified=True)}
    assert routes["a"]["verified"] is False and routes["b"]["verified"] is True
    assert [r["id"] for r in load_routes(f, include_unverified=False)] == ["b"]
    monkeypatch.setenv("SHOW_UNVERIFIED_ROUTES", "no")              # the .env switch for the demo
    assert [r["id"] for r in load_routes(f)] == ["b"]
    monkeypatch.setenv("SHOW_UNVERIFIED_ROUTES", "yes")
    assert len(load_routes(f)) == 2


def test_suggested_stream_for_lab_scientist(data):
    s = suggested_stream(data, LAB)                    # strong Biology + Chemistry knowledge
    assert s["stream"].startswith("Science") and set(s["because"]) & {"Biology", "Chemistry"}


def test_courses_need_a_verified_date(tmp_path):
    f = tmp_path / "courses.csv"
    f.write_text("element,title,provider,url,cost,language,verified_on\n"
                 "Programming,Intro to Python,Uni,https://example.org/py,free,English,2026-10-20\n"
                 "Programming,Unchecked course,X,https://example.org/x,paid,English,\n", encoding="utf-8")
    courses = load_courses(f)
    assert [c["title"] for c in courses] == ["Intro to Python"]
    assert courses_for(["programming", "Biology"], courses) == {"programming": courses}


def test_education_levels_from_onet_file(onet_dir):
    import pandas as pd
    pd.DataFrame({"O*NET-SOC Code": [LAB] * 3, "Element ID": "2.D.1", "Element Name": "Required Level of Education",
                  "Scale ID": "RL", "Category": ["6", "8", "11"], "Data Value": ["20.5", "50.2", "29.3"],
                  "Recommend Suppress": "N"}).to_csv(onet_dir / "Education, Training, and Experience.txt", sep="\t", index=False)
    edu, info = load_education(onet_dir)
    assert "RL" in info
    data = {"education": edu}
    from ml.pathways import education_for
    assert [e["label"] for e in education_for(data, LAB)] == ["Master's degree", "Doctoral degree", "Bachelor's degree"]
    assert load_education(onet_dir.parent / "nowhere")[0] is None


def test_career_ladder_by_job_zone():
    import pandas as pd
    occ = pd.DataFrame({"Title": ["Nurse", "Nursing Assistant", "Nurse Practitioner", "Other"]},
                       index=["29-1141.00", "29-1149.00", "29-1171.00", "47-0001.00"])
    data = {"occupations": occ, "job_zone": pd.Series({"29-1141.00": 3, "29-1149.00": 2, "29-1171.00": 5, "47-0001.00": 1}),
            "related": pd.DataFrame({"code": ["29-1141.00"], "related_code": ["29-1171.00"], "order": [1]})}
    ladder = career_ladder(data, "29-1141.00")
    assert [r["code"] for r in ladder["ways_in"]] == ["29-1149.00"]
    assert ladder["grow_into"][0] == {"code": "29-1171.00", "job_zone": 5, "source": "O*NET related occupation"}


def test_pathway_endpoint(client):
    cid = career_id(client, LAB)
    p = client.get(f"/careers/{cid}/pathway").json()
    assert p["display_title"] == "Research Scientist" and p["stream"]["stream"].startswith("Science")
    assert p["routes"] == [] and p["courses"] == {}          # no route covers 19-0001 in the fake data


def test_shared_short_titles_are_made_specific():
    import pandas as pd
    from ml.localise import disambiguate
    short = pd.Series({"a": "Professor", "b": "Professor", "c": "Engineer", "d": "Engineer", "e": "Nurse"})
    official = pd.Series({"a": "Engineering Teachers, Postsecondary", "b": "Nursing Instructors and Teachers, Postsecondary",
                          "c": "Ship Engineers", "d": "Automotive Engineers", "e": "Registered Nurses"})
    out = disambiguate(short, official)
    assert out["a"] == "Professor (Engineering)" and out["b"] == "Professor (Nursing Instructors and)" or out["b"].startswith("Professor (")
    assert out["c"] == "Ship Engineers" and out["d"] == "Automotive Engineers"
    assert out["e"] == "Nurse"                                   # a unique short title is kept
    assert not out.duplicated().any()
