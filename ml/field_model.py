"""Field model: predicts the career FIELD a student is likely aiming for, from their 22 quiz answers.

Trained on the survey (data/raw/survey/responses.csv, question 8 = the field each student aims for) with
Logistic Regression - the model that did best in experiments/ml_compare.py. Two versions are trained:
  with_branch   the 22 answers + the student's branch (survey Q2). Used when the student gave their course
                (config/course_areas.csv maps each course to a Q2 option). Best in experiments/model_features.py:
                69.6% accuracy vs 60.5% without the branch (final survey: 5 fields, 77 students, cross-validated).
  answers_only  used when no course was given.
Used by the app when a student picks no areas (ml/preferences.py): engine v3 then fills the first places
from the predicted field - the "hybrid" evaluated in experiments/hybrid.py.

Privacy: the model is trained in memory when the server starts, only on the PC that has the survey file
(the file is git-ignored and never leaves that PC). Nothing is saved to disk or committed. Without the file
the app simply works without it. Because it retrains on every start, new survey responses are used
automatically. Set USE_FIELD_MODEL=no in .env to switch it off.
"""
import logging
import os
import warnings

import numpy as np
import pandas as pd

from ml.recommender_v2 import NONE_YET, RATED, SKILL_MAP_V2, SUBJECT_MAP_V2, parse_answer
from ml.baseline_recommender import RIASEC

log = logging.getLogger("pathfinder.field_model")
MIN_TRAIN = 3                # fields with fewer survey students than this are not learned
SEED = 42
FEATURES = list(RIASEC) + [f"skill:{r}" for r in SKILL_MAP_V2] + [f"subject:{r}" for r in SUBJECT_MAP_V2]
# The answer options of survey question 2 (tools/create_career_survey.gs), one-hot coded in this order.
BRANCHES = ["Engineering (B.E. / B.Tech)", "Computer Applications (BCA)", "Science (B.Sc)", "Commerce (B.Com)",
            "Management (BBA / BMS)", "Arts / Humanities (BA)", "Medical / Nursing / Pharmacy", "Design / Fine Arts",
            "Law", "Other"]
BRANCH_FEATURES = [f"branch:{b}" for b in BRANCHES]


def branch_columns(branches):
    """One-hot branch columns (unknown / unlisted branch -> "Other")."""
    known = [b if b in BRANCHES else "Other" for b in branches]
    return pd.DataFrame([[float(k == b) for b in BRANCHES] for k in known], columns=BRANCH_FEATURES)


def logreg_pipeline():
    """Missing answers filled with the training median (plus 'was missing' flags), scaled, then
    Logistic Regression with balanced classes. Fixed, standard settings; no tuning on the survey."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0))


def student_features(student, branch=None):
    """One row of model input from an engine-style student dict (same coding as ml.survey.feature_table):
    a rating stays 1-5, no_experience / not_studied -> 0, cant_assess / missing -> NaN.
    With a branch (a survey Q2 option), the one-hot branch columns are added."""
    row = {t: float(student["interests"][t]) for t in RIASEC}
    for key, mapping, prefix in (("skills", SKILL_MAP_V2, "skill"), ("subjects", SUBJECT_MAP_V2, "subject")):
        answers = student.get(key, {})
        for r in mapping:
            status, rating = parse_answer(answers.get(r))
            row[f"{prefix}:{r}"] = rating if status == RATED else 0.0 if status in NONE_YET else np.nan
    answers = pd.DataFrame([row], columns=FEATURES)
    return answers if branch is None else pd.concat([answers, branch_columns([branch])], axis=1)


class FieldModel:
    def __init__(self, answers_only, with_branch, field_map, n_students, left_out):
        self.answers_only, self.with_branch, self.field_map = answers_only, with_branch, field_map
        self.n_students, self.left_out = n_students, left_out
        self.fields = list(answers_only.classes_)

    def predict(self, student, branch=None):
        """{"field", "probability", "prefixes", "used_branch"} for the most likely field.
        branch: the student's survey-Q2 branch (from their course), or None."""
        pipe = self.with_branch if branch is not None else self.answers_only
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            proba = pipe.predict_proba(student_features(student, branch))[0]
        best = int(np.argmax(proba))
        field = pipe.classes_[best]
        return {"field": field, "probability": round(float(proba[best]), 3), "prefixes": self.field_map[field],
                "used_branch": branch is not None}


def train_field_model(survey_path=None, field_map=None):
    """Train on the survey. Returns None (and logs why) if the file is missing, switched off, or too small."""
    from ml.survey import DEFAULT_SURVEY, NOT_SURE, feature_table, is_complete, load_field_map, load_survey
    if os.getenv("USE_FIELD_MODEL", "yes").strip().lower() in ("no", "n", "false", "0"):
        log.info("Field model switched off (USE_FIELD_MODEL=no)")
        return None
    path = survey_path or DEFAULT_SURVEY
    if not os.path.exists(path):
        log.info("Field model not trained: no survey file at %s (the app works without it)", path)
        return None
    field_map = field_map or load_field_map()
    tidy = load_survey(path)
    tidy = tidy[(tidy["aimed_field"] != NOT_SURE) & tidy["aimed_field"].isin(field_map) & tidy.apply(is_complete, axis=1)]
    counts = tidy["aimed_field"].value_counts()
    small = counts[counts < MIN_TRAIN]
    tidy = tidy[~tidy["aimed_field"].isin(small.index)]
    if tidy["aimed_field"].nunique() < 2:
        log.info("Field model not trained: fewer than 2 fields with %d+ students", MIN_TRAIN)
        return None
    X, y = feature_table(tidy)[FEATURES].reset_index(drop=True), tidy["aimed_field"].to_numpy()
    X_branch = pd.concat([X, branch_columns(tidy["branch"].fillna("Other").tolist())], axis=1)
    answers_only, with_branch = logreg_pipeline(), logreg_pipeline()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        answers_only.fit(X, y)
        with_branch.fit(X_branch, y)
    model = FieldModel(answers_only, with_branch, field_map, len(tidy), dict(small))
    log.info("Field model trained on %d survey students, fields: %s", len(tidy), model.fields)
    return model


__all__ = ["BRANCHES", "FieldModel", "branch_columns", "logreg_pipeline", "student_features", "train_field_model"]
