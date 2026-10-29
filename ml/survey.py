"""Read the Google Form export (tools/create_career_survey.gs) and turn each response into engine input.

Google Forms "Download responses (.csv)" gives one column per question, and one column per ROW of a grid
question, named like "6. Rate your current ability in these skills [Programming]". Columns are found by
the question number and the row name in brackets, so small wording changes in the form do not matter.

The raw file stays untouched in data/raw/survey/; clean_survey() returns a tidy table (one row per student)
that experiments/ save to data/processed/. No names or emails are collected by the form.

    responses = load_survey("data/raw/survey/responses.csv")   # tidy DataFrame
    student = to_student(responses.iloc[0])                    # engine v2 input
"""
import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

from ml.baseline_recommender import RIASEC
from ml.recommender_v2 import SKILL_MAP_V2, SUBJECT_MAP_V2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SURVEY = PROJECT_ROOT / "data" / "raw" / "survey" / "responses.csv"
FIELD_MAP_FILE = PROJECT_ROOT / "config" / "survey_field_map.csv"
NOT_SURE = "Not sure yet"
# The survey was closed for analysis at 87 responses (26 Oct), before any result on later ones was seen.
# The report's main results use these first 87 rows (the export is in submission order); responses that came
# in later are reported separately by experiments/later_responses.py. The app's field model uses all rows.
ANALYSIS_CUTOFF = 87

# Question 5 rows (in form order) -> RIASEC type
INTEREST_ROWS = {
    "Working with machines, tools or building things": "Realistic",
    "Solving problems, research and analysing data": "Investigative",
    "Designing, writing or creating things": "Artistic",
    "Helping, teaching or caring for people": "Social",
    "Leading, persuading or starting a business": "Enterprising",
    "Organising data and records, following clear procedures": "Conventional",
}
SINGLE = {1: "year", 2: "branch", 3: "clarity", 4: "counsellor", 8: "aimed_field", 9: "would_use"}
GRIDS = {5: ("interest", list(INTEREST_ROWS)), 6: ("skill", list(SKILL_MAP_V2)), 7: ("subject", list(SUBJECT_MAP_V2))}


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def find_columns(columns):
    """{our_name: csv column}. Raises ValueError listing what is missing, so wrong exports fail loudly."""
    found, missing = {}, []
    for number, name in SINGLE.items():
        col = next((c for c in columns if re.match(rf"^\s*{number}\s*[.)]", str(c)) and "[" not in str(c)), None)
        (found.__setitem__(name, col) if col else missing.append(f"question {number} ({name})"))
    for number, (prefix, rows) in GRIDS.items():
        grid_cols = [c for c in columns if re.match(rf"^\s*{number}\s*[.)]", str(c)) and "[" in str(c)]
        for row in rows:
            col = next((c for c in grid_cols if _norm(str(c).rsplit("[", 1)[1].rstrip("] ")) == _norm(row)), None)
            (found.__setitem__(f"{prefix}:{row}", col) if col else missing.append(f"question {number} row [{row}]"))
    if missing:
        raise ValueError("These survey columns were not found in the CSV: " + "; ".join(missing) +
                         f". Columns in the file: {list(columns)}")
    return found


def parse_cell(value, kind):
    """One grid answer -> number 1-5, "no_experience", "not_studied", "cant_assess" or None (blank)."""
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value).strip() == "":
        return None
    text = str(value).strip()
    m = re.match(r"^([1-5])(\.0)?(?![0-9.])", text)      # "4", "4.0", "5 (High)", "1 - Low", "3 = it is okay"
    if m:
        return int(m.group(1))
    key = _norm(text)
    if key in ("no experience", "never tried", "i have never tried it"):
        return "no_experience"
    if key in ("not studied", "i have not studied it"):
        return "not_studied"
    if key in ("can t assess", "cant assess", "cannot assess", "not sure"):
        return "cant_assess"
    raise ValueError(f"Unknown {kind} answer {value!r}")


