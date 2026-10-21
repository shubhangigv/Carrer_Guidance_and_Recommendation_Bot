"""Build the report's results tables straight from the results files (no number is typed by hand).

Re-run after every new experiment run (e.g. when the survey reaches 100 responses) and copy the tables
into the report. Each table has a caption and a fixed note on what it can and cannot show.

Reads   docs/results/*.csv, docs/results/survey/*.csv|json|md, docs/results/user_test/summary.md (if run)
Writes  docs/report/results_tables.md
Run:    python experiments\\report_tables.py
"""
import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "docs" / "results"
OUT = ROOT / "docs" / "report" / "results_tables.md"


def md(df):
    rows = [list(map(str, df.columns))] + df.astype(str).values.tolist()
    return "\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(df.columns)]
                     + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def pct(x):
    return "" if pd.isna(x) else f"{100 * float(x):.1f}%"


def ci(lo, hi):
    return "" if pd.isna(lo) else f"{100 * float(lo):.1f}-{100 * float(hi):.1f}%"


def read(path):
    return pd.read_csv(path) if path.exists() else None


class Report:
    def __init__(self):
        self.parts, self.n = [], 0

    def table(self, caption, df, note):
        self.n += 1
        self.parts += [f"**Table {self.n}. {caption}**", "", md(df), "", f"*{note}*", ""]

    def missing(self, caption, how):
        self.parts += [f"**{caption}**: not available yet - {how}", ""]


def survey_key_numbers(r):
    path = RES / "survey" / "survey_summary.md"
    if not path.exists():
        return r.missing("Survey key numbers", "run experiments/survey_analysis.py")
    text = path.read_text(encoding="utf-8").splitlines()
    title = next((l for l in text if l.startswith("# ")), "# Survey").lstrip("# ")
    bullets = [l for l in text if l.startswith("- ")][:6]
    r.parts += [f"**Survey key numbers ({title})**", ""] + bullets + ["",
                "*Self-reported answers from one college; the problem statement, not an evaluation.*", ""]


def evaluation(r):
    hit, hyb = read(RES / "survey" / "hit_rate.csv"), read(RES / "survey" / "hybrid.csv")
    tuned = RES / "survey" / "tuned_weights.json"
    if hit is None:
        return r.missing("Hit Rate table", "run experiments/hit_rate.py")
    names = {"random": "Random choice (expected)", "v1": "Engine v1 (correlation)", "v2": "Engine v2 (readiness)",
             "v2_no_div": "Engine v2 without field diversity", "v3": "Engine v3 (readiness + strength fit)",
             "hybrid": "Hybrid: ML field (22 answers) + engine v3", "hybrid_branch": "Hybrid: ML field (answers + branch) + engine v3"}
    rows = []
    frames = [hit] + ([hyb[~hyb["method"].isin(["v3", "random"])]] if hyb is not None else [])
    for df in frames:
        for method, g in df.groupby("method", sort=False):
            g = g.set_index("k")
            rows.append({"Method": names.get(method, method), "Students": int(g["students"].iloc[0]),
                         **{f"Hit@{k}": pct(g.at[k, "hit_rate"]) for k in (1, 3, 5)},
                         "95% CI of Hit@5": ci(g.at[5, "ci95_low"], g.at[5, "ci95_high"])})
    if tuned.exists():
        t = json.loads(tuned.read_text(encoding="utf-8"))
        rows.append({"Method": "Engine v3, weights tuned by CV (held-out)", "Students": t["students"],
                     **{f"Hit@{k}": pct(t["cv_hit_rate"][f"cv_hit@{k}"]) for k in (1, 3, 5)}, "95% CI of Hit@5": ""})
    order = ["Random choice (expected)", "Engine v1 (correlation)", "Engine v2 without field diversity",
             "Engine v2 (readiness)", "Engine v3 (readiness + strength fit)", "Engine v3, weights tuned by CV (held-out)",
             "Hybrid: ML field (22 answers) + engine v3", "Hybrid: ML field (answers + branch) + engine v3"]
    table = pd.DataFrame(rows)
    table["_o"] = table["Method"].map({m: i for i, m in enumerate(order)}).fillna(99)
    r.table("Is the career field a student aims for (survey Q8) among their top-k careers? (Hit Rate@k)",
            table.sort_values("_o").drop(columns="_o"),
            "Students who chose a field; 'Not sure yet' left out. Hybrids are cross-validated (the ML part never saw the "
            "student it predicts). The aimed field is the student's own plan, not a proven fit; one college, small sample. "
            "CI = Wilson 95% interval.")


def ml_vs_engine(r):
    df = read(RES / "survey" / "ml_compare.csv")
    if df is None:
        return r.missing("ML vs engine", "run experiments/ml_compare.py")
    names = {"majority": "Always the most common field", "logreg": "Logistic Regression", "forest": "Random Forest",
             "svm": "SVM (RBF)", "xgboost": "XGBoost", "engine_v2": "Engine v2 top-1 field (not trained)",
             "engine_v3": "Engine v3 top-1 field (not trained)"}
    out = pd.DataFrame({"Model": df["model"].map(lambda m: names.get(m, m)),
                        "Accuracy": [f"{100 * a:.1f}% ± {100 * s:.1f}" if t else f"{100 * a:.1f}%"
                                     for a, s, t in zip(df["accuracy_mean"], df["accuracy_std"], df["trained"])],
                        "Macro-F1": [f"{f:.3f} ± {s:.3f}" if t else f"{f:.3f}"
                                     for f, s, t in zip(df["macro_f1_mean"], df["macro_f1_std"], df["trained"])]})
    counts = (RES / "survey" / "ml_counts.txt")
    extra = ""
    if counts.exists():
        kv = dict(l.split("=", 1) for l in counts.read_text(encoding="utf-8").splitlines() if "=" in l)
        extra = f" {kv.get('students_used', '?')} students in {kv.get('fields', '?')} fields;"
    r.table("Predicting the aimed field: supervised ML vs the knowledge-based engine", out,
            f"Repeated stratified 5-fold cross-validation (mean ± std over 5 repeats);{extra} fields with fewer than 3 "
            "students left out. The models choose between these fields only; the engine ranks ~900 careers, so this "
            "comparison favours the models.")


