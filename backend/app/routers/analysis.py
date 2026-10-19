import json
from collections import Counter
from datetime import datetime
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
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
    assess_risk_of_bias, ROB_DOMAIN_KEYS, classify_center_type,
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
        # Fallback: studies that report an effect estimate with its 95% CI (in the review's measure)
        try:
            if effect_measure == "PROP":
                raise ValueError("proportions have no precalculated fallback")
            result = run_meta_analysis(study_data, "PRECALCULATED", model_type, precalc_as=effect_measure)
            effect_measure = result.effect_measure
        except ValueError:
            needed = {
                "OR": "eventos y total por grupo", "RR": "eventos y total por grupo",
                "RD": "eventos y total por grupo", "MD": "media, DE y n por grupo",
                "SMD": "media, DE y n por grupo",
                "PROP": "eventos y total del grupo de la intervención",
            }.get(effect_measure, "datos por grupo")
            # Earlier results no longer describe the current set of included studies.
            stale = db.query(Analysis).filter(Analysis.review_id == review_id).delete()
            review.prisma_reports_included = 0
            db.commit()
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Ninguno de los {len(study_data)} estudios incluidos tiene datos para calcular "
                    f"{effect_measure}: faltan {needed} (o un efecto {effect_measure} con su IC 95 %). "
                    "Ejecuta «Extraer datos con IA» o captura los datos en la base de estudios; "
                    "no se generó ningún resultado."
                    + (f" Se eliminaron {stale} análisis anteriores que ya no corresponden a los "
                       "estudios incluidos." if stale else "")
                ),
            )

    result_dict = result_to_dict(result)
    if effect_measure == "PROP":
        result_dict.update(_multicenter_sensitivity(study_data, model_type))

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


def _has_prop_data(s: dict) -> bool:
    return s.get("events_intervention") is not None and bool(s.get("total_intervention"))


def _multicenter_sensitivity(study_data: list[dict], model_type: str) -> dict:
    """Center-type composition of the pooled studies and the analysis restricted to multicentre ones."""
    usable = [s for s in study_data if _has_prop_data(s)]
    counts = {"single": 0, "multi": 0, "unclear": 0, "unclassified": 0}
    for s in usable:
        counts[s.get("center_type") if s.get("center_type") in counts else "unclassified"] += 1
    multi = [s for s in usable if s.get("center_type") == "multi"]
    if len(multi) < 2:
        sens = {"available": False,
                "reason": f"solo {len(multi)} estudio(s) multicéntrico(s) con datos; se necesitan al menos 2"
                          + (f" ({counts['unclassified']} sin clasificar: ejecuta «Clasificar centros»)"
                             if counts["unclassified"] else "")}
    else:
        try:
            sens = {"available": True, **result_to_dict(run_meta_analysis(multi, "PROP", model_type))}
        except ValueError as exc:
            sens = {"available": False, "reason": str(exc)}
    return {"center_counts": counts, "sensitivity_multicenter": sens}


