import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study, Analysis
from ..schemas import AnalysisOut
from ..services.statistics import run_meta_analysis, result_to_dict
from ..services.plots import generate_forest_plot, generate_funnel_plot, generate_rob_traffic_light, generate_prisma_2020, generate_grade_table  # used by on-demand endpoints
from ..services.ai_generator import generate_prisma_autofill, screen_studies_with_ai, extract_quantitative_data

router = APIRouter(prefix="/reviews/{review_id}/analysis", tags=["analysis"])


def _study_dicts(review_id: int, db: Session, only_included: bool = True) -> list[dict]:
    q = db.query(Study).filter(Study.review_id == review_id)
    if only_included:
        q = q.filter(Study.included == True)  # noqa: E712
    return [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in q.all()
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

    # Plots are generated on-demand via /forest, /funnel, /grade endpoints
    # to avoid OOM — do NOT generate them here
    analysis = Analysis(
        review_id=review_id,
        name=f"Analysis {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        effect_measure=effect_measure,
        model_type=model_type,
        results_json=json.dumps(result_dict),
        forest_plot_b64=None,
        funnel_plot_b64=None,
        rob_plot_b64=None,
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


def _get_latest_or_404(review_id: int, db: Session):
    analysis = (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found. Run the meta-analysis first.")
    return analysis


@router.get("/forest")
def get_forest_plot(review_id: int, db: Session = Depends(get_db)):
    """Return (or regenerate) the forest plot for the latest analysis."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    if analysis.forest_plot_b64:
        return {"forest_b64": analysis.forest_plot_b64}
    # Regenerate from stored results
    try:
        from ..services.statistics import MetaResult
        result_dict = json.loads(analysis.results_json)
        result = run_meta_analysis(_study_dicts(review_id, db), analysis.effect_measure, analysis.model_type)
        b64 = generate_forest_plot(result, title=review.title or "Forest Plot")
        analysis.forest_plot_b64 = b64
        db.commit()
        return {"forest_b64": b64}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating forest plot: {exc}")


@router.get("/funnel")
def get_funnel_plot(review_id: int, db: Session = Depends(get_db)):
    """Return (or regenerate) the funnel plot for the latest analysis."""
    analysis = _get_latest_or_404(review_id, db)
    if analysis.funnel_plot_b64:
        return {"funnel_b64": analysis.funnel_plot_b64}
    try:
        result = run_meta_analysis(_study_dicts(review_id, db), analysis.effect_measure, analysis.model_type)
        b64 = generate_funnel_plot(result, title="Funnel Plot")
        analysis.funnel_plot_b64 = b64
        db.commit()
        return {"funnel_b64": b64}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating funnel plot: {exc}")


@router.get("/grade")
def get_grade_table(review_id: int, db: Session = Depends(get_db)):
    """Generate a GRADE evidence profile table."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    try:
        result_dict = json.loads(analysis.results_json)
        studies = _study_dicts(review_id, db)
        b64 = generate_grade_table(result_dict, studies, outcome=review.title or "")
        return {"grade_b64": b64}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating GRADE table: {exc}")


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


@router.post("/prisma/autofill")
def autofill_prisma(review_id: int, db: Session = Depends(get_db)):
    """Use AI to generate and save realistic PRISMA numbers based on the review's studies."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    study_count = db.query(Study).filter(Study.review_id == review_id).count()
    if study_count == 0:
        raise HTTPException(status_code=422, detail="Agrega estudios a la revisión antes de auto-generar el PRISMA.")

    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}

    try:
        data = generate_prisma_autofill(review_dict, study_count)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en generación IA del PRISMA: {exc}")

    # Persist generated values to the review
    for field, value in data.items():
        if hasattr(review, field):
            setattr(review, field, value)
    db.commit()
    db.refresh(review)

    return {
        "message": f"PRISMA auto-generado para {study_count} estudios incluidos",
        "data": data,
    }


@router.post("/ai-screen")
def ai_screen_studies(review_id: int, db: Session = Depends(get_db)):
    """Use AI to screen all studies against PICO criteria and set included/exclusion_reason."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    all_studies = db.query(Study).filter(Study.review_id == review_id).all()
    if not all_studies:
        raise HTTPException(status_code=422, detail="No hay estudios para cribar.")

    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
    studies_list = [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in all_studies
    ]

    try:
        decisions = screen_studies_with_ai(review_dict, studies_list)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en cribado IA: {exc}")

    included_count = 0
    excluded_count = 0
    for study in all_studies:
        decision = decisions.get(study.id)
        if decision is None:
            continue
        study.included = decision["included"]
        study.exclusion_reason = decision.get("reason") if not decision["included"] else None
        if decision["included"]:
            included_count += 1
        else:
            excluded_count += 1

    db.commit()
    return {
        "message": f"Cribado completado: {included_count} incluidos, {excluded_count} excluidos",
        "included": included_count,
        "excluded": excluded_count,
    }


@router.post("/ai-extract")
def ai_extract_data(review_id: int, db: Session = Depends(get_db)):
    """
    Use AI to extract quantitative outcome data from each study's abstract.
    Only processes included studies that are missing quantitative fields.
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    studies = db.query(Study).filter(
        Study.review_id == review_id,
        Study.included == True,  # noqa: E712
    ).all()
    if not studies:
        raise HTTPException(status_code=422, detail="No hay estudios incluidos para extraer datos.")

    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
    studies_list = [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in studies
    ]

    try:
        extractions = extract_quantitative_data(review_dict, studies_list)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en extracción IA: {exc}")

    updated_count = 0
    numeric_fields = {
        "events_intervention", "total_intervention", "events_control", "total_control",
        "mean_intervention", "sd_intervention", "n_intervention",
        "mean_control", "sd_control", "n_control",
        "effect_size", "effect_size_lower", "effect_size_upper", "sample_size",
    }

    study_map = {s.id: s for s in studies}
    for study_id, fields in extractions.items():
        study = study_map.get(study_id)
        if not study:
            continue
        changed = False
        for field, value in fields.items():
            if field not in numeric_fields:
                continue
            if getattr(study, field, None) is None and value is not None:
                try:
                    if field in {"events_intervention", "total_intervention", "events_control",
                                 "total_control", "n_intervention", "n_control", "sample_size"}:
                        setattr(study, field, int(float(value)))
                    else:
                        setattr(study, field, float(value))
                    changed = True
                except (TypeError, ValueError):
                    pass
        if changed:
            updated_count += 1

    db.commit()
    return {
        "message": f"Extracción completada: {updated_count} estudios actualizados con datos numéricos",
        "updated": updated_count,
        "total_included": len(studies),
        "candidates_with_abstract": len([s for s in studies_list if s.get("abstract_text")]),
    }
