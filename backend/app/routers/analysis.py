import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study, Analysis
from ..schemas import AnalysisOut
from ..services.statistics import run_meta_analysis, result_to_dict, meta_result_from_dict
from ..services.plots import generate_forest_plot, generate_funnel_plot, generate_rob_traffic_light, generate_prisma_2020, generate_grade_table  # used by on-demand endpoints
from ..services.prisma import sync_prisma, prisma_plot_kwargs
from ..services.eligibility import eligible_studies, pending_count, find_duplicates
from ..services.plots import _short_label
from ..services.ai_generator import (
    screen_studies_with_ai, extract_quantitative_data, eligibility_block,
    assess_risk_of_bias, ROB_DOMAIN_KEYS,
    interpret_forest_plot, interpret_funnel_plot, interpret_grade_table, interpret_rob_plot,
)

router = APIRouter(prefix="/reviews/{review_id}/analysis", tags=["analysis"])


def _study_dicts(review_id: int, db: Session) -> list[dict]:
    return [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in eligible_studies(db, review_id)
    ]


@router.post("/run", response_model=AnalysisOut)
def run_analysis(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    pending = pending_count(db, review_id)
    if pending:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Hay {pending} estudio(s) sin cribar. Ejecuta el cribado (o decide manualmente su "
                "inclusión) antes del metaanálisis: solo se analizan estudios que cumplen los criterios."
            ),
        )
    study_data = _study_dicts(review_id, db)
    if not study_data:
        raise HTTPException(status_code=422, detail="No hay estudios incluidos tras el cribado para analizar.")

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

    # "Studies included in review" (prisma_included) counts every study marked
    # included=True; "Reports of included studies" must instead reflect how many
    # of those actually made it into the pooled estimate (k) — a study can be
    # included in the qualitative review but dropped from the meta-analysis for
    # lacking quantitative data. Keeping these in sync is what makes the PRISMA
    # diagram match the number the Pipeline IA actually analyzed.
    review.prisma_reports_included = result.k

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
    """Return (or regenerate) the forest plot + AI interpretation."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    result_dict = json.loads(analysis.results_json)

    # Always regenerate (ensures fresh output, bypasses any stale cache)
    try:
        result = meta_result_from_dict(result_dict)
        b64 = generate_forest_plot(result, title=review.title or "Forest Plot")
        if not b64:
            raise ValueError("generate_forest_plot returned empty result")
        analysis.forest_plot_b64 = b64
        db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating forest plot: {exc}")

    # AI interpretation (always fresh, non-fatal)
    interpretation = ""
    try:
        review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
        interpretation = interpret_forest_plot(review_dict, result_dict)
    except Exception:
        pass

    return {"forest_b64": b64, "interpretation": interpretation}


@router.get("/funnel")
def get_funnel_plot(review_id: int, db: Session = Depends(get_db)):
    """Return (or regenerate) the funnel plot + AI interpretation."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    result_dict = json.loads(analysis.results_json)

    try:
        result = meta_result_from_dict(result_dict)
        b64 = generate_funnel_plot(result, title="Funnel Plot")
        if not b64:
            raise ValueError("generate_funnel_plot returned empty result")
        analysis.funnel_plot_b64 = b64
        db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating funnel plot: {exc}")

    interpretation = ""
    try:
        review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
        interpretation = interpret_funnel_plot(review_dict, result_dict)
    except Exception:
        pass

    return {"funnel_b64": b64, "interpretation": interpretation}


@router.get("/grade")
def get_grade_table(review_id: int, db: Session = Depends(get_db)):
    """Generate a GRADE evidence profile table + AI interpretation."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    result_dict = json.loads(analysis.results_json)
    studies = _study_dicts(review_id, db)

    try:
        b64 = generate_grade_table(result_dict, studies, outcome=review.title or "")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating GRADE table: {exc}")

    interpretation = ""
    try:
        review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
        interpretation = interpret_grade_table(review_dict, result_dict, studies)
    except Exception:
        pass

    return {"grade_b64": b64, "interpretation": interpretation}


@router.get("/rob")
def get_rob_plot(review_id: int, db: Session = Depends(get_db)):
    """Generate the Cochrane RoB 2 risk-of-bias traffic-light plot + AI interpretation.

    Unlike forest/funnel/grade, this doesn't depend on the meta-analysis
    result — only on each study's rob_* domain ratings — but it's still
    stored on the latest Analysis row (where rob_plot_b64 lives) so it
    persists for the PDF export the same way the other plots do.
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    studies = _study_dicts(review_id, db)
    if not studies:
        raise HTTPException(status_code=422, detail="No hay estudios incluidos con datos de riesgo de sesgo.")

    try:
        b64 = generate_rob_traffic_light(studies)
        analysis.rob_plot_b64 = b64
        db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generando el gráfico de riesgo de sesgo: {exc}")

    interpretation = ""
    try:
        review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
        interpretation = interpret_rob_plot(review_dict, studies)
    except Exception:
        pass

    return {"rob_b64": b64, "interpretation": interpretation}


