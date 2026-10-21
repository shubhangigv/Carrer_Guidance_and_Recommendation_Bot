"""B1. Self-match: can each method find a career for a synthetic student copied from that career?

For every rankable career we build a SYNTHETIC "perfect student" from its own O*NET profile
(experiments/common.py: perfect_student) and rank all careers with:
  V0 = v1's Pearson correlation (on the v2 survey rows)
  V1 = importance-weighted Pearson (weights w = (IM - 1) / 4)
  V2 = engine v2 readiness (recommender_v2.score_all_v2)
  V3 = engine v3 = readiness + strength fit, with the app's weights (recommender_v3.score_all_v3)
No Job Zone filter and no diversity re-ranking, so every career can find itself.

This is a consistency check of the scoring formulas, NOT accuracy: real students are not copies of a career.

Run (PowerShell, project root):  python experiments\\self_match.py
Writes docs/results/self_match.csv (one row per career) and docs/results/self_match_summary.csv.
"""
import argparse
from pathlib import Path

import pandas as pd

from common import (DEFAULT_ONET_DIR, DEFAULT_OUT_DIR, correlation_scores, field, load, order,
                    perfect_student, progress, ties_at_top)
from ml.recommender_v2 import score_all_v2
from ml.recommender_v3 import score_all_v3

METHODS = ["V0", "V1", "V2", "V3"]


def scores_for(method, student, data, codes):
    """(score, tie-break) per career for one method."""
    if method in ("V2", "V3"):
        table, _ = (score_all_v2 if method == "V2" else score_all_v3)(student, data, codes)
        return table["match_low"], table["interest_fit"]
    return correlation_scores(student, data, codes, weighted=(method == "V1"))


def run(data, limit=None):
    codes = data["codes"]
    targets = list(codes[:limit] if limit else codes)
    rows = []
    for i, code in enumerate(targets):
        student = perfect_student(data, code)
        row = {"code": code, "career": data["occupations"].loc[code, "Title"], "field": field(code)}
        for m in METHODS:
            score, tie = scores_for(m, student, data, codes)
            ranked = order(score, tie)
            row[f"rank_{m}"] = ranked.index(code) + 1
            row[f"top1_{m}"] = ranked[0]
            row[f"top1_same_field_{m}"] = field(ranked[0]) == field(code)
            row[f"ties_at_top_{m}"] = ties_at_top(score)
        rows.append(row)
        progress(i, len(targets))
    per_career = pd.DataFrame(rows)

    summary = []
    for m in METHODS:
        r = per_career[f"rank_{m}"]
        summary.append({
            "method": m, "n_students": len(per_career), "n_careers_ranked": len(codes),
            "pct_own_in_top5": round(100 * (r <= 5).mean(), 1),
            "pct_own_in_top10": round(100 * (r <= 10).mean(), 1),
            "median_own_rank": float(r.median()),
            "pct_top1_in_own_field": round(100 * per_career[f"top1_same_field_{m}"].mean(), 1),
            "mean_ties_at_top": round(per_career[f"ties_at_top_{m}"].mean(), 2),
            "pct_students_with_tie_at_top": round(100 * (per_career[f"ties_at_top_{m}"] > 1).mean(), 1),
        })
    return per_career, pd.DataFrame(summary)


def main(onet_dir=DEFAULT_ONET_DIR, out_dir=DEFAULT_OUT_DIR, limit=None):
    data = load(onet_dir)
    per_career, summary = run(data, limit)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    per_career.to_csv(out_dir / "self_match.csv", index=False)
    summary.to_csv(out_dir / "self_match_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(f"Saved {out_dir / 'self_match.csv'} and {out_dir / 'self_match_summary.csv'}")
    return per_career, summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--onet-dir", default=DEFAULT_ONET_DIR)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--limit", type=int, default=None, help="only the first N careers (quick test)")
    a = ap.parse_args()
    main(a.onet_dir, a.out_dir, a.limit)
