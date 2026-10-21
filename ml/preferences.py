"""Personalised recommendations: the student's areas, course, lifestyle and "not for me" choices.

Engine v3 (ml/recommender_v3.py) scores every career from interests, skills and subjects. On its own it
cannot know WHAT a student wants to work on (computers? animals? law?), what they study, or what life
they want - so results felt random. This file adds those answers on top, in plain, explainable steps:

  1. Pool      careers with Job Zone >= 3 (as before), minus careers the student marked "not for me".
  2. Filters   (only if the student chose them; each filter reports how many careers it removed)
               further_study = "no"  -> Job Zone <= 4 (O*NET Job Zone 5 = extensive preparation,
                                        usually a master's, PhD or medical degree)
               work_setting = "desk" -> leave out careers with outdoor work about weekly or more
                                        (Work Context "Outdoors, Exposed to All Weather Conditions", CX >= 3.5;
                                        scale 1 = never ... 4 = once a week or more ... 5 = every day)
               work_setting = "active" -> leave out careers that sit more than half the time
                                        (Work Context "Spend Time Sitting", CX >= 4; 4 = more than half the time)
               A filter that would leave fewer than MIN_POOL careers is skipped (and reported).
  3. Score     engine v3 on the pool (strongest / weakest skill picks feed its strength fit).
  4. Group     "your areas": the best careers in the areas the student picked (config/areas.csv; if no
               area was picked, the areas linked to their course, config/course_areas.csv), spread across
               the picked areas; then "also worth a look": the best careers elsewhere (field diversity on),
               so a student still sees options outside their own idea.
               No areas and no course: if a field model is available (ml/field_model.py, trained on the
               survey), the field it predicts from the 22 answers fills the first PREDICTED_SLOTS places -
               the cross-validated "hybrid" of experiments/hybrid.py.
  5. Reasons   "In an area you picked", "Linked to your course", "Uses your strength: Programming" (only when
               this career needs that skill more than 75% of careers do AND rates it important, IM >= 3).
  6. Clashes   a career CLASHES with the student when it needs one of their weak points more than 75% of
               careers do and rates it important (IM >= 3) - the same rule as 5. Weak points: skills picked as weakest, and skill/subject rows rated
               1-2 or answered "no experience" / "not studied". Clashing careers go after non-clashing ones in
               every group (order kept otherwise) and, if still shown, say why ("Needs Programming more than
               most careers - you marked it as a weakness").
  Clashing careers never fill places chosen AUTOMATICALLY (predicted field, course areas).
  A skill picked as one of the 2 weakest but RATED 3 or more is scored as 2 ("Weak"): the later, explicit
  choice wins over the rating (the page says so).

No weight or threshold here was tuned on the survey. The survey's Hit@k evaluation does NOT use this
file (it would be circular: a student who picks "Computers & IT" will of course get IT careers).
Sensitive attributes (gender, religion, caste ...) are never used.
"""
import math
from pathlib import Path

import pandas as pd

from ml.baseline_recommender import _read
from ml.recommender_v2 import NONE_YET, RATED, SKILL_MAP_V2, SUBJECT_MAP_V2, diversify, eligible_codes, parse_answer, rank_order
from ml.recommender_v3 import career_row_needs, result_frame, score_all_v3

CONFIG = Path(__file__).resolve().parents[1] / "config"
ALSO_CONSIDER = 3            # places kept for careers outside the student's areas (top 10 -> 7 + 3)
PREDICTED_SLOTS = 3          # predicted field (ml/field_model.py): first 3 places, as evaluated in experiments/hybrid.py
MIN_POOL = 30                # a filter that leaves fewer careers than this is skipped
OUTDOOR_CX = 3.5             # desk filter: outdoor work about weekly or more
SITTING_CX = 4.0             # active filter: sitting more than half the time
STRENGTH_QUANTILE = 0.75     # "uses your strength" only if this career needs that skill more than 75% of careers do
WEAK_RATING = 2              # a picked weakness rated higher than this is scored as this; ratings <= this are weak points
IMPORTANT_IM = 3.0           # ... and the need must also be important in itself (IM >= 3, as for skill gaps in engine v2)
MAX_AREAS, MAX_STRENGTHS, MAX_WEAKNESSES = 3, 3, 2
WORK_SETTINGS = {"desk": "Mostly at a desk / indoors", "active": "Active, on my feet or outdoors", "any": "No preference"}
FURTHER_STUDY = {"no": "No - I want to work after my current degree", "yes": "Yes - a master's, PhD or long degree is fine",
                 "any": "Not sure yet"}
WORK_CONTEXT = {"outdoors": "Outdoors, Exposed to All Weather Conditions", "sitting": "Spend Time Sitting"}


