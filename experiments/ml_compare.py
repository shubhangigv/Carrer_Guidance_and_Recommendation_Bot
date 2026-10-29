"""Supervised ML vs the knowledge-based engine: predict the career field a student aims for (survey Q8).

Features: the 22 quiz answers (6 interests, 8 skills, 8 subjects). "No experience"/"Not studied" = 0,
"Can't assess"/blank = missing (filled INSIDE the pipeline from the training folds only).
Label: Q8 aimed field. "Not sure yet" is left out. Fields with fewer than --min-class students are left out
(too few to learn or test); the report must say which and how many.

Models (scikit-learn Pipelines: imputer -> scaler -> model, so nothing leaks from the test fold):
  majority     always predicts the most common field (the floor any model must beat)
  logreg       Logistic Regression, class_weight="balanced"
  forest       Random Forest, class_weight="balanced"
  svm          SVM (RBF kernel), class_weight="balanced"
  xgboost      only if the xgboost package is installed
  engine_v2    NOT trained: the field of the engine's top-1 career (config/survey_field_map.csv);
               evaluated on the same students, so it is directly comparable
  engine_v3    the same with engine v3 and its PRE-REGISTERED hand weights (not the app's weights: those
               were chosen on these students; their fair number is in tuned_weights.json)
Note: the engine can name any of 900 careers in ~10 fields, while the models only choose between the
fields kept here, so this comparison favours the models.
Evaluation: repeated stratified k-fold cross-validation (k = 5, or fewer if a field has fewer students),
5 repeats with fixed seeds. Metrics: accuracy and macro-F1 (each field counts equally) as mean +- std.
No hyper-parameter search: with ~50 students a search would mostly fit noise. Fixed, standard settings.

Writes  docs/results/survey/ml_compare.csv, ml_confusion_<best>.png, ml_feature_importance.csv
Run:    python experiments\\ml_compare.py            (add --onet-dir to change where O*NET is)
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
from ml.localise import apply_local_rules  # noqa: E402
from ml.recommender_v2 import load_onet_v2, recommend_v2  # noqa: E402
from ml.recommender_v3 import HAND_FIT_SHARE, HAND_WEIGHTS, recommend_v3  # noqa: E402
from ml.survey import (DEFAULT_SURVEY, ANALYSIS_CUTOFF, NOT_SURE, feature_table, field_of_code, is_complete,  # noqa: E402
                       load_field_map, load_survey, to_student)

ONET_DIR = ROOT / "data" / "raw" / "onet"
OUT_DIR = ROOT / "docs" / "results" / "survey"
SEED = 42
REPEATS = 5


def models():
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    def pipe(model):
        return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), model)
    out = {"majority": pipe(DummyClassifier(strategy="most_frequent")),
           "logreg": logreg_pipeline(),          # the same pipeline the app's field model uses
           "forest": pipe(RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=SEED)),
           "svm": pipe(SVC(kernel="rbf", class_weight="balanced", C=1.0, random_state=SEED))}
    try:
        from xgboost import XGBClassifier
        out["xgboost"] = pipe(XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1,
                                            random_state=SEED, eval_metric="mlogloss"))
    except ImportError:
        pass
    return out


ENGINES = {
    "engine_v2": lambda s, data: recommend_v2(s, data, top_n=1, min_job_zone=3, diversity=True),
    "engine_v3": lambda s, data: recommend_v3(s, data, top_n=1, min_job_zone=3, diversity=True,
                                              weights=HAND_WEIGHTS, fit_share=HAND_FIT_SHARE),
}


def engine_predictions(tidy, data, field_map):
    """{engine name: the survey field of its top-1 career per student (None if outside every field)}."""
    out = {}
    for name, rank in ENGINES.items():
        print(f"  running {name} for {len(tidy)} students ...", flush=True)
        preds = []
        for _, r in tidy.iterrows():
            top = rank(to_student(r), data)
            preds.append(field_of_code(top["code"].iloc[0], field_map) if len(top) else None)
        out[name] = pd.Series(preds, index=tidy.index)
    return out


def run(X, y, engine_pred=None, repeats=REPEATS):
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.preprocessing import LabelEncoder

    enc = LabelEncoder().fit(y)
    y_num = enc.transform(y)
    k = int(min(5, pd.Series(y).value_counts().min()))
    rows, best_preds = [], {}
    for name, model in models().items():
        print(f"  cross-validating {name} ...", flush=True)
        accs, f1s = [], []
        for rep in range(repeats):
            cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=SEED + rep)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pred = cross_val_predict(model, X, y_num, cv=cv)
            accs.append(accuracy_score(y_num, pred))
            f1s.append(f1_score(y_num, pred, average="macro", zero_division=0))
            if rep == 0:
                best_preds[name] = enc.inverse_transform(pred)
        rows.append({"model": name, "trained": True, "folds": k, "repeats": repeats,
                     "accuracy_mean": np.mean(accs), "accuracy_std": np.std(accs),
                     "macro_f1_mean": np.mean(f1s), "macro_f1_std": np.std(f1s)})
    for name, engine in (engine_pred or {}).items():
        pred = engine.fillna("(outside the survey fields)").to_numpy()
        rows.append({"model": name, "trained": False, "folds": None, "repeats": None,
                     "accuracy_mean": accuracy_score(y, pred), "accuracy_std": 0.0,
                     "macro_f1_mean": f1_score(y, pred, labels=list(enc.classes_), average="macro", zero_division=0),
                     "macro_f1_std": 0.0})
        best_preds[name] = pred
    return pd.DataFrame(rows).round(3), best_preds, list(enc.classes_), k


def confusion_png(y, pred, labels, title, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix
    m = confusion_matrix(y, pred, labels=labels)
    fig, ax = plt.subplots(figsize=(0.7 * len(labels) + 3, 0.6 * len(labels) + 2.5))
    ax.imshow(m, cmap="Greens")
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, m[i, j], ha="center", va="center", fontsize=8, color="black" if m[i, j] < m.max() / 2 else "white")
    ax.set_xlabel("Predicted field")
    ax.set_ylabel("Field the student is aiming for")
    ax.set_title(title, fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def feature_importance(X, y):
    """Random Forest importances on all students (for explanation only, not for evaluation)."""
    model = models()["forest"].fit(X, y)
    forest = model[-1]
    names = model[0].get_feature_names_out(X.columns)
    return (pd.DataFrame({"feature": names, "importance": forest.feature_importances_})
            .sort_values("importance", ascending=False).round(4))


def main(argv=None):
    p = argparse.ArgumentParser(description="ML vs engine on the survey")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--first-n", type=int, default=ANALYSIS_CUTOFF,
                   help="use only the first N responses (default: the analysis cut-off; 0 = all)")
    p.add_argument("--onet-dir", type=Path, default=ONET_DIR)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--min-class", type=int, default=3, help="leave out fields with fewer students than this")
    p.add_argument("--no-engine", action="store_true", help="skip the engine comparison (no O*NET needed)")
    args = p.parse_args(argv)

    tidy = load_survey(args.survey, first_n=args.first_n or None)
    field_map = load_field_map()
    keep = (~tidy["aimed_field"].eq(NOT_SURE)) & tidy["aimed_field"].isin(field_map) & tidy.apply(is_complete, axis=1)
    tidy = tidy[keep]
    counts = tidy["aimed_field"].value_counts()
    small = counts[counts < args.min_class]
    tidy = tidy[~tidy["aimed_field"].isin(small.index)]
    print(f"{int(keep.sum())} students with a chosen field; left out {int(small.sum())} in fields with fewer than "
          f"{args.min_class} students ({dict(small)}); using {len(tidy)} students in {tidy['aimed_field'].nunique()} fields")
    if tidy["aimed_field"].nunique() < 2:
        raise SystemExit("Need at least 2 fields with enough students.")

    X, y = feature_table(tidy), tidy["aimed_field"].to_numpy()
    engine_pred = None
    if not args.no_engine:
        data = apply_local_rules(load_onet_v2(args.onet_dir), args.onet_dir)
        engine_pred = engine_predictions(tidy, data, field_map)
    table, preds, labels, k = run(X, y, engine_pred)

    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "ml_compare.csv", index=False)
    trained = table[table["trained"]]
    best = trained.sort_values("macro_f1_mean", ascending=False)["model"].iloc[0]
    confusion_png(y, preds[best], labels, f"{best}: cross-validated predictions ({len(y)} students)",
                  args.out / f"ml_confusion_{best}.png")
    for name in engine_pred or {}:
        confusion_png(y, preds[name], labels + ["(outside the survey fields)"],
                      f"{name.replace('_', ' ')} top-1 field ({len(y)} students)", args.out / f"ml_confusion_{name}.png")
    feature_importance(X, y).to_csv(args.out / "ml_feature_importance.csv", index=False)
    (args.out / "ml_counts.txt").write_text(
        f"students_used={len(tidy)}\nfields={tidy['aimed_field'].nunique()}\nfolds={k}\nrepeats={REPEATS}\n"
        f"left_out_small_fields={dict(small)}\nfield_counts={dict(tidy['aimed_field'].value_counts())}\n", encoding="utf-8")
    print(table.to_string(index=False))
    print(f"\nBest trained model by macro-F1: {best}. Wrote {args.out / 'ml_compare.csv'}")


if __name__ == "__main__":
    main()
