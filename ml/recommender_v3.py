"""Career recommender v3 - engine v2 plus "strength fit" for skills and subjects.

Why v3 exists (found on the real O*NET data and the survey, Oct 2026):
  v2 scores skills and subjects only by READINESS ("do you meet the required level?"). A surplus never
  lowers it, so a student who rates most rows 4 "meets" almost every career: skill readiness was >= 0.99
  for 99% of careers in a test profile. Skills and subjects then cannot tell careers apart, and the
  ranking is decided by the interest score alone (coaches, fire chiefs ... for an Enterprising student).

What v3 adds: STRENGTH FIT, per category (skills, subjects).
  For each survey row (e.g. "Programming"), the career's need = mean O*NET importance (IM) of the row's
  elements. Strength fit = Pearson correlation between the student's row ratings and the career's row
  needs, rescaled to 0..1 - the same idea as the interest fit. It asks "are your STRONGEST rows the
  ones this career relies on MOST?". Because correlation compares shapes:
    * rating every row 4 gives a neutral 0.5 everywhere (no false "good at everything");
    * being great at Programming raises careers where Programming matters most, and lowers careers
      that use none of your strong rows.
  Answers: a rating 1-5 is used as given; no_experience / not_studied count as 1; cant_assess rows
  are left out of the correlation. Fewer than 3 usable rows, or flat answers -> 0.5 (neutral).

  skill part   = (1 - FIT_SHARE) x readiness + FIT_SHARE x strength fit     (same for subjects)
  match        = (0.25 interest + 0.30 skill part + 0.15 subject part) / 0.70 x 100   (v2 weights)
  Ranges, coverage, display rule, follow-ups, diversity and ranking by the lower bound are unchanged from
  v2 (ml/recommender_v2.py): the fit term is the same in the low and high bound, because it only uses
  known answers.

Weights: HAND_* = interest 0.25 / skill 0.30 / subject 0.15, fit share 0.5, chosen BEFORE any survey result
(experiments/hit_rate.py reports them as "v3"). The app uses them too (WEIGHTS = HAND_WEIGHTS): after the
21 Oct fix in career_row_needs, weights tuned by experiments/tune_weights.py (5-fold CV x 5) no longer beat
them on held-out students (CV Hit@1/@5 13.1%/29.9% vs 14.5%/31.9%), so there is no evidence for tuned weights.
Before the fix, tuned weights (0.3/0.4/0.3, fit 0.75) were used; that result was measured on partly ignored data.
"""
import numpy as np
import pandas as pd

from ml.recommender_v2 import (CATEGORIES, NONE_YET, RATED, _critical_names,
                               _follow_ups, diversify, eligible_codes, parse_answer, rank_order,
                               score_all_v2)

MODEL_VERSION = "v3"
HAND_WEIGHTS = {"interest": 0.25, "skill": 0.30, "subject": 0.15}   # pre-registered (= v2's weights)
HAND_FIT_SHARE = 0.5
WEIGHTS = dict(HAND_WEIGHTS)  # what the app uses (tuning did not beat the pre-registered weights, see above)
FIT_SHARE = HAND_FIT_SHARE   # share of strength fit inside the skill and subject parts (rest = readiness)
MIN_FIT_ROWS = 3             # fewer usable rows than this -> neutral fit 0.5
PICK_BONUS = 1.0             # "my 3 strongest skills" +1, "my 2 weakest" -1 (strength fit only, not readiness)


def student_row_values(answers, mapping, strengths=(), weaknesses=()):
    """Survey rows -> the student's value per row. cant_assess / missing rows are left out.

    strengths / weaknesses: rows the student PICKED as strongest / weakest (quiz step "pick your top 3").
    They move the row up or down by PICK_BONUS, so the fit sees a real difference even when the student
    rated most rows the same. A picked row with no rating counts as 5 (strength) or 1 (weakness).
    They never change readiness: "meets the required level" still uses the plain rating."""
    out = {}
    for row in mapping:
        status, rating = parse_answer(answers.get(row))
        if status == RATED:
            out[row] = rating
        elif status in NONE_YET:
            out[row] = 1.0
    for row in mapping:
        if row in strengths:
            out[row] = out[row] + PICK_BONUS if row in out else 5.0
        elif row in weaknesses:
            out[row] = out[row] - PICK_BONUS if row in out else 1.0
    return pd.Series(out, dtype=float)


