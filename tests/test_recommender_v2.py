"""Tests for ml/recommender_v2.py (spec A9 in CLAUDE.md), using the tiny fake O*NET folder.

All students here are synthetic test inputs, not real students.
Run:  pytest -q tests/test_recommender_v2.py
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fake_onet import add_careers  # noqa: E402
from ml.baseline_recommender import RIASEC, load_onet  # noqa: E402
from ml.recommender_v2 import (SKILL_MAP_V2, SUBJECT_MAP_V2, add_extras, display_rule,  # noqa: E402
                               explain_v2, load_onet_v2, parse_answer, questions_needed,
                               recommend_v2, score_all_v2, target_career)

LAB = "19-0001.00"   # fake "Lab Scientist": strong Science, Critical Thinking, Writing; Biology, Chemistry


def student(top="Investigative", skills=None, subjects=None, default=3):
    """A synthetic test student: every row rated `default` unless given."""
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


def scores(s, data):
    return score_all_v2(s, data)[0]


# ---------------------------------------------------------------- readiness (A4)
def test_surplus_never_lowers_readiness(data):
    # Lab Scientist needs level 5 in Science. Rating 4 = level 5.25, rating 5 = level 7 (a surplus).
    by_rating = [scores(student(skills={"Research": {"rating": r}}), data).loc[LAB, "skill_low"]
                 for r in range(1, 6)]
    assert by_rating == sorted(by_rating)                 # higher rating never lowers readiness
    assert by_rating[3] == pytest.approx(by_rating[4])    # being above the requirement adds nothing, removes nothing


def test_no_experience_lowers_readiness_and_gives_start_from_scratch_gap(data):
    rated_3 = scores(student(skills={"Research": {"rating": 3}}), data).loc[LAB, "skill_low"]
    none = student(skills={"Research": "no_experience"})
    assert scores(none, data).loc[LAB, "skill_low"] < rated_3
    _, gaps = explain_v2(none, data, LAB)
    science = gaps[gaps["element"] == "Science"].iloc[0]
    assert science["note"] == "start from scratch"
    assert science["your_level"] == 0 and science["gap"] == pytest.approx(5.0)


# ---------------------------------------------------------------- unknowns and ranges (A5, A6)
def test_cant_assess_never_raises_match_low_and_low_le_high(data):
    base = scores(SCIENTIST, data)
    for key, mapping in (("skills", SKILL_MAP_V2), ("subjects", SUBJECT_MAP_V2)):
        for row in mapping:
            s = {**SCIENTIST, key: {**SCIENTIST[key], row: "cant_assess"}}
            t = scores(s, data)
            assert (t["match_low"] <= base["match_low"] + 1e-9).all(), row
            assert (t["match_low"] <= t["match_high"] + 1e-9).all(), row
            assert (t["match_high"] >= base["match_low"] - 1e-9).all(), row   # the true score is inside the range


def test_all_rated_gives_one_score_and_full_coverage(data):
    t = scores(SCIENTIST, data)
    assert (t["match_low"] == t["match_high"]).all()
    assert (t["coverage"] == 1).all()
    assert (t["display"] == "score").all()


def test_unknowns_stay_in_the_denominator(data):
    s = student(skills={"Research": "cant_assess"})
    got = scores(s, data).loc[LAB]

    # Manual calculation, written out separately from the engine.
    im, lv = data["skill_importance"].loc[LAB], data["skill_level"].loc[LAB]
    num_low = num_high = den = 0.0
    for row, elements in SKILL_MAP_V2.items():
        for e in elements:
            w = (im[e] - 1) / 4
            if row == "Research":                        # unknown
                met_low, met_high = 1 - max(0, lv[e] - 0) / 7, 1.0
            else:                                        # rated 3 -> level 3.5
                met_low = met_high = 1 - max(0, lv[e] - 3.5) / 7
            num_low += w * met_low
            num_high += w * met_high
            den += w                                     # unknowns ARE counted here
    assert got["skill_low"] == pytest.approx(num_low / den)
    assert got["skill_high"] == pytest.approx(num_high / den)
    known_w = sum((im[e] - 1) / 4 for r, els in SKILL_MAP_V2.items() if r != "Research" for e in els)
    assert got["coverage"] == pytest.approx((known_w + den_subjects(data)) / (den + den_subjects(data)))


def den_subjects(data):
    im = data["knowledge_importance"].loc[LAB]
    return sum((im[e] - 1) / 4 for els in SUBJECT_MAP_V2.values() for e in els)


def test_display_rule_thresholds():
    assert display_rule(0.0, 0) == "score"
    assert display_rule(0.2, 0) == "score"
    assert display_rule(0.2, 1) == "range"          # a critical unknown always forces a range
    assert display_rule(0.21, 0) == "range"
    assert display_rule(0.5, 0) == "range"
    assert display_rule(0.51, 0) == "withheld"
    assert display_rule(0.6, 2) == "withheld"


def test_display_in_recommendations(data):
    every_unknown = student(skills={r: "cant_assess" for r in SKILL_MAP_V2},
                            subjects={r: "cant_assess" for r in SUBJECT_MAP_V2})
    recs = recommend_v2(every_unknown, data, min_job_zone=None)
    assert (recs["display"] == "withheld").all() and (recs["coverage"] == 0).all()

    one_unknown = {**SCIENTIST, "skills": {**SCIENTIST["skills"], "Research": "cant_assess"}}
    lab = recommend_v2(one_unknown, data, min_job_zone=None).set_index("code").loc[LAB]
    assert lab["display"] == "range"                 # Science (IM 4.5) is a critical unknown
    assert "Science" in lab["critical_unknowns"]
    assert lab["follow_ups"][0] == "skill: Research"
    assert len(lab["follow_ups"]) <= 3


# ---------------------------------------------------------------- ranking (A3, A7)
def test_matching_profile_ranks_first(data):
    recs = recommend_v2(SCIENTIST, data, min_job_zone=None)
    assert recs.iloc[0]["career"] == "Lab Scientist"
    assert list(recs["match_low"]) == sorted(recs["match_low"], reverse=True)


def test_flat_interests_give_interest_fit_half(data):
    flat = {**SCIENTIST, "interests": {t: 3 for t in RIASEC}}
    assert (scores(flat, data)["interest_fit"] == 0.5).all()


def test_job_zone_filter(data):
    recs = recommend_v2(SCIENTIST, data)                  # default min_job_zone=3
    assert "Helper" not in set(recs["career"])


SCIENCE_CLONES = [(f"19-00{i}.00", f"Scientist {i}", 4, "Investigative", ["Science", "Critical Thinking", "Writing"],
                   ["Biology", "Chemistry"]) for i in range(2, 7)]


def test_diversity_max_two_per_field_in_top5(onet_dir):
    other_fields = [("15-0001.00", "Analyst", 4, "Investigative", ["Critical Thinking"], ["Mathematics"]),
                    ("29-0001.00", "Clinician", 5, "Social", ["Science"], ["Biology"])]
    data = load_onet_v2(add_careers(onet_dir, SCIENCE_CLONES + other_fields))
    plain = recommend_v2(SCIENTIST, data, min_job_zone=None, diversity=False)
    assert (plain.head(5)["field"] == "Life, Physical & Social Science").sum() == 5   # without re-ranking
    diverse = recommend_v2(SCIENTIST, data, min_job_zone=None, diversity=True)
    assert diverse.head(5)["field"].value_counts().max() <= 2
    assert diverse.iloc[0]["code"] == plain.iloc[0]["code"]   # the best career stays first
    assert set(diverse["code"]) == set(plain["code"])         # same careers, only the order changes


def test_diversity_fills_top5_when_too_few_fields(onet_dir):
    data = load_onet_v2(add_careers(onet_dir, SCIENCE_CLONES))   # only 3 fields exist
    diverse = recommend_v2(SCIENTIST, data, min_job_zone=None)
    assert len(diverse) == 8
    assert (diverse.head(5)["field"] == "Life, Physical & Social Science").sum() == 3   # 2 + 1 filler


# ---------------------------------------------------------------- data cleaning (A2)
def test_recommend_suppress_rows_are_ignored(onet_dir):
    path = onet_dir / "Knowledge.txt"
    df = pd.read_csv(path, sep="\t", dtype=str)
    hit = (df["O*NET-SOC Code"] == LAB) & (df["Element Name"] == "Biology") & (df["Scale ID"] == "LV")
    df.loc[hit, ["Data Value", "Recommend Suppress"]] = ["0.0", "Y"]
    df.to_csv(path, sep="\t", index=False)

    assert pd.isna(load_onet(onet_dir)["knowledge_level"].loc[LAB, "Biology"])
    assert load_onet(onet_dir, drop_suppressed=False)["knowledge_level"].loc[LAB, "Biology"] == 0.0
    # Without a level, Biology is left out of Lab Scientist's subject readiness instead of counting as 0.
    data = load_onet_v2(onet_dir)
    _, cats = score_all_v2(SCIENTIST, data)
    assert cats["subject"]["w"].loc[LAB, "Biology"] == 0


# ---------------------------------------------------------------- explanations and target career (A8)
def test_explain_v2_reasons_come_from_own_answers(data):
    reasons, gaps = explain_v2(SCIENTIST, data, LAB)
    assert any("Investigative" in r for r in reasons)
    assert any(r.startswith("Your Research") for r in reasons)
    assert sum(r.startswith("Your") for r in reasons) <= 2
    reasons, _ = explain_v2(SCIENTIST, data, "27-0001.00")   # Designer: Investigative is only 1.5 of 7 there
    assert not any("Investigative" in r for r in reasons)
    nothing_high = student(default=2)
    reasons, _ = explain_v2(nothing_high, data, LAB)
    assert not any(r.startswith("Your") for r in reasons)  # no rating >= 4 -> no skill reasons
    weak = student(default=1)
    _, gaps = explain_v2(weak, data, LAB)
    assert len(gaps) > 0 and (gaps["gap"] > 0.5).all() and (gaps["importance"] >= 3).all()
    assert list(gaps["priority"]) == sorted(gaps["priority"], reverse=True)


def test_target_career_questions_and_alternatives(data):
    s = {**SCIENTIST, "skills": {k: v for k, v in SCIENTIST["skills"].items() if k != "Writing"}}  # unanswered
    q = questions_needed(s, data, LAB)
    assert [x["item"] for x in q] == ["Writing"]
    t = target_career(s, data, LAB, min_job_zone=None)
    assert t["readiness"]["match_low"] <= t["readiness"]["match_high"]
    assert t["interest_fit"]["label"] == "strong"
    assert 0 < len(t["alternatives"]) <= 5 and LAB not in [a["code"] for a in t["alternatives"]]
    assert all(a["source"] == "similar profile" for a in t["alternatives"])


def test_related_occupations_file_is_used_when_columns_fit(onet_dir):
    # Column names as published in earlier O*NET releases; add_extras checks them before use.
    pd.DataFrame({"O*NET-SOC Code": [LAB], "Related O*NET-SOC Code": ["27-0001.00"],
                  "Relatedness Tier": ["Primary-Short"], "Index": ["1"]}).to_csv(
        onet_dir / "Related Occupations.txt", sep="\t", index=False)
    data = load_onet_v2(onet_dir)
    t = target_career(SCIENTIST, data, LAB, min_job_zone=None)
    assert t["alternatives"][0] == {**t["alternatives"][0], "code": "27-0001.00",
                                    "source": "O*NET related occupation"}


def test_unusable_related_file_falls_back(onet_dir):
    pd.DataFrame({"Code A": [LAB], "Code B": ["27-0001.00"]}).to_csv(
        onet_dir / "Related Occupations.txt", sep="\t", index=False)
    data = add_extras(load_onet(onet_dir), onet_dir)
    assert "related" not in data
    assert "not usable" in data["extras_info"][0]


def test_parse_answer():
    assert parse_answer({"rating": 4}) == ("rated", 4.0)
    assert parse_answer("Can't assess") == ("cant_assess", None)
    assert parse_answer(None) == ("cant_assess", None)
    assert parse_answer("no_experience") == ("no_experience", None)
    with pytest.raises(ValueError):
        parse_answer(6)
    with pytest.raises(ValueError):
        parse_answer("maybe")
