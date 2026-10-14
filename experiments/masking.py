"""B3. Masking: what happens when a student answers "Can't assess"?

For every SYNTHETIC self-match student (see self_match.py) we hide the 1, 2 and 3 most important
answered survey rows for the student's own career (importance = sum of w = (IM - 1) / 4 over the
row's elements; ties broken randomly with a fixed seed) by setting them to "cant_assess", and compare
two ways of scoring against the result with ALL answers ("full"):

  naive = drop unknown elements from the denominator (what a simple system would do)
  range = engine v2: unknowns stay in the denominator, low/high bounds, rank by the low bound

Measures (all careers ranked, no Job Zone filter, no diversity re-ranking):
  mean_inflation         mean of (score - full score) over all student x career pairs (range: the low bound)
  mean_abs_error         mean of |score - full score|
  false_top5_entries     careers in the top 5 that are not in the full top 5 AND got a higher score than
                         with full answers (pushed up by the missing answer); mean per student
  top5_overlap           careers shared with the full top 5, divided by 5; mean per student
  pct_contains_full      range: % of pairs where low <= full <= high; naive: % where naive == full
  top5_overlap_after_follow_ups   range only: answer the follow-up questions shown for the top 5 with
                         their true values, re-rank, compare with the full top 5

Run (PowerShell, project root):  python experiments\\masking.py
Writes docs/results/masking.csv.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from common import (DEFAULT_ONET_DIR, DEFAULT_OUT_DIR, SEED, combine, load, order, perfect_student,
                    progress, top5_overlap)
from ml.recommender_v2 import CATEGORIES, _follow_ups, rank_order, score_all_v2

KS = (1, 2, 3)
EPS = 1e-9


def rows_by_importance(data, code, student, rng):
    """(category key, row) of the student's answered rows, most important for `code` first."""
    items = []
    for cat, (mapping, im_key, _, key) in CATEGORIES.items():
        im = data[im_key].loc[code]
        for row, elements in mapping.items():
            if student[key].get(row) == "cant_assess":
                continue
            weight = sum(max(0.0, (im[e] - 1) / 4) for e in elements if e in im.index and pd.notna(im[e]))
            items.append((weight, rng.random(), key, row))
    return [(key, row) for _, _, key, row in sorted(items, key=lambda x: (-x[0], x[1]))]


def masked(student, rows):
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in student.items()}
    for key, row in rows:
        out[key][row] = "cant_assess"
    return out


def naive_score(table, cats):
    """Drop unknowns from the denominator. A category with no known element counts as 0.5 (neutral)."""
    return combine(table["interest_fit"], cats["skill"]["naive"].fillna(0.5), cats["subject"]["naive"].fillna(0.5))


def run(data, limit=None):
    codes = data["codes"]
    targets = list(codes[:limit] if limit else codes)
    rng = np.random.default_rng(SEED)
    label = {key: cat for cat, (_, _, _, key) in CATEGORIES.items()}   # "skills" -> "skill"
    acc = {(k, m): {"infl": [], "abs": [], "false": [], "overlap": [], "contains": [], "after": []}
           for k in KS for m in ("naive", "range")}
    for i, code in enumerate(targets):
        full_student = perfect_student(data, code)
        full_table, _ = score_all_v2(full_student, data, codes)
        full = full_table["match_low"]
        full_top = set(order(full, full_table["interest_fit"])[:5])
        ranked_rows = rows_by_importance(data, code, full_student, rng)
        for k in KS:
            hidden = ranked_rows[:k]
            student = masked(full_student, hidden)
            table, cats = score_all_v2(student, data, codes)
            results = {"naive": (naive_score(table, cats), order(naive_score(table, cats), table["interest_fit"])),
                       "range": (table["match_low"], list(rank_order(table)))}
            for method, (score, ranking) in results.items():
                a = acc[(k, method)]
                top = ranking[:5]
                a["infl"].append((score - full).mean())
                a["abs"].append((score - full).abs().mean())
                a["false"].append(sum(1 for c in top if c not in full_top and score[c] > full[c] + EPS))
                a["overlap"].append(top5_overlap(full_top, top))
                if method == "range":
                    inside = (table["match_low"] <= full + EPS) & (full <= table["match_high"] + EPS)
                    a["contains"].append(inside.mean())
                    # The student answers the follow-up questions shown for the top 5 (true values).
                    asked = {lab for c in top if table.loc[c, "display"] == "range" for lab in _follow_ups(cats, c)}
                    still_hidden = [(key, row) for key, row in hidden if f"{label[key]}: {row}" not in asked]
                    answered = masked(full_student, still_hidden)
                    t2, _ = score_all_v2(answered, data, codes)
                    a["after"].append(top5_overlap(full_top, list(rank_order(t2))[:5]))
                else:
                    a["contains"].append(((score - full).abs() < EPS).mean())
        progress(i, len(targets))
    out = []
    for (k, method), a in acc.items():
        out.append({"hidden_rows": k, "method": method, "n_students": len(targets),
                    "mean_inflation": round(float(np.mean(a["infl"])), 3),
                    "mean_abs_error": round(float(np.mean(a["abs"])), 3),
                    "false_top5_entries": round(float(np.mean(a["false"])), 3),
                    "top5_overlap": round(float(np.mean(a["overlap"])), 3),
                    "pct_contains_full": round(100 * float(np.mean(a["contains"])), 1),
                    "top5_overlap_after_follow_ups": round(float(np.mean(a["after"])), 3) if a["after"] else np.nan})
    return pd.DataFrame(out)


def main(onet_dir=DEFAULT_ONET_DIR, out_dir=DEFAULT_OUT_DIR, limit=None):
    result = run(load(onet_dir), limit)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "masking.csv", index=False)
    print(result.to_string(index=False))
    print(f"Saved {out_dir / 'masking.csv'}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--onet-dir", default=DEFAULT_ONET_DIR)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--limit", type=int, default=None, help="only the first N careers (quick test)")
    a = ap.parse_args()
    main(a.onet_dir, a.out_dir, a.limit)
