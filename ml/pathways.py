"""How to get into a career: education routes in India, the stream to pick, a career ladder and courses.

Four parts, each honest about where it comes from:
  1. Routes (config/career_paths.csv): step-by-step Indian routes for common careers, e.g.
     Class 12 PCB -> NEET-UG -> MBBS. Written by hand with a link to the official website for each
     exam/body. A route stays marked "not yet checked" until the team sets verified = yes after
     checking it on the official site.
  2. Suggested stream after Class 10: from the career's most important O*NET knowledge areas
     (e.g. Biology + Chemistry -> Science with Biology). A Pathfinder rule, shown as a suggestion.
  3. Education in O*NET (US survey): the share of workers with each education level, from
     "Education, Training, and Experience.txt" (scale RL) when that file is in data/raw/onet/.
  4. Career ladder: related careers (O*NET Related Occupations, else the same occupation group)
     that need LESS preparation (ways in) or MORE preparation (where you can grow), by Job Zone.
  5. Courses (config/courses.csv): only courses the team has opened and checked; nothing invented.
"""
import csv
import os
from pathlib import Path

import pandas as pd

from ml.baseline_recommender import _read

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTES_FILE = PROJECT_ROOT / "config" / "career_paths.csv"
COURSES_FILE = PROJECT_ROOT / "config" / "courses.csv"

# ---------------------------------------------------------------- 1. routes
def show_unverified_routes():
    """SHOW_UNVERIFIED_ROUTES in .env: "yes" (default, while the team is still checking; each such route is
    labelled "not yet checked") or "no" (for the demo/report: only routes checked on the official sites)."""
    return os.getenv("SHOW_UNVERIFIED_ROUTES", "yes").strip().lower() not in ("no", "n", "false", "0")


def load_routes(path=ROUTES_FILE, include_unverified=None):
    """[{id, name, prefixes, verified, steps: [{stage, text, link_name, link_url}]}], file order kept.
    A route counts as verified only if EVERY one of its rows has verified = yes.
    include_unverified: None = follow SHOW_UNVERIFIED_ROUTES; False = leave unverified routes out."""
    if include_unverified is None:
        include_unverified = show_unverified_routes()
    path = Path(path)
    if not path.exists():
        return []
    routes = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rid = (r.get("route_id") or "").strip()
            if not rid:
                continue
            route = routes.setdefault(rid, {
                "id": rid, "name": r["route_name"].strip(),
                "prefixes": [p.strip() for p in r["applies_to"].split(";") if p.strip()],
                "verified": True, "steps": []})
            route["verified"] &= (r.get("verified") or "").strip().lower() in ("yes", "y", "true")
            route["steps"].append({"stage": r["stage"].strip(), "text": r["text"].strip(),
                                   "link_name": (r.get("link_name") or "").strip() or None,
                                   "link_url": (r.get("link_url") or "").strip() or None})
    return [r for r in routes.values() if include_unverified or r["verified"]]


def routes_for(code, routes):
    """Routes whose applies_to prefixes match this O*NET code. A longer (more specific) prefix first."""
    hits = []
    for r in routes:
        best = max((len(p) for p in r["prefixes"] if code.startswith(p)), default=0)
        if best:
            hits.append((best, r))
    return [r for _, r in sorted(hits, key=lambda h: -h[0])]


# ---------------------------------------------------------------- 2. stream after Class 10
STREAMS = {   # O*NET knowledge area -> the Class 11-12 stream it points to (Pathfinder's rule)
    "Biology": "Science with Biology (PCB)", "Medicine and Dentistry": "Science with Biology (PCB)",
    "Chemistry": "Science (PCB or PCM)", "Physics": "Science with Maths (PCM)",
    "Mathematics": "Science with Maths (PCM)", "Engineering and Technology": "Science with Maths (PCM)",
    "Computers and Electronics": "Science with Maths (PCM)", "Design": "Any stream (Arts/Design helps)",
    "Fine Arts": "Arts / Humanities", "Economics and Accounting": "Commerce",
    "Administration and Management": "Commerce", "Sales and Marketing": "Commerce",
    "History and Archeology": "Arts / Humanities", "Sociology and Anthropology": "Arts / Humanities",
    "Psychology": "Arts / Humanities", "Geography": "Arts / Humanities", "Philosophy and Theology": "Arts / Humanities",
    "Law and Government": "Arts / Humanities", "English Language": "Arts / Humanities",
    "Foreign Language": "Arts / Humanities", "Communications and Media": "Arts / Humanities",
}
STREAM_MIN_IM = 3.5


def suggested_stream(data, code):
    """{stream, because: [knowledge areas]} or None. Weighted by importance above 3.5."""
    if code not in data["knowledge_importance"].index:
        return None
    im = data["knowledge_importance"].loc[code].dropna()
    score, why = {}, {}
    for element, value in im.sort_values(ascending=False).items():
        stream = STREAMS.get(element)
        if stream and value >= STREAM_MIN_IM:
            score[stream] = score.get(stream, 0) + value - 3
            why.setdefault(stream, []).append(element)
    if not score:
        return {"stream": "Any stream", "because": []}
    best = max(score, key=score.get)
    return {"stream": best, "because": why[best][:3]}