@router.post("/ai-centers")
def ai_classify_centers(review_id: int, db: Session = Depends(get_db)):
    """AI classification of included studies as single-centre or multicentre (unclassified ones only)."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    included = eligible_studies(db, review_id)
    pending = [s for s in included if not s.center_type]
    if not pending:
        return {"message": "Todos los estudios incluidos ya tienen tipo de centro; no se modificó ninguno.",
                "classified": 0}
    try:
        decisions = classify_center_type(
            [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in pending])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al clasificar los centros: {exc}")
    tally = {"single": 0, "multi": 0, "unclear": 0}
    for s in pending:
        d = decisions.get(s.id)
        if d:
            s.center_type, s.center_evidence = d["center_type"], d["evidence"] or None
            tally[d["center_type"]] += 1
    db.commit()
    return {
        "message": (f"Centros clasificados: {tally['multi']} multicéntricos, {tally['single']} unicéntricos, "
                    f"{tally['unclear']} sin información suficiente."),
        "classified": sum(tally.values()),
        **tally,
    }


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
def get_forest_plot(review_id: int, subset: str | None = None, db: Session = Depends(get_db)):
    """Return (or regenerate) the forest plot + AI interpretation.
    subset="multicenter" draws the sensitivity analysis restricted to multicentre studies."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    analysis = _get_latest_or_404(review_id, db)
    result_dict = json.loads(analysis.results_json)
    title = review.title or "Forest Plot"
    if subset == "multicenter":
        sens = result_dict.get("sensitivity_multicenter") or {}
        if not sens.get("available"):
            raise HTTPException(status_code=422, detail="Análisis de sensibilidad no disponible: "
                                + (sens.get("reason") or "no es un metaanálisis de proporciones"))
        result_dict = sens
        title = f"{title} — sensibilidad: solo estudios multicéntricos"

    # Always regenerate (ensures fresh output, bypasses any stale cache)
    try:
        result = meta_result_from_dict(result_dict)
        b64 = generate_forest_plot(result, title=title)
        if not b64:
            raise ValueError("generate_forest_plot returned empty result")
        if subset != "multicenter":
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

    It only depends on each study's rob_* ratings, so it works without a
    meta-analysis; when one exists the image is also stored on it.
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    studies = [s for s in _study_dicts(review_id, db)
               if any(s.get(k) for k in (*ROB_DOMAIN_KEYS, "rob_overall"))]
    if not studies:
        raise HTTPException(status_code=422, detail="No hay estudios incluidos con riesgo de sesgo evaluado.")

    try:
        b64 = generate_rob_traffic_light(studies)
        analysis = (db.query(Analysis).filter(Analysis.review_id == review_id)
                    .order_by(Analysis.created_at.desc()).first())
        if analysis:
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


class ScreenRequest(BaseModel):
    reasons: list[str] | None = None      # the author's exclusion-reason list (Rayyan-style)
    study_ids: list[int] | None = None    # screen these records, even if already decided
    dry_run: bool = False                 # return suggestions without saving
    limit: int | None = None              # pending records sent to the AI in this call (default: one lot)


SCREEN_LOT_SIZE = 50
_SCREEN_CALL_SIZE = 15


def _decision_reason(decision: dict, with_options: bool) -> str | None:
    """exclusion_reason stored for an AI decision; with the author's list it is the chosen reason."""
    kind, criterion = decision["decision"], decision["criterion"]
    if kind == "include":
        return None
    if kind == "exclude":
        return criterion if with_options else f"{criterion}: {decision['reason']}"
    return (f"Requiere revisión a texto completo — {criterion}" if with_options
            else f"Requiere revisión a texto completo — {criterion}: {decision['reason']}")


