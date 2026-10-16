"""Explore careers by industry (Beauty & Wellness, Agriculture, Film & Entertainment, ...).

The categories and which O*NET codes belong to each are in config/industries.csv, so the team can
change them without touching code. Careers excluded for India (config/india_exclusions.csv) are never listed.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from backend import schemas
from backend.deps import AppContext, get_context
from ml.localise import industry_codes
from ml.recommender_v2 import field_of

router = APIRouter(tags=["explore"])


def _brief(ctx, code):
    return {"career_id": ctx.career_ids[code], "code": code, "title": ctx.official_title(code),
            "display_title": ctx.display_title(code), "field": field_of(code), "ranked": code in ctx.ranked,
            "matched_title": None, "excluded_reason": None, "job_zone": ctx.job_zone(code)}


@router.get("/industries", response_model=list[schemas.Industry])
def list_industries(ctx: AppContext = Depends(get_context)):
    """Every category with how many careers it holds."""
    return [{"id": i["id"], "name": i["name"], "description": i["description"],
             "careers": sum(c in ctx.career_ids for c in industry_codes(i, ctx.data))} for i in ctx.industries]


@router.get("/industries/{industry_id}", response_model=schemas.IndustryCareers)
def industry_careers(industry_id: str, ctx: AppContext = Depends(get_context)):
    """The careers in one category, A to Z by their short title."""
    industry = next((i for i in ctx.industries if i["id"] == industry_id), None)
    if industry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Industry {industry_id!r} not found")
    codes = [c for c in industry_codes(industry, ctx.data) if c in ctx.career_ids]
    return {"id": industry["id"], "name": industry["name"], "description": industry["description"],
            "careers": [_brief(ctx, c) for c in codes]}