# ---------------------------------------------------------------- config
def load_areas(path=CONFIG / "areas.csv"):
    """Areas a student can pick: key, label, example, prefixes (list of O*NET-SOC code prefixes)."""
    df = pd.read_csv(path, dtype=str).fillna("")
    df["prefixes"] = df["soc_prefixes"].str.split(";").apply(lambda xs: [x.strip() for x in xs if x.strip()])
    return df.set_index("key")


def load_courses(path=CONFIG / "course_areas.csv", areas=None):
    """Courses: key, label, areas (list of area keys). Fails loudly if a course names an unknown area."""
    df = pd.read_csv(path, dtype=str).fillna("")
    df["areas"] = df["areas"].str.split(";").apply(lambda xs: [x.strip() for x in xs if x.strip()])
    known = set((areas if areas is not None else load_areas()).index)
    bad = {k: [a for a in v if a not in known] for k, v in zip(df["key"], df["areas"])}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        raise ValueError(f"config/course_areas.csv names unknown areas: {bad}")
    return df.set_index("key")


def areas_of(code, areas, keys=None):
    """Area keys (from `keys`, default all) whose SOC prefixes match this career code."""
    keys = list(areas.index) if keys is None else keys
    return [k for k in keys if any(str(code).startswith(p) for p in areas.at[k, "prefixes"])]


def add_work_context(data, onet_dir):
    """data["work_context"]: careers x {outdoors, sitting} (CX means, 1-5), if Work Context.txt is usable.
    Column names are checked first; rows with Recommend Suppress = Y are ignored."""
    info = data.setdefault("extras_info", [])
    try:
        wc = _read(onet_dir, "Work Context.txt")
    except FileNotFoundError:
        info.append("Work Context.txt: not found; work-setting filter switched off")
        return data
    need = {"O*NET-SOC Code", "Element Name", "Scale ID", "Data Value"}
    if not need <= set(wc.columns):
        info.append(f"Work Context.txt: columns not usable {list(wc.columns)}; work-setting filter off")
        return data
    if "Recommend Suppress" in wc.columns:
        wc = wc[wc["Recommend Suppress"].fillna("").str.strip().str.upper() != "Y"]
    wc = wc[(wc["Scale ID"] == "CX") & wc["Element Name"].isin(WORK_CONTEXT.values())]
    table = (wc.assign(value=pd.to_numeric(wc["Data Value"], errors="coerce"))
             .pivot_table(index="O*NET-SOC Code", columns="Element Name", values="value", aggfunc="mean"))
    data["work_context"] = table.rename(columns={v: k for k, v in WORK_CONTEXT.items()})
    info.append(f"Work Context.txt: {len(table)} careers with outdoor / sitting ratings (CX)")
    return data


# ---------------------------------------------------------------- checking the student's choices
def clean_profile(profile, areas=None, courses=None):
    """Check and normalise the extra quiz answers. Raises ValueError with a readable message."""
    profile = dict(profile or {})
    areas = load_areas() if areas is None else areas
    courses = load_courses(areas=areas) if courses is None else courses
    out = {"areas": list(dict.fromkeys(profile.get("areas") or [])),
           "course": profile.get("course") or None,
           "strengths": list(dict.fromkeys(profile.get("strengths") or [])),
           "weaknesses": list(dict.fromkeys(profile.get("weaknesses") or [])),
           "work_setting": profile.get("work_setting") or "any",
           "further_study": profile.get("further_study") or "any"}
    if len(out["areas"]) > MAX_AREAS or any(a not in areas.index for a in out["areas"]):
        raise ValueError(f"areas: pick up to {MAX_AREAS} of {list(areas.index)}")
    if out["course"] is not None and out["course"] not in courses.index:
        raise ValueError(f"course: unknown course {out['course']!r}")
    for key, most in (("strengths", MAX_STRENGTHS), ("weaknesses", MAX_WEAKNESSES)):
        if len(out[key]) > most or any(r not in SKILL_MAP_V2 for r in out[key]):
            raise ValueError(f"{key}: pick up to {most} of {list(SKILL_MAP_V2)}")
    if set(out["strengths"]) & set(out["weaknesses"]):
        raise ValueError("a skill cannot be both a strength and a weakness")
    if out["work_setting"] not in WORK_SETTINGS:
        raise ValueError(f"work_setting must be one of {list(WORK_SETTINGS)}")
    if out["further_study"] not in FURTHER_STUDY:
        raise ValueError(f"further_study must be one of {list(FURTHER_STUDY)}")
    return out


