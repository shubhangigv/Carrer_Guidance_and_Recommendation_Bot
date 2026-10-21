"""Hybrid: an ML model predicts the student's career FIELD, then engine v3 ranks careers inside it.

Why: on the survey, the 6 interest answers barely differ between fields (survey_insights.md), so the
engine - which leans on interests - rarely puts the aimed field first (v3 Hit@1 15.9%). A Logistic
Regression on all 22 answers predicts the aimed field far better (63.5% on 4 fields, ml_compare.csv).
The hybrid uses each for what it is good at:
  1. Logistic Regression (the ml_compare pipeline, no tuning) predicts the field from the 22 answers.
  2. Engine v3 (pre-registered hand weights) ranks all careers as usual.
  3. The top 5 = the engine's best N_FROM_FIELD careers inside the predicted field
                 (config/survey_field_map.csv), then the engine's best others (field diversity on).
N_FROM_FIELD = 3 was fixed before this was run. Nothing else is tuned.

Honest evaluation: repeated stratified 5-fold cross-validation (5 repeats). The model is trained on 4/5
of the students and predicts the other 1/5, so no student's own answer is used to predict their field.
Fields with fewer than MIN_TRAIN students are not learned (the model cannot predict them), but those
students are still evaluated, so the hybrid is not flattered by leaving them out.

Reads   data/raw/survey/responses.csv, O*NET in data/raw/onet/
Writes  docs/results/survey/hybrid.csv (method, k, hit rate, 95% interval)
Run:    python experiments\\hybrid.py
"""
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from hit_rate import random_hit, wilson  # noqa: E402
from ml_compare import models  # noqa: E402
from ml.localise import apply_local_rules  # noqa: E402
from ml.recommender_v2 import diversify, eligible_codes, field_of, load_onet_v2, rank_order  # noqa: E402
from ml.recommender_v3 import HAND_FIT_SHARE, HAND_WEIGHTS, score_all_v3  # noqa: E402
from ml.survey import (DEFAULT_SURVEY, feature_table, in_field, is_complete, load_field_map,  # noqa: E402
                       load_survey, to_student)

ONET_DIR = ROOT / "data" / "raw" / "onet"
OUT_DIR = ROOT / "docs" / "results" / "survey"
KS = (1, 3, 5)
N_FROM_FIELD = 3
MIN_TRAIN = 3
REPEATS = 5
SEED = 42


def engine_orders(tidy, data, codes):
    """Each student's full engine v3 ranking (best first), computed once."""
    out = []
    for i, (_, r) in enumerate(tidy.iterrows(), start=1):
        if i == 1 or i % 10 == 0 or i == len(tidy):
            print(f"  ranking careers for student {i} of {len(tidy)} ...", flush=True)
        table, _ = score_all_v3(to_student(r), data, codes, weights=HAND_WEIGHTS, fit_share=HAND_FIT_SHARE)
        out.append(list(rank_order(table)))
    return out


def hybrid_top(order, prefixes, fields, k=max(KS), n_field=N_FROM_FIELD):
    """Best n_field careers inside the predicted field, then the best others (with field diversity)."""
    inside = [c for c in order if in_field(c, prefixes)][:n_field]
    rest = diversify([c for c in order if c not in set(inside)], fields)
    return (inside + rest)[:k]


def hits(top, prefixes):
    return [float(any(in_field(c, prefixes) for c in top[:k])) for k in KS]


def evaluate(tidy, orders, field_map, fields, repeats=REPEATS):
    from sklearn.model_selection import StratifiedKFold
    X, y = feature_table(tidy), tidy["aimed_field"].to_numpy()
    learnable = pd.Series(y).map(pd.Series(y).value_counts()) >= MIN_TRAIN
    rows = []
    for rep in range(repeats):
        # stratify on learnable fields; students of tiny fields are spread at random but still tested
        strata = np.where(learnable, y, "_small")
        k = int(min(5, pd.Series(strata).value_counts().min())) if (~learnable).sum() >= 2 else 5
        cv = StratifiedKFold(n_splits=max(2, min(5, k)), shuffle=True, random_state=SEED + rep)
        for train, test in cv.split(X, strata):
            fit = train[learnable.to_numpy()[train]]
            model = models()["logreg"]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(X.iloc[fit], y[fit])
                predicted = model.predict(X.iloc[test])
            for idx, pred in zip(test, predicted):
                truth = field_map[y[idx]]
                rows.append({"repeat": rep, "student": idx, "method": "hybrid", "predicted_field": pred,
                             **dict(zip([f"hit@{k}" for k in KS], hits(hybrid_top(orders[idx], field_map[pred], fields), truth)))})
    for idx in range(len(tidy)):                   # the engine alone does not depend on the folds
        truth = field_map[y[idx]]
        rows.append({"repeat": -1, "student": idx, "method": "v3", "predicted_field": None,
                     **dict(zip([f"hit@{k}" for k in KS], hits(diversify(orders[idx], fields)[:max(KS)], truth)))})
    return pd.DataFrame(rows)


def summarise(per, tidy, field_map, pool):
    out = []
    for method, g in per.groupby("method", sort=False):
        per_student = g.groupby("student")[[f"hit@{k}" for k in KS]].mean()   # average over repeats
        n = len(per_student)
        for k in KS:
            rate = per_student[f"hit@{k}"].mean()
            lo, hi = wilson(round(rate * n), n)
            out.append({"method": method, "k": k, "students": n, "hit_rate": round(rate, 3),
                        "ci95_low": round(lo, 3), "ci95_high": round(hi, 3)})
    for k in KS:
        rates = [random_hit(len(pool), sum(in_field(c, field_map[f]) for c in pool), k) for f in tidy["aimed_field"]]
        out.append({"method": "random", "k": k, "students": len(tidy), "hit_rate": round(float(np.mean(rates)), 3),
                    "ci95_low": None, "ci95_high": None})
    return pd.DataFrame(out)


def main(argv=None):
    p = argparse.ArgumentParser(description="Hybrid ML field + engine v3 ranking, cross-validated")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--onet-dir", type=Path, default=ONET_DIR)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--repeats", type=int, default=REPEATS)
    args = p.parse_args(argv)

    field_map = load_field_map()
    tidy = load_survey(args.survey)
    tidy = tidy[tidy["aimed_field"].isin(field_map) & tidy.apply(is_complete, axis=1)].reset_index(drop=True)
    print(f"{len(tidy)} students with an aimed field")
    data = apply_local_rules(load_onet_v2(args.onet_dir), args.onet_dir)
    pool = list(eligible_codes(data, 3))
    fields = pd.Series([field_of(c) for c in pool], index=pool)
    orders = engine_orders(tidy, data, pool)
    per = evaluate(tidy, orders, field_map, fields, args.repeats)
    summary = summarise(per, tidy, field_map, pool)
    acc = per[per["method"] == "hybrid"].assign(
        ok=lambda d: d["predicted_field"].to_numpy() == tidy["aimed_field"].to_numpy()[d["student"]])["ok"].mean()

    args.out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.out / "hybrid.csv", index=False)
    print(summary.to_string(index=False))
    print(f"\nField predicted correctly (held-out, all {len(tidy)} students incl. small fields): {acc:.3f}")
    print(f"Wrote {args.out / 'hybrid.csv'}")
    return summary


if __name__ == "__main__":
    main()
