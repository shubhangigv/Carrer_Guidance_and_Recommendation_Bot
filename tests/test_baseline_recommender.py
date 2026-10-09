"""Tests for ml/baseline_recommender.py using a tiny fake O*NET folder (no real data needed).

Run:  pytest -q
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.baseline_recommender import RIASEC, SKILL_MAP, SUBJECT_MAP, explain, load_onet, recommend  # noqa: E402

SKILLS = sorted({e for v in SKILL_MAP.values() for e in v})
KNOWLEDGE = sorted({e for v in SUBJECT_MAP.values() for e in v})

# Three clearly different fake careers: (code, title, job zone, top interest, strong skills, strong knowledge)
CAREERS = [
    ("19-0001.00", "Lab Scientist", 4, "Investigative", ["Science", "Critical Thinking", "Writing"], ["Biology", "Chemistry"]),
    ("27-0001.00", "Designer", 3, "Artistic", ["Speaking", "Persuasion", "Coordination"], ["Fine Arts", "Design"]),
    ("47-0001.00", "Helper", 1, "Realistic", ["Repairing", "Installation", "Troubleshooting"], ["Building and Construction"]),
]


def _rows(code, elements, scales, strong, extra_cols=True):
    rows = []
    for e in elements:
        for scale, (lo, hi) in scales.items():
            value = hi if e in strong else lo
            row = {"O*NET-SOC Code": code, "Element ID": "x", "Element Name": e, "Scale ID": scale, "Data Value": value}
            if extra_cols:
                row.update({"N": "", "Standard Error": "", "Lower CI Bound": "", "Upper CI Bound": "",
                            "Recommend Suppress": "N", "Not Relevant": ""})
            row.update({"Date": "08/2026", "Domain Source": "Test"})
            rows.append(row)
    return rows


@pytest.fixture
def onet_dir(tmp_path):
    occ, interests, skills, know = [], [], [], []
    for code, title, zone, top, strong_sk, strong_kn in CAREERS:
        occ.append({"O*NET-SOC Code": code, "Title": title, "Description": f"{title} test career."})
        interests += _rows(code, RIASEC, {"OI": (1.5, 6.5)}, [top], extra_cols=False)
        skills += _rows(code, SKILLS, {"IM": (1.5, 4.5), "LV": (1.0, 5.0)}, strong_sk)
        know += _rows(code, KNOWLEDGE, {"IM": (1.5, 4.5), "LV": (1.0, 5.0)}, strong_kn)
    half = len(skills) // 2
    files = {
        "Occupation Data.txt": occ,
        "Career Interest Types.txt": interests,
        "Essential Skills.txt": skills[:half],
        "Transferable Skills.txt": skills[half:],
        "Knowledge.txt": know,
        "Job Zones.txt": [{"O*NET-SOC Code": c[0], "Job Zone": c[2], "Date": "08/2026", "Domain Source": "Test"} for c in CAREERS],
    }
    for name, rows in files.items():
        pd.DataFrame(rows).to_csv(tmp_path / name, sep="\t", index=False)
    return tmp_path


def _student(top_interest, skill_items, subjects):
    return {
        "interests": {t: (5 if t == top_interest else 2) for t in RIASEC},
        "skills": {s: (5 if s in skill_items else 1) for s in SKILL_MAP},
        "subjects": {s: (5 if s in subjects else 1) for s in SUBJECT_MAP},
    }


SCIENCE_STUDENT = _student("Investigative", ["Research", "Critical Thinking", "Writing"], ["Biology", "Chemistry"])


def test_load_counts(onet_dir):
    data = load_onet(onet_dir)
    assert len(data["codes"]) == 3
    assert list(data["interests"].columns) == RIASEC


def test_scores_are_between_0_and_100_and_sorted(onet_dir):
    recs = recommend(SCIENCE_STUDENT, load_onet(onet_dir), top_n=3)
    assert recs["match_score"].between(0, 100).all()
    assert list(recs["match_score"]) == sorted(recs["match_score"], reverse=True)


def test_matching_profile_ranks_first(onet_dir):
    recs = recommend(SCIENCE_STUDENT, load_onet(onet_dir), top_n=3)
    assert recs.iloc[0]["career"] == "Lab Scientist"


def test_flat_profile_gives_neutral_50(onet_dir):
    flat = {"interests": {t: 3 for t in RIASEC}, "skills": {s: 3 for s in SKILL_MAP},
            "subjects": {s: 3 for s in SUBJECT_MAP}}
    recs = recommend(flat, load_onet(onet_dir), top_n=3)
    assert (recs["match_score"] == 50).all()


def test_job_zone_filter_hides_low_preparation_jobs(onet_dir):
    recs = recommend(SCIENCE_STUDENT, load_onet(onet_dir), top_n=3, min_job_zone=3)
    assert "Helper" not in set(recs["career"])


def test_explain_gives_reasons_and_positive_sorted_gaps(onet_dir):
    data = load_onet(onet_dir)
    weak = _student("Investigative", [], ["Biology"])   # low skills -> gaps expected
    reasons, gaps = explain(weak, data, "19-0001.00")
    assert any("Investigative" in r for r in reasons)
    assert len(gaps) > 0
    assert (gaps["gap"] > 0).all()
    assert list(gaps["priority"]) == sorted(gaps["priority"], reverse=True)
