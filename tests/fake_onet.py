"""A tiny fake O*NET folder shared by the tests (no real data needed).

Three clearly different careers, written in the same tab-separated format and
with the same column names as the real O*NET 31.0 files.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.baseline_recommender import RIASEC, SKILL_MAP, SUBJECT_MAP  # noqa: E402

SKILLS = sorted({e for v in SKILL_MAP.values() for e in v})
KNOWLEDGE = sorted({e for v in SUBJECT_MAP.values() for e in v})

# Three clearly different fake careers: (code, title, job zone, top interest, strong skills, strong knowledge)
CAREERS = [
    ("19-0001.00", "Lab Scientist", 4, "Investigative", ["Science", "Critical Thinking", "Writing"], ["Biology", "Chemistry"]),
    ("27-0001.00", "Designer", 3, "Artistic", ["Speaking", "Persuasion", "Coordination"], ["Fine Arts", "Design"]),
    ("47-0001.00", "Helper", 1, "Realistic", ["Repairing", "Installation", "Troubleshooting"], ["Building and Construction"]),
]


def _rows(code, elements, scales, strong, extra_cols=True):
    rows = []
    for e in elements:
        for scale, (lo, hi) in scales.items():
            value = hi if e in strong else lo
            row = {"O*NET-SOC Code": code, "Element ID": "x", "Element Name": e, "Scale ID": scale, "Data Value": value}
            if extra_cols:
                row.update({"N": "", "Standard Error": "", "Lower CI Bound": "", "Upper CI Bound": "",
                            "Recommend Suppress": "N", "Not Relevant": ""})
            row.update({"Date": "08/2026", "Domain Source": "Test"})
            rows.append(row)
    return rows


def write_fake_onet(folder):
    occ, interests, skills, know = [], [], [], []
    for code, title, zone, top, strong_sk, strong_kn in CAREERS:
        occ.append({"O*NET-SOC Code": code, "Title": title, "Description": f"{title} test career."})
        interests += _rows(code, RIASEC, {"OI": (1.5, 6.5)}, [top], extra_cols=False)
        skills += _rows(code, SKILLS, {"IM": (1.5, 4.5), "LV": (1.0, 5.0)}, strong_sk)
        know += _rows(code, KNOWLEDGE, {"IM": (1.5, 4.5), "LV": (1.0, 5.0)}, strong_kn)
    half = len(skills) // 2
    files = {
        "Occupation Data.txt": occ,
        "Career Interest Types.txt": interests,
        "Essential Skills.txt": skills[:half],
        "Transferable Skills.txt": skills[half:],
        "Knowledge.txt": know,
        "Job Zones.txt": [{"O*NET-SOC Code": c[0], "Job Zone": c[2], "Date": "08/2026", "Domain Source": "Test"} for c in CAREERS],
    }
    for name, rows in files.items():
        pd.DataFrame(rows).to_csv(folder / name, sep="\t", index=False)
    return folder


def _student(top_interest, skill_items, subjects):
    return {
        "interests": {t: (5 if t == top_interest else 2) for t in RIASEC},
        "skills": {s: (5 if s in skill_items else 1) for s in SKILL_MAP},
        "subjects": {s: (5 if s in subjects else 1) for s in SUBJECT_MAP},
    }


SCIENCE_STUDENT = _student("Investigative", ["Research", "Critical Thinking", "Writing"], ["Biology", "Chemistry"])
