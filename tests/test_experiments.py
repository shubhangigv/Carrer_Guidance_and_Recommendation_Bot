"""The Phase B experiment scripts run end to end on the tiny fake O*NET data.

These check that the scripts work and that guaranteed properties hold (e.g. the range method can
never inflate a score). The numbers they produce on fake data mean nothing and are not results.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
import masking  # noqa: E402
import self_match  # noqa: E402
import summarise  # noqa: E402
import weight_sensitivity  # noqa: E402
from common import _weighted_pearson, load, perfect_student  # noqa: E402
from fake_onet import add_careers  # noqa: E402
from ml.baseline_recommender import _profile_similarity  # noqa: E402

EXTRA = [("19-0002.00", "Scientist 2", 4, "Investigative", ["Science", "Writing"], ["Biology"]),
         ("15-0001.00", "Analyst", 4, "Investigative", ["Critical Thinking", "Mathematics"], ["Mathematics"]),
         ("29-0001.00", "Clinician", 5, "Social", ["Science", "Speaking"], ["Biology", "Psychology"]),
         ("41-0001.00", "Seller", 2, "Enterprising", ["Persuasion", "Negotiation"], ["Economics and Accounting"])]


@pytest.fixture
def data(onet_dir):
    return load(add_careers(onet_dir, EXTRA))


def test_perfect_student_ratings_are_on_the_1_to_5_scale(data):
    s = perfect_student(data, "19-0001.00")
    assert all(1 <= v <= 5 for v in s["interests"].values())
    for key in ("skills", "subjects"):
        assert all(1 <= a["rating"] <= 5 for a in s[key].values())


def test_weighted_pearson_with_equal_weights_is_plain_pearson(data):
    x = pd.Series({"Science": 5.0, "Writing": 2.0, "Speaking": 3.0, "Mathematics": 1.0})
    table = data["skill_importance"].loc[data["codes"]]
    equal = pd.DataFrame(1.0, index=table.index, columns=table.columns)
    np.testing.assert_allclose(_weighted_pearson(x, table, equal), _profile_similarity(x, table))


def test_self_match_runs(data):
    per_career, summary = self_match.run(data)
    assert len(per_career) == len(data["codes"])
    assert list(summary["method"]) == ["V0", "V1", "V2", "V3"]
    for m in ("V0", "V1", "V2", "V3"):
        assert per_career[f"rank_{m}"].between(1, len(data["codes"])).all()
    assert summary["pct_own_in_top5"].between(0, 100).all()


def test_weight_sensitivity_runs(data):
    result = weight_sensitivity.run(data)
    assert len(result) == 6                                  # 3 components x (+10%, -10%)
    assert result["mean_top5_overlap"].between(0, 1).all()
    assert (result["min_top5_overlap"] <= result["mean_top5_overlap"]).all()


def test_masking_range_method_never_inflates(data):
    result = masking.run(data)
    assert set(result["hidden_rows"]) == {1, 2, 3}
    rng = result[result["method"] == "range"]
    assert (rng["mean_inflation"] <= 0).all()               # low bound is never above the full score
    assert (rng["false_top5_entries"] == 0).all()           # nothing is pushed up by a missing answer
    assert (rng["pct_contains_full"] == 100).all()          # the full score is always inside [low, high]
    assert result.loc[result["method"] == "naive", "top5_overlap_after_follow_ups"].isna().all()


def test_summarise_writes_markdown(data, tmp_path):
    weight_sensitivity.run(data).to_csv(tmp_path / "weight_sensitivity.csv", index=False)
    summarise.main(tmp_path)
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| component | change |" in text and "_Not run yet._" in text
