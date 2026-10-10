"""Career recommender v2 - readiness scores, honest ranges for unknown answers, field diversity.

What changed from v1 (ml/baseline_recommender.py) and why:
  * Inputs match the survey: 6 interests, 8 skill rows, 8 subject rows. A skill/subject can be
    answered with a rating 1-5, "no_experience" / "not_studied", or "cant_assess" (don't know).
  * Skills and subjects use READINESS instead of correlation: "how much of what this career needs
    do you already have?" Being better than required never lowers the score.
  * An unknown answer gives a score RANGE (low..high) instead of a guess. Careers are ranked by the
    LOW end, so not answering can never push a career up.
  * At most 2 careers from the same field in the top 5.

The full spec is in CLAUDE.md, section "Design decisions v2" (items A1-A9).
"""
import numpy as np
import pandas as pd

from ml.baseline_recommender import (RIASEC, SOC_MAJOR_GROUPS, _profile_similarity, _read,
                                     load_from_mysql, load_onet)

# ---------------------------------------------------------------- settings (change here, not in the code)
COMPONENT_WEIGHTS = {"interest": 0.25, "skill": 0.30, "subject": 0.15}   # rescaled to add up to 1

SCORE_MAX_UNKNOWN = 0.20     # unknown share <= 20% and no critical unknown -> show one score
RANGE_MAX_UNKNOWN = 0.50     # unknown share <= 50% -> show a range; above -> withhold the score
CRITICAL_IM = 4.0            # an unknown element this important (IM >= 4) always forces a range
MAX_FOLLOW_UPS = 3           # follow-up questions shown with a range

DIVERSITY_TOP = 5            # the top 5 ...
MAX_PER_FIELD = 2            # ... holds at most 2 careers of the same field

GAP_MIN_IM = 3.0             # a skill gap is shown when the element's importance >= 3 ...
GAP_MIN = 0.5                # ... and the gap is more than 0.5 levels (0-7 scale)
QUESTION_MIN_IM = 3.0        # target_career asks about rows with an element of importance >= 3
REASON_MIN_RATING = 4        # a skill/subject reason needs the student's rating >= 4 ...
REASON_MIN_IM = 3.5          # ... and the element's importance >= 3.5 for this career
REASON_MIN_INTEREST = 3.5    # an interest reason needs the student's interest >= 3.5
INTEREST_FIT_STRONG = 0.65   # interest fit labels used by target_career
INTEREST_FIT_OK = 0.50

# Answer types
RATED, NO_EXPERIENCE, NOT_STUDIED, CANT_ASSESS = "rated", "no_experience", "not_studied", "cant_assess"
NONE_YET = {NO_EXPERIENCE, NOT_STUDIED}          # known answer: level 0 ("start from scratch")

# Survey rows (Q6 and Q7) -> O*NET element names. A merged row gives its answer to every element.
SKILL_MAP_V2 = {
    "Mathematics": ["Mathematics"],
    "Programming": ["Programming"],
    "Problem Solving": ["Complex Problem Solving", "Critical Thinking"],
    "Research": ["Science", "Active Learning"],
    "Communication": ["Speaking", "Active Listening"],
    "Writing": ["Writing", "Reading Comprehension"],
    "Leadership": ["Coordination", "Persuasion", "Negotiation", "Management of Personnel Resources"],
    "Technical/Practical Skills": ["Troubleshooting", "Repairing", "Equipment Maintenance",
                                   "Operation and Control"],
}
SUBJECT_MAP_V2 = {
    "Mathematics": ["Mathematics"],
    "Physics/Chemistry": ["Physics", "Chemistry"],
    "Biology": ["Biology"],
    "Computer Science": ["Computers and Electronics"],
    "Commerce/Economics": ["Economics and Accounting"],
    "Languages": ["English Language", "Foreign Language"],
    "Social Sciences": ["Sociology and Anthropology", "Psychology", "History and Archeology", "Geography"],
    "Arts/Design": ["Fine Arts", "Design"],
}

