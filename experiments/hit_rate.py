"""Hit Rate@k: does the career field a student is aiming for (survey Q8) appear among their top-k careers?

For every student who chose a field (not "Not sure yet") and answered all 6 interest rows, each method
ranks the careers exactly as the app does (Job Zone >= 3, careers excluded for India removed):
  v2           engine v2 with field diversity (what the app shows)
  v2_no_div    engine v2 without the field-diversity re-ranking
  v3           engine v3 (v2 + strength fit) with its PRE-REGISTERED hand weights, field diversity
               (the app's CV-tuned weights are evaluated in experiments/tune_weights.py instead)
  v1           engine v1 (correlation; only the numeric answers are used)
  random       expected hit rate if k careers were picked at random from the same pool (exact formula)
A "hit" = at least one of the top-k careers belongs to the student's field (config/survey_field_map.csv,
fixed before any result was computed). 95% confidence intervals: Wilson score interval.

Important limits (write them in the report): Q8 is the field a 1st-3rd year student is AIMING for, not a
proven fit; the sample is small; students are from one college. A high hit rate means the engine agrees
with students' own plans, not that it is "accurate".

Reads   data/raw/survey/responses.csv, O*NET in data/raw/onet/
Writes  docs/results/survey/hit_rate.csv (one row per method and k) and hit_rate_by_field.csv
        data/processed/hit_rate_per_student.csv (git-ignored)
Run:    python experiments\\hit_rate.py
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.baseline_recommender import recommend_v1  # noqa: E402
from ml.localise import apply_local_rules  # noqa: E402
from ml.recommender_v2 import eligible_codes, load_onet_v2, recommend_v2  # noqa: E402
from ml.recommender_v3 import HAND_FIT_SHARE, HAND_WEIGHTS, recommend_v3  # noqa: E402
from ml.survey import (DEFAULT_SURVEY, ANALYSIS_CUTOFF, NOT_SURE, in_field, is_complete, load_field_map,  # noqa: E402
                       load_survey, to_student, to_student_v1)

ONET_DIR = ROOT / "data" / "raw" / "onet"
OUT_DIR = ROOT / "docs" / "results" / "survey"
KS = (1, 3, 5)
MIN_JOB_ZONE = 3


def wilson(hits, n, z=1.96):
    """95% Wilson score interval for a proportion (works well for small n)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def random_hit(pool_size, in_field_count, k):
    """P(at least one of k careers drawn at random without replacement is in the field)."""
    if in_field_count == 0:
        return 0.0
    if pool_size - in_field_count < k:
        return 1.0
    return 1 - math.comb(pool_size - in_field_count, k) / math.comb(pool_size, k)


def evaluate(tidy, data, field_map, ks=KS):
    """Per-student table: one row per student and method with hit@k columns."""
    pool = list(eligible_codes(data, MIN_JOB_ZONE))
    kmax = max(ks)
    rows = []
    for i, (_, r) in enumerate(tidy.iterrows(), start=1):
        if i == 1 or i % 10 == 0 or i == len(tidy):
            print(f"  ranking careers for student {i} of {len(tidy)} ...", flush=True)
        field = r["aimed_field"]
        prefixes = field_map[field]
        tops = {
            "v2": list(recommend_v2(to_student(r), data, top_n=kmax, min_job_zone=MIN_JOB_ZONE, diversity=True)["code"]),
            "v2_no_div": list(recommend_v2(to_student(r), data, top_n=kmax, min_job_zone=MIN_JOB_ZONE, diversity=False)["code"]),
            "v3": list(recommend_v3(to_student(r), data, top_n=kmax, min_job_zone=MIN_JOB_ZONE, diversity=True,
                                    weights=HAND_WEIGHTS, fit_share=HAND_FIT_SHARE)["code"]),
            "v1": list(recommend_v1(to_student_v1(r), data, top_n=kmax, min_job_zone=MIN_JOB_ZONE)["code"]),
        }
        for method, top in tops.items():
            rows.append({"response_id": r["response_id"], "aimed_field": field, "method": method,
                         "top": ";".join(top), **{f"hit@{k}": float(any(in_field(c, prefixes) for c in top[:k])) for k in ks}})
        n_in = sum(in_field(c, prefixes) for c in pool)
        rows.append({"response_id": r["response_id"], "aimed_field": field, "method": "random", "top": "",
                     **{f"hit@{k}": random_hit(len(pool), n_in, k) for k in ks}})
    return pd.DataFrame(rows)


def summarise(per_student, ks=KS):
    out = []
    for method, g in per_student.groupby("method", sort=False):
        n = len(g)
        for k in ks:
            rate = g[f"hit@{k}"].mean()
            lo, hi = wilson(round(rate * n), n) if method != "random" else (float("nan"), float("nan"))
            out.append({"method": method, "k": k, "students": n, "hit_rate": round(rate, 3),
                        "ci95_low": round(lo, 3), "ci95_high": round(hi, 3)})
    return pd.DataFrame(out)


def main(argv=None):
    p = argparse.ArgumentParser(description="Hit Rate@k on the survey")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--first-n", type=int, default=ANALYSIS_CUTOFF,
                   help="use only the first N responses (default: the analysis cut-off; 0 = all)")
    p.add_argument("--onet-dir", type=Path, default=ONET_DIR)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--processed", type=Path, default=ROOT / "data" / "processed",
                   help="where the per-student table is written (git-ignored)")
    args = p.parse_args(argv)

    tidy = load_survey(args.survey, first_n=args.first_n or None)
    field_map = load_field_map()
    n_all = len(tidy)
    unsure = tidy["aimed_field"].eq(NOT_SURE)
    unknown = ~tidy["aimed_field"].isin(list(field_map) + [NOT_SURE])
    incomplete = ~tidy.apply(is_complete, axis=1)
    used = tidy[~unsure & ~unknown & ~incomplete]
    print(f"{n_all} responses: {unsure.sum()} 'Not sure yet' skipped, {unknown.sum()} with an unknown field skipped "
          f"({sorted(tidy.loc[unknown, 'aimed_field'].unique())}), {(incomplete & ~unsure).sum()} with missing interests skipped "
          f"-> {len(used)} students evaluated")
    if used.empty:
        raise SystemExit("No students to evaluate.")

    data = apply_local_rules(load_onet_v2(args.onet_dir), args.onet_dir)
    per_student = evaluate(used, data, field_map)
    summary = summarise(per_student)
    by_field = (per_student[per_student["method"].isin(["v2", "v3"])]
                .pivot_table(index="aimed_field", columns="method", values="hit@5", aggfunc="mean")
                .add_prefix("hit_at_5_").round(3))
    by_field.insert(0, "students", per_student[per_student["method"] == "v2"].groupby("aimed_field").size())
    by_field = by_field.reset_index()

    args.out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.out / "hit_rate.csv", index=False)
    by_field.to_csv(args.out / "hit_rate_by_field.csv", index=False)
    processed = args.processed
    processed.mkdir(parents=True, exist_ok=True)
    per_student.to_csv(processed / "hit_rate_per_student.csv", index=False)
    (args.out / "hit_rate_counts.txt").write_text(
        f"responses={n_all}\nnot_sure_skipped={int(unsure.sum())}\nunknown_field_skipped={int(unknown.sum())}\n"
        f"missing_interests_skipped={int((incomplete & ~unsure).sum())}\nevaluated={len(used)}\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print("\nHit@5 of engines v2 and v3 by field:\n" + by_field.to_string(index=False))
    print(f"\nWrote {args.out / 'hit_rate.csv'}")


if __name__ == "__main__":
    main()
