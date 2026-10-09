"""Tests for ml/baseline_recommender.py using a tiny fake O*NET folder (tests/fake_onet.py).

Run:  pytest -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fake_onet import SCIENCE_STUDENT, _student  # noqa: E402
from ml.baseline_recommender import RIASEC, SKILL_MAP, SUBJECT_MAP, explain, load_onet, recommend  # noqa: E402


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