# category -> (survey map, importance table, level table, key in the student dict)
CATEGORIES = {
    "skill": (SKILL_MAP_V2, "skill_importance", "skill_level", "skills"),
    "subject": (SUBJECT_MAP_V2, "knowledge_importance", "knowledge_level", "subjects"),
}


def field_of(code):
    """Career field = SOC major group, the first 2 digits of the O*NET-SOC code."""
    return SOC_MAJOR_GROUPS.get(str(code)[:2], "Other")


# ---------------------------------------------------------------- loading
def check_maps(data, verbose=True):
    """List mapped element names that are missing from the loaded O*NET tables (should be none)."""
    missing = {}
    for cat, (mapping, im_key, lv_key, _) in CATEGORIES.items():
        names = {e for elements in mapping.values() for e in elements}
        missing[cat] = sorted(n for n in names
                              if n not in data[im_key].columns or n not in data[lv_key].columns)
        if verbose and missing[cat]:
            print(f"WARNING: {cat} elements not found in O*NET: {missing[cat]}")
    return missing


def add_extras(data, onet_dir):
    """Add optional tables if their files exist and have usable columns:
      data["related"]    - Related Occupations.txt  (code, related_code, order)
      data["alt_titles"] - other job titles per career, for search
    Column names are checked first (O*NET 31.0 renamed files); unusable files are skipped
    with a message in data["extras_info"] instead of failing."""
    info = []
    try:
        rel = _read(onet_dir, "Related Occupations.txt")
        related_cols = [c for c in rel.columns if "related" in c.lower() and "code" in c.lower()]
        if "O*NET-SOC Code" in rel.columns and related_cols:
            table = pd.DataFrame({"code": rel["O*NET-SOC Code"], "related_code": rel[related_cols[0]]})
            table["order"] = pd.to_numeric(rel["Index"], errors="coerce") if "Index" in rel.columns \
                else range(len(rel))
            data["related"] = table.sort_values(["code", "order"]).reset_index(drop=True)
            info.append(f"Related Occupations.txt: used columns 'O*NET-SOC Code', '{related_cols[0]}'")
        else:
            info.append(f"Related Occupations.txt: columns not usable {list(rel.columns)}; using nearest profiles")
    except FileNotFoundError:
        info.append("Related Occupations.txt: not found; using nearest profiles")

    titles = []
    for filename in ("Alternate Titles.txt", "Job Titles.txt", "Sample of Reported Titles.txt"):
        try:
            df = _read(onet_dir, filename)
        except FileNotFoundError:
            continue
        cols = [c for c in df.columns if "title" in c.lower()]
        if "O*NET-SOC Code" not in df.columns or not cols:
            info.append(f"{filename}: no title columns, skipped ({list(df.columns)})")
            continue
        for col in cols:
            titles.append(df[["O*NET-SOC Code", col]].set_axis(["code", "title"], axis=1))
        info.append(f"{filename}: title columns {cols}")
    if titles:
        alt = pd.concat(titles).dropna().drop_duplicates()
        own = data["occupations"]["Title"]
        alt = alt[alt["title"] != alt["code"].map(own)]           # drop the career's own title
        data["alt_titles"] = alt.groupby("code")["title"].apply(list)
    data["extras_info"] = info
    return data


def load_onet_v2(onet_dir):
    """load_onet() (Recommend Suppress rows already dropped) plus the optional extra tables."""
    return add_extras(load_onet(onet_dir), onet_dir)