# ---------------------------------------------------------------- recommending
def _apply_filters(pool, data, profile, notes):
    def keep(mask_drop, message):
        nonlocal pool
        dropped = pool[mask_drop]
        if len(pool) - len(dropped) < MIN_POOL:
            notes.append(f"{message}: skipped, it would leave too few careers")
        elif len(dropped):
            pool = pool[~mask_drop]
            notes.append(f"{message}: {len(dropped)} careers left out")

    if profile["further_study"] == "no" and "job_zone" in data:
        jz = data["job_zone"].reindex(pool)
        keep((jz >= 5).to_numpy(), "No further study after your degree (careers needing a master's, PhD or medical degree)")
    wc = data.get("work_context")
    if profile["work_setting"] != "any" and wc is None:
        notes.append("Work-setting preference not used: O*NET Work Context data is not loaded")
    elif profile["work_setting"] == "desk":
        out = wc["outdoors"].reindex(pool) if "outdoors" in wc else pd.Series(index=pool, dtype=float)
        keep((out >= OUTDOOR_CX).fillna(False).to_numpy(), "Desk / indoor work (careers outdoors about weekly or more)")
    elif profile["work_setting"] == "active":
        sit = wc["sitting"].reindex(pool) if "sitting" in wc else pd.Series(index=pool, dtype=float)
        keep((sit >= SITTING_CX).fillna(False).to_numpy(), "Active work (careers that sit more than half the time)")
    return pool


def _apply_weakness_picks(student, weaknesses):
    """A skill picked as weakest but rated above WEAK_RATING is scored as WEAK_RATING. Returns (student, lowered rows)."""
    skills, lowered = dict(student.get("skills", {})), []
    for row in weaknesses:
        status, rating = parse_answer(skills.get(row))
        if status == RATED and rating > WEAK_RATING:
            skills[row] = {"rating": WEAK_RATING}
            lowered.append(row)
    return {**student, "skills": skills}, lowered


def _clashes(student, weaknesses, cats):
    """{career code: [weak rows this career needs more than STRENGTH_QUANTILE of careers do]}."""
    weak = []
    for key, mapping, cat in (("skills", SKILL_MAP_V2, "skill"), ("subjects", SUBJECT_MAP_V2, "subject")):
        for row in mapping:
            status, rating = parse_answer(student.get(key, {}).get(row))
            if (cat == "skill" and row in weaknesses) or status in NONE_YET or (status == RATED and rating <= WEAK_RATING):
                weak.append((cat, row, mapping))
    out = {}
    needs = {cat: career_row_needs(cats[cat], mapping) for cat, mapping in
             (("skill", SKILL_MAP_V2), ("subject", SUBJECT_MAP_V2))}
    high = {cat: n.quantile(STRENGTH_QUANTILE) for cat, n in needs.items()}
    for code in needs["skill"].index:
        out[code] = [row for cat, row, _ in weak
                     if row in needs[cat].columns and needs[cat].at[code, row] >= max(high[cat][row], IMPORTANT_IM)]
    return out


def _spread(codes, area_of, n, n_areas):
    """The best n careers, at most ceil(n / n_areas) from each picked area (then fill with the next best)."""
    if n_areas <= 1:
        return list(codes)[:n]
    return diversify(list(codes), area_of, top=n, max_per_field=math.ceil(n / n_areas))[:n]


