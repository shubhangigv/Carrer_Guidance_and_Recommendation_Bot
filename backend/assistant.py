"""The career assistant: a chatbot that answers from OUR career records (retrieval-augmented generation).

How one answer is made:
  1. Retrieve: find the careers the question is about - the semantic matcher (ml/semantic.py) on the
     question, careers named in it, the career page the student is looking at, and (if logged in) the
     student's own top matches.
  2. Ground: turn those careers into short text records (title, field, preparation, most important
     skills and knowledge, cited salary or "not in our data").
  3. Generate: send the records + the conversation to Google Gemini with strict instructions to use
     only the records for career facts and to say when it does not know.
Without a GEMINI_API_KEY in .env the assistant still answers in "offline" mode: it lists the matching
careers from the database instead of writing free text.

Settings (.env): GEMINI_API_KEY (from https://aistudio.google.com), GEMINI_MODEL (default below).
"""
import logging
import os

import httpx

from ml.career_needs import JOB_ZONES, requirements

log = logging.getLogger("pathfinder.assistant")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"
MAX_RECORDS = 8
TIMEOUT_SECONDS = 40

SYSTEM_PROMPT = """You are Pathfinder's career assistant for students in India (mostly college students).
Be warm, practical and brief: at most about 150 words unless the student asks for detail. Use simple English.

Rules:
- For facts about a career (what it is, skills, knowledge, preparation level, salary) use ONLY the
  CAREER RECORDS below. If the records do not contain the answer, say you do not have that information
  and suggest where the student can check (for example official exam or college websites, or job adverts).
- Never invent numbers: no salaries, fees, cut-offs, exam dates, statistics or college rankings that are
  not in the records. A record that says "Salary in India: not in our data" means you must not guess one.
- You may give general counselling advice (how to choose, how to explore, how to build a skill, how to
  talk to parents) without records, but say it is general advice.
- Do not judge or use gender, religion, caste or family background. Do not discourage any career.
- When you mention a career from the records, use its short title. Refer students to the app's pages:
  "Matches", "Explore", career details ("Skills to build") and "Roadmap".
- If the student seems distressed, be kind and suggest talking to someone they trust or a counsellor.
"""


def gemini_key():
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def career_record(ctx, code, student=None):
    """One career as a short text record for the model."""
    jz = ctx.job_zone(code)
    prep = f"Job Zone {jz} of 5 - {JOB_ZONES[jz][0]}: {JOB_ZONES[jz][1]}" if jz in JOB_ZONES else "not rated"
    needs = requirements(student, ctx.data, code)
    skills = [f"{r['element']} ({r['importance']}/5)" for r in needs if r["kind"] == "skill"][:8]
    knowledge = [f"{r['element']} ({r['importance']}/5)" for r in needs if r["kind"] == "knowledge"][:6]
    to_build = [r["element"] for r in needs if r["status"] == "build"][:5]
    salary = ctx.salary(code)
    salary_text = (f"{salary['min_lpa']}-{salary['max_lpa']} lakh per year (source: {salary['source_name']}"
                   f"{', ' + salary['year'] if salary['year'] else ''})" if salary else "not in our data")
    names = {i["id"]: i["name"] for i in ctx.industries}
    desc = str(ctx.data["occupations"].loc[code].get("Description") or "")
    lines = [f"[career_id {ctx.career_ids.get(code)}] {ctx.display_title(code)} "
             f"(official O*NET title: {ctx.official_title(code)})",
             f"Industries: {', '.join(names[i] for i in ctx.industry_ids(code) if i in names) or 'other'}",
             f"Description: {desc}", f"Preparation: {prep}",
             f"Most important skills: {', '.join(skills) or 'not rated'}",
             f"Most important knowledge: {', '.join(knowledge) or 'not rated'}",
             f"Salary in India: {salary_text}"]
    if ctx.excluded_reason(code):
        lines.append(f"Not recommended in India by Pathfinder: {ctx.excluded_reason(code)}")
    if to_build:
        lines.append(f"This student still needs to build: {', '.join(to_build)}")
    return "\n".join(lines)