@router.post("/ai-screen")
def ai_screen_studies(review_id: int, payload: ScreenRequest | None = Body(None),
                      db: Session = Depends(get_db)):
    """Use AI to screen pending studies against PICO criteria and set included/exclusion_reason.

    Studies that already have an inclusion decision (manually toggled by the user,
    or screened by a previous AI run) are skipped, so this never overwrites a
    selection that was already made — e.g. the final set of studies you curated
    to match the PRISMA flow diagram.

    Only one lot of pending records (SCREEN_LOT_SIZE unless `limit` says otherwise)
    is sent to the AI per call, and decisions are saved after every model call, so
    credits are spent on a known number of records and an error keeps what was done.
    """
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    payload = payload or ScreenRequest()
    reasons = [r.strip() for r in (payload.reasons or []) if r and r.strip()] or None
    all_studies = db.query(Study).filter(Study.review_id == review_id).order_by(Study.id).all()
    if not all_studies:
        raise HTTPException(status_code=422, detail="No hay estudios para cribar.")

    if payload.study_ids:
        wanted = set(payload.study_ids)
        pending_studies = [s for s in all_studies if s.id in wanted]
        if not pending_studies:
            raise HTTPException(status_code=404, detail="Estudio no encontrado en esta revisión.")
    else:
        pending_studies = [s for s in all_studies if not s.screening_reviewed]
    already_reviewed = len(all_studies) - len(pending_studies)

    if not pending_studies:
        return {
            "message": (
                f"No hay estudios pendientes de cribar: los {already_reviewed} estudios "
                "ya tienen una decisión de inclusión/exclusión (manual o de un cribado IA previo)."
            ),
            "included": 0, "excluded": 0, "uncertain": 0, "quantitative": 0, "duplicates": 0,
            "screened": 0, "remaining": 0,
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

    if payload.dry_run:
        try:
            decisions = screen_studies_with_ai(
                review_dict,
                [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in pending_studies],
                reasons,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error en cribado IA: {exc}")
        return {"suggestions": {
            sid: {
                "decision": "maybe" if d["decision"] == "uncertain" else d["decision"],
                "reason": _decision_reason(d, bool(reasons)),
                "explanation": d["reason"],
                "suitability": None if d["suitability"] == "not_applicable" else d["suitability"],
                "suitability_note": d["suitability_note"] or None,
            }
            for sid, d in decisions.items()
        }}

    duplicates = {} if payload.study_ids else find_duplicates(all_studies, pending_studies)
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
    db.commit()
    if not payload.study_ids:
        pending_studies = pending_studies[:max(1, min(payload.limit or SCREEN_LOT_SIZE, 500))]

    counts: Counter = Counter()
    error = None
    for i in range(0, len(pending_studies), _SCREEN_CALL_SIZE):
        chunk = pending_studies[i:i + _SCREEN_CALL_SIZE]
        try:
            decisions = screen_studies_with_ai(
                review_dict, [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in chunk], reasons)
        except Exception as exc:
            error = exc
            break
        for study in chunk:
            decision = decisions.get(study.id)
            if decision is None:
                continue
            kind = decision["decision"]
            study.screening_decision = kind if kind in ("include", "exclude") else "maybe"
            study.screening_stage = "title_abstract"
            study.ai_screening_note = decision["reason"] or None
            if kind == "include":
                study.included = True
                study.exclusion_reason = None
                study.analysis_suitability = None if decision["suitability"] == "not_applicable" else decision["suitability"]
                study.suitability_note = decision["suitability_note"] or None
                counts["included"] += 1
                if study.analysis_suitability == "quantitative":
                    counts["quantitative"] += 1
            elif kind == "exclude":
                study.included = False
                study.exclusion_reason = _decision_reason(decision, bool(reasons))
                counts["excluded"] += 1
            else:
                # Eligibility couldn't be verified from the available data: keep it out of the
                # pooled analysis until the author checks the full text and includes it manually.
                study.included = False
                study.exclusion_reason = _decision_reason(decision, bool(reasons))
                counts["uncertain"] += 1
            study.screening_reviewed = True
        db.commit()

    screened = counts["included"] + counts["excluded"] + counts["uncertain"]
    if error is not None and not screened:
        raise HTTPException(status_code=500, detail=f"Error en cribado IA: {error}")
    remaining = db.query(Study).filter(Study.review_id == review_id,
                                       Study.screening_reviewed == False).count()  # noqa: E712
    return {
        "message": (
            f"Lote cribado: {screened} estudios — {counts['included']} incluidos "
            f"({counts['quantitative']} con datos cuantitativos para el metaanálisis), "
            f"{counts['excluded']} excluidos, {counts['uncertain']} requieren revisión a texto completo"
            + (f"; {len(duplicates)} duplicados excluidos sin usar IA" if duplicates else "")
            + (f". El lote se interrumpió por un error ({error}); lo cribado quedó guardado" if error else "")
            + (f". Quedan {remaining} pendientes." if remaining else ". No quedan estudios pendientes.")
        ),
        "included": counts["included"],
        "excluded": counts["excluded"],
        "uncertain": counts["uncertain"],
        "quantitative": counts["quantitative"],
        "duplicates": len(duplicates),
        "screened": screened,
        "remaining": remaining,
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
             Study.screening_decision: None, Study.screening_stage: None,
             Study.analysis_suitability: None, Study.suitability_note: None,
             Study.ai_screening_note: None},
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
