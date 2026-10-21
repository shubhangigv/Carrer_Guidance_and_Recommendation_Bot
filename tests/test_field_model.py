"""Tests for ml/field_model.py and the predicted-field path in ml/preferences.py.
The survey CSV here is SYNTHETIC (tests/test_survey.py: fake_form_csv); no real responses are used."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import ml.preferences as prefs  # noqa: E402
from ml.baseline_recommender import RIASEC  # noqa: E402
from ml.field_model import FEATURES, student_features, train_field_model  # noqa: E402
from ml.recommender_v2 import SKILL_MAP_V2, SUBJECT_MAP_V2, load_onet_v2  # noqa: E402
from test_survey import fake_form_csv  # noqa: E402

LAB, DESIGNER = "19-0001.00", "27-0001.00"


def student(top):
    return {"interests": {t: (5 if t == top else 2) for t in RIASEC},
            "skills": {r: {"rating": 3} for r in SKILL_MAP_V2} | {"Programming": "no_experience", "Research": "cant_assess"},
            "subjects": {r: {"rating": 3} for r in SUBJECT_MAP_V2}}


def test_student_features_use_the_survey_coding():
    row = student("Artistic")
    x = student_features(row)
    assert list(x.columns) == FEATURES
    assert x.at[0, "Artistic"] == 5 and x.at[0, "skill:Programming"] == 0 and np.isnan(x.at[0, "skill:Research"])


def test_train_and_predict_on_synthetic_survey(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FIELD_MODEL", "yes")
    model = train_field_model(fake_form_csv(tmp_path / "s.csv"))
    assert model is not None and model.n_students == 30
    # the synthetic fields differ by top interest: IT -> Investigative, Healthcare -> Social, Arts -> Artistic
    assert model.predict(student("Artistic"))["field"] == "Arts, Design & Media"
    assert model.predict(student("Social"))["field"] == "Healthcare & Medicine"
    assert 0 <= model.predict(student("Investigative"))["probability"] <= 1


def test_no_file_or_switched_off_gives_none(tmp_path, monkeypatch):
    assert train_field_model(tmp_path / "missing.csv") is None
    monkeypatch.setenv("USE_FIELD_MODEL", "no")
    assert train_field_model(fake_form_csv(tmp_path / "s.csv")) is None


class FakeModel:
    def predict(self, student, branch=None):
        return {"field": "Arts, Design & Media", "probability": 0.8, "prefixes": ["27"], "used_branch": False}


@pytest.fixture
def data(onet_dir):
    return load_onet_v2(onet_dir)


def test_predicted_field_used_only_without_areas_or_course(data, monkeypatch):
    monkeypatch.setattr(prefs, "MIN_POOL", 1)
    out, info = prefs.personalised(student("Investigative"), data, {}, top_n=3, min_job_zone=None, field_model=FakeModel())
    assert info["areas_from"] == "predicted" and out.iloc[0]["code"] == DESIGNER
    assert out.iloc[0]["area_labels"] == ["Arts, Design & Media"]
    assert list(out["group"]) == ["your_areas", "also_consider", "also_consider"]
    assert any("best guess" in n for n in info["notes"])
    out, info = prefs.personalised(student("Investigative"), data, {"areas": ["science"]}, top_n=3,
                                   min_job_zone=None, field_model=FakeModel())
    assert info["areas_from"] == "picked"                       # the student's own choice wins


def test_branch_model_is_used_when_a_course_is_given(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FIELD_MODEL", "yes")
    model = train_field_model(fake_form_csv(tmp_path / "s.csv"))
    assert model.predict(student("Artistic"))["used_branch"] is False
    with_branch = model.predict(student("Artistic"), "Engineering (B.E. / B.Tech)")
    assert with_branch["used_branch"] is True and with_branch["field"] in model.fields
    x = student_features(student("Artistic"), "Not a real branch")       # unknown branch -> "Other"
    assert x.at[0, "branch:Other"] == 1 and x.filter(like="branch:").sum(axis=1).iat[0] == 1
