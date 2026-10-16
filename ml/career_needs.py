"""Everything a career needs (all O*NET skills and knowledge areas) and a step-by-step roadmap.

Why this file exists: the quiz measures only 8 skills and 8 subjects, but O*NET rates every career
on 35 skills and 33 knowledge areas. "Skills to build" should show ALL the important ones, and say
honestly which ones the quiz measured and which it did not.

requirements(student, data, code) -> one row per important element (importance >= 3 of 5):
    status "have"          the student's level meets the required level (within 0.5 of 7)
           "build"         below the required level -> part of the roadmap
           "not_assessed"  measured by a quiz row the student answered "Can't assess"
           "not_measured"  the quiz has no question for it (e.g. Negotiation, Law and Government)
roadmap(student, data, code) -> ordered steps: education (from O*NET Job Zone), skills to build in
    priority order (importance x gap), skills to check, experience, applying.

Only O*NET ratings and the student's own answers are used. No course links or salaries are invented.
"""
import numpy as np
import pandas as pd

from ml.recommender_v2 import GAP_MIN, SKILL_MAP_V2, SUBJECT_MAP_V2, _element_answers

MIN_IMPORTANCE = 3.0          # "important" on O*NET's 1-5 importance scale
STAGE_SIZES = (3, 3)          # the first 3 skills to build are "Start now", the next 3 "Next", the rest "Later"

KINDS = [  # kind, importance table, level table, quiz map, key in the student dict
    ("skill", "skill_importance", "skill_level", SKILL_MAP_V2, "skills"),
    ("knowledge", "knowledge_importance", "knowledge_level", SUBJECT_MAP_V2, "subjects"),
]

# O*NET Job Zone titles (official) and what they usually mean for a student in India (our reading).
JOB_ZONES = {
    1: ("Little or no preparation needed", "You can usually start after school; training happens on the job."),
    2: ("Some preparation needed", "Usually Class 10/12, plus a few months of training or experience."),
    3: ("Medium preparation needed", "Usually a vocational course, ITI, diploma or polytechnic, or a related "
                                      "degree, plus some work experience."),
    4: ("Considerable preparation needed", "Usually a bachelor's degree (for example B.Tech, B.Sc, B.Com, BA, "
                                           "BBA) and some years of related experience."),
    5: ("Extensive preparation needed", "Usually a postgraduate or professional degree (for example a "
                                        "master's, PhD, MBBS/MD, LLB/LLM), and often several years of experience."),
}


def _num(x):
    return None if x is None or pd.isna(x) else round(float(x), 2)


def requirements(student, data, code, min_importance=MIN_IMPORTANCE):
    """All important skills and knowledge areas of one career, most important first."""
    rows = []
    for kind, im_key, lv_key, mapping, answer_key in KINDS:
        if code not in data[im_key].index:
            continue
        im = data[im_key].loc[code]
        lv = data[lv_key].loc[code] if lv_key in data and code in data[lv_key].index else pd.Series(dtype=float)
        answers = _element_answers((student or {}).get(answer_key, {}), mapping)
        for element, importance in im.items():
            if pd.isna(importance) or importance < min_importance:
                continue
            required = lv.get(element, np.nan)
            in_quiz = element in answers.index
            known = in_quiz and bool(answers.loc[element, "known"])
            your = float(answers.loc[element, "level"]) if known else None
            gap = None if your is None or pd.isna(required) else max(0.0, float(required) - your)
            if known:
                status = "build" if gap is not None and gap > GAP_MIN else "have"
            else:
                status = "not_assessed" if in_quiz else "not_measured"
            rows.append({
                "element": element, "kind": kind, "importance": _num(importance),
                "required_level": _num(required), "your_level": _num(your), "gap": _num(gap),
                "priority": _num(importance * gap) if status == "build" else None,
                "status": status,
                "quiz_row": ", ".join(answers.loc[element, "rows"]) if in_quiz else None,
                "start_from_scratch": bool(known and answers.loc[element, "scratch"]),
            })
    rows.sort(key=lambda r: (-r["importance"], r["element"]))
    return rows


def roadmap(student, data, code, job_zone=None, route_name=None):
    """Ordered roadmap steps. Each step has a stable key so progress can be saved per student.
    route_name: the matching Indian education route (config/career_paths.csv), if any."""
    from ml.pathways import suggested_stream
    needs = requirements(student, data, code)
    steps = []
    title, meaning = JOB_ZONES.get(job_zone, ("Preparation level not rated by O*NET", "Check the education "
                                              "usually asked for in job adverts for this career."))
    stream = suggested_stream(data, code)
    if stream and stream["because"]:
        steps.append({"key": "stream", "stage": "Foundation", "title": f"Choose your stream: {stream['stream']}",
                      "detail": "Suggested because this career uses " + ", ".join(stream["because"]) +
                                " (Pathfinder's suggestion from O*NET). Skip this step if you are past Class 12.",
                      "items": []})
    detail = f"O*NET: {title}. {meaning}"
    if route_name:
        detail += f" See the route '{route_name}' on the career page for the exams and degree."
    steps.append({"key": "education", "stage": "Foundation", "title": "Get the right qualification",
                  "detail": detail, "items": []})

    build = sorted([r for r in needs if r["status"] == "build"], key=lambda r: -r["priority"])
    first, second = STAGE_SIZES
    for stage, part in (("Start now", build[:first]), ("Next", build[first:first + second]),
                        ("Later", build[first + second:])):
        for r in part:
            steps.append({"key": f"build:{r['element']}", "stage": stage,
                          "title": f"Build {r['element']}" + (" (start from scratch)" if r["start_from_scratch"] else ""),
                          "detail": f"Needed at level {r['required_level']} of 7; you are at about "
                                    f"{r['your_level']}. Importance {r['importance']} of 5.",
                          "items": [r]})

    check = [r for r in needs if r["status"] in ("not_assessed", "not_measured")]
    if check:
        steps.append({"key": "check", "stage": "Next", "title": "Check these skills yourself",
                      "detail": "Important for this career, but your quiz answers do not tell us your level. "
                                "Try a beginner exercise or course in each and see where you stand.",
                      "items": check})
    steps.append({"key": "experience", "stage": "Later", "title": "Get real experience",
                  "detail": "Do an internship, a project, volunteering or a part-time job in this field. "
                            "It shows employers the skills above and tells you if you enjoy the work.",
                  "items": []})
    steps.append({"key": "apply", "stage": "Later", "title": "Look for openings",
                  "detail": "Search current job adverts in your preferred location to see what employers ask for.",
                  "items": []})
    return {"steps": steps, "requirements": needs}