# ---------------------------------------------------------------- reading the student's answers
def parse_answer(answer):
    """One survey answer -> (status, rating). Accepts {"rating": 4}, 4, "no_experience",
    "not_studied", "cant_assess" (also "Can't assess" etc.). None / missing = cant_assess."""
    if answer is None:
        return CANT_ASSESS, None
    if isinstance(answer, dict):
        if answer.get("rating") is not None:
            return parse_answer(answer["rating"])
        return parse_answer(answer.get("status"))
    if isinstance(answer, (int, float, np.number)) and not isinstance(answer, bool):
        if not 1 <= float(answer) <= 5:
            raise ValueError(f"rating must be between 1 and 5, got {answer}")
        return RATED, float(answer)
    key = str(answer).strip().lower().replace("'", "").replace(" ", "_")
    key = {"cant_assess": CANT_ASSESS, "cannot_assess": CANT_ASSESS, "no_experience": NO_EXPERIENCE,
           "not_studied": NOT_STUDIED, "rated": None}.get(key, "?")
    if key == "?" or key is None:
        raise ValueError(f"unknown answer {answer!r}")
    return key, None


def _element_answers(answers, mapping):
    """Survey rows -> one line per O*NET element: known?, level L (0-7), start from scratch?, rows.
    Missing rows count as unknown. An element in two rows uses the mean of its known levels."""
    collected = {}
    for row, elements in mapping.items():
        status, rating = parse_answer(answers.get(row))
        for e in elements:
            collected.setdefault(e, []).append((row, status, rating))
    out = {}
    for e, items in collected.items():
        known = [(s, 0.0 if s in NONE_YET else (r - 1) / 4 * 7) for _, s, r in items if s != CANT_ASSESS]
        out[e] = {"known": bool(known),
                  "level": float(np.mean([lv for _, lv in known])) if known else 0.0,
                  "scratch": bool(known) and all(s in NONE_YET for s, _ in known),
                  "rows": [row for row, _, _ in items]}
    return pd.DataFrame.from_dict(out, orient="index")


def _row_status(answers, row):
    return parse_answer(answers.get(row))[0]


# ---------------------------------------------------------------- scoring
def _category(answers, data, cat, codes):
    """Readiness of every career in `codes` for one category (skills or subjects).

    w     = (IM - 1) / 4                 how much the element matters (0..1)
    L     = (rating - 1) / 4 * 7         student level on O*NET's 0-7 scale (0 for no experience)
    met   = 1 - max(0, LV - L) / 7       1 = requirement met; a surplus never lowers it
    low   = unknown element -> L = 0     (worst case)
    high  = unknown element -> met = 1   (best case)
    readiness = sum(w * met) / sum(w)    unknowns always stay in the denominator
    """
    mapping, im_key, lv_key, _ = CATEGORIES[cat]
    order = list(dict.fromkeys(e for elements in mapping.values() for e in elements))
    elements = [e for e in order if e in data[im_key].columns and e in data[lv_key].columns]
    ans = _element_answers(answers, mapping).loc[elements]
    im = data[im_key].reindex(index=codes, columns=elements).astype(float)
    lv = data[lv_key].reindex(index=codes, columns=elements).astype(float)
    valid = im.notna() & lv.notna()          # an element counts only if both IM and LV exist
    w = ((im - 1) / 4).clip(lower=0).where(valid, 0.0)
    known = ans["known"].astype(bool)

    met_low = 1 - lv.fillna(0).sub(ans["level"], axis=1).clip(lower=0) / 7
    met_high = met_low.copy()
    met_high.loc[:, ~known.to_numpy()] = 1.0
    sum_w = w.sum(axis=1)
    known_w = w.loc[:, known.to_numpy()].sum(axis=1)
    safe = sum_w.replace(0, np.nan)
    low = ((w * met_low).sum(axis=1) / safe).fillna(1.0)       # nothing required -> fully ready
    high = ((w * met_high).sum(axis=1) / safe).fillna(1.0)
    # "naive" = drop unknowns from the denominator. NOT used for ranking; only for experiments/masking.py.
    known_cols = known.to_numpy()
    naive = ((w * met_low).loc[:, known_cols].sum(axis=1) / known_w.replace(0, np.nan))

    gain = w * (met_high - met_low)                            # how much each unknown could add
    row_gain = pd.DataFrame({row: gain[[e for e in els if e in elements]].sum(axis=1)
                             for row, els in mapping.items()}, index=codes)
    critical = (im >= CRITICAL_IM) & valid & ~known.to_numpy()
    return {"low": low, "high": high, "naive": naive, "sum_w": sum_w, "known_w": known_w,
            "row_gain": row_gain, "critical": critical, "answers": ans,
            "im": im, "lv": lv, "valid": valid, "w": w}


