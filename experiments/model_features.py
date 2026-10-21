"""Which answers should the field model use? Compare feature sets with the same cross-validation.

Feature sets (all with the same Logistic Regression pipeline as the app, ml/field_model.logreg_pipeline):
  answers22        the 22 quiz answers (what the app uses now)
  answers22+branch the 22 answers + the student's branch (survey Q2, one-hot; the app's quiz asks the course)
  skills+subjects  the 16 skill and subject answers only (interests barely differ by field, insights.md)
  branch_only      the branch alone (how much does the course already tell us?)
Same students, same folds (repeated stratified 5-fold x 5, fixed seeds), fields with fewer than 3 students
left out, as in experiments/ml_compare.py. Metrics: accuracy and macro-F1, mean and std over repeats.

Decision rule, fixed BEFORE running: the app switches to another feature set only if it beats answers22 on
BOTH mean accuracy and mean macro-F1. With ~60 students, small differences are noise - report them as such.

Writes  docs/results/survey/model_features.csv
Run:    python experiments\\model_features.py
"""
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.field_model import logreg_pipeline  # noqa: E402
from ml.survey import DEFAULT_SURVEY, NOT_SURE, feature_table, is_complete, load_field_map, load_survey  # noqa: E402

OUT_DIR = ROOT / "docs" / "results" / "survey"
SEED, REPEATS, MIN_CLASS = 42, 5, 3


def feature_sets(tidy):
    answers = feature_table(tidy)
    branch = pd.get_dummies(tidy["branch"].fillna("Other"), prefix="branch").astype(float)
    sub = [c for c in answers.columns if c.startswith(("skill:", "subject:"))]
    return {"answers22": answers, "answers22+branch": pd.concat([answers, branch], axis=1),
            "skills+subjects": answers[sub], "branch_only": branch}


def compare(tidy, repeats=REPEATS):
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    y = tidy["aimed_field"].to_numpy()
    k = int(min(5, pd.Series(y).value_counts().min()))
    rows = []
    for name, X in feature_sets(tidy).items():
        accs, f1s = [], []
        for rep in range(repeats):
            cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=SEED + rep)   # same folds for every set
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pred = cross_val_predict(logreg_pipeline(), X, y, cv=cv)
            accs.append(accuracy_score(y, pred))
            f1s.append(f1_score(y, pred, average="macro", zero_division=0))
        rows.append({"features": name, "n_features": X.shape[1], "students": len(y), "folds": k, "repeats": repeats,
                     "accuracy_mean": np.mean(accs), "accuracy_std": np.std(accs),
                     "macro_f1_mean": np.mean(f1s), "macro_f1_std": np.std(f1s)})
    table = pd.DataFrame(rows).round(3)
    base = table.set_index("features").loc["answers22"]
    table["beats_answers22_on_both"] = (table["accuracy_mean"] > base["accuracy_mean"]) & \
                                       (table["macro_f1_mean"] > base["macro_f1_mean"])
    return table


def main(argv=None):
    p = argparse.ArgumentParser(description="Compare feature sets for the field model")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--repeats", type=int, default=REPEATS)
    args = p.parse_args(argv)
    field_map = load_field_map()
    tidy = load_survey(args.survey)
    tidy = tidy[(tidy["aimed_field"] != NOT_SURE) & tidy["aimed_field"].isin(field_map) & tidy.apply(is_complete, axis=1)]
    counts = tidy["aimed_field"].value_counts()
    tidy = tidy[tidy["aimed_field"].map(counts) >= MIN_CLASS]
    table = compare(tidy, args.repeats)
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "model_features.csv", index=False)
    print(table.to_string(index=False))
    print(f"Wrote {args.out / 'model_features.csv'}")
    return table


if __name__ == "__main__":
    main()
