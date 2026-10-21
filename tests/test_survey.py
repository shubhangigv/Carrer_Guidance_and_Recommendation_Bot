"""Tests for the survey reader and the survey experiments.

The responses here are SYNTHETIC (random, made inside the test) in the same CSV format Google Forms exports.
They only check that the code works; they are not data and no result from them is reported anywhere.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from ml.recommender_v2 import SKILL_MAP_V2, SUBJECT_MAP_V2  # noqa: E402
from ml.survey import (INTEREST_ROWS, feature_table, field_of_code, load_field_map, load_survey,  # noqa: E402
                       parse_cell, to_student, to_student_v1)

Q5 = "5. How much do you enjoy these activities?"
Q6 = "6. Rate your current ability in these skills"
Q7 = "7. How good are you at these subjects?"
FIELDS = ["IT & Computing", "Healthcare & Medicine", "Arts, Design & Media"]


def fake_form_csv(path, n_per_field=10, seed=0, extra_rows=()):
    """A Google-Forms-shaped CSV with random answers; each field has its own interest pattern."""
    rng = np.random.default_rng(seed)
    rows = []
    for f_i, field in enumerate(FIELDS):
        for _ in range(n_per_field):
            row = {"Timestamp": "2026/10/16 10:00:00 AM GMT+5:30", "1. Which year are you in?": "2nd year",
                   "2. What is your branch / field of study?": "Science (B.Sc)",
                   "3. Do you feel you are on the right career path?": rng.choice(["Not sure", "Mostly yes"]),
                   "4. Have you used a career counsellor?": "No, never",
                   "8. Which career field are you aiming for?": field,
                   "9. Would you use an AI career guidance tool?": "Yes"}
            for j, text in enumerate(INTEREST_ROWS):
                base = 5 if j == [1, 3, 2][f_i] else 2
                row[f"{Q5} [{text}]"] = str(int(np.clip(base + rng.integers(-1, 2), 1, 5)))
            for r in SKILL_MAP_V2:
                row[f"{Q6} [{r}]"] = rng.choice(["1", "2", "3", "4", "5", "No experience", "Can't assess"])
            for r in SUBJECT_MAP_V2:
                row[f"{Q7} [{r}]"] = rng.choice(["1", "2", "3", "4", "5", "Not studied"])
            rows.append(row)
    rows += list(extra_rows)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


@pytest.fixture
def survey_csv(tmp_path):
    unsure = {"Timestamp": "x", "1. Which year are you in?": "1st year", "2. What is your branch / field of study?": "Law",
              "3. Do you feel you are on the right career path?": "No", "4. Have you used a career counsellor?": "No, never",
              "8. Which career field are you aiming for?": "Not sure yet", "9. Would you use an AI career guidance tool?": "Maybe",
              **{f"{Q5} [{t}]": "3" for t in INTEREST_ROWS}, **{f"{Q6} [{r}]": "3" for r in SKILL_MAP_V2},
              **{f"{Q7} [{r}]": "3" for r in SUBJECT_MAP_V2}}
    return fake_form_csv(tmp_path / "responses.csv", extra_rows=[unsure])


def test_load_survey_and_engine_input(survey_csv):
    tidy = load_survey(survey_csv)
    assert len(tidy) == 31 and tidy["aimed_field"].iloc[-1] == "Not sure yet"
    student = to_student(tidy.iloc[0])
    assert set(student["skills"]) == set(SKILL_MAP_V2) and set(student["subjects"]) == set(SUBJECT_MAP_V2)
    assert all(isinstance(v, int) for v in student["interests"].values())
    v1 = to_student_v1(tidy.iloc[0])
    assert all(isinstance(v, int) for v in v1["skills"].values())       # only numeric answers go to v1


def test_parse_cell():
    assert parse_cell("5 (High)", "interest") == 5 and parse_cell("1 (Low)", "interest") == 1
    assert parse_cell("3 = it is okay", "interest") == 3 and parse_cell("4.0", "skill") == 4
    with pytest.raises(ValueError):
        parse_cell("10", "skill")
    assert parse_cell("4", "skill") == 4 and parse_cell("No experience", "skill") == "no_experience"
    assert parse_cell("Can't assess", "skill") == "cant_assess" and parse_cell("Not studied", "subject") == "not_studied"
    assert parse_cell("", "skill") is None
    with pytest.raises(ValueError):
        parse_cell("maybe", "skill")


def test_missing_column_fails_loudly(tmp_path):
    path = fake_form_csv(tmp_path / "r.csv")
    df = pd.read_csv(path, dtype=str).drop(columns=[f"{Q6} [Programming]"])
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match=r"Programming"):
        load_survey(path)


def test_feature_table_codes_answers(survey_csv):
    X = feature_table(load_survey(survey_csv))
    assert X.shape[1] == 22
    assert set(np.unique(X.to_numpy()[~np.isnan(X.to_numpy())])) <= {0, 1, 2, 3, 4, 5}


def test_field_map_is_complete_and_unambiguous():
    fm = load_field_map()
    options = ["IT & Computing", "Engineering", "Healthcare & Medicine", "Life & Physical Sciences", "Business & Finance",
               "Management", "Education", "Law & Public Service", "Arts, Design & Media", "Social Work & Psychology",
               "Agriculture & Environment"]
    assert list(fm) == options                       # every Q8 option except "Not sure yet"
    assert field_of_code("15-1252.00", fm) == "IT & Computing"
    assert field_of_code("19-3033.00", fm) == "Social Work & Psychology"   # longest prefix wins over 19-
    assert field_of_code("11-9013.00", fm) == "Agriculture & Environment"  # over Management (11)


def test_random_baseline_and_wilson():
    from hit_rate import random_hit, wilson
    assert random_hit(10, 0, 5) == 0 and random_hit(10, 6, 5) == 1.0
    assert math.isclose(random_hit(10, 1, 1), 0.1)
    assert math.isclose(random_hit(100, 10, 5), 1 - math.comb(90, 5) / math.comb(100, 5))
    lo, hi = wilson(30, 50)
    assert lo < 0.6 < hi and 0 <= lo and hi <= 1


def test_hit_rate_runs_on_fake_onet(survey_csv, onet_dir, tmp_path):
    import hit_rate
    hit_rate.main(["--survey", str(survey_csv), "--onet-dir", str(onet_dir), "--out", str(tmp_path / "out"),
                   "--processed", str(tmp_path / "processed")])
    summary = pd.read_csv(tmp_path / "out" / "hit_rate.csv")
    assert set(summary["method"]) == {"v2", "v2_no_div", "v3", "v1", "random"}
    assert (summary["students"] == 30).all()                     # "Not sure yet" left out
    assert summary["hit_rate"].between(0, 1).all()
    assert "not_sure_skipped=1" in (tmp_path / "out" / "hit_rate_counts.txt").read_text()


def test_ml_compare_runs_without_leakage(survey_csv, onet_dir, tmp_path):
    import ml_compare
    ml_compare.main(["--survey", str(survey_csv), "--onet-dir", str(onet_dir), "--out", str(tmp_path / "out")])
    table = pd.read_csv(tmp_path / "out" / "ml_compare.csv")
    assert {"majority", "logreg", "forest", "svm", "engine_v2", "engine_v3"} <= set(table["model"])
    assert table[["accuracy_mean", "macro_f1_mean"]].stack().between(0, 1).all()
    majority = table.set_index("model").loc["majority", "accuracy_mean"]
    assert math.isclose(majority, 10 / 30, abs_tol=0.01)          # 3 equal classes -> 1/3
    assert (tmp_path / "out" / "ml_feature_importance.csv").exists()


def test_tune_weights_runs_with_cross_validation(survey_csv, onet_dir, tmp_path):
    import json
    import tune_weights
    tune_weights.main(["--survey", str(survey_csv), "--onet-dir", str(onet_dir), "--out", str(tmp_path / "out"),
                       "--repeats", "1"])
    saved = json.loads((tmp_path / "out" / "tuned_weights.json").read_text())
    assert sum(saved["weights"][k] for k in ("interest", "skill", "subject")) == pytest.approx(1)
    assert all(0 <= v <= 1 for v in saved["cv_hit_rate"].values())
    assert saved["students"] == 30                                 # "Not sure yet" left out


def test_hybrid_runs_with_cross_validation(survey_csv, onet_dir, tmp_path):
    import hybrid
    summary = hybrid.main(["--survey", str(survey_csv), "--onet-dir", str(onet_dir), "--out", str(tmp_path / "out"),
                           "--repeats", "1"])
    assert set(summary["method"]) == {"hybrid", "hybrid_branch", "v3", "random"}
    assert (summary.loc[summary["method"] != "random", "students"] == 30).all()
    assert summary["hit_rate"].between(0, 1).all()


def test_survey_insights_runs(survey_csv, tmp_path):
    import survey_insights
    by_field, eta = survey_insights.main(["--survey", str(survey_csv), "--out", str(tmp_path / "out"), "--no-charts",
                                          "--per-student", str(tmp_path / "missing.csv")])
    assert (by_field["students"] >= survey_insights.MIN_GROUP).all() or survey_insights.SMALL in by_field.index
    assert eta.between(0, 1).all()
    assert "Answer quality" in (tmp_path / "out" / "insights.md").read_text(encoding="utf-8")


def test_survey_analysis_runs(survey_csv, tmp_path):
    import survey_analysis
    survey_analysis.main(["--survey", str(survey_csv), "--out", str(tmp_path / "out"), "--no-charts",
                         "--clean-out", str(tmp_path / "clean.csv")])
    text = (tmp_path / "out" / "survey_summary.md").read_text(encoding="utf-8")
    assert "31 responses" in text and "Q3 by year of study" in text


def test_labelled_scale_and_all_unknown_answers_reported(tmp_path):
    path = fake_form_csv(tmp_path / "r.csv")
    df = pd.read_csv(path, dtype=str)
    col = f"{Q5} [{list(INTEREST_ROWS)[0]}]"
    df[col] = df[col].map(lambda v: f"{v} (High)" if v == "5" else f"{v} (Low)" if v == "1" else v)
    df.to_csv(path, index=False)
    assert load_survey(path)["Realistic"].between(1, 5).all()      # labelled answers are read as numbers
    df.loc[0, f"{Q6} [Programming]"] = "Expert"
    df.loc[1, f"{Q7} [Biology]"] = "Sometimes"
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match=r"Q6: \['Expert'\].*Q7: \['Sometimes'\]"):
        load_survey(path)


def test_model_features_compares_the_same_folds(survey_csv, tmp_path):
    import model_features
    table = model_features.main(["--survey", str(survey_csv), "--out", str(tmp_path / "out"), "--repeats", "1"])
    assert list(table["features"]) == ["answers22", "answers22+branch", "skills+subjects", "branch_only"]
    assert not table.set_index("features").loc["answers22", "beats_answers22_on_both"]
    assert table[["accuracy_mean", "macro_f1_mean"]].stack().between(0, 1).all()