def eligible_codes(data, min_job_zone=None):
    """Careers that can be ranked (interest + skill + knowledge data), optionally Job Zone >= min."""
    codes = data["codes"]
    if min_job_zone is not None and "job_zone" in data:
        jz = data["job_zone"].reindex(codes)
        codes = codes[(jz >= min_job_zone).to_numpy()]
    return codes


def _check_interests(student):
    interests = pd.Series(student["interests"], dtype=float)
    missing = [t for t in RIASEC if t not in interests.index or pd.isna(interests[t])]
    if missing:
        raise ValueError(f"interests must include all 6 RIASEC types; missing {missing}")
    if not interests[RIASEC].between(1, 5).all():
        raise ValueError("interest ratings must be between 1 and 5")
    return interests[RIASEC]


def display_rule(unknown_share, n_critical):
    """How to show a score (A6). Works on single numbers or whole columns.
    <= 20% unknown and no critical unknown -> "score"; up to 50% or any critical -> "range"; else "withheld"."""
    unknown = np.asarray(unknown_share, dtype=float)
    eps = 1e-9                                   # 0.2 computed as 0.2000000001 still counts as 20%
    out = np.where(unknown > RANGE_MAX_UNKNOWN + eps, "withheld",
                   np.where((unknown > SCORE_MAX_UNKNOWN + eps) | (np.asarray(n_critical) > 0), "range", "score"))
    return out if out.ndim else str(out)


def score_all_v2(student, data, codes=None, weights=None):
    """Score every career in `codes` (default: all rankable). Not sorted, not rounded.

    Returns (table, details): table has one row per career; details holds the per-category
    results that follow-ups, explanations and experiments need."""
    weights = weights or COMPONENT_WEIGHTS
    codes = data["codes"] if codes is None else pd.Index(codes)
    interest = _profile_similarity(_check_interests(student), data["interests"].loc[codes])
    cats = {cat: _category(student.get(key, {}), data, cat, codes)
            for cat, (_, _, _, key) in CATEGORIES.items()}
    sk, su = cats["skill"], cats["subject"]

    total = sum(weights.values())
    def combine(skill, subject):
        return (weights["interest"] * interest + weights["skill"] * skill
                + weights["subject"] * subject) / total * 100

    all_w = sk["sum_w"] + su["sum_w"]
    coverage = ((sk["known_w"] + su["known_w"]) / all_w.replace(0, np.nan)).fillna(1.0)
    n_critical = sk["critical"].sum(axis=1) + su["critical"].sum(axis=1)
    display = display_rule(1 - coverage, n_critical)
    table = pd.DataFrame({
        "career": data["occupations"]["Title"].reindex(codes).to_numpy(),
        "field": [field_of(c) for c in codes],
        "interest_fit": interest,
        "skill_low": sk["low"], "skill_high": sk["high"],
        "subject_low": su["low"], "subject_high": su["high"],
        "match_low": combine(sk["low"], su["low"]), "match_high": combine(sk["high"], su["high"]),
        "coverage": coverage, "n_critical": n_critical, "display": display,
    }, index=codes)
    table.index.name = "code"
    return table, cats


def rank_order(table):
    """Sort by the LOWER bound (then upper bound, interest fit, code) - best first."""
    tmp = table.assign(_code=table.index)
    return tmp.sort_values(["match_low", "match_high", "interest_fit", "_code"],
                           ascending=[False, False, False, True]).index