@router.get("/prisma")
def get_prisma_diagram(review_id: int, db: Session = Depends(get_db)):
    """Recompute the PRISMA 2020 flow from the records and return it as a base64 PNG."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    result = sync_prisma(db, review)
    try:
        b64 = generate_prisma_2020(**prisma_plot_kwargs(result["fields"]))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating PRISMA diagram: {exc}")
    return {"prisma_b64": b64, **result}


@router.post("/prisma/compute")
def compute_prisma_flow(review_id: int, db: Session = Depends(get_db)):
    """Exact PRISMA counts derived from the search log and every record's screening decision."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return sync_prisma(db, review)


@router.post("/ai-screen")
def ai_screen_studies(review_id: int, db: Session = Depends(get_db)):
    """Use AI to screen pending studies against PICO criteria and set included/exclusion_reason.

    Studies that already have an inclusion decision (manually toggled by the user,
    or screened by a previous AI run) are skipped, so this never overwrites a
    selection that was already made — e.g. the final set of studies you curated
    to match the PRISMA flow diagram.
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    all_studies = db.query(Study).filter(Study.review_id == review_id).all()
    if not all_studies:
        raise HTTPException(status_code=422, detail="No hay estudios para cribar.")

    pending_studies = [s for s in all_studies if not s.screening_reviewed]
    already_reviewed = len(all_studies) - len(pending_studies)

    if not pending_studies:
        return {
            "message": (
                f"No hay estudios pendientes de cribar: los {already_reviewed} estudios "
                "ya tienen una decisión de inclusión/exclusión (manual o de un cribado IA previo)."
            ),
            "included": 0,
            "excluded": 0,
            "skipped_already_reviewed": already_reviewed,
        }

    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
    if not eligibility_block(review_dict).strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Define primero los criterios de elegibilidad de la revisión (PICO y/o criterios "
                "de inclusión y exclusión) antes de ejecutar el cribado."
            ),
        )

    duplicates = find_duplicates(all_studies, pending_studies)
    for study in pending_studies:
        original = duplicates.get(study.id)
        if original is None:
            continue
        study.included = False
        study.screening_decision = "exclude"
        study.screening_stage = "title_abstract"
        study.screening_reviewed = True
        study.exclusion_reason = (
            f"Duplicado: mismo DOI o título que el registro "
            f"'{_short_label(original.study_label or original.title or str(original.id))}'"
        )
    pending_studies = [s for s in pending_studies if s.id not in duplicates]

    studies_list = [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in pending_studies
    ]

    try:
        decisions = screen_studies_with_ai(review_dict, studies_list) if studies_list else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en cribado IA: {exc}")

    included_count = 0
    excluded_count = 0
    uncertain_count = 0
    for study in pending_studies:
        decision = decisions.get(study.id)
        if decision is None:
            continue
        kind = decision["decision"]
        study.screening_decision = kind if kind in ("include", "exclude") else "maybe"
        study.screening_stage = "title_abstract"
        if kind == "include":
            study.included = True
            study.exclusion_reason = None
            included_count += 1
        elif kind == "exclude":
            study.included = False
            study.exclusion_reason = f"{decision['criterion']}: {decision['reason']}"
            excluded_count += 1
        else:
            # Eligibility couldn't be verified from the available data: keep it out of the
            # pooled analysis until the author checks the full text and includes it manually.
            study.included = False
            study.exclusion_reason = (
                f"Requiere revisión a texto completo — {decision['criterion']}: {decision['reason']}"
            )
            uncertain_count += 1
        study.screening_reviewed = True

    db.commit()
    no_decision = len(pending_studies) - included_count - excluded_count - uncertain_count
    return {
        "message": (
            f"Cribado completado: {included_count} incluidos, {excluded_count} excluidos, "
            + (f"{len(duplicates)} duplicados, " if duplicates else "")
            + f"{uncertain_count} requieren revisión a texto completo"
            + (f", {no_decision} sin decisión (quedan pendientes)" if no_decision else "")
            + f" ({already_reviewed} ya tenían decisión previa y no se modificaron)"
        ),
        "included": included_count,
        "excluded": excluded_count,
        "uncertain": uncertain_count,
        "skipped_already_reviewed": already_reviewed,
    }


@router.post("/ai-rob")
def ai_assess_rob(review_id: int, db: Session = Depends(get_db)):
    """AI risk-of-bias assessment for included studies that have no domain rated yet."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    included = eligible_studies(db, review_id)
    if not included:
        raise HTTPException(status_code=422, detail="No hay estudios incluidos para evaluar el riesgo de sesgo.")

    pending = [s for s in included if not any(getattr(s, k) for k in ROB_DOMAIN_KEYS)]
    if not pending:
        return {
            "message": "Todos los estudios incluidos ya tienen evaluación de riesgo de sesgo; no se modificó ninguno.",
            "assessed": 0,
            "skipped_already_rated": len(included),
        }

    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
    studies_list = [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in pending]
    try:
        assessments = assess_risk_of_bias(review_dict, studies_list)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en la evaluación de riesgo de sesgo: {exc}")

    for study in pending:
        fields = assessments.get(study.id)
        if fields:
            for field, value in fields.items():
                setattr(study, field, value)
    db.commit()

    assessed = sum(1 for s in pending if s.id in assessments)
    return {
        "message": (
            f"Riesgo de sesgo evaluado en {assessed} estudios"
            + (f" ({len(pending) - assessed} sin respuesta, quedan pendientes)" if assessed < len(pending) else "")
            + f"; {len(included) - len(pending)} ya tenían evaluación y no se modificaron. "
            "Es una evaluación sugerida por IA: verifícala con el texto completo."
        ),
        "assessed": assessed,
        "skipped_already_rated": len(included) - len(pending),
    }