def load_survey(path=DEFAULT_SURVEY, first_n=None):
    """Tidy table: one row per response, columns year, branch, clarity, counsellor, aimed_field, would_use,
    the 6 RIASEC interests (1-5), skill:<row> and subject:<row> answers. first_n: keep only the first N
    responses (None = all)."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    if first_n:
        raw = raw.head(first_n)
    cols = find_columns(raw.columns)
    out = pd.DataFrame(index=raw.index)
    out["response_id"] = range(1, len(raw) + 1)
    for name in SINGLE.values():
        out[name] = raw[cols[name]].str.strip()
    unknown = {}                                    # question -> answers we could not read (all reported at once)

    def read(values, kind, question):
        parsed = []
        for v in values:
            try:
                parsed.append(parse_cell(v, kind))
            except ValueError:
                unknown.setdefault(question, set()).add(str(v))
                parsed.append(None)
        return parsed

    for row, riasec in INTEREST_ROWS.items():
        out[riasec] = read(raw[cols[f"interest:{row}"]], "interest", "Q5")
    for prefix, question in (("skill", "Q6"), ("subject", "Q7")):
        for row in GRIDS[6 if prefix == "skill" else 7][1]:
            out[f"{prefix}:{row}"] = read(raw[cols[f"{prefix}:{row}"]], prefix, question)
    if unknown:
        raise ValueError("Some survey answers could not be read (add them to parse_cell in ml/survey.py): " +
                         "; ".join(f"{q}: {sorted(v)}" for q, v in unknown.items()))
    return out


def is_complete(row):
    """All 6 interests answered with a number (the engine needs them). Skills/subjects may be blank."""
    return all(isinstance(row[t], (int, np.integer)) for t in RIASEC)


def to_student(row):
    """Engine v2 input from one tidy row. Blank skill/subject answers count as "cant_assess"."""
    def answer(v):
        return {"rating": int(v)} if isinstance(v, (int, np.integer)) else (v or "cant_assess")
    return {"interests": {t: int(row[t]) for t in RIASEC},
            "skills": {r: answer(row[f"skill:{r}"]) for r in SKILL_MAP_V2},
            "subjects": {r: answer(row[f"subject:{r}"]) for r in SUBJECT_MAP_V2}}


def to_student_v1(row):
    """Engine v1 input (ml/baseline_recommender SKILL_MAP / SUBJECT_MAP): only numeric answers are passed;
    merged survey rows are copied to v1's separate subjects."""
    num = lambda v: int(v) if isinstance(v, (int, np.integer)) else None          # noqa: E731
    skills = {r: num(row[f"skill:{r}"]) for r in SKILL_MAP_V2}
    subj = {r: num(row[f"subject:{r}"]) for r in SUBJECT_MAP_V2}
    v1_subjects = {"Mathematics": subj["Mathematics"], "Physics": subj["Physics/Chemistry"],
                   "Chemistry": subj["Physics/Chemistry"], "Biology": subj["Biology"],
                   "Computer Science": subj["Computer Science"], "Economics": subj["Commerce/Economics"],
                   "Commerce/Accounting": subj["Commerce/Economics"], "Languages": subj["Languages"],
                   "Social Sciences": subj["Social Sciences"], "Arts/Design": subj["Arts/Design"]}
    return {"interests": {t: int(row[t]) for t in RIASEC},
            "skills": {k: v for k, v in skills.items() if v is not None},
            "subjects": {k: v for k, v in v1_subjects.items() if v is not None}}


def load_field_map(path=FIELD_MAP_FILE):
    """{aimed field answer: [SOC prefixes]} from config/survey_field_map.csv."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        return {r["aimed_field"].strip(): [p.strip() for p in r["soc_prefixes"].split(";") if p.strip()]
                for r in csv.DictReader(f) if (r.get("aimed_field") or "").strip()}


def in_field(code, prefixes):
    return any(code.startswith(p) for p in prefixes)


def field_of_code(code, field_map):
    """The survey field an O*NET code belongs to (longest matching prefix), or None."""
    best, best_len = None, 0
    for name, prefixes in field_map.items():
        for p in prefixes:
            if code.startswith(p) and len(p) > best_len:
                best, best_len = name, len(p)
    return best


def feature_table(tidy):
    """Numbers for ML: 6 interests, 8 skills, 8 subjects. A rating stays 1-5; "no_experience"/"not_studied"
    -> 0 (a known 'none'); "cant_assess"/blank -> NaN (imputed inside the ML pipeline, never before)."""
    cols = list(RIASEC) + [f"skill:{r}" for r in SKILL_MAP_V2] + [f"subject:{r}" for r in SUBJECT_MAP_V2]
    def num(v):
        if isinstance(v, (int, np.integer)):
            return float(v)
        return 0.0 if v in ("no_experience", "not_studied") else np.nan
    return pd.DataFrame({c: [num(v) for v in tidy[c]] for c in cols}, index=tidy.index)
