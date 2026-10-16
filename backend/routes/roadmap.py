"""Skills to build and the roadmap for one career, with progress saved per student.

GET  /careers/{id}/requirements   every important O*NET skill and knowledge area of the career;
                                  with ?assessment_id= (logged in) also the student's level and status
GET  /roadmap/{career_id}         the student's step-by-step plan + which steps are done
PUT  /roadmap/{career_id}/progress   tick or untick one step
GET  /roadmaps                    careers the student has started a roadmap for
GET  /careers/{id}/pathway        how to get there: Indian routes, stream, O*NET education, career ladder, courses
The logic is in ml/career_needs.py; this file only checks login and ownership and saves progress.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend import schemas
from backend.deps import AppContext, career_code, current_student, get_context, optional_student, own_assessment
from ml.career_needs import requirements, roadmap
from ml.pathways import career_ladder, courses_for, education_for, routes_for, suggested_stream

router = APIRouter(tags=["roadmap"])


def _latest_student(ctx, student_id, assessment_id=None):
    """The student's answers from the given (or latest) assessment; None if they have none yet."""
    assessment_id = assessment_id or ctx.repo.latest_assessment_id(student_id)
    return own_assessment(ctx, assessment_id, student_id) if assessment_id else None


@router.get("/careers/{career_id}/requirements", response_model=schemas.RequirementsOut)
def career_requirements(career_id: int, assessment_id: Optional[int] = None,
                        student_id: Optional[int] = Depends(optional_student),
                        ctx: AppContext = Depends(get_context)):
    code = career_code(ctx, career_id)
    student = None
    if student_id is not None:
        student = _latest_student(ctx, student_id, assessment_id)
    elif assessment_id is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Log in to compare with your answers")
    return {"career_id": career_id, "display_title": ctx.display_title(code),
            "requirements": requirements(student, ctx.data, code)}


@router.get("/roadmap/{career_id}", response_model=schemas.RoadmapOut)
def get_roadmap(career_id: int, student_id: int = Depends(current_student), ctx: AppContext = Depends(get_context)):
    code = career_code(ctx, career_id)
    student = _latest_student(ctx, student_id)
    route = next(iter(routes_for(code, ctx.routes)), None)
    plan = roadmap(student, ctx.data, code, ctx.job_zone(code), route["name"] if route else None)
    done = ctx.repo.get_progress(student_id, career_id)
    steps = [{**s, "done": s["key"] in done} for s in plan["steps"]]
    return {"career_id": career_id, "code": code, "display_title": ctx.display_title(code),
            "career": ctx.official_title(code), "job_zone": ctx.job_zone(code),
            "preferred_location": (student or {}).get("preferred_location"), "steps": steps,
            "done": sum(s["done"] for s in steps), "total": len(steps)}


@router.put("/roadmap/{career_id}/progress", response_model=schemas.RoadmapOut)
def set_progress(career_id: int, body: schemas.ProgressIn, student_id: int = Depends(current_student),
                 ctx: AppContext = Depends(get_context)):
    code = career_code(ctx, career_id)
    keys = {s["key"] for s in roadmap(_latest_student(ctx, student_id), ctx.data, code, ctx.job_zone(code))["steps"]}
    if body.step_key not in keys:
        raise HTTPException(422, f"Unknown roadmap step {body.step_key!r}")
    ctx.repo.set_progress(student_id, career_id, body.step_key, body.done)
    return get_roadmap(career_id, student_id, ctx)


@router.get("/roadmaps", response_model=list[schemas.RoadmapSummary])
def my_roadmaps(student_id: int = Depends(current_student), ctx: AppContext = Depends(get_context)):
    return [{"career_id": cid, "display_title": ctx.display_title(ctx.codes_by_id[cid]), "done": n}
            for cid, n in ctx.repo.roadmap_careers(student_id) if cid in ctx.codes_by_id]


@router.get("/careers/{career_id}/pathway", response_model=schemas.PathwayOut)
def career_pathway(career_id: int, student_id: Optional[int] = Depends(optional_student),
                   ctx: AppContext = Depends(get_context)):
    code = career_code(ctx, career_id)
    student = _latest_student(ctx, student_id) if student_id is not None else None
    needs = requirements(student, ctx.data, code)
    wanted = [r["element"] for r in needs if r["status"] == "build"] or [r["element"] for r in needs[:8]]
    ladder = career_ladder(ctx.data, code)
    to_out = lambda rows: [{"career_id": ctx.career_ids[r["code"]], "display_title": ctx.display_title(r["code"]),  # noqa: E731
                            "job_zone": r["job_zone"], "source": r["source"]} for r in rows if r["code"] in ctx.career_ids]
    return {"career_id": career_id, "display_title": ctx.display_title(code), "job_zone": ctx.job_zone(code),
            "stream": suggested_stream(ctx.data, code),
            "routes": [{k: r[k] for k in ("id", "name", "verified", "steps")} for r in routes_for(code, ctx.routes)],
            "education_us": education_for(ctx.data, code),
            "ways_in": to_out(ladder["ways_in"]), "grow_into": to_out(ladder["grow_into"]),
            "courses": courses_for(wanted, ctx.courses)}
