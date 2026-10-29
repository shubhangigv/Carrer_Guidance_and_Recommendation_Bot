"""Responses that arrived after the analysis cut-off: re-run the main evaluations on ALL responses.

The survey was closed for analysis at ANALYSIS_CUTOFF (87) responses; the report's main results use those.
52 more came in later (139 in total on 29 Oct). Nothing is tuned here: the same scripts, settings and
decision rules are run with --first-n 0 (all responses), and the per-student hits are split into
"first 87" and "later" to show whether the later responses behave differently.

Reads   data/raw/survey/responses.csv, O*NET in data/raw/onet/
Writes  docs/results/survey/later/  hit_rate.csv, ml_compare.csv, model_features.csv, hybrid.csv (+ their extra files),
        batches.csv (engine Hit@k for the first 87 vs the later responses) and batches.txt (counts per batch)
        data/processed/later/hit_rate_per_student.csv (git-ignored)
Run:    python experiments\\later_responses.py
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
import hit_rate  # noqa: E402
import hybrid  # noqa: E402
import ml_compare  # noqa: E402
import model_features  # noqa: E402
from ml.survey import ANALYSIS_CUTOFF, DEFAULT_SURVEY, load_survey  # noqa: E402

OUT_DIR = ROOT / "docs" / "results" / "survey" / "later"
PROCESSED = ROOT / "data" / "processed" / "later"


def batch_table(per_student, cutoff=ANALYSIS_CUTOFF):
    """Engine Hit@k for the first `cutoff` responses vs the later ones (same runs, split afterwards)."""
    d = per_student[per_student["method"].isin(["v1", "v2", "v3"])].copy()
    d["batch"] = d["response_id"].map(lambda i: f"first {cutoff}" if i <= cutoff else "later")
    out = d.groupby(["method", "batch"])[["hit@1", "hit@3", "hit@5"]].mean().round(3)
    out.insert(0, "students", d.groupby(["method", "batch"]).size())
    return out.reset_index()


def batch_counts(tidy, cutoff=ANALYSIS_CUTOFF):
    """Plain counts per batch: responses, aimed fields, flat skill answers (all skill rows the same)."""
    skills = [c for c in tidy.columns if c.startswith("skill:")]
    flat = tidy[skills].apply(lambda r: r.dropna().nunique() <= 1, axis=1)
    lines = [f"cutoff={cutoff}", f"responses_total={len(tidy)}"]
    for name, part in (("first", tidy.index < cutoff), ("later", tidy.index >= cutoff)):
        sub = tidy[part]
        lines += [f"{name}_responses={len(sub)}", f"{name}_flat_skill_pct={100 * flat[part].mean():.1f}",
                  f"{name}_aimed_field={sub['aimed_field'].value_counts().to_dict()}"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="Main evaluations on all responses, incl. those after the cut-off")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--processed", type=Path, default=PROCESSED)
    args = p.parse_args(argv)
    tidy = load_survey(args.survey)
    if len(tidy) <= ANALYSIS_CUTOFF:
        print(f"Only {len(tidy)} responses - nothing after the cut-off of {ANALYSIS_CUTOFF}.")
        return None
    common = ["--survey", str(args.survey), "--first-n", "0", "--out", str(args.out)]
    hit_rate.main(common + ["--processed", str(args.processed)])
    ml_compare.main(common)
    model_features.main(common)
    hybrid.main(common)
    per_student = pd.read_csv(args.processed / "hit_rate_per_student.csv")
    table = batch_table(per_student)
    table.to_csv(args.out / "batches.csv", index=False)
    (args.out / "batches.txt").write_text(batch_counts(tidy), encoding="utf-8")
    print(table.to_string(index=False))
    print(f"Wrote {args.out / 'batches.csv'}")
    return table


if __name__ == "__main__":
    main()