def find_careers(ctx, message, matcher=None, extra_codes=(), n=MAX_RECORDS):
    """Careers the question is about, most relevant first (no duplicates)."""
    text = message.lower()
    named = [c for c in ctx.data["occupations"].index
             if len(ctx.display_title(c)) > 3 and ctx.display_title(c).lower() in text]
    semantic = [c for c, _ in matcher.match(message, top_n=n)] if matcher is not None else []
    out = []
    for c in list(extra_codes) + named + semantic:
        if c in ctx.career_ids and c not in out:
            out.append(c)
    return out[:n]


def offline_reply(ctx, codes):
    if not codes:
        return ("The AI assistant is not switched on (no GEMINI_API_KEY in .env), and I could not find a "
                "career matching your words. Try the Explore page or Search with a job name.")
    names = "\n".join(f"- {ctx.display_title(c)}" for c in codes[:5])
    return ("The AI assistant is not switched on (no GEMINI_API_KEY in .env), so here are the careers in our "
            f"database that match your message:\n{names}\nOpen one from Search to see its skills and roadmap.")


class GeminiError(Exception):
    pass


class GeminiClient:
    """Minimal Gemini REST client (generateContent). The model can be changed with GEMINI_MODEL."""

    def __init__(self, key, model=None, http=None):
        self.key = key
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.http = http or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _post(self, model, body):
        return self.http.post(f"{GEMINI_URL}/models/{model}:generateContent", json=body,
                              headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})

    def _pick_available_model(self):
        """When the configured model no longer exists: ask Google which models this key can use and pick
        a current general 'flash' model (else the first that supports generateContent)."""
        r = self.http.get(f"{GEMINI_URL}/models", headers={"x-goog-api-key": self.key}, params={"pageSize": 200})
        if r.status_code != 200:
            return None
        models = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", [])]
        skip = ("preview", "exp", "tts", "image", "live", "audio", "embedding", "thinking", "lite")
        flash = sorted((m for m in models if "flash" in m and not any(s in m for s in skip)), reverse=True)
        return (flash or models or [None])[0]

    def generate(self, system, turns, temperature=0.4, max_tokens=700):
        body = {"system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "model" if t["role"] == "assistant" else "user", "parts": [{"text": t["text"]}]}
                             for t in turns],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        r = self._post(self.model, body)
        if r.status_code == 404:                     # model retired or renamed
            better = self._pick_available_model()
            if better and better != self.model:
                log.warning("Gemini model %s not found; using %s (set GEMINI_MODEL in .env)", self.model, better)
                self.model = better
                r = self._post(self.model, body)
        if r.status_code in (401, 403):
            raise GeminiError("Gemini refused the API key. Check GEMINI_API_KEY in .env.")
        if r.status_code == 429:
            raise GeminiError("Gemini's free limit was reached. Wait a minute and try again.")
        if r.status_code != 200:
            raise GeminiError(f"Gemini error {r.status_code}: {r.text[:200]}")
        data = r.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            reason = (data.get("promptFeedback") or {}).get("blockReason") or \
                     (data.get("candidates") or [{}])[0].get("finishReason")
            raise GeminiError(f"Gemini returned no answer ({reason or 'empty reply'}). Try rephrasing.")
        return text


def answer(ctx, message, history, codes, student_summary=None, client=None):
    """(reply text, mode). mode is "gemini" or "offline"."""
    key = gemini_key()
    if client is None and not key:
        return offline_reply(ctx, codes), "offline"
    client = client or GeminiClient(key)
    records = "\n\n".join(career_record(ctx, c, student_summary.get("answers") if student_summary else None)
                          for c in codes) or "(no matching careers found)"
    system = SYSTEM_PROMPT + "\nCAREER RECORDS:\n" + records
    if student_summary and student_summary.get("top"):
        system += "\n\nTHIS STUDENT'S CURRENT TOP MATCHES (from their quiz): " + ", ".join(student_summary["top"])
    turns = [t for t in history if t.get("text")][-10:]
    while turns and turns[0]["role"] != "user":          # Gemini wants the conversation to start with the user
        turns.pop(0)
    turns.append({"role": "user", "text": message})
    return client.generate(system, turns), "gemini"
