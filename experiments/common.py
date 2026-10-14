"""Shared helpers for the no-survey experiments (Phase B).

IMPORTANT: every "student" made here is SYNTHETIC - built from a career's own O*NET profile.
These experiments test whether the engine behaves sensibly; they are NOT accuracy results.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.baseline_recommender import RIASEC, _profile_similarity  # noqa: E402
from ml.recommender_v2 import (CATEGORIES, COMPONENT_WEIGHTS, field_of, load_onet_v2,  # noqa: E402
                               parse_answer)

DEFAULT_ONET_DIR = ROOT / "data" / "raw" / "onet"
DEFAULT_OUT_DIR = ROOT / "docs" / "results"
SEED = 42


def load(onet_dir):
    data = load_onet_v2(onet_dir)
    print(f"Loaded {len(data['codes'])} rankable careers from {onet_dir}")
    return data


def perfect_student(data, code):
    """A synthetic student who looks exactly like career `code` in O*NET (spec B1):
    interest = (OI - 1) / 6 * 4 + 1; each skill/subject row = mean over its elements of LV / 7 * 4 + 1,
    clipped to 1-5. A row whose elements all lack a level is "cant_assess"."""
    oi = data["interests"].loc[code, RIASEC].astype(float)
    student = {"interests": ((oi - 1) / 6 * 4 + 1).clip(1, 5).to_dict()}
    for cat, (mapping, _, lv_key, key) in CATEGORIES.items():
        lv = data[lv_key].loc[code]
        answers = {}
        for row, elements in mapping.items():
            values = [lv[e] for e in elements if e in lv.index and pd.notna(lv[e])]
            answers[row] = ({"rating": float(np.clip(np.mean(values) / 7 * 4 + 1, 1, 5))}
                            if values else "cant_assess")
        student[key] = answers
    return student


def combine(interest, skill, subject, weights=None):
    """Match score 0-100 from the three parts (same formula as the engine)."""
    w = weights or COMPONENT_WEIGHTS
    return (w["interest"] * interest + w["skill"] * skill + w["subject"] * subject) / sum(w.values()) * 100


def order(score, tiebreak):
    """Codes best first: score, then tie-break (interest fit), then code - the same rule for every method."""
    df = pd.DataFrame({"s": score, "t": tiebreak, "c": score.index})
    return list(df.sort_values(["s", "t", "c"], ascending=[False, False, True]).index)


def top5_overlap(reference, other):
    """Careers in both top-5 lists divided by 5 (by the list length if fewer than 5 careers exist)."""
    reference, other = set(reference), set(other)
    return len(reference & other) / max(1, len(reference))


def ties_at_top(score):
    """How many careers share the best score (1 = no tie)."""
    return int((np.abs(score - score.max()) < 1e-9).sum())


# ---------------------------------------------------------------- V0 and V1 (correlation baselines)
def _element_vector(answers, mapping):
    """Survey rows -> element values on the 1-5 scale (only rated rows; mean if an element is in 2 rows)."""
    collected = {}
    for row, elements in mapping.items():
        status, rating = parse_answer(answers.get(row))
        if status == "rated":
            for e in elements:
                collected.setdefault(e, []).append(rating)
    return pd.Series({e: np.mean(v) for e, v in collected.items()}, dtype=float)


def _weighted_pearson(x, table, weights):
    """Pearson correlation per career, each element weighted by w = (IM - 1) / 4, rescaled to 0-1."""
    cols = [c for c in x.index if c in table.columns]
    y = table[cols].astype(float)
    w = weights[cols].astype(float).where(y.notna(), 0.0).fillna(0.0)
    y = y.fillna(0.0)
    xv = x[cols].to_numpy()
    sw = w.sum(axis=1).replace(0, np.nan)
    mx = (w * xv).sum(axis=1) / sw
    my = (w * y).sum(axis=1) / sw
    dx = pd.DataFrame(xv[None, :] - mx.to_numpy()[:, None], index=y.index, columns=cols)   # x - mean_x, per career
    dy = y.sub(my, axis=0)
    cov = (w * dx * dy).sum(axis=1)
    denom = np.sqrt((w * dx ** 2).sum(axis=1) * (w * dy ** 2).sum(axis=1))
    r = (cov / denom).replace([np.inf, -np.inf], np.nan).fillna(0)
    return (r + 1) / 2


def correlation_scores(student, data, codes, weighted=False, weights=None):
    """V0 (weighted=False): v1's Pearson method on the v2 survey rows.
    V1 (weighted=True): the same, but each element weighted by its importance for that career.
    Returns (match score, interest part) per career."""
    interest = _profile_similarity(pd.Series(student["interests"])[RIASEC], data["interests"].loc[codes])
    parts = {}
    for cat, (mapping, im_key, _, key) in CATEGORIES.items():
        x = _element_vector(student.get(key, {}), mapping)
        table = data[im_key].loc[codes]
        if weighted:
            parts[cat] = _weighted_pearson(x, table, ((table - 1) / 4).clip(lower=0))
        else:
            parts[cat] = _profile_similarity(x, table)
    return combine(interest, parts["skill"], parts["subject"], weights), interest


def progress(i, n, every=100):
    if (i + 1) % every == 0 or i + 1 == n:
        print(f"  {i + 1}/{n} synthetic students done")


def field(code):
    return field_of(code)
