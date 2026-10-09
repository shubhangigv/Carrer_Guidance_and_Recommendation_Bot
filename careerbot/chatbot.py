"""Conversational layer for the career guidance bot.

The bot walks the user through a short questionnaire, builds a UserProfile,
asks the recommender for matches and then answers follow-up questions such as
"roadmap for data scientist" or "salary of lawyer".
"""

from __future__ import annotations

import re
from dataclasses import asdict

from .recommender import (
    EDUCATION_LEVELS,
    WORK_STYLES,
    CareerRecommender,
    Recommendation,
    UserProfile,
    parse_education,
    parse_list,
)

# (state, profile field, question)
QUESTIONS = [
    ("name", "name", "Hi! I'm CareerBot 🎓. I'll help you discover careers that suit you. What's your name?"),
    (
        "education",
        "education",
        "Nice to meet you, {name}! What is your current education level? "
        "(e.g. 10th, 12th, diploma, B.Tech, B.Com, master's)",
    ),
    (
        "interests",
        "interests",
        "What are you interested in or passionate about? List a few, separated by commas "
        "(e.g. technology, art, helping people, business, sports).",
    ),
    (
        "skills",
        "skills",
        "What are you good at? List your skills "
        "(e.g. coding, maths, communication, drawing, writing, leadership).",
    ),
    (
        "subjects",
        "subjects",
        "Which school/college subjects do you enjoy most? (e.g. maths, biology, economics, English)",
    ),
    (
        "work_style",
        "work_style",
        "Last one! How do you like to work? Pick any: " + ", ".join(WORK_STYLES) + ".",
    ),
]

HELP_TEXT = (
    "Here's what you can ask me:\n"
    "• **roadmap for <career>** – step-by-step plan\n"
    "• **salary of <career>** – typical salary in India\n"
    "• **about <career>** – full career details\n"
    "• **resources for <career>** – courses and websites\n"
    "• **categories** / **careers in <category>** – browse all careers\n"
    "• **recommend** – show my matches again\n"
    "• **restart** – start over"
)


def format_recommendation(i: int, rec: Recommendation) -> str:
    c = rec.career
    reasons = []
    labels = {"interests": "interests", "skills": "skills", "subjects": "subjects", "work_style": "work style"}
    for dim, label in labels.items():
        if rec.matched.get(dim):
            reasons.append(f"{label}: {', '.join(rec.matched[dim])}")
    why = "; ".join(reasons) if reasons else "general fit"
    text = (
        f"**{i}. {c['title']}** ({c['category']}) – {rec.percent}% match\n"
        f"   {c['description']}\n"
        f"   Why: {why}\n"
        f"   Salary: {c['avg_salary_inr']} | Growth: {c['growth']}"
    )
    if rec.education_note:
        text += f"\n   Note: {rec.education_note}"
    return text


def format_career(c: dict) -> str:
    steps = "\n".join(f"   {i}. {s}" for i, s in enumerate(c["roadmap"], 1))
    return (
        f"**{c['title']}** ({c['category']})\n"
        f"{c['description']}\n"
        f"• Key skills: {', '.join(c['skills'])}\n"
        f"• Good subjects: {', '.join(c['subjects'])}\n"
        f"• Minimum education: {c['min_education']}\n"
        f"• Salary: {c['avg_salary_inr']} | Growth: {c['growth']}\n"
        f"• Roadmap:\n{steps}\n"
        f"• Resources: {', '.join(c['resources'])}"
    )


