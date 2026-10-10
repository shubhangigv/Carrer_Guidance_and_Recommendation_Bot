"""Baseline career recommender - transparent, no machine learning yet.

It compares a student's profile with every O*NET occupation on three parts:
  1. Interests  (6 RIASEC interest types)  -> Career Interest Types.txt
  2. Skills     (35 O*NET skills)          -> Essential + Transferable Skills.txt
  3. Academic   (subject knowledge)        -> Knowledge.txt
and combines them into one Profile Match Score from 0 to 100.

This is the baseline that later ML / semantic models will be compared against.
"""
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- settings
# Starting weights from our plan (skills 30, interests 25, academic 15).
# Work style, preferences and market data are not used yet, so the three
# weights are rescaled to add up to 100%. These will be tuned in experiments.
WEIGHTS = {"skills": 0.30, "interests": 0.25, "academic": 0.15}

RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]

# Our questionnaire's skills -> the O*NET skills they correspond to.
# Skills with no clear O*NET equivalent (Statistics, Data Analysis, Creativity,
# Design) are left out for now; semantic matching will cover them later.
SKILL_MAP = {
    "Mathematics": ["Mathematics"],
    "Programming": ["Programming"],
    "Problem Solving": ["Complex Problem Solving"],
    "Logical Reasoning": ["Critical Thinking"],
    "Critical Thinking": ["Critical Thinking"],
    "Research": ["Science", "Active Learning"],
    "Communication": ["Speaking", "Active Listening"],
    "Writing": ["Writing"],
    "Public Speaking": ["Speaking"],
    "Leadership": ["Coordination", "Management of Personnel Resources"],
    "Teamwork": ["Social Perceptiveness", "Coordination"],
    "Time Management": ["Time Management"],
    "Project Management": ["Coordination", "Time Management", "Management of Material Resources"],
    "Financial/Business Skills": ["Management of Financial Resources", "Negotiation", "Persuasion"],
    "Teaching": ["Instructing", "Learning Strategies"],
    "Technical/Practical Skills": ["Installation", "Equipment Maintenance", "Troubleshooting",
                                   "Repairing", "Operation and Control", "Equipment Selection"],
}

# Our questionnaire's subjects -> O*NET knowledge areas.
SUBJECT_MAP = {
    "Mathematics": ["Mathematics"],
    "Physics": ["Physics"],
    "Chemistry": ["Chemistry"],
    "Biology": ["Biology"],
    "Computer Science": ["Computers and Electronics"],
    "Economics": ["Economics and Accounting"],
    "Commerce/Accounting": ["Economics and Accounting", "Administration and Management"],
    "Languages": ["English Language", "Foreign Language"],
    "Social Sciences": ["Sociology and Anthropology", "Psychology", "History and Archeology",
                        "Geography", "Law and Government"],
    "Arts/Design": ["Fine Arts", "Design"],
}

# First two digits of an O*NET-SOC code = its SOC 2018 major group (career domain).
SOC_MAJOR_GROUPS = {
    "11": "Management", "13": "Business & Finance", "15": "Computer & Mathematical",
    "17": "Architecture & Engineering", "19": "Life, Physical & Social Science",
    "21": "Community & Social Service", "23": "Legal", "25": "Education & Library",
    "27": "Arts, Design, Entertainment, Sports & Media", "29": "Healthcare Practitioners",
    "31": "Healthcare Support", "33": "Protective Service", "35": "Food Preparation & Serving",
    "37": "Building & Grounds Maintenance", "39": "Personal Care & Service", "41": "Sales",
    "43": "Office & Administrative Support", "45": "Farming, Fishing & Forestry",
    "47": "Construction & Extraction", "49": "Installation, Maintenance & Repair",
    "51": "Production", "53": "Transportation & Material Moving", "55": "Military",
}


