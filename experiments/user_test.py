"""User test: how do students rate their OWN matches? ("Would you consider this career?" 1-5)

Why: the survey Hit@k test cannot judge the personalised app (a student who picks "Computers & IT" will of
course get IT careers). So real students take the quiz in the app and rate each of their matches 1-5.
The app stores each rating with the position (1-10) and group the career had (table career_rating).

Reported (counts and averages only, no names or emails):
  * by position 1-10: number of ratings, mean rating, share rated 4-5 ("would consider")
  * by group: "your_areas" (the areas the student picked) vs "also_consider" (outside them)
  * per student: share of their rated top-5 careers rated 4-5 (students who rated >= 3 of their top 5),
    then the mean over students; plus the pooled share with a 95% Wilson interval
Only each student's LATEST rated assessment counts (a student who retook the quiz counts once).

Leave out the team's own test accounts with --exclude-emails and test runs before the real test with
--since. Say in the report how students were recruited and how many took part: a handful of volunteers
from one college is a small, self-selected sample, so the result is indicative, not general.

Reads   MySQL (settings from .env) - or --csv with the same columns as career_rating (for tests)
Writes  docs/results/user_test/by_rank.csv, by_group.csv, summary.md
Run:    python experiments\\user_test.py --since 2026-10-22 --exclude-emails me@x.com,friend@y.com
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "docs" / "results" / "user_test"
GOOD = 4                     # a rating of 4 or 5 = "would consider"
MIN_TOP5_RATED = 3           # a student counts in the per-student top-5 measure if they rated >= 3 of their top 5


def wilson(hits, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def read_mysql(since=None, exclude_emails=()):
    from sqlalchemy import text
    from backend.db import get_engine
    sql = """SELECT r.student_id, r.assessment_id, r.career_id, r.rating, r.shown_rank, r.shown_group,
                    r.model_version, r.rated_at
             FROM career_rating r JOIN student s ON s.student_id = r.student_id
             WHERE (:since IS NULL OR r.rated_at >= :since)"""
    with get_engine().connect() as conn:
        df = pd.read_sql(text(sql), conn, params={"since": since})
        if exclude_emails:
            ids = pd.read_sql(text("SELECT student_id, email FROM student"), conn)
            drop = set(ids.loc[ids["email"].str.lower().isin([e.lower() for e in exclude_emails]), "student_id"])
            df = df[~df["student_id"].isin(drop)]
    return df


def latest_only(df):
    """Keep each student's latest rated assessment."""
    last = df.groupby("student_id")["assessment_id"].transform("max")
    return df[df["assessment_id"] == last]


def analyse(df):
    df = latest_only(df).copy()
    df["good"] = df["rating"] >= GOOD
    by_rank = (df.groupby("shown_rank").agg(ratings=("rating", "size"), mean_rating=("rating", "mean"),
                                            share_would_consider=("good", "mean")).round(3).reset_index())
    by_group = (df.groupby("shown_group").agg(ratings=("rating", "size"), students=("student_id", "nunique"),
                                              mean_rating=("rating", "mean"), share_would_consider=("good", "mean"))
                .round(3).reset_index())
    top5 = df[df["shown_rank"] <= 5]
    per_student = top5.groupby("student_id").agg(rated=("good", "size"), good=("good", "mean"))
    per_student = per_student[per_student["rated"] >= MIN_TOP5_RATED]
    lo, hi = wilson(int(top5["good"].sum()), len(top5))
    summary = {"students": int(df["student_id"].nunique()), "ratings": len(df),
               "students_in_top5_measure": len(per_student),
               "mean_top5_share_would_consider": round(per_student["good"].mean(), 3) if len(per_student) else None,
               "pooled_top5_share_would_consider": round(top5["good"].mean(), 3) if len(top5) else None,
               "pooled_top5_ci95": (round(lo, 3), round(hi, 3)), "mean_rating_all": round(df["rating"].mean(), 2),
               "model_versions": sorted(df["model_version"].unique())}
    return by_rank, by_group, summary


def md_table(df):
    """A Markdown table without extra packages."""
    rows = [list(df.columns)] + df.astype(str).values.tolist()
    return "\n".join(["| " + " | ".join(map(str, r)) + " |" for r in rows[:1]]
                     + ["|" + "---|" * len(df.columns)]
                     + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def write(out, by_rank, by_group, summary):
    out.mkdir(parents=True, exist_ok=True)
    by_rank.to_csv(out / "by_rank.csv", index=False)
    by_group.to_csv(out / "by_group.csv", index=False)
    lines = ["# User test: students rate their own matches", "",
             "Generated by `experiments/user_test.py` - do not edit by hand. \"Would consider\" = rating 4 or 5.", "",
             f"- Students: {summary['students']} (latest quiz each), ratings: {summary['ratings']}, "
             f"engine: {', '.join(summary['model_versions'])}",
             f"- Top 5, pooled: {summary['pooled_top5_share_would_consider']} would consider "
             f"(95% CI {summary['pooled_top5_ci95'][0]}-{summary['pooled_top5_ci95'][1]})",
             f"- Top 5, mean per student ({summary['students_in_top5_measure']} students who rated >= {MIN_TOP5_RATED} "
             f"of their top 5): {summary['mean_top5_share_would_consider']}",
             f"- Mean rating over all rated matches: {summary['mean_rating_all']}", "",
             "## By position", "", md_table(by_rank), "", "## By group", "",
             md_table(by_group), "",
             "Limits: small, self-selected sample from one college; students rate their own results, which they "
             "may judge kindly; a rating is an intention, not a career outcome."]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description="Analyse the students' ratings of their own matches")
    p.add_argument("--csv", type=Path, help="read ratings from this CSV instead of MySQL")
    p.add_argument("--since", help="only ratings on or after this date, e.g. 2026-10-22")
    p.add_argument("--exclude-emails", default="", help="comma-separated team/test accounts to leave out")
    p.add_argument("--out", type=Path, default=OUT_DIR)
    args = p.parse_args(argv)
    emails = [e.strip() for e in args.exclude_emails.split(",") if e.strip()]
    if args.csv:
        df = pd.read_csv(args.csv)
        if args.since:
            df = df[pd.to_datetime(df["rated_at"]) >= pd.Timestamp(args.since)]
    else:
        df = read_mysql(args.since, emails)
    if df.empty:
        raise SystemExit("No ratings yet. Students rate their matches on the 'My matches' page (1-5 under each career).")
    by_rank, by_group, summary = analyse(df)
    write(args.out, by_rank, by_group, summary)
    print(by_rank.to_string(index=False), "\n", by_group.to_string(index=False), "\n", summary, sep="")
    print(f"Wrote {args.out / 'summary.md'}")
    return summary


if __name__ == "__main__":
    main()