def diversify(codes, fields, top=DIVERSITY_TOP, max_per_field=MAX_PER_FIELD):
    """Greedy re-rank: walk down the ranking and fill the top `top` places with at most
    `max_per_field` careers per field. Everything else keeps its normal order after them.
    If there are too few fields, the top is filled with the next best careers anyway."""
    head, count = [], {}
    for c in codes:
        if len(head) == top:
            break
        if count.get(fields[c], 0) < max_per_field:
            head.append(c)
            count[fields[c]] = count.get(fields[c], 0) + 1
    chosen = set(head)
    for c in codes:                        # not enough different fields: fill normally
        if len(head) == top:
            break
        if c not in chosen:
            head.append(c)
            chosen.add(c)
    return head + [c for c in codes if c not in chosen]


def _follow_ups(cats, code, n=MAX_FOLLOW_UPS):
    """Survey rows whose answer would narrow this career's range most: sum of w * (high - low)."""
    gains = []
    for cat, res in cats.items():
        for row, g in res["row_gain"].loc[code].items():
            if g > 1e-12:
                gains.append((g, f"{cat}: {row}"))
    return [label for _, label in sorted(gains, key=lambda x: -x[0])[:n]]


def _critical_names(cats, code):
    return [e for res in cats.values() for e in res["critical"].columns[res["critical"].loc[code].to_numpy()]]


def recommend_v2(student, data, top_n=10, min_job_zone=3, diversity=True, weights=None):
    """Top careers for one student (spec A1-A8). Returns a DataFrame, best first.

    match_low / match_high: the score range (equal when every important answer is known).
    display: "score" (show match_low), "range" (show low-high + follow_ups), "withheld" (show interest fit only).
    """
    table, cats = score_all_v2(student, data, eligible_codes(data, min_job_zone), weights)
    order = list(rank_order(table))
    if diversity:
        order = diversify(order, table["field"])
    top = table.loc[order[:top_n]]
    return pd.DataFrame({
        "rank": range(1, len(top) + 1),
        "code": top.index,
        "career": top["career"].to_numpy(),
        "field": top["field"].to_numpy(),
        "interest_fit": top["interest_fit"].round(3).to_numpy(),
        "skill_low": top["skill_low"].round(3).to_numpy(),
        "skill_high": top["skill_high"].round(3).to_numpy(),
        "subject_low": top["subject_low"].round(3).to_numpy(),
        "subject_high": top["subject_high"].round(3).to_numpy(),
        "match_low": top["match_low"].round(1).to_numpy(),
        "match_high": top["match_high"].round(1).to_numpy(),
        "coverage": top["coverage"].round(3).to_numpy(),
        "critical_unknowns": [_critical_names(cats, c) for c in top.index],
        "display": top["display"].to_numpy(),
        "follow_ups": [_follow_ups(cats, c) if d == "range" else []
                       for c, d in zip(top.index, top["display"])],
    })


# ---------------------------------------------------------------- explaining
def _fmt(x):
    return f"{x:g}"