# ---------------------------------------------------------------- loading
def _read(onet_dir, filename):
    """Find an O*NET file anywhere under onet_dir and read it (all columns as text)."""
    path = next(Path(onet_dir).rglob(filename), None)
    if path is None:
        raise FileNotFoundError(f"'{filename}' not found under {onet_dir}")
    return pd.read_csv(path, sep="\t", dtype=str)


def _drop_suppressed(df):
    """Remove ratings O*NET flags as unreliable (Recommend Suppress = "Y", e.g. a very small sample).
    Files without that column (Career Interest Types.txt) are returned unchanged."""
    if "Recommend Suppress" not in df.columns:
        return df
    return df[df["Recommend Suppress"].fillna("").str.strip().str.upper() != "Y"]


def _pivot(df, scale_id):
    """One row per occupation, one column per element, for one rating scale."""
    part = df[df["Scale ID"] == scale_id].copy()
    part["Data Value"] = pd.to_numeric(part["Data Value"], errors="coerce")
    return part.pivot_table(index="O*NET-SOC Code", columns="Element Name",
                            values="Data Value", aggfunc="mean")


def load_onet(onet_dir, drop_suppressed=True):
    """Load the O*NET tables the engines need. Never modifies the raw files.

    drop_suppressed=True ignores rating rows marked Recommend Suppress = "Y" (data cleaning, Oct 2026).
    Use False only to reproduce results from before that change.
    """
    clean = _drop_suppressed if drop_suppressed else (lambda df: df)
    skills_raw = clean(pd.concat([_read(onet_dir, "Essential Skills.txt"),
                                  _read(onet_dir, "Transferable Skills.txt")]))
    knowledge_raw = clean(_read(onet_dir, "Knowledge.txt"))
    data = {
        "occupations": _read(onet_dir, "Occupation Data.txt").set_index("O*NET-SOC Code"),
        "interests": _pivot(_read(onet_dir, "Career Interest Types.txt"), "OI")[RIASEC],
        "skill_importance": _pivot(skills_raw, "IM"),   # how important (1-5)
        "skill_level": _pivot(skills_raw, "LV"),        # how much is needed (0-7)
        "knowledge_importance": _pivot(knowledge_raw, "IM"),
        "knowledge_level": _pivot(knowledge_raw, "LV"),   # used by engine v2 (subject readiness)
    }
    # Job Zone (1 = little preparation ... 5 = extensive preparation) - optional
    try:
        jz = _read(onet_dir, "Job Zones.txt")
        if "Job Zone" in jz.columns:
            data["job_zone"] = pd.to_numeric(
                jz.groupby("O*NET-SOC Code")["Job Zone"].first(), errors="coerce")
    except FileNotFoundError:
        pass
    # Only rank occupations that have interest, skill AND knowledge data
    data["codes"] = (data["interests"].index
                     .intersection(data["skill_importance"].index)
                     .intersection(data["knowledge_importance"].index))
    return data


