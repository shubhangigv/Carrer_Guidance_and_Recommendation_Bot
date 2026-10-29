"""Endpoints that understand the student's own words.

POST /match/text       careers whose descriptions best match free text (Sentence-BERT or TF-IDF)
POST /assistant/chat   the career assistant chatbot (Gemini, grounded on our career records)
GET  /assistant/status whether the chatbot uses Gemini or offline mode, and which text matcher is used
Logic: ml/semantic.py (matching) and backend/assistant.py (retrieval + Gemini).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend import assistant, schemas
from backend.deps import (MIN_JOB_ZONE, AppContext, career_brief, career_code, get_context, optional_student,
                          own_assessment, personal_recommend)
from ml.recommender_v2 import eligible_codes

router = APIRouter(tags=["assistant"])
log = logging.getLogger("pathfinder.assistant")


def _matcher(ctx, timeout=60):
    m = ctx.get_matcher(timeout)
    if m is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The text matcher is still starting; try again shortly")
    return m


@router.post("/match/text", response_model=schemas.TextMatchOut)
def match_text(body: schemas.TextMatchIn, ctx: AppContext = Depends(get_context)):
    m = _matcher(ctx)
    pool = eligible_codes(ctx.data, MIN_JOB_ZONE)        # same careers as the quiz (Job Zone >= 3)
    return {"method": m.method,
            "results": [{**career_brief(ctx, code), "similarity": sim}
                        for code, sim in m.match(body.text, top_n=body.top_n, codes=pool) if code in ctx.career_ids]}


@router.get("/assistant/status", response_model=schemas.AssistantStatus)
def assistant_status(ctx: AppContext = Depends(get_context)):
    m = ctx.get_matcher(timeout=0)
    return {"mode": "gemini" if assistant.gemini_key() else "offline", "semantic_method": m.method if m else None}


def _student_summary(ctx, student_id):
    """The student's answers and current top 5 (titles) for the assistant; None if logged out / no quiz."""
    if student_id is None:
        return None
    aid = ctx.repo.latest_assessment_id(student_id)
    if not aid:
        return None
    answers = own_assessment(ctx, aid, student_id)
    top, _ = personal_recommend(ctx, answers, top_n=5, hidden_ids=ctx.repo.hidden_careers(student_id))
    return {"answers": answers, "top": [ctx.display_title(c) for c in top["code"]], "codes": list(top["code"])}


@router.post("/assistant/chat", response_model=schemas.ChatOut)
def chat(body: schemas.ChatIn, student_id: Optional[int] = Depends(optional_student),
         ctx: AppContext = Depends(get_context)):
    summary = _student_summary(ctx, student_id)
    extra = [career_code(ctx, body.career_id)] if body.career_id else []
    if summary:
        extra += summary["codes"][:3]
    codes = assistant.find_careers(ctx, body.message, ctx.get_matcher(timeout=5), extra)
    # If Gemini fails (busy, limit, wrong key, no internet), answer from our own data instead of an error,
    # so the chat never breaks; the reason is the first line of the reply.
    try:
        reply, mode = assistant.answer(ctx, body.message, [t.model_dump() for t in body.history], codes, summary)
    except assistant.GeminiError as err:
        log.warning("Chat fell back to offline: %s", err)
        reply, mode = assistant.offline_reply(ctx, codes, f"The AI could not answer just now. {err}"), "offline"
    except Exception as err:                      # network down, timeout ...
        log.warning("Chat fell back to offline: %s", type(err).__name__)
        reply, mode = assistant.offline_reply(
            ctx, codes, "The AI could not answer just now (Gemini could not be reached). Try again in a minute."
        ), "offline"
    return {"reply": reply, "mode": mode, "sources": [career_brief(ctx, c) for c in codes[:5]]}
