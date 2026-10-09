"""Career recommendation engine.

Scores every career in the dataset against a user profile (skills, interests,
favourite subjects, work style and education level) and returns the best
matches together with a human-readable explanation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "careers.json"

# Ordered from lowest to highest.
EDUCATION_LEVELS = ["high school", "diploma", "bachelor", "master", "phd"]

# How much each profile dimension contributes to the final score.
WEIGHTS = {"skills": 0.35, "interests": 0.35, "subjects": 0.15, "work_style": 0.15}

# Maps common user phrasings to the vocabulary used in careers.json.
SYNONYMS = {
    "coding": "programming",
    "code": "programming",
    "developer": "programming",
    "software": "programming",
    "python": "programming",
    "java": "programming",
    "javascript": "programming",
    "maths": "mathematics",
    "math": "mathematics",
    "cs": "computer science",
    "computers science": "computer science",
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "stats": "statistics",
    "bio": "biology",
    "chem": "chemistry",
    "accounts": "accountancy",
    "painting": "drawing",
    "sketching": "drawing",
    "speaking": "public speaking",
    "public-speaking": "public speaking",
    "talking": "communication",
    "communicating": "communication",
    "leading": "leadership",
    "helping others": "helping people",
    "helping": "helping people",
    "social work": "helping people",
    "games": "gaming",
    "video games": "gaming",
    "sport": "sports",
    "gym": "fitness",
    "exercise": "fitness",
    "food": "cooking",
    "baking": "cooking",
    "movies": "media",
    "films": "media",
    "youtube": "social media",
    "instagram": "social media",
    "climate": "environment",
    "stocks": "finance",
    "investing": "finance",
    "economy": "economics",
    "polity": "political science",
    "civics": "political science",
    "pe": "physical education",
    "spreadsheets": "excel",
    "autocad": "cad",
    "solidworks": "cad",
    "team work": "teamwork",
    "working with people": "people",
    "alone": "independent",
    "solo": "independent",
    "logical": "analytical",
    "analytics": "analysis",
    "analysing": "analysis",
    "analyzing": "analysis",
    "practical": "hands-on",
    "hands on": "hands-on",
    "research work": "research",
}

WORK_STYLES = ["analytical", "creative", "people", "team", "independent", "research", "hands-on"]


def normalize(term: str) -> str:
    """Lower-case, trim and map a single term onto the dataset vocabulary."""
    term = re.sub(r"\s+", " ", term.strip().lower())
    term = term.strip(".!?")
    return SYNONYMS.get(term, term)


def parse_list(text: str | list[str] | None) -> list[str]:
    """Turn free text like "coding, maths and art" into normalised terms."""
    if not text:
        return []
    if isinstance(text, list):
        parts = text
    else:
        parts = re.split(r",|;|/|\band\b|\n|&", text, flags=re.IGNORECASE)
    terms = [normalize(p) for p in parts]
    # Preserve order, drop empties and duplicates.
    return list(dict.fromkeys(t for t in terms if t))


def parse_education(text: str | None) -> str | None:
    """Map free text onto one of EDUCATION_LEVELS."""
    if not text:
        return None
    t = text.lower()
    patterns = [
        ("phd", r"ph\.?d|doctorate"),
        ("master", r"master|\bm\.?tech|\bm\.?sc|\bmba\b|\bm\.?a\b|\bm\.?com|post ?grad|\bpg\b"),
        ("bachelor", r"bachelor|\bb\.?tech|\bb\.?e\b|\bb\.?sc|\bb\.?com|\bb\.?a\b|\bbba\b|\bbca\b|degree|graduat|college|undergrad"),
        ("diploma", r"diploma|polytechnic|\biti\b"),
        ("high school", r"school|\b1[02]|class|grade|\bhsc\b|\bssc\b|\bpuc\b|intermediate|student"),
    ]
    for level, pattern in patterns:
        if re.search(pattern, t):
            return level
    return None


@dataclass
class UserProfile:
    name: str = ""
    education: str | None = None
    skills: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    work_style: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    career: dict
    score: float
    matched: dict[str, list[str]]
    education_note: str

    @property
    def percent(self) -> int:
        return round(self.score * 100)

    def to_dict(self) -> dict:
        return {
            "id": self.career["id"],
            "title": self.career["title"],
            "category": self.career["category"],
            "description": self.career["description"],
            "match_percent": self.percent,
            "matched": self.matched,
            "education_note": self.education_note,
            "avg_salary_inr": self.career["avg_salary_inr"],
            "growth": self.career["growth"],
            "roadmap": self.career["roadmap"],
            "resources": self.career["resources"],
        }


def load_careers(path: Path = DATA_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _matches(user_terms: list[str], career_terms: list[str]) -> list[str]:
    """Return the career terms the user matched (exact or partial word match)."""
    found = []
    for c in career_terms:
        for u in user_terms:
            if u == c or (len(u) > 3 and (u in c or c in u)):
                found.append(c)
                break
    return found


class CareerRecommender:
    def __init__(self, careers: list[dict] | None = None):
        self.careers = careers if careers is not None else load_careers()

    def find(self, query: str) -> dict | None:
        """Look up a career by id, exact title, or partial title."""
        q = query.strip().lower()
        if not q:
            return None
        for c in self.careers:
            if q in (c["id"], c["title"].lower()):
                return c
        for c in self.careers:
            title = c["title"].lower()
            if q in title or any(w in q.split() for w in re.split(r"\W+", title) if len(w) > 3):
                return c
        return None

    def score(self, profile: UserProfile, career: dict) -> Recommendation:
        matched: dict[str, list[str]] = {}
        total = 0.0
        for dim, weight in WEIGHTS.items():
            user_terms = getattr(profile, dim)
            career_terms = career[dim]
            hits = _matches(user_terms, career_terms)
            matched[dim] = hits
            if career_terms:
                # Matching ~half of a career's attributes counts as a full match
                # for that dimension; nobody is expected to tick every box.
                coverage = min(1.0, len(hits) / max(1, min(len(career_terms), 3)))
                total += weight * coverage

        note = ""
        if profile.education:
            user_lvl = EDUCATION_LEVELS.index(profile.education)
            need_lvl = EDUCATION_LEVELS.index(career["min_education"])
            if user_lvl < need_lvl:
                note = f"Requires at least a {career['min_education']} level qualification - plan for it."
                # Small nudge only: students can still pursue the path.
                total *= 0.95
        return Recommendation(career=career, score=round(total, 4), matched=matched, education_note=note)

    def recommend(self, profile: UserProfile, top_n: int = 3) -> list[Recommendation]:
        results = [self.score(profile, c) for c in self.careers]
        results = [r for r in results if r.score > 0]
        results.sort(key=lambda r: (-r.score, r.career["title"]))
        return results[:top_n]

    def categories(self) -> list[str]:
        return sorted({c["category"] for c in self.careers})

    def by_category(self, category: str) -> list[dict]:
        return [c for c in self.careers if c["category"].lower() == category.strip().lower()]
