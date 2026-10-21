"""Tests for ml/recommender_v3.py (engine v2 + strength fit), using the tiny fake O*NET folder.

All students here are synthetic test inputs, not real students.
Run:  pytest -q tests/test_recommender_v3.py
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.baseline_recommender import RIASEC  # noqa: E402
from ml.recommender_v2 import COMPONENT_WEIGHTS, SKILL_MAP_V2, SUBJECT_MAP_V2, load_onet_v2, score_all_v2  # noqa: E402
from ml.recommender_v3 import recommend_v3, score_all_v3, strength_fit  # noqa: E402

LAB = "19-0001.00"   # fake "Lab Scientist": strong Science, Critical Thinking, Writing; Biology, Chemistry


def student(top="Investigative", skills=None, subjects=None, default=3):
    return {
        "interests": {t: (5 if t == top else 2) for t in RIASEC},
        "skills": {row: {"rating": default} for row in SKILL_MAP_V2} | (skills or {}),
        "subjects": {row: {"rating": default} for row in SUBJECT_MAP_V2} | (subjects or {}),
    }


SCIENTIST = student(skills={"Research": {"rating": 5}, "Problem Solving": {"rating": 5}, "Writing": {"rating": 5}},
                    subjects={"Biology": {"rating": 5}, "Physics/Chemistry": {"rating": 5}}, default=1)


@pytest.fixture
def data(onet_dir):
    return load_onet_v2(onet_dir)


def test_flat_ratings_give_neutral_fit(data):
    # "all 4s" must not look like "good at everything": the fit is 0.5 for every career
    t, _ = score_all_v3(student(default=4), data)
    assert t["skill_fit"].eq(0.5).all() and t["subject_fit"].eq(0.5).all()


def test_strengths_matching_the_career_raise_the_fit(data):
    t, _ = score_all_v3(SCIENTIST, data)
    assert t.loc[LAB, "skill_fit"] > 0.5
    assert t.loc[LAB, "skill_fit"] == t["skill_fit"].max()


def test_fit_share_zero_is_engine_v2(data):
    v2, _ = score_all_v2(SCIENTIST, data)
    v3, _ = score_all_v3(SCIENTIST, data, weights=COMPONENT_WEIGHTS, fit_share=0)
    pd.testing.assert_series_equal(v3["match_low"], v2["match_low"])


def test_all_rated_gives_one_score_and_cant_assess_gives_low_le_high(data):
    t, _ = score_all_v3(SCIENTIST, data, fit_share=0.5)
    assert (t["match_low"] == t["match_high"]).all()
    s = {**SCIENTIST, "skills": {**SCIENTIST["skills"], "Programming": "cant_assess"}}
    t, _ = score_all_v3(s, data, fit_share=0.5)
    assert (t["match_low"] <= t["match_high"] + 1e-9).all()


def test_too_few_rows_gives_neutral_fit():
    needs = pd.DataFrame({"A": [5.0, 1.0], "B": [1.0, 5.0], "C": [3.0, 3.0]}, index=["x", "y"])
    assert strength_fit(pd.Series({"A": 5.0, "B": 1.0}), needs).eq(0.5).all()
    full = strength_fit(pd.Series({"A": 5.0, "B": 1.0, "C": 3.0}), needs)
    assert full["x"] == pytest.approx(1.0) and full["y"] == pytest.approx(0.0)


def test_matching_profile_ranks_first(data):
    top = recommend_v3(SCIENTIST, data, top_n=3, min_job_zone=None)
    assert top.iloc[0]["code"] == LAB
    assert {"skill_fit", "subject_fit", "match_low", "display"} <= set(top.columns)



def test_row_needs_use_importance_even_without_a_level(data):
    from ml.recommender_v3 import career_row_needs
    _, cats = score_all_v3(SCIENTIST, data)
    cats["skill"]["valid"].loc[LAB, :] = False                          # as if every level were suppressed
    needs = career_row_needs(cats["skill"], SKILL_MAP_V2)
    assert not pd.isna(needs.at[LAB, "Research"])                       # importance is still used