# ---------------------------------------------------------------- 3. O*NET education levels (US)
EDUCATION_LEVELS = {   # O*NET "Required Level of Education" (RL) categories; the Categories file wins if present
    1: "Less than a high school diploma", 2: "High school diploma (Class 12)", 3: "Post-secondary certificate",
    4: "Some college courses", 5: "Associate's degree (2-year)", 6: "Bachelor's degree",
    7: "Post-baccalaureate certificate", 8: "Master's degree", 9: "Post-master's certificate",
    10: "First professional degree (e.g. medicine, law)", 11: "Doctoral degree", 12: "Post-doctoral training",
}


def load_education(onet_dir):
    """DataFrame (code, level, label, percent) for scale RL, or None, plus a message saying what was used."""
    try:
        df = _read(onet_dir, "Education, Training, and Experience.txt")
    except FileNotFoundError:
        return None, "Education, Training, and Experience.txt: not found; education shares not shown"
    need = {"O*NET-SOC Code", "Scale ID", "Category", "Data Value"}
    if not need.issubset(df.columns):
        return None, f"Education, Training, and Experience.txt: columns not usable {list(df.columns)}"
    df = df[df["Scale ID"] == "RL"].copy()
    if "Recommend Suppress" in df.columns:
        df = df[df["Recommend Suppress"].astype(str).str.upper() != "Y"]
    df["level"] = pd.to_numeric(df["Category"], errors="coerce")
    df["percent"] = pd.to_numeric(df["Data Value"], errors="coerce")
    labels = dict(EDUCATION_LEVELS)
    try:
        cats = _read(onet_dir, "Education, Training, and Experience Categories.txt")
        if {"Scale ID", "Category", "Category Description"}.issubset(cats.columns):
            rl = cats[cats["Scale ID"] == "RL"]
            labels.update({int(c): str(d) for c, d in zip(pd.to_numeric(rl["Category"], errors="coerce"),
                                                           rl["Category Description"]) if pd.notna(c)})
    except FileNotFoundError:
        pass
    df = df.dropna(subset=["level", "percent"])
    df["label"] = df["level"].astype(int).map(labels)
    out = df[["O*NET-SOC Code", "level", "label", "percent"]].rename(columns={"O*NET-SOC Code": "code"})
    return out.reset_index(drop=True), "Education, Training, and Experience.txt: used scale RL (required level of education)"


def education_for(data, code, top=3, min_percent=5):
    edu = data.get("education")
    if edu is None:
        return []
    rows = edu[(edu["code"] == code) & (edu["percent"] >= min_percent)].sort_values("percent", ascending=False)
    return [{"level": int(r.level), "label": r.label, "percent": round(float(r.percent))} for r in rows.head(top).itertuples()]


# ---------------------------------------------------------------- 4. career ladder
def career_ladder(data, code, n=4):
    """{"ways_in": [...], "grow_into": [...]}: related careers needing less / more preparation (Job Zone)."""
    jz = data.get("job_zone", pd.Series(dtype=float))
    mine = jz.get(code)
    if mine is None or pd.isna(mine):
        return {"ways_in": [], "grow_into": []}
    excluded = data.get("excluded", {})
    known = set(data["occupations"].index)
    related, source = [], {}
    if "related" in data:
        for c in data["related"].loc[data["related"]["code"] == code, "related_code"]:
            if c not in related:
                related.append(c)
                source[c] = "O*NET related occupation"
    for c in sorted(known):                     # same occupation group (first 5 characters, e.g. 29-11)
        if c[:5] == code[:5] and c not in related:
            related.append(c)
            source[c] = "same occupation group"
    out = {"ways_in": [], "grow_into": []}
    for c in related:
        if c == code or c not in known or c in excluded or pd.isna(jz.get(c)):
            continue
        key = "ways_in" if jz[c] < mine else "grow_into" if jz[c] > mine else None
        if key and len(out[key]) < n:
            out[key].append({"code": c, "job_zone": int(jz[c]), "source": source[c]})
    return out


# ---------------------------------------------------------------- 5. courses (checked by the team)
def load_courses(path=COURSES_FILE):
    """Rows of config/courses.csv with a title, a URL and a verified_on date. Others are ignored."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if all((r.get(k) or "").strip() for k in ("element", "title", "url", "verified_on")):
            out.append({k: (r.get(k) or "").strip() or None
                        for k in ("element", "title", "provider", "url", "cost", "language", "verified_on")})
    return out


def courses_for(elements, courses, per_element=3):
    """{element: [course, ...]} for the given O*NET skill/knowledge names (case-insensitive)."""
    wanted = {e.lower(): e for e in elements}
    out = {}
    for c in courses:
        e = wanted.get(c["element"].lower())
        if e and len(out.setdefault(e, [])) < per_element:
            out[e].append(c)
    return out