class CareerBot:
    """A stateful chatbot. One instance per user conversation."""

    def __init__(self, recommender: CareerRecommender | None = None):
        self.recommender = recommender or CareerRecommender()
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        self.profile = UserProfile()
        self.step = 0
        self.results: list[Recommendation] = []

    @property
    def finished_questions(self) -> bool:
        return self.step >= len(QUESTIONS)

    def greeting(self) -> str:
        return QUESTIONS[0][2]

    def to_state(self) -> dict:
        """Serialisable state (used to store the conversation in a web session)."""
        return {"profile": asdict(self.profile), "step": self.step}

    @classmethod
    def from_state(cls, state: dict | None, recommender: CareerRecommender | None = None) -> "CareerBot":
        bot = cls(recommender)
        if state:
            bot.profile = UserProfile(**state.get("profile", {}))
            bot.step = state.get("step", 0)
            if bot.finished_questions:
                bot.results = bot.recommender.recommend(bot.profile)
        return bot

    # --------------------------------------------------------------- replies
    def reply(self, message: str) -> str:
        msg = (message or "").strip()
        lower = msg.lower()

        if lower in {"restart", "reset", "start over"}:
            self.reset()
            return self.greeting()
        if lower in {"help", "?", "menu"}:
            return HELP_TEXT

        if not self.finished_questions:
            return self._answer_question(msg)
        return self._follow_up(msg)

    def _answer_question(self, msg: str) -> str:
        if not msg:
            return "Please type an answer so I can help you. 🙂"
        state, attr, _ = QUESTIONS[self.step]

        if state == "name":
            name = re.sub(r"^(hi|hello|hey)?[,!\s]*(i'?m|i am|my name is|this is)?\s*", "", msg, flags=re.I)
            self.profile.name = (name.split() or [msg])[0].strip(".,!").title()[:30]
        elif state == "education":
            level = parse_education(msg)
            if not level:
                return (
                    "Sorry, I didn't catch that. Please choose one of: "
                    + ", ".join(EDUCATION_LEVELS)
                    + " (or say e.g. '12th', 'B.Tech')."
                )
            self.profile.education = level
        else:
            terms = parse_list(msg)
            if lower_skip(msg):
                terms = []
            setattr(self.profile, attr, terms)

        self.step += 1
        if self.finished_questions:
            return self._recommend_text()
        return QUESTIONS[self.step][2].format(name=self.profile.name or "friend")

    def _recommend_text(self) -> str:
        self.results = self.recommender.recommend(self.profile, top_n=3)
        if not self.results:
            return (
                "I couldn't find a strong match from your answers. Try 'restart' and give a few more "
                "interests or skills, or type 'categories' to browse careers."
            )
        body = "\n\n".join(format_recommendation(i, r) for i, r in enumerate(self.results, 1))
        return (
            f"Thanks, {self.profile.name}! Based on your profile, here are your top career matches:\n\n"
            f"{body}\n\n"
            "Want more? Try **roadmap for " + self.results[0].career["title"] + "** or type **help**."
        )

    def _follow_up(self, msg: str) -> str:
        lower = msg.lower()

        if lower in {"recommend", "recommendations", "results", "matches"}:
            return self._recommend_text()

        if lower in {"categories", "category", "list", "all careers"}:
            cats = self.recommender.categories()
            return "Career categories: " + ", ".join(cats) + ". Ask e.g. **careers in Technology**."

        m = re.match(r"(?:careers?|jobs?) in (.+)", lower)
        if m:
            careers = self.recommender.by_category(m.group(1))
            if not careers:
                return "I don't know that category. Type **categories** to see the list."
            return f"Careers in {careers[0]['category']}: " + ", ".join(c["title"] for c in careers)

        if re.match(r"^(thanks|thank you|bye|goodbye|ok|okay)\b", lower):
            return f"You're welcome, {self.profile.name}! All the best for your future. 🚀 (type 'restart' anytime)"

        intents = [
            ("roadmap", r"(roadmap|steps|how (do i|to) become|path)\b"),
            ("salary", r"(salary|pay|earn|income)"),
            ("resources", r"(resources?|courses?|learn|websites?)\b"),
            ("about", r"(about|details?|info|tell me|what is|describe)"),
        ]
        intent = next((name for name, pat in intents if re.search(pat, lower)), "about")
        career = self._career_from_text(lower)
        if not career:
            return "I'm not sure which career you mean. " + HELP_TEXT

        if intent == "roadmap":
            steps = "\n".join(f"{i}. {s}" for i, s in enumerate(career["roadmap"], 1))
            return f"Roadmap to become {article(career['title'])} **{career['title']}**:\n{steps}"
        if intent == "salary":
            return (
                f"{article(career['title']).title()} **{career['title']}** in India typically earns {career['avg_salary_inr']} "
                f"(growth outlook: {career['growth']})."
            )
        if intent == "resources":
            return f"Resources for **{career['title']}**: " + ", ".join(career["resources"])
        return format_career(career)

    def _career_from_text(self, text: str) -> dict | None:
        # "roadmap for #1" / "about 2" -> refer to the recommendation list.
        m = re.search(r"#?\b([1-9])\b", text)
        if m and self.results and int(m.group(1)) <= len(self.results):
            return self.results[int(m.group(1)) - 1].career
        cleaned = re.sub(
            r"\b(roadmap|steps|salary|pay|resources?|courses?|about|details?|info|tell me|what is|"
            r"describe|how (do i|to) become|for|of|a|an|the|me|to|become|path|earn|income|learn|websites?)\b",
            " ",
            text,
        )
        cleaned = re.sub(r"[^\w\s/-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return self.recommender.find(cleaned) if cleaned else None


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def lower_skip(msg: str) -> bool:
    return msg.strip().lower() in {"skip", "none", "no", "nothing", "-", "na", "n/a"}
