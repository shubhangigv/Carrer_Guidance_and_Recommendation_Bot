"""Study the survey answers: how reliable are they, and what do students in each field say?

Four questions (counts and averages only; fields with fewer than MIN_GROUP students are pooled as
"Other (small fields)" so that no single student can be picked out):
  1. Answer quality  - how many students gave all 8 skills the same rating ("flat"), how often they rated
                       themselves 4-5, how often "Can't assess" / "Not studied" was used per row.
  2. Branch vs aim   - do students aim for the field they study (Q2 x Q8)?
  3. Profiles        - mean answer per aimed field for all 22 rows, and which rows differ most between fields
                       (eta squared = share of the answer's variance explained by the field; 0 = no difference).
  4. Engine misses   - the engine's Hit@5 for students with flat vs varied skill answers
                       (needs data/processed/hit_rate_per_student.csv from experiments/hit_rate.py).
With ~70 students these are descriptions of this sample, not general findings; differences are not tested.

Reads   data/raw/survey/responses.csv (+ data/processed/hit_rate_per_student.csv if present)
Writes  docs/results/survey/insights.md, insights_by_field.csv, insights_heatmap.png
Run:    python experiments\\survey_insights.py
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.survey import DEFAULT_SURVEY, ANALYSIS_CUTOFF, NOT_SURE, feature_table, load_survey  # noqa: E402

OUT_DIR = ROOT / "docs" / "results" / "survey"
PER_STUDENT = ROOT / "data" / "processed" / "hit_rate_per_student.csv"
MIN_GROUP = 5
SMALL = "Other (small fields)"


def md_table(df):
    rows = [list(df.columns)] + df.astype(str).values.tolist()
    return "\n".join(["| " + " | ".join(map(str, rows[0])) + " |", "|" + "---|" * len(df.columns)]
                     + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def pooled_field(tidy):
    counts = tidy["aimed_field"].value_counts()
    return tidy["aimed_field"].where(tidy["aimed_field"].map(counts) >= MIN_GROUP, SMALL)


def quality(tidy):
    skills = [c for c in tidy.columns if c.startswith("skill:")]
    rated = tidy[skills].apply(lambda r: [v for v in r if isinstance(v, (int, float)) and not pd.isna(v)], axis=1)
    flat = rated.apply(lambda v: len(v) >= 6 and len(set(v)) == 1)
    nums = feature_table(tidy)[[c for c in feature_table(tidy).columns if ":" in c]]
    high = (nums >= 4).sum().sum() / nums.notna().sum().sum()
    special = pd.DataFrame({
        "row": [c for c in tidy.columns if ":" in c],
        "cant_assess_or_blank_%": [round(100 * tidy[c].isin(["cant_assess"]).mean() + 100 * tidy[c].isna().mean(), 1)
                                   for c in tidy.columns if ":" in c],
        "no_experience_or_not_studied_%": [round(100 * tidy[c].isin(["no_experience", "not_studied"]).mean(), 1)
                                           for c in tidy.columns if ":" in c]})
    return flat, high, special


def eta_squared(values, groups):
    ok = values.notna()
    v, g = values[ok].astype(float), groups[ok]
    total = ((v - v.mean()) ** 2).sum()
    between = sum(len(x) * (x.mean() - v.mean()) ** 2 for _, x in v.groupby(g))
    return between / total if total else 0.0


def heatmap(by_field, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 0.55 * len(by_field) + 2.6))
    im = ax.imshow(by_field.to_numpy(dtype=float), cmap="Greens", vmin=1, vmax=5, aspect="auto")
    ax.set_xticks(range(len(by_field.columns)), [c.replace("skill:", "S: ").replace("subject:", "Sub: ")
                                                 for c in by_field.columns], rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(by_field)), by_field.index, fontsize=9)
    for i in range(by_field.shape[0]):
        for j in range(by_field.shape[1]):
            val = by_field.iat[i, j]
            if not pd.isna(val):
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=7, color="white" if val > 3.8 else "black")
    fig.colorbar(im, ax=ax, fraction=0.02, label="mean answer (1-5)")
    ax.set_title("Mean answer by the field students aim for (survey)", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main(argv=None):
    p = argparse.ArgumentParser(description="Study the survey answers")
    p.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    p.add_argument("--first-n", type=int, default=ANALYSIS_CUTOFF,
                   help="use only the first N responses (default: the analysis cut-off; 0 = all)")
    p.add_argument("--per-student", type=Path, default=PER_STUDENT)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--no-charts", action="store_true")
    args = p.parse_args(argv)

    tidy = load_survey(args.survey, first_n=args.first_n or None)
    n = len(tidy)
    flat, high, special = quality(tidy)
    X = feature_table(tidy)

    # 2. branch vs aimed field
    cross = pd.crosstab(tidy["branch"], tidy["aimed_field"])
    small_branches = cross.sum(axis=1) < MIN_GROUP
    cross = pd.concat([cross[~small_branches], cross[small_branches].sum().to_frame("Other branches").T])
    cross = cross[cross.sum(axis=1) > 0]

    # 3. profiles by aimed field
    aimed = tidy[tidy["aimed_field"] != NOT_SURE]
    groups = pooled_field(aimed)
    by_field = X.loc[aimed.index].groupby(groups).mean().round(2)
    by_field.insert(0, "students", groups.value_counts())
    eta = pd.Series({c: eta_squared(X.loc[aimed.index, c], groups) for c in X.columns}).sort_values(ascending=False)

    # 4. engine hits for flat vs varied answers
    engine_lines = []
    if args.per_student.exists():
        ps = pd.read_csv(args.per_student)
        ps = ps[ps["method"].isin(["v2", "v3"])].merge(
            pd.DataFrame({"response_id": tidy["response_id"], "flat": flat.to_numpy()}), on="response_id")
        g = ps.groupby(["method", "flat"])["hit@5"].agg(["size", "mean"]).round(3).reset_index()
        g["flat"] = g["flat"].map({True: "all skills rated the same", False: "varied skill ratings"})
        engine_lines = ["## 4. Engine Hit@5 for flat vs varied skill answers", "",
                        md_table(g.rename(columns={"size": "students", "mean": "hit_at_5"})), ""]

    args.out.mkdir(parents=True, exist_ok=True)
    by_field.to_csv(args.out / "insights_by_field.csv")
    eta.round(3).rename_axis("row").rename("eta_squared").to_csv(args.out / "insights_eta.csv")
    if not args.no_charts:
        heatmap(by_field.drop(columns="students"), args.out / "insights_heatmap.png")
    top_eta = eta.head(8).round(3).reset_index().set_axis(["row", "eta_squared"], axis=1)
    low_eta = eta.tail(5).round(3).reset_index().set_axis(["row", "eta_squared"], axis=1)
    same_field = sum(cross.get(f, pd.Series(0, index=cross.index)).get(b, 0) for b, f in (
        ("Engineering (B.E. / B.Tech)", "Engineering"), ("Computer Applications (BCA)", "IT & Computing"),
        ("Medical / Nursing / Pharmacy", "Healthcare & Medicine")))
    lines = [f"# What the survey answers show ({n} responses)", "",
             "Generated by `experiments/survey_insights.py` - do not edit by hand. Describes this sample only; "
             f"fields with fewer than {MIN_GROUP} students are pooled as \"{SMALL}\".", "",
             "## 1. Answer quality", "",
             f"- {int(flat.sum())} of {n} students ({100 * flat.mean():.1f}%) gave **all their skill ratings the same value**.",
             f"- {100 * high:.1f}% of all numeric skill/subject answers are 4 or 5 (students rate themselves kindly).",
             "- Rows most often answered \"Can't assess\" / blank or \"No experience\" / \"Not studied\":", "",
             md_table(special.sort_values("no_experience_or_not_studied_%", ascending=False).head(6)), "",
             "## 2. Branch (Q2) vs the field students aim for (Q8)", "",
             md_table(cross.reset_index().rename(columns={"index": "branch"})), "",
             f"Students whose branch leads straight to their aimed field (Engineering->Engineering, BCA->IT, "
             f"Medical->Healthcare): {int(same_field)}.", "",
             "## 3. Mean answer by aimed field", "", "![heatmap](insights_heatmap.png)", "",
             md_table(by_field.reset_index().rename(columns={"aimed_field": "field"})), "",
             "Rows that differ MOST between fields (eta squared):", "", md_table(top_eta), "",
             "Rows that differ LEAST:", "", md_table(low_eta), ""] + engine_lines + [
             "Limits: one college, small groups, self-ratings; eta squared describes this sample and is not a test."]
    (args.out / "insights.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return by_field, eta


if __name__ == "__main__":
    main()
