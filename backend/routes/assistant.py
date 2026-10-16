"""Endpoints that understand the student's own words.

POST /match/text       careers whose descriptions best match free text (Sentence-BERT or TF-IDF)
POST /assistant/chat   the career assistant chatbot (Gemini, grounded on our career records)
GET  /assistant/status whether the chatbot uses Gemini or offline mode, and which text matcher is used
Logic: ml/semantic.py (matching) and backend/assistant.py (retrieval + Gemini).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend import assistant, schemas
from backend.deps import (MIN_JOB_ZONE, AppContext, career_brief, career_code, get_context, optional_student,
                          own_assessment)
from ml.recommender_v2 import recommend_v2

router = APIRouter(tags=["assistant"])


def _matcher(ctx, timeout=60):
    m = ctx.get_matcher(timeout)
    if m is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The text matcher is still starting; try again shortly")
    return m


@router.post("/match/text", response_model=schemas.TextMatchOut)
def match_text(body: schemas.TextMatchIn, ctx: AppContext = Depends(get_context)):
    m = _matcher(ctx)
    return {"method": m.method,
            "results": [{**career_brief(ctx, code), "similarity": sim}
                        for code, sim in m.match(body.text, top_n=body.top_n) if code in ctx.career_ids]}


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
    top = recommend_v2(answers, ctx.data, top_n=5, min_job_zone=MIN_JOB_ZONE, diversity=True)
    return {"answers": answers, "top": [ctx.display_title(c) for c in top["code"]], "codes": list(top["code"])}


@router.post("/assistant/chat", response_model=schemas.ChatOut)
def chat(body: schemas.ChatIn, student_id: Optional[int] = Depends(optional_student),
         ctx: AppContext = Depends(get_context)):
    summary = _student_summary(ctx, student_id)
    extra = [career_code(ctx, body.career_id)] if body.career_id else []
    if summary:
        extra += summary["codes"][:3]
    codes = assistant.find_careers(ctx, body.message, ctx.get_matcher(timeout=5), extra)
    try:
        reply, mode = assistant.answer(ctx, body.message, [t.model_dump() for t in body.history], codes, summary)
    except assistant.GeminiError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err))
    except Exception as err:                      # network down, timeout ...
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not reach Gemini: {type(err).__name__}")
    return {"reply": reply, "mode": mode, "sources": [career_brief(ctx, c) for c in codes[:5]]}