def career_row_needs(cat_details, mapping):
    """Careers x survey rows: mean importance (IM 1-5) of the row's elements that have an IM value.

    Only IM is needed here. (Until 21 Oct this also required a level (LV), which O*NET sometimes flags as
    unreliable while the importance is fine - e.g. Software Developers' Programming level - so ~1,000
    importance values were wrongly ignored. Readiness still needs both IM and LV.)"""
    im = cat_details["im"]
    cols = {}
    for row, elements in mapping.items():
        present = [e for e in elements if e in im.columns]
        if present:
            cols[row] = im[present].mean(axis=1)
    return pd.DataFrame(cols, index=im.index)


def strength_fit(values, needs):
    """Pearson correlation (rescaled to 0..1) between the student's row values and each career's needs."""
    rows = [r for r in values.index if r in needs.columns]
    if len(rows) < MIN_FIT_ROWS:
        return pd.Series(0.5, index=needs.index)
    s = values[rows]
    t = needs[rows]
    t = t.where(t.notna(), t.mean(axis=1), axis=0)          # missing need -> that career's row mean
    s_c = s - s.mean()
    t_c = t.sub(t.mean(axis=1), axis=0)
    denom = np.sqrt((s_c ** 2).sum()) * np.sqrt((t_c ** 2).sum(axis=1))
    r = (t_c @ s_c) / denom
    r = r.replace([np.inf, -np.inf], np.nan).fillna(0)      # flat answers or flat career -> neutral
    return (r + 1) / 2


def score_all_v3(student, data, codes=None, weights=None, fit_share=FIT_SHARE):
    """Like score_all_v2, plus skill_fit / subject_fit columns; skill_*, subject_* and match_* include the fit."""
    weights = weights or WEIGHTS
    table, cats = score_all_v2(student, data, codes, weights)
    for cat, (mapping, _, _, key) in CATEGORIES.items():
        picks = (student.get("strengths") or [], student.get("weaknesses") or []) if cat == "skill" else ((), ())
        values = student_row_values(student.get(key, {}), mapping, *picks)
        fit = strength_fit(values, career_row_needs(cats[cat], mapping))
        table[f"{cat}_readiness_low"] = table[f"{cat}_low"]
        table[f"{cat}_fit"] = fit
        for bound in ("low", "high"):
            table[f"{cat}_{bound}"] = (1 - fit_share) * table[f"{cat}_{bound}"] + fit_share * fit
    total = sum(weights.values())
    for bound in ("low", "high"):
        table[f"match_{bound}"] = (weights["interest"] * table["interest_fit"]
                                   + weights["skill"] * table[f"skill_{bound}"]
                                   + weights["subject"] * table[f"subject_{bound}"]) / total * 100
    return table, cats


def recommend_v3(student, data, top_n=10, min_job_zone=3, diversity=True, weights=None, fit_share=FIT_SHARE):
    """Top careers for one student. Same columns as recommend_v2, plus skill_fit and subject_fit."""
    table, cats = score_all_v3(student, data, eligible_codes(data, min_job_zone), weights, fit_share)
    order = list(rank_order(table))
    if diversity:
        order = diversify(order, table["field"])
    return result_frame(table, cats, order[:top_n])


def result_frame(table, cats, codes):
    """The output table for the given careers, in the given order (rank 1, 2, 3 ...)."""
    top = table.loc[list(codes)]
    cols = ["interest_fit", "skill_low", "skill_high", "subject_low", "subject_high",
            "skill_fit", "subject_fit", "coverage"]
    return pd.DataFrame({
        "rank": range(1, len(top) + 1),
        "code": top.index,
        "career": top["career"].to_numpy(),
        "field": top["field"].to_numpy(),
        **{c: top[c].round(3).to_numpy() for c in cols},
        "match_low": top["match_low"].round(1).to_numpy(),
        "match_high": top["match_high"].round(1).to_numpy(),
        "critical_unknowns": [_critical_names(cats, c) for c in top.index],
        "display": top["display"].to_numpy(),
        "follow_ups": [_follow_ups(cats, c) if d == "range" else []
                       for c, d in zip(top.index, top["display"])],
    })


__all__ = ["FIT_SHARE", "HAND_FIT_SHARE", "HAND_WEIGHTS", "MODEL_VERSION", "PICK_BONUS", "WEIGHTS",
           "career_row_needs", "recommend_v3", "result_frame", "score_all_v3", "strength_fit"]