def explain_v2(student, data, code, n=None):
    """Why this career (only from the student's own answers) and what to learn.

    Returns (reasons, gaps). reasons: max 2 interest, 2 skill, 2 subject, most important for
    THIS career first. gaps: one row per important element (IM >= 3) the student is below
    (gap > 0.5 levels), priority = IM * gap; "start from scratch" for no experience / not studied;
    unknown elements are listed last as "not assessed - answer to check"."""
    reasons = []

    # Interests: the student's high interests that are among this career's top 3 types
    occ = data["interests"].loc[code].sort_values(ascending=False)
    stu = _check_interests(student)
    hits = [(occ[t], t) for t in occ.index[:3] if stu[t] >= REASON_MIN_INTEREST]
    for _, t in sorted(hits, reverse=True)[:2]:
        reasons.append(f"High {t} interest ({_fmt(stu[t])}/5) - a top interest type for this career")

    _, cats = score_all_v2(student, data, [code])
    for cat, (mapping, _, _, key) in CATEGORIES.items():
        res, answers = cats[cat], student.get(key, {})
        im, lv, valid = res["im"].loc[code], res["lv"].loc[code], res["valid"].loc[code]
        candidates = []
        for row, elements in mapping.items():
            status, rating = parse_answer(answers.get(row))
            hits = [e for e in elements if e in im.index and valid[e] and im[e] >= REASON_MIN_IM]
            if status == RATED and rating >= REASON_MIN_RATING and hits:
                candidates.append((max(im[e] for e in hits), rating, row, hits))
        used = set()
        count = 0
        for _, rating, row, hits in sorted(candidates, key=lambda x: (-x[0], -x[1], x[2])):
            hits = [e for e in hits if e not in used]
            if not hits or count == 2:
                continue
            used.update(hits)
            count += 1
            level = (rating - 1) / 4 * 7
            meets = " - you meet the required level" if all(level >= lv[e] for e in hits) else ""
            if cat == "skill":
                reasons.append(f"Your {row} ({_fmt(rating)}/5) - important here ({', '.join(hits)}){meets}")
            else:
                reasons.append(f"{row} ({_fmt(rating)}/5) - this career uses {', '.join(hits)} knowledge{meets}")

    rows = []
    for cat, res in cats.items():
        ans = res["answers"]
        im, lv, valid = res["im"].loc[code], res["lv"].loc[code], res["valid"].loc[code]
        for e in im.index:
            if not valid[e] or im[e] < GAP_MIN_IM:
                continue
            base = {"area": cat, "survey_row": ", ".join(ans.loc[e, "rows"]), "element": e,
                    "importance": round(im[e], 2), "required_level": round(lv[e], 2)}
            if not ans.loc[e, "known"]:
                rows.append({**base, "your_level": np.nan, "gap": np.nan, "priority": np.nan,
                             "note": "not assessed - answer to check"})
                continue
            gap = lv[e] - ans.loc[e, "level"]
            if gap > GAP_MIN:
                rows.append({**base, "your_level": round(ans.loc[e, "level"], 2), "gap": round(gap, 2),
                             "priority": round(im[e] * gap, 2),
                             "note": "start from scratch" if ans.loc[e, "scratch"] else ""})
    gaps = pd.DataFrame(rows, columns=["area", "survey_row", "element", "importance", "required_level",
                                       "your_level", "gap", "priority", "note"])
    gaps["_unknown"] = gaps["gap"].isna()
    gaps = (gaps.sort_values(["_unknown", "priority", "importance"], ascending=[True, False, False])
                .drop(columns="_unknown").reset_index(drop=True))
    if n is not None:
        gaps = gaps.head(n)
    return reasons, gaps


# ---------------------------------------------------------------- target career
def _profile_matrix(data, codes):
    """Interests + skill importance + knowledge importance, each column z-scored."""
    parts = [data["interests"], data["skill_importance"], data["knowledge_importance"]]
    m = pd.concat([p.reindex(codes) for p in parts], axis=1).astype(float)
    m = m.fillna(m.mean())
    std = m.std().replace(0, 1)
    return ((m - m.mean()) / std).fillna(0)


def nearby_careers(data, code, n=5, min_job_zone=3):
    """Up to n careers close to `code`: O*NET Related Occupations first (if loaded),
    then the nearest careers by profile (any field). Returns [(code, source), ...]."""
    pool = eligible_codes(data, min_job_zone)
    out = []
    if "related" in data:
        rel = data["related"]
        for c in rel.loc[rel["code"] == code, "related_code"]:
            if c in pool and c != code and c not in [x for x, _ in out]:
                out.append((c, "O*NET related occupation"))
            if len(out) == n:
                return out
    candidates = pool.union(pd.Index([code]))
    m = _profile_matrix(data, candidates)
    dist = np.sqrt(((m - m.loc[code]) ** 2).sum(axis=1)).drop(code)
    for c in dist.sort_values(kind="stable").index:
        if c not in [x for x, _ in out]:
            out.append((c, "similar profile"))
        if len(out) == n:
            break
    return out


