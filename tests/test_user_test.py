"""Tests for experiments/user_test.py on a SYNTHETIC ratings CSV (no real students)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import user_test  # noqa: E402


def ratings_csv(path):
    rows = []
    # student 1: two assessments - only the latest (2) may count
    rows += [dict(student_id=1, assessment_id=1, career_id=c, rating=1, shown_rank=c, shown_group="all") for c in range(1, 6)]
    rows += [dict(student_id=1, assessment_id=2, career_id=c, rating=5, shown_rank=c,
                  shown_group="your_areas" if c <= 3 else "also_consider") for c in range(1, 6)]
    # student 2: rated only 2 of the top 5 -> not in the per-student measure, still in the pooled one
    rows += [dict(student_id=2, assessment_id=3, career_id=c, rating=r, shown_rank=c, shown_group="all")
             for c, r in ((1, 4), (2, 2), (8, 3))]
    df = pd.DataFrame(rows).assign(model_version="v3", rated_at="2026-10-23 10:00:00")
    df.to_csv(path, index=False)
    return path


def test_user_test_summary(tmp_path):
    summary = user_test.main(["--csv", str(ratings_csv(tmp_path / "r.csv")), "--out", str(tmp_path / "out")])
    assert summary["students"] == 2 and summary["ratings"] == 8               # student 1's old assessment dropped
    assert summary["students_in_top5_measure"] == 1 and summary["mean_top5_share_would_consider"] == 1.0
    assert summary["pooled_top5_share_would_consider"] == pytest.approx(6 / 7, abs=1e-3)
    by_group = pd.read_csv(tmp_path / "out" / "by_group.csv").set_index("shown_group")
    assert by_group.loc["your_areas", "ratings"] == 3 and by_group.loc["also_consider", "mean_rating"] == 5
    assert "Top 5, pooled" in (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")


def test_since_filter_and_empty(tmp_path):
    with pytest.raises(SystemExit, match="No ratings yet"):
        user_test.main(["--csv", str(ratings_csv(tmp_path / "r.csv")), "--since", "2026-11-01",
                        "--out", str(tmp_path / "out")])