@router.post("/reset-screening")
def reset_screening(review_id: int, db: Session = Depends(get_db)):
    """Clear every inclusion/exclusion decision so all studies are screened again."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    reset_count = (
        db.query(Study)
        .filter(Study.review_id == review_id)
        .update(
            {Study.included: True, Study.exclusion_reason: None, Study.screening_reviewed: False,
             Study.screening_decision: None, Study.screening_stage: None},
            synchronize_session=False,
        )
    )
    db.commit()
    return {
        "message": f"Cribado reiniciado: {reset_count} estudios quedaron pendientes de cribar.",
        "reset": reset_count,
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

    studies = eligible_studies(db, review_id)
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
    report = []
    study_map = {s.id: s for s in studies}
    for study_id, res in extractions.items():
        study = study_map.get(study_id)
        if not study:
            continue
        written = {}
        for field, value in res["values"].items():
            # Never overwrite data the author already entered.
            if getattr(study, field, None) is None:
                setattr(study, field, value)
                written[field] = value
        if written:
            updated_count += 1
            try:
                evidence = json.loads(study.extraction_evidence or "{}")
            except ValueError:
                evidence = {}
            for field in written:
                evidence[field] = {**res["evidence"][field], "method": "IA (cita verificada)",
                                   "date": datetime.utcnow().strftime("%Y-%m-%d")}
            study.extraction_evidence = json.dumps(evidence, ensure_ascii=False)
        report.append({
            "id": study.id,
            "study": study.study_label or study.authors or f"ID {study.id}",
            "outcome": res["outcome"],
            "written": written,
            "rejected": res["rejected"],
        })

    db.commit()
    n_rejected = sum(len(r["rejected"]) for r in report)
    return {
        "message": (
            f"Extracción verificada: {updated_count} estudios actualizados con datos citados textualmente"
            + (f"; {n_rejected} valores descartados por no poder verificarse" if n_rejected else "")
        ),
        "updated": updated_count,
        "total_included": len(studies),
        "candidates_with_abstract": len([s for s in studies_list if s.get("abstract_text")]),
        "report": report,
    }
