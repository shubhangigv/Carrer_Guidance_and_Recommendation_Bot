"""Choose engine v3's weights from the survey with 5-fold cross-validation (no test-set tuning).

Why: on the survey, the interest score alone puts the student's aimed field (Q8) in the top 5 for only
~22% of students (random: ~36%), while skill fit and subject fit alone reach ~38-39%. The hand-picked
weights (interest 0.25, skill 0.30, subject 0.15, fit share 0.5) still let interests decide the ranking.

How (honest evaluation):
  1. For every student, the score parts of every career are computed once (interest fit, skill/subject
     readiness, skill/subject strength fit).
  2. Candidate weights: interest/skill/subject on a 0.1 grid that adds up to 1, fit share 0.25-0.75.
     Fit share 1.0 is NOT allowed: readiness must keep some weight, otherwise "can't assess" answers no
     longer give a score range (spec A5) - a design rule fixed before tuning.
  3. 5-fold CV, repeated 5 times: the weights with the best Hit@5 on 4/5 of the students (ties: Hit@1)
     are scored on the held-out 1/5. The average held-out Hit@k is the number to report.
  4. The final weights are then chosen on ALL students (normal practice); their in-sample score is
     optimistic and must not be reported as accuracy - report the CV number.

Reads   data/raw/survey/responses.csv, O*NET in data/raw/onet/
Writes  docs/results/survey/tune_weights.csv (CV result) and tuned_weights.json (final weights)
Run:    python experiments\\tune_weights.py
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.localise import apply_local_rules  # noqa: E402
from ml.recommender_v2 import diversify, eligible_codes, field_of, load_onet_v2  # noqa: E402
from ml.recommender_v3 import score_all_v3  # noqa: E402
from ml.survey import DEFAULT_SURVEY, in_field, is_complete, load_field_map, load_survey, to_student  # noqa: E402

ONET_DIR = ROOT / "data" / "raw" / "onet"
OUT_DIR = ROOT / "docs" / "results" / "survey"
KS = (1, 3, 5)
FIT_SHARES = (0.25, 0.5, 0.75)   # max 0.75: readiness keeps >= 25% so unknown answers still give ranges
SEED = 42


def weight_grid(step=0.1):
    n = round(1 / step)
    for i, s in itertools.product(range(n + 1), range(n + 1)):
        if i + s <= n:
            for f in FIT_SHARES:
                yield {"interest": i / n, "skill": s / n, "subject": (n - i - s) / n, "fit_share": f}


def parts_per_student(tidy, data, codes):
    """One small table per student: the score parts of every career (computed once)."""
    out = []
    for i, (_, r) in enumerate(tidy.iterrows(), start=1):
        if i == 1 or i % 10 == 0 or i == len(tidy):
            print(f"  scoring careers for student {i} of {len(tidy)} ...", flush=True)
        t, _ = score_all_v3(to_student(r), data, codes)
        out.append(t[["interest_fit", "skill_readiness_low", "skill_fit",
                      "subject_readiness_low", "subject_fit"]].to_numpy(dtype=float))
    return out


def top_codes(parts, codes, fields, w, k=max(KS)):
    f = w["fit_share"]
    skill = (1 - f) * parts[:, 1] + f * parts[:, 2]
    subject = (1 - f) * parts[:, 3] + f * parts[:, 4]
    score = w["interest"] * parts[:, 0] + w["skill"] * skill + w["subject"] * subject
    order = [codes[i] for i in np.argsort(-score, kind="stable")[:60]]   # diversity only needs the head
    return diversify(order, fields)[:k]


def hits_table(all_parts, prefixes, codes, fields, grid):
    """hits[g, s, j] = 1 if student s has a field hit in the top KS[j] with weights grid[g]."""
    hits = np.zeros((len(grid), len(all_parts), len(KS)))
    for g, w in enumerate(grid):
        for s, parts in enumerate(all_parts):
            top = top_codes(parts, codes, fields, w)
            for j, k in enumerate(KS):
                hits[g, s, j] = any(in_field(c, prefixes[s]) for c in top[:k])
    return hits


def best(hits, idx):
    mean = hits[:, idx, :].mean(axis=1)                    # grid x KS
    return int(np.lexsort((mean[:, 0], mean[:, -1]))[-1])  # best Hit@5, ties -> Hit@1


def main(argv=None):
    p = argparse.ArgumentParser(description="Cross-validated weights for engine v3")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--onet-dir", type=Path, default=ONET_DIR)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--repeats", type=int, default=5)
    args = p.parse_args(argv)

    field_map = load_field_map()
    tidy = load_survey(args.survey)
    tidy = tidy[tidy["aimed_field"].isin(field_map) & tidy.apply(is_complete, axis=1)].reset_index(drop=True)
    print(f"{len(tidy)} students with an aimed field")
    data = apply_local_rules(load_onet_v2(args.onet_dir), args.onet_dir)
    codes = list(eligible_codes(data, 3))
    fields = pd.Series([field_of(c) for c in codes], index=codes)
    all_parts = parts_per_student(tidy, data, codes)
    prefixes = [field_map[f] for f in tidy["aimed_field"]]

    grid = list(weight_grid())
    print(f"  trying {len(grid)} weight settings ...", flush=True)
    hits = hits_table(all_parts, prefixes, codes, fields, grid)
    default = next(g for g, w in enumerate(grid) if w == {"interest": 0.4, "skill": 0.4, "subject": 0.2,
                                                         "fit_share": 0.5})  # nearest grid point to v3's 0.25/0.30/0.15

    rows = []
    for rep in range(args.repeats):
        for fold, (tr, te) in enumerate(KFold(5, shuffle=True, random_state=SEED + rep).split(tidy)):
            g = best(hits, tr)
            rows.append({"repeat": rep, "fold": fold, **grid[g],
                         **{f"test_hit@{k}": hits[g, te, j].mean() for j, k in enumerate(KS)}})
    cv = pd.DataFrame(rows)
    summary = {f"cv_hit@{k}": round(cv[f"test_hit@{k}"].mean(), 3) for k in KS}
    final = grid[best(hits, np.arange(len(tidy)))]
    print("\nCross-validated (held-out) Hit@k with tuned weights:", summary)
    print("Weights picked per fold (how stable the choice is):")
    print(cv.groupby(["interest", "skill", "subject", "fit_share"]).size().sort_values(ascending=False).head(5).to_string())
    print("Final weights (chosen on all students):", final)

    args.out.mkdir(parents=True, exist_ok=True)
    cv.round(3).to_csv(args.out / "tune_weights.csv", index=False)
    (args.out / "tuned_weights.json").write_text(json.dumps({
        "weights": final, "cv_hit_rate": summary, "students": len(tidy), "folds": 5, "repeats": args.repeats,
        "note": "cv_hit_rate is the honest estimate; the final weights were then chosen on all students"},
        indent=2), encoding="utf-8")
    print(f"Wrote {args.out / 'tuned_weights.json'}")
    return summary, final


if __name__ == "__main__":
    main()