def load_from_mysql(engine=None):
    """Same tables as load_onet(), read from MySQL instead of the .txt files.

    Fill the database first with scripts/load_onet_to_mysql.py. Each query returns
    long rows in the same shape as the O*NET files (code, element, scale, value),
    so they go through the same _pivot() and give identical results.
    """
    from sqlalchemy import text   # imported here so the file-based engine works without SQLAlchemy
    if engine is None:
        from backend.db import get_engine
        engine = get_engine()

    def query(sql):
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        return df.rename(columns={"code": "O*NET-SOC Code", "element": "Element Name",
                                  "scale": "Scale ID", "value": "Data Value"})

    careers = query("SELECT onet_code AS code, title, description, job_zone FROM career")
    interests = query("""
        SELECT c.onet_code AS code, i.name AS element, 'OI' AS scale, ci.score AS value
        FROM career_interest ci JOIN career c USING (career_id) JOIN interest i USING (interest_id)""")
    skills = query("""
        SELECT c.onet_code AS code, s.name AS element, 'IM' AS scale, cs.importance AS value
        FROM career_skill cs JOIN career c USING (career_id) JOIN skill s USING (skill_id)
        UNION ALL
        SELECT c.onet_code, s.name, 'LV', cs.required_level
        FROM career_skill cs JOIN career c USING (career_id) JOIN skill s USING (skill_id)""")
    knowledge = query("""
        SELECT c.onet_code AS code, k.name AS element, 'IM' AS scale, ck.importance AS value
        FROM career_knowledge ck JOIN career c USING (career_id) JOIN knowledge k USING (knowledge_id)
        UNION ALL
        SELECT c.onet_code, k.name, 'LV', ck.level
        FROM career_knowledge ck JOIN career c USING (career_id) JOIN knowledge k USING (knowledge_id)""")

    careers = careers.set_index("O*NET-SOC Code")
    data = {
        "occupations": careers.rename(columns={"title": "Title", "description": "Description"})[["Title", "Description"]],
        "interests": _pivot(interests, "OI")[RIASEC],
        "skill_importance": _pivot(skills, "IM"),
        "skill_level": _pivot(skills, "LV"),
        "knowledge_importance": _pivot(knowledge, "IM"),
        "knowledge_level": _pivot(knowledge, "LV"),
    }
    job_zone = pd.to_numeric(careers["job_zone"], errors="coerce").dropna()
    if not job_zone.empty:
        data["job_zone"] = job_zone
    data["codes"] = (data["interests"].index
                     .intersection(data["skill_importance"].index)
                     .intersection(data["knowledge_importance"].index))
    return data


# ---------------------------------------------------------------- matching
def _student_vector(ratings, mapping):
    """Turn the student's 1-5 ratings into values for O*NET element names."""
    collected = {}
    for item, value in ratings.items():
        for element in mapping.get(item, []):
            collected.setdefault(element, []).append(float(value))
    return pd.Series({element: np.mean(values) for element, values in collected.items()})


def _profile_similarity(student, table):
    """Pearson correlation between the student's profile and each occupation's
    profile, rescaled from [-1, 1] to [0, 1].

    Correlation compares the SHAPE of two profiles ("your strongest areas are
    this career's most important areas"), so the student's 1-5 scale and
    O*NET's scales do not need converting first.
    """
    cols = [c for c in student.index if c in table.columns]
    s = student[cols].astype(float)
    t = table[cols].astype(float)
    t = t.where(t.notna(), t.mean(axis=1), axis=0)   # fill a missing value with that row's mean
    s_c = s - s.mean()
    t_c = t.sub(t.mean(axis=1), axis=0)
    denom = np.sqrt((s_c ** 2).sum()) * np.sqrt((t_c ** 2).sum(axis=1))
    r = (t_c @ s_c) / denom
    r = r.replace([np.inf, -np.inf], np.nan).fillna(0)  # flat profile -> neutral 0.5
    return (r + 1) / 2


def recommend_v1(student, data, top_n=5, min_job_zone=None):
    """v1: rank all occupations for one student. Returns the top_n as a table."""
    codes = data["codes"]
    if min_job_zone is not None and "job_zone" in data:
        jz = data["job_zone"].reindex(codes)
        codes = codes[(jz >= min_job_zone).to_numpy()]

    parts = pd.DataFrame({
        "interests": _profile_similarity(pd.Series(student["interests"])[RIASEC],
                                         data["interests"].loc[codes]),
        "skills": _profile_similarity(_student_vector(student["skills"], SKILL_MAP),
                                      data["skill_importance"].loc[codes]),
        "academic": _profile_similarity(_student_vector(student["subjects"], SUBJECT_MAP),
                                        data["knowledge_importance"].loc[codes]),
    })
    total = sum(WEIGHTS.values())
    parts["score"] = sum(parts[k] * w for k, w in WEIGHTS.items()) / total * 100

    top = parts.sort_values("score", ascending=False).head(top_n)
    return pd.DataFrame({
        "rank": range(1, len(top) + 1),
        "code": top.index,
        "career": data["occupations"].loc[top.index, "Title"].values,
        "domain": [SOC_MAJOR_GROUPS.get(c[:2], "Other") for c in top.index],
        "match_score": top["score"].round(0).astype(int).values,
        "interest_match_%": (top["interests"] * 100).round(0).astype(int).values,
        "skill_match_%": (top["skills"] * 100).round(0).astype(int).values,
        "academic_match_%": (top["academic"] * 100).round(0).astype(int).values,
    })