def personalised(student, data, profile=None, top_n=10, hidden=(), min_job_zone=3, areas=None, courses=None,
                 field_model=None):
    """Top careers for one student, using the extra answers in `profile` (see clean_profile).

    Returns (DataFrame, info). The DataFrame has recommend_v3's columns plus group ("your_areas",
    "also_consider" or "all"), area_keys, course_link and extra_reasons. info = {"notes": [...],
    "chosen_areas": [...], "areas_from": "picked" | "course" | "predicted" | None, "predicted": {...} or None}."""
    areas = load_areas() if areas is None else areas
    courses = load_courses(areas=areas) if courses is None else courses
    profile = clean_profile(profile, areas, courses)
    notes = []
    student, lowered = _apply_weakness_picks(student, profile["weaknesses"])
    if lowered:
        notes.append(f"You picked {', '.join(lowered)} as one of your weakest skills but rated it higher earlier - "
                     f"we used 'Weak' for {'them' if len(lowered) > 1 else 'it'}")
    student = {**student, "strengths": profile["strengths"], "weaknesses": profile["weaknesses"]}

    pool = eligible_codes(data, min_job_zone)
    hidden = set(hidden)
    if hidden:
        pool = pool[~pool.isin(hidden)]
        notes.append(f"{len(hidden)} career(s) you marked 'not for me' are hidden")
    pool = _apply_filters(pool, data, profile, notes)

    table, cats = score_all_v3(student, data, pool)
    clashes = _clashes(student, profile["weaknesses"], cats)
    order = list(rank_order(table))
    order = [c for c in order if not clashes[c]] + [c for c in order if clashes[c]]   # clashing careers last

    course_areas = courses.at[profile["course"], "areas"] if profile["course"] else []
    predicted = None
    if not profile["areas"] and field_model is not None:
        # the field model (answers + branch from the course) beat the fixed course -> areas rule:
        # 74.0% vs 66.7% for the branch alone (experiments/model_features.py)
        branch = (courses.at[profile["course"], "survey_branch"]
                  if profile["course"] and "survey_branch" in courses.columns else None)
        predicted = field_model.predict(student, branch or None)
        extra = pd.DataFrame({"label": [predicted["field"]], "example": [""], "soc_prefixes": [";".join(predicted["prefixes"])],
                              "prefixes": [predicted["prefixes"]]}, index=["_predicted"])
        areas = pd.concat([areas, extra])
        chosen, source = ["_predicted"], "predicted"
    else:
        chosen, source = ((profile["areas"], "picked") if profile["areas"] else
                          (course_areas, "course") if course_areas else ([], None))
    in_area = {c: areas_of(c, areas, chosen) for c in order} if chosen else {}
    if chosen:
        mine = [c for c in order if in_area[c]]
        if source in ("predicted", "course"):          # chosen automatically: never fill with a clash
            mine = [c for c in mine if not clashes[c]]
        rest = [c for c in order if not in_area[c]]
        n_mine = min(len(mine), PREDICTED_SLOTS if source == "predicted" else max(top_n - ALSO_CONSIDER, 1))
        top_mine = _spread(mine, {c: in_area[c][0] for c in mine}, n_mine, len(chosen))
        top = top_mine + diversify(rest, table["field"])[:top_n - len(top_mine)]
        groups = (["your_areas"] * len(top_mine) + ["also_consider"] * (len(top) - len(top_mine)) if top_mine
                  else ["all"] * len(top))
    else:
        top = diversify(order, table["field"])[:top_n]
        groups = ["all"] * len(top)

    out = result_frame(table, cats, top)
    needs = career_row_needs(cats["skill"], SKILL_MAP_V2)
    high_need = needs.quantile(STRENGTH_QUANTILE)            # per skill row, over all careers in the pool
    labels = areas["label"]
    course_label = courses.at[profile["course"], "label"] if profile["course"] else None
    out["group"] = groups
    out["area_keys"] = [areas_of(c, areas, chosen) if chosen else [] for c in top]
    out["area_labels"] = [[labels[k] for k in keys] for keys in out["area_keys"]]
    out["course_link"] = [bool(course_areas and areas_of(c, areas, course_areas)) for c in top]
    extra = []
    for code, keys, linked in zip(top, out["area_keys"], out["course_link"]):
        reasons = []
        if keys and source == "picked":
            reasons.append(f"In an area you picked: {', '.join(labels[k] for k in keys)}")
        elif keys and source == "predicted":
            reasons.append(f"In the field students with answers like yours usually aim for: {predicted['field']}")
        if linked:
            reasons.append(f"Linked to your course: {course_label}")
        strong = [r for r in profile["strengths"] if r in needs.columns
                  and needs.at[code, r] >= max(high_need[r], IMPORTANT_IM)]
        if strong:
            reasons.append(f"Uses your strength{'s' if len(strong) > 1 else ''}: {', '.join(strong)} - "
                           "needed here more than in most careers")
        if clashes[code]:
            reasons.insert(0, "Heads-up: needs " + ", ".join(clashes[code]) + " more than most careers - "
                           "you marked " + ("it" if len(clashes[code]) == 1 else "them") + " as weak")
        extra.append(reasons)
    out["extra_reasons"] = extra
    if source == "course":
        notes.append(f"You did not pick areas, so we used the areas linked to your course ({course_label})")
    if source in ("predicted", "course") and not any(g == "your_areas" for g in groups):
        suggested = predicted["field"] if source == "predicted" else ", ".join(labels[k] for k in chosen)
        notes.append(f"Your answers and course point to {suggested}, but those careers rely on skills or subjects "
                     "you marked as weak, so we did not put them first. Pick areas in the quiz if you still want them.")
    elif source == "predicted":
        notes.append(f"You did not pick areas, so the first {PREDICTED_SLOTS} careers come from the field "
                     f"that survey students with answers{' and a course' if predicted['used_branch'] else ''} "
                     f"like yours aimed for: {predicted['field']} "
                     "(the model's best guess from a small survey). Pick areas in the quiz to choose yourself.")
    return out, {"notes": notes, "chosen_areas": [labels[k] for k in chosen], "areas_from": source,
                 "predicted": predicted}


__all__ = ["FURTHER_STUDY", "WORK_SETTINGS", "add_work_context", "areas_of", "clean_profile", "load_areas",
           "load_courses", "personalised"]
