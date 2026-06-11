import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study, Analysis
from ..schemas import AnalysisOut
from ..services.statistics import run_meta_analysis, result_to_dict
from ..services.plots import generate_forest_plot, generate_funnel_plot, generate_rob_traffic_light, generate_prisma_2020

router = APIRouter(prefix="/reviews/{review_id}/analysis", tags=["analysis"])


def _study_dicts(review_id: int, db: Session) -> list[dict]:
    studies = db.query(Study).filter(Study.review_id == review_id).all()
    return [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in studies
    ]


@router.post("/run", response_model=AnalysisOut)
def run_analysis(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    study_data = _study_dicts(review_id, db)
    if not study_data:
        raise HTTPException(status_code=422, detail="No studies found for this review.")

    effect_measure = review.effect_measure or "OR"
    model_type = review.model_type or "random"

    try:
        result = run_meta_analysis(study_data, effect_measure, model_type)
    except ValueError:
        # Fallback: try pre-calculated effect sizes
        try:
            result = run_meta_analysis(study_data, "PRECALCULATED", model_type)
            effect_measure = "PRECALCULATED"
        except ValueError as exc2:
            raise HTTPException(status_code=422, detail=str(exc2))

    result_dict = result_to_dict(result)
    try:
        forest_b64 = generate_forest_plot(result, title=review.title or "Forest Plot")
    except Exception:
        forest_b64 = None
    try:
        funnel_b64 = generate_funnel_plot(result, title="Funnel Plot")
    except Exception:
        funnel_b64 = None
    try:
        rob_b64 = generate_rob_traffic_light(study_data)
    except Exception:
        rob_b64 = None

    analysis = Analysis(
        review_id=review_id,
        name=f"Analysis {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        effect_measure=effect_measure,
        model_type=model_type,
        results_json=json.dumps(result_dict),
        forest_plot_b64=forest_b64,
        funnel_plot_b64=funnel_b64,
        rob_plot_b64=rob_b64,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@router.get("/latest", response_model=AnalysisOut)
def get_latest_analysis(review_id: int, db: Session = Depends(get_db)):
    analysis = (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this review.")
    return analysis


@router.get("/", response_model=list[AnalysisOut])
def list_analyses(review_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .all()
    )


@router.get("/prisma")
def get_prisma_diagram(review_id: int, db: Session = Depends(get_db)):
    """Generate and return a PRISMA 2020 flowchart as base64 PNG."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    try:
        b64 = generate_prisma_2020(
            db_names=review.prisma_db_names,
            other_sources=review.prisma_other_sources,
            duplicates_removed=review.prisma_duplicates_removed,
            other_removed=review.prisma_other_removed,
            screened=review.prisma_screened,
            excluded_screening=review.prisma_excluded_screening,
            sought=review.prisma_sought,
            not_retrieved=review.prisma_not_retrieved,
            assessed=review.prisma_assessed,
            excluded_eligibility=review.prisma_excluded_eligibility,
            exclusion_reasons=review.prisma_exclusion_reasons,
            included=review.prisma_included,
            reports_included=review.prisma_reports_included,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating PRISMA diagram: {exc}")
    return {"prisma_b64": b64}