# ---------------------------------------------------------------- explaining
def explain_v1(student, data, code, n=3):
    """v1: reasons for a recommendation and the student's biggest skill gaps,
    built only from the student's answers and the O*NET ratings."""
    reasons = []

    # 1) Interests: student's top 2 interest types that are also in this career's top 3
    occ_int = data["interests"].loc[code].sort_values(ascending=False)
    stu_int = pd.Series(student["interests"]).sort_values(ascending=False)
    for name in stu_int.index[:2]:
        if name in occ_int.index[:3] and stu_int[name] >= 3.5:
            reasons.append(f"High {name} interest ({stu_int[name]}/5) - a top interest type for this career")

    # 2) Skills: student rates it 4+ and the career rates it important (3.5+ of 5).
    #    Ranked by how important the skill is for THIS career, so reasons differ per career.
    imp = data["skill_importance"].loc[code]
    candidates = []
    for item, rating in student["skills"].items():
        hits = [e for e in SKILL_MAP.get(item, []) if imp.get(e, 0) >= 3.5]
        if rating >= 4 and hits:
            candidates.append((max(imp[e] for e in hits), item, rating, hits))
    used = set()                                     # avoid repeating the same O*NET skill
    for _, item, rating, hits in sorted(candidates, reverse=True):
        hits = [e for e in hits if e not in used]
        if hits and sum(r.startswith("Your") for r in reasons) < 2:   # max 2 skill reasons
            used.update(hits)
            reasons.append(f"Your {item} ({rating}/5) - important here ({', '.join(hits)})")

    # 3) Academic: subject rated 4+ that maps to important knowledge (max 2, most important first)
    kimp = data["knowledge_importance"].loc[code]
    candidates = []
    for subject, rating in student["subjects"].items():
        hits = [e for e in SUBJECT_MAP.get(subject, []) if kimp.get(e, 0) >= 3.5]
        if rating >= 4 and hits:
            candidates.append((max(kimp[e] for e in hits), subject, rating, hits))
    for _, subject, rating, hits in sorted(candidates, reverse=True)[:2]:
        reasons.append(f"{subject} ({rating}/5) - this career uses {', '.join(hits)} knowledge")

    # Skill gaps: required level (O*NET LV, 0-7) vs the student's self-rating
    # mapped onto the same 0-7 range (rough mapping - to be calibrated later).
    lvl = data["skill_level"].loc[code]
    stu_skill = _student_vector(student["skills"], SKILL_MAP)
    gaps = []
    for element, rating in stu_skill.items():
        if element in imp.index and pd.notna(lvl.get(element)) and imp[element] >= 3:
            your_level = (rating - 1) / 4 * 7
            gap = lvl[element] - your_level
            if gap > 0.5:
                gaps.append({"skill": element, "importance": round(imp[element], 1),
                             "required_level": round(lvl[element], 1),
                             "your_level": round(your_level, 1), "gap": round(gap, 1),
                             "priority": round(imp[element] * gap, 1)})
    gaps = pd.DataFrame(gaps, columns=["skill", "importance", "required_level",
                                       "your_level", "gap", "priority"])
    gaps = gaps.sort_values("priority", ascending=False).head(n).reset_index(drop=True)
    return reasons, gaps


# Old names still work (tests, notebook 02 and the MySQL comparison use them).
recommend = recommend_v1
explain = explain_v1