def features(r):
    df = read(RES / "survey" / "model_features.csv")
    if df is None:
        return r.missing("Feature sets", "run experiments/model_features.py")
    names = {"answers22": "22 quiz answers", "answers22+branch": "22 answers + branch",
             "skills+subjects": "Skills + subjects only (16)", "branch_only": "Branch only"}
    out = pd.DataFrame({"Inputs": df["features"].map(lambda f: names.get(f, f)), "Features": df["n_features"],
                        "Accuracy": df["accuracy_mean"].map(pct), "Macro-F1": df["macro_f1_mean"].round(3)})
    r.table("Which answers predict the aimed field best? (Logistic Regression, same folds)", out,
            "Decision rule fixed before running: switch only if better on both accuracy and macro-F1.")


def survey_study(r):
    df = read(RES / "survey" / "insights_eta.csv")
    if df is None:
        return r.missing("Survey study", "run experiments/survey_insights.py")
    df = df.sort_values("eta_squared", ascending=False)
    show = pd.concat([df.head(5), df.tail(3)])
    show["row"] = show["row"].str.replace("skill:", "Skill: ").str.replace("subject:", "Subject: ")
    r.table("How much each answer differs between aimed fields (eta squared; top 5 and bottom 3)",
            show.rename(columns={"row": "Answer", "eta_squared": "Eta squared"}),
            "Share of an answer's variation explained by the aimed field (0 = none). Describes this sample; not a test.")


def phase_b(r):
    sm, ws, mk = read(RES / "self_match_summary.csv"), read(RES / "weight_sensitivity.csv"), read(RES / "masking.csv")
    if sm is not None:
        names = {"V0": "Pearson (v1 style)", "V1": "Weighted Pearson", "V2": "Engine v2 readiness",
                 "V3": "Engine v3 (readiness + fit)"}
        r.table("Self-match on synthetic students built from each career's own O*NET profile",
                pd.DataFrame({"Method": sm["method"].map(lambda m: names.get(m, m)),
                              "Own career in top 5": sm["pct_own_in_top5"].map(lambda x: f"{x}%"),
                              "In top 10": sm["pct_own_in_top10"].map(lambda x: f"{x}%"),
                              "Median rank": sm["median_own_rank"],
                              "Top-1 in own field": sm["pct_top1_in_own_field"].map(lambda x: f"{x}%")}),
                "A consistency check of the formulas, NOT accuracy: synthetic students are copies of careers. "
                "V3's fit resembles how the synthetic students are built, so V3 is partly favoured.")
    if ws is not None:
        r.table("Weight sensitivity (engine v2): each weight changed by ±10%",
                ws[["component", "change", "mean_top5_overlap", "min_top5_overlap", "pct_identical_top5"]]
                .rename(columns={"component": "Weight", "change": "Change", "mean_top5_overlap": "Mean top-5 overlap",
                                 "min_top5_overlap": "Min overlap", "pct_identical_top5": "% identical top 5"}),
                "Synthetic students; high overlap = the ranking does not hinge on the exact starting weights.")
    if mk is not None:
        r.table("Unanswered questions: dropping unknowns (naive) vs score ranges (engine v2)",
                mk[["hidden_rows", "method", "false_top5_entries", "top5_overlap", "top5_overlap_after_follow_ups"]]
                .rename(columns={"hidden_rows": "Answers hidden", "method": "Method",
                                 "false_top5_entries": "Wrong careers pushed into top 5", "top5_overlap": "Top-5 overlap",
                                 "top5_overlap_after_follow_ups": "Overlap after follow-ups"}).fillna(""),
                "Synthetic students. 0 wrong entries for the range method is guaranteed by its design (ranked by the lower bound).")


def user_test(r):
    path = RES / "user_test" / "summary.md"
    if not path.exists():
        return r.missing("User test", "run the user test (docs/user_test_protocol.md), then experiments/user_test.py")
    text = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    r.parts += ["**User test (students rate their own matches)**", ""] + text + [""]


def main(argv=None):
    p = argparse.ArgumentParser(description="Build docs/report/results_tables.md from the results files")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)
    r = Report()
    r.parts += ["# Results tables (generated)", "",
                "Generated by `experiments/report_tables.py` from the files in `docs/results/` - do not edit by hand; "
                "re-run after any experiment. Copy tables into the report as they are.", "",
                "## 1. The problem (survey)", ""]
    survey_key_numbers(r)
    r.parts += ["## 2. Evaluation on the survey", ""]
    evaluation(r)
    ml_vs_engine(r)
    features(r)
    survey_study(r)
    r.parts += ["## 3. Checks of the scoring formulas (O*NET, synthetic students)", ""]
    phase_b(r)
    r.parts += ["## 4. User test", ""]
    user_test(r)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(r.parts) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} ({r.n} tables)")
    return args.out


if __name__ == "__main__":
    main()
