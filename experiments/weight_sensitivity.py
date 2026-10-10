"""B2. Weight sensitivity: does the top 5 change much if one component weight changes by 10%?

Base weights: interest 0.25, skill 0.30, subject 0.15 (COMPONENT_WEIGHTS). Each weight in turn is
multiplied by 1.1 and by 0.9 (the formula divides by the sum, so the weights are renormalised).
Engine v2 is re-run on the SYNTHETIC self-match students (see self_match.py), without Job Zone filter
and without diversity re-ranking. Top-5 overlap = careers shared with the base top 5, divided by 5.

Run (PowerShell, project root):  python experiments\\weight_sensitivity.py
Writes docs/results/weight_sensitivity.csv.
"""
import argparse
from pathlib import Path

import pandas as pd

from common import (DEFAULT_ONET_DIR, DEFAULT_OUT_DIR, combine, load, order, perfect_student, progress,
                    top5_overlap)
from ml.recommender_v2 import COMPONENT_WEIGHTS, score_all_v2

CHANGES = [(component, factor) for component in COMPONENT_WEIGHTS for factor in (1.1, 0.9)]


def run(data, limit=None):
    codes = data["codes"]
    targets = list(codes[:limit] if limit else codes)
    overlaps = {change: [] for change in CHANGES}
    for i, code in enumerate(targets):
        table, _ = score_all_v2(perfect_student(data, code), data, codes)   # parts computed once
        parts = (table["interest_fit"], table["skill_low"], table["subject_low"])
        base = set(order(combine(*parts), table["interest_fit"])[:5])
        for component, factor in CHANGES:
            weights = dict(COMPONENT_WEIGHTS)
            weights[component] *= factor
            top = set(order(combine(*parts, weights=weights), table["interest_fit"])[:5])
            overlaps[(component, factor)].append(top5_overlap(base, top))
        progress(i, len(targets))
    rows = []
    for (component, factor), values in overlaps.items():
        s = pd.Series(values)
        weights = dict(COMPONENT_WEIGHTS)
        weights[component] *= factor
        total = sum(weights.values())
        rows.append({"component": component, "change": f"{(factor - 1) * 100:+.0f}%",
                     "weights_after_renormalising": ", ".join(f"{k} {v / total:.3f}" for k, v in weights.items()),
                     "n_students": len(s), "mean_top5_overlap": round(s.mean(), 3),
                     "min_top5_overlap": round(s.min(), 3),
                     "pct_identical_top5": round(100 * (s == 1).mean(), 1)})
    return pd.DataFrame(rows)


def main(onet_dir=DEFAULT_ONET_DIR, out_dir=DEFAULT_OUT_DIR, limit=None):
    result = run(load(onet_dir), limit)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "weight_sensitivity.csv", index=False)
    print(result.to_string(index=False))
    print(f"Saved {out_dir / 'weight_sensitivity.csv'}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--onet-dir", default=DEFAULT_ONET_DIR)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--limit", type=int, default=None, help="only the first N careers (quick test)")
    a = ap.parse_args()
    main(a.onet_dir, a.out_dir, a.limit)
