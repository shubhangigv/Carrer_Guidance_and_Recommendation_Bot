"""Proof that MySQL gives exactly the same recommendations as the O*NET files.

These tests need a running MySQL server and the settings in .env.
They are skipped (not failed) when MySQL is not reachable.

  * test_loader_*       use a throw-away database (MYSQL_TEST_DATABASE, default
                        career_guidance_test) filled with fake O*NET data, then delete it.
  * test_real_onet_*    compare the real O*NET files in data/raw/onet/ with your real
                        database. Run scripts/load_onet_to_mysql.py first.

Run:  pytest -q tests/test_mysql_matches_files.py -rs     (-rs prints why a test was skipped)
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("pymysql")
from sqlalchemy import text  # noqa: E402

from backend.db import get_engine  # noqa: E402
from fake_onet import SCIENCE_STUDENT, write_fake_onet  # noqa: E402
from load_onet_to_mysql import load  # noqa: E402
from ml.baseline_recommender import (RIASEC, SKILL_MAP, SUBJECT_MAP, explain,  # noqa: E402
                                     load_from_mysql, load_onet, recommend)

TEST_DB = os.getenv("MYSQL_TEST_DATABASE", "career_guidance_test")
REAL_ONET_DIR = ROOT / "data" / "raw" / "onet"

# The two hand-made profiles from notebooks/02_baseline_demo.ipynb
STUDENT_A = {
    "interests": {"Realistic": 2.8, "Investigative": 4.6, "Artistic": 3.4,
                  "Social": 3.2, "Enterprising": 2.1, "Conventional": 3.0},
    "skills": {"Mathematics": 3, "Programming": 3, "Problem Solving": 4, "Logical Reasoning": 4,
               "Critical Thinking": 4, "Research": 5, "Communication": 3, "Writing": 4,
               "Public Speaking": 2, "Leadership": 2, "Teamwork": 3, "Time Management": 3,
               "Project Management": 2, "Financial/Business Skills": 1, "Teaching": 3,
               "Technical/Practical Skills": 3},
    "subjects": {"Mathematics": 3, "Physics": 3, "Chemistry": 4, "Biology": 5,
                 "Computer Science": 4, "Economics": 2, "Commerce/Accounting": 1,
                 "Languages": 3, "Social Sciences": 2, "Arts/Design": 3},
}
STUDENT_B = {
    "interests": {"Realistic": 1.8, "Investigative": 2.5, "Artistic": 4.4,
                  "Social": 3.9, "Enterprising": 4.2, "Conventional": 2.6},
    "skills": {"Mathematics": 2, "Programming": 1, "Problem Solving": 3, "Logical Reasoning": 3,
               "Critical Thinking": 3, "Research": 3, "Communication": 5, "Writing": 4,
               "Public Speaking": 4, "Leadership": 4, "Teamwork": 4, "Time Management": 3,
               "Project Management": 3, "Financial/Business Skills": 3, "Teaching": 3,
               "Technical/Practical Skills": 1},
    "subjects": {"Mathematics": 2, "Physics": 1, "Chemistry": 1, "Biology": 2,
                 "Computer Science": 2, "Economics": 3, "Commerce/Accounting": 3,
                 "Languages": 5, "Social Sciences": 4, "Arts/Design": 5},
}
STUDENTS = [STUDENT_A, STUDENT_B, SCIENCE_STUDENT]


def _connect(database):
    """Return an engine, or skip the test if MySQL is not reachable."""
    try:
        engine = get_engine(database)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as err:   # no server, wrong password, unknown database ...
        pytest.skip(f"MySQL not reachable ({type(err).__name__}): {err}")


def _assert_same(student, files, mysql, top_n=10, min_job_zone=None):
    """Same top-N table and the same reasons and skill gaps for every career in it."""
    a = recommend(student, files, top_n=top_n, min_job_zone=min_job_zone)
    b = recommend(student, mysql, top_n=top_n, min_job_zone=min_job_zone)
    pd.testing.assert_frame_equal(a, b)
    for code in a["code"]:
        reasons_a, gaps_a = explain(student, files, code)
        reasons_b, gaps_b = explain(student, mysql, code)
        assert reasons_a == reasons_b
        pd.testing.assert_frame_equal(gaps_a, gaps_b)


# ---------------------------------------------------------------- fake data, throw-away database
@pytest.fixture
def messy_onet_dir(tmp_path):
    """The fake O*NET folder plus 40 random careers with 2-decimal values and a few
    missing ratings, so ties, gaps and missing values are all exercised."""
    folder = write_fake_onet(tmp_path)
    rng = np.random.default_rng(7)
    skills = sorted({e for v in SKILL_MAP.values() for e in v})
    knowledge = sorted({e for v in SUBJECT_MAP.values() for e in v})

    def add(filename, rows):
        old = pd.read_csv(folder / filename, sep="\t", dtype=str)
        pd.concat([old, pd.DataFrame(rows).astype(str)]).to_csv(folder / filename, sep="\t", index=False)

    occ, interests, skill_rows, know_rows, zones = [], [], [], [], []
    for i in range(40):
        code = f"{rng.choice(['11', '15', '19', '27', '29', '47'])}-9{i:03d}.00"
        occ.append({"O*NET-SOC Code": code, "Title": f"Random Career {i}", "Description": "Random test career."})
        zones.append({"O*NET-SOC Code": code, "Job Zone": int(rng.integers(1, 6)), "Date": "08/2026", "Domain Source": "Test"})
        for e in RIASEC:
            interests.append({"O*NET-SOC Code": code, "Element ID": "x", "Element Name": e, "Scale ID": "OI",
                              "Data Value": f"{rng.uniform(1, 7):.2f}", "Date": "08/2026", "Domain Source": "Test"})
        if i % 10 == 9:
            continue                                   # no skills/knowledge -> not ranked
        for rows, elements in ((skill_rows, skills), (know_rows, knowledge)):
            for e in elements:
                if rng.random() < 0.05:
                    continue                           # a missing rating
                for scale, (lo, hi) in {"IM": (1, 5), "LV": (0, 7)}.items():
                    rows.append({"O*NET-SOC Code": code, "Element ID": "x", "Element Name": e, "Scale ID": scale,
                                 "Data Value": f"{rng.uniform(lo, hi):.2f}", "N": "", "Standard Error": "",
                                 "Lower CI Bound": "", "Upper CI Bound": "", "Recommend Suppress": "N",
                                 "Not Relevant": "", "Date": "08/2026", "Domain Source": "Test"})
    add("Occupation Data.txt", occ)
    add("Career Interest Types.txt", interests)
    add("Transferable Skills.txt", skill_rows)
    add("Knowledge.txt", know_rows)
    add("Job Zones.txt", zones)
    return folder


@pytest.fixture
def test_engine():
    server = _connect("")
    with server.begin() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{TEST_DB}`"))
        conn.execute(text(f"CREATE DATABASE `{TEST_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    engine = get_engine(TEST_DB)
    yield engine
    engine.dispose()
    with server.begin() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{TEST_DB}`"))


def _counts(engine):
    tables = ["career", "skill", "interest", "knowledge", "career_skill", "career_interest", "career_knowledge"]
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in tables}


def test_loader_creates_all_13_tables(test_engine, onet_dir):
    load(test_engine, onet_dir)
    with test_engine.connect() as conn:
        tables = set(conn.execute(text("SHOW TABLES")).scalars())
    assert tables == {"student", "assessment", "assessment_rating", "recommendation", "career", "skill",
                      "career_skill", "interest", "career_interest", "knowledge", "career_knowledge",
                      "course", "job"}


def test_loader_can_run_twice_without_duplicates(test_engine, messy_onet_dir):
    load(test_engine, messy_onet_dir)
    first = _counts(test_engine)
    load(test_engine, messy_onet_dir)
    assert _counts(test_engine) == first
    assert first["career"] == 43 and first["interest"] == 6


def test_loader_mysql_gives_same_results_as_files(test_engine, messy_onet_dir):
    load(test_engine, messy_onet_dir)
    files, mysql = load_onet(messy_onet_dir), load_from_mysql(test_engine)
    assert list(files["codes"]) == list(mysql["codes"])
    for student in STUDENTS:
        _assert_same(student, files, mysql)
        _assert_same(student, files, mysql, min_job_zone=3)


# ---------------------------------------------------------------- real O*NET, real database
def test_real_onet_mysql_gives_same_top5_as_files():
    if not (REAL_ONET_DIR / "Occupation Data.txt").exists() and next(REAL_ONET_DIR.rglob("Occupation Data.txt"), None) is None:
        pytest.skip("Real O*NET files not found in data/raw/onet/")
    engine = _connect(None)
    try:
        mysql = load_from_mysql(engine)
    except Exception as err:
        pytest.skip(f"Database not loaded yet - run scripts/load_onet_to_mysql.py ({err})")
    files = load_onet(REAL_ONET_DIR)
    assert len(mysql["codes"]) == len(files["codes"])
    for student in (STUDENT_A, STUDENT_B):
        _assert_same(student, files, mysql, top_n=5, min_job_zone=3)