def questions_needed(student, data, code):
    """Survey rows that matter for this career (an element with IM >= 3) but are unanswered or
    "cant_assess", most useful first (largest possible change of the score)."""
    if code not in data["codes"]:
        raise KeyError(f"{code} cannot be ranked (missing O*NET interest/skill/knowledge data)")
    _, cats = score_all_v2(student, data, [code])
    out = []
    for cat, (mapping, _, _, key) in CATEGORIES.items():
        res = cats[cat]
        im, valid = res["im"].loc[code], res["valid"].loc[code]
        for row, elements in mapping.items():
            important = [e for e in elements if e in im.index and valid[e] and im[e] >= QUESTION_MIN_IM]
            if important and _row_status(student.get(key, {}), row) == CANT_ASSESS:
                out.append({"category": cat, "item": row, "elements": important,
                            "max_importance": round(float(max(im[e] for e in important)), 2),
                            "possible_gain": float(res["row_gain"].loc[code, row])})
    return sorted(out, key=lambda q: -q["possible_gain"])


def target_career(student, data, code, min_job_zone=3, n_alternatives=5):
    """Everything about one career the student is aiming for: the questions still needed,
    the readiness range, gaps, an interest check and up to 5 nearby alternatives."""
    questions = questions_needed(student, data, code)
    table, _ = score_all_v2(student, data, [code])
    row = table.loc[code]
    reasons, gaps = explain_v2(student, data, code)

    fit = float(row["interest_fit"])
    label = "strong" if fit >= INTEREST_FIT_STRONG else "moderate" if fit >= INTEREST_FIT_OK else "weak"
    career_top = list(data["interests"].loc[code].sort_values(ascending=False).index[:2])
    student_top = list(_check_interests(student).sort_values(ascending=False, kind="stable").index[:2])

    near = nearby_careers(data, code, n_alternatives, min_job_zone)
    alt_table, _ = score_all_v2(student, data, [c for c, _ in near]) if near else (None, None)
    alternatives = [{"code": c, "career": alt_table.loc[c, "career"], "field": alt_table.loc[c, "field"],
                     "match_low": round(float(alt_table.loc[c, "match_low"]), 1),
                     "match_high": round(float(alt_table.loc[c, "match_high"]), 1),
                     "display": alt_table.loc[c, "display"], "source": source} for c, source in near]
    return {
        "code": code, "career": row["career"], "field": row["field"],
        "job_zone": None if pd.isna(data.get("job_zone", pd.Series(dtype=float)).get(code, np.nan))
        else int(data["job_zone"][code]),
        "questions_needed": questions,
        "readiness": {k: round(float(row[k]), 3) for k in
                      ["skill_low", "skill_high", "subject_low", "subject_high", "coverage"]}
                     | {"match_low": round(float(row["match_low"]), 1),
                        "match_high": round(float(row["match_high"]), 1), "display": row["display"]},
        "reasons": reasons,
        "gaps": gaps,
        "interest_fit": {"value": round(fit, 3), "label": label,
                         "career_top_types": career_top, "your_top_types": student_top},
        "alternatives": alternatives,
    }


__all__ = ["COMPONENT_WEIGHTS", "SKILL_MAP_V2", "SUBJECT_MAP_V2", "check_maps", "load_onet",
           "load_onet_v2", "load_from_mysql", "add_extras", "parse_answer", "score_all_v2",
           "recommend_v2", "explain_v2", "target_career", "questions_needed", "nearby_careers",
           "diversify", "display_rule", "eligible_codes", "field_of"]
