"""Tests for ml/preferences.py (areas, course, lifestyle filters, "not for me", strongest skills).

Uses the tiny fake O*NET folder (3 careers) and small hand-made area lists. All students are synthetic.
Run:  pytest -q tests/test_preferences.py
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ml.preferences as prefs  # noqa: E402
from ml.baseline_recommender import RIASEC  # noqa: E402
from ml.recommender_v2 import SKILL_MAP_V2, SUBJECT_MAP_V2, load_onet_v2  # noqa: E402
from ml.recommender_v3 import score_all_v3  # noqa: E402

LAB, DESIGNER, HELPER = "19-0001.00", "27-0001.00", "47-0001.00"


@pytest.fixture
def data(onet_dir):
    return load_onet_v2(onet_dir)


@pytest.fixture(autouse=True)
def small_pool(monkeypatch):
    monkeypatch.setattr(prefs, "MIN_POOL", 1)          # the fake data has only 3 careers


@pytest.fixture
def areas(tmp_path):
    (tmp_path / "areas.csv").write_text("key,label,example,soc_prefixes\nlab,Labs,,19-0\nart,Art,,27-0\n", encoding="utf-8")
    return prefs.load_areas(tmp_path / "areas.csv")


@pytest.fixture
def courses(tmp_path, areas):
    (tmp_path / "courses.csv").write_text("key,label,areas\nbdes,B.Des,art\nother,Other,\n", encoding="utf-8")
    return prefs.load_courses(tmp_path / "courses.csv", areas=areas)


def scientist(**extra):
    return {"interests": {t: (5 if t == "Investigative" else 2) for t in RIASEC},
            "skills": {r: {"rating": 3} for r in SKILL_MAP_V2} | {"Research": {"rating": 5}},
            "subjects": {r: {"rating": 3} for r in SUBJECT_MAP_V2} | {"Biology": {"rating": 5}}, **extra}


def run(data, profile, areas, courses, **kw):
    return prefs.personalised(scientist(), data, profile, top_n=3, min_job_zone=None, areas=areas, courses=courses, **kw)


# ---------------------------------------------------------------- config files
def test_real_config_files_are_valid():
    areas = prefs.load_areas()
    courses = prefs.load_courses(areas=areas)          # raises if a course names an unknown area
    assert areas["prefixes"].apply(len).gt(0).all()
    assert "tech" in areas.index and "btech_cse" in courses.index


def test_unknown_area_in_course_file_fails(tmp_path, areas):
    (tmp_path / "bad.csv").write_text("key,label,areas\nx,X,nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown areas"):
        prefs.load_courses(tmp_path / "bad.csv", areas=areas)


# ---------------------------------------------------------------- checking answers
def test_clean_profile_defaults_and_errors(areas, courses):
    assert prefs.clean_profile(None, areas, courses) == {"areas": [], "course": None, "strengths": [], "weaknesses": [],
                                                        "work_setting": "any", "further_study": "any"}
    for bad in ({"areas": ["nope"]}, {"areas": ["lab", "art", "lab", "x", "y"]}, {"course": "nope"},
                {"strengths": ["Programming"], "weaknesses": ["Programming"]}, {"strengths": ["Dancing"]},
                {"work_setting": "moon"}, {"further_study": "maybe"}):
        with pytest.raises(ValueError):
            prefs.clean_profile(bad, areas, courses)


# ---------------------------------------------------------------- grouping, hiding, filters
def test_picked_area_comes_first_even_against_the_quiz_score(data, areas, courses):
    plain, _ = run(data, {}, areas, courses)
    assert plain.iloc[0]["code"] == LAB and set(plain["group"]) == {"all"}
    out, info = run(data, {"areas": ["art"]}, areas, courses)
    assert out.iloc[0]["code"] == DESIGNER and out.iloc[0]["group"] == "your_areas"
    assert out.iloc[0]["area_keys"] == ["art"] and "In an area you picked: Art" in out.iloc[0]["extra_reasons"]
    assert set(out["group"][1:]) == {"also_consider"}           # the rest is still shown, after it
    assert info["areas_from"] == "picked" and info["chosen_areas"] == ["Art"]


def test_course_areas_are_used_when_no_area_is_picked(data, areas, courses):
    out, info = run(data, {"course": "bdes"}, areas, courses)
    assert out.iloc[0]["code"] == DESIGNER and bool(out.iloc[0]["course_link"])
    assert info["areas_from"] == "course" and any("course" in n for n in info["notes"])
    _, info = run(data, {"course": "other"}, areas, courses)    # a course with no areas: plain ranking
    assert info["areas_from"] is None


def test_hidden_careers_are_left_out(data, areas, courses):
    out, info = run(data, {}, areas, courses, hidden={LAB})
    assert LAB not in set(out["code"]) and any("not for me" in n for n in info["notes"])


def test_no_further_study_drops_job_zone_5(data, areas, courses):
    data["job_zone"] = data["job_zone"].copy()
    data["job_zone"][LAB] = 5
    out, info = run(data, {"further_study": "no"}, areas, courses)
    assert LAB not in set(out["code"]) and any("1 careers left out" in n for n in info["notes"])


def test_work_setting_filters_use_work_context(data, areas, courses):
    data["work_context"] = pd.DataFrame({"outdoors": [1.0, 1.5, 4.8], "sitting": [4.5, 3.0, 1.5]},
                                        index=[LAB, DESIGNER, HELPER])
    desk, _ = run(data, {"work_setting": "desk"}, areas, courses)
    active, _ = run(data, {"work_setting": "active"}, areas, courses)
    assert HELPER not in set(desk["code"]) and LAB in set(desk["code"])
    assert LAB not in set(active["code"]) and HELPER in set(active["code"])


def test_filter_that_leaves_too_few_careers_is_skipped(data, areas, courses, monkeypatch):
    monkeypatch.setattr(prefs, "MIN_POOL", 3)
    data["work_context"] = pd.DataFrame({"outdoors": [4.0, 4.0, 4.0], "sitting": [1, 1, 1]}, index=[LAB, DESIGNER, HELPER])
    out, info = run(data, {"work_setting": "desk"}, areas, courses)
    assert len(out) == 3 and any("skipped" in n for n in info["notes"])


def test_missing_work_context_is_reported_not_fatal(data, areas, courses):
    out, info = run(data, {"work_setting": "desk"}, areas, courses)
    assert len(out) == 3 and any("not loaded" in n for n in info["notes"])


# ---------------------------------------------------------------- strongest / weakest skills
def test_picked_strengths_break_flat_ratings(data):
    flat = {"interests": {t: 3 for t in RIASEC}, "skills": {r: {"rating": 4} for r in SKILL_MAP_V2},
            "subjects": {r: {"rating": 4} for r in SUBJECT_MAP_V2}}
    t, _ = score_all_v3(flat, data)
    assert t["skill_fit"].eq(0.5).all()                         # all 4s: no information
    picked = {**flat, "strengths": ["Research", "Problem Solving", "Writing"], "weaknesses": ["Leadership"]}
    t2, _ = score_all_v3(picked, data)
    assert t2.loc[LAB, "skill_fit"] > 0.5 and t2.loc[LAB, "skill_fit"] == t2["skill_fit"].max()
    assert (t2["skill_readiness_low"] == t["skill_readiness_low"]).all()   # picks never change readiness


def test_add_work_context_reads_the_file(tmp_path, data):
    rows = [{"O*NET-SOC Code": LAB, "Element ID": "x", "Element Name": name, "Scale ID": scale, "Category": "n/a",
             "Data Value": value, "Recommend Suppress": sup}
            for name, scale, value, sup in [("Outdoors, Exposed to All Weather Conditions", "CX", "1.2", "N"),
                                            ("Spend Time Sitting", "CX", "4.4", "N"),
                                            ("Spend Time Sitting", "CXP", "0.9", "N"),          # other scale: ignored
                                            ("Outdoors, Exposed to All Weather Conditions", "CX", "5", "Y")]]  # suppressed
    pd.DataFrame(rows).to_csv(tmp_path / "Work Context.txt", sep="\t", index=False)
    prefs.add_work_context(data, tmp_path)
    assert data["work_context"].loc[LAB, "outdoors"] == pytest.approx(1.2)
    assert data["work_context"].loc[LAB, "sitting"] == pytest.approx(4.4)
