import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study, Analysis, SearchDatabase
from ..services.prisma import sync_prisma, search_summary
from ..schemas import GenerateRequest, GenerateResponse
from ..services.ai_generator import generate_section

router = APIRouter(prefix="/reviews/{review_id}/generate", tags=["generate"])

_SECTION_FIELD = {
    "abstract": "abstract",
    "background": "background_text",
    "objectives": "objectives",
    "methods": "methods_text",
    "results": "results_text",
    "discussion": "discussion",
    "risk_of_bias": "risk_of_bias_results",
    "references": "references",
    "plot_interpretation": "plot_interpretation",
}


@router.post("/{section}", response_model=GenerateResponse)
def generate_text(
    review_id: int,
    section: str,
    payload: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db),
):
    section_key = section.lower().strip()
    if section_key not in _SECTION_FIELD:
        raise HTTPException(
            status_code=400,
            detail=f"Sección desconocida '{section}'. Válidas: {list(_SECTION_FIELD)}",
        )

    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Revisión no encontrada")

    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
    if section_key in ("methods", "results", "abstract"):
        searches = (db.query(SearchDatabase).filter(SearchDatabase.review_id == review_id)
                    .order_by(SearchDatabase.id).all())
        flow = sync_prisma(db, review)
        f = flow["fields"]
        review_dict["_search_log"] = search_summary(searches)
        review_dict["_prisma_flow"] = (
            "Registros identificados por fuente: "
            + (", ".join(f"{x['name']} n={x['n']}" for x in flow["sources"]) or "ninguno")
            + f"\nDuplicados eliminados: {f['prisma_duplicates_removed']}"
            + f"\nOtros eliminados antes del cribado: {f['prisma_other_removed']}"
            + f"\nRegistros cribados (título/resumen): {f['prisma_screened']}"
            + f"\nExcluidos en el cribado: {f['prisma_excluded_screening']}"
            + f"\nTextos completos buscados: {f['prisma_sought']}; no recuperados: {f['prisma_not_retrieved']}"
            + f"\nEvaluados a texto completo: {f['prisma_assessed']}; excluidos: {f['prisma_excluded_eligibility']}"
            + f" ({(f['prisma_exclusion_reasons'] or 'sin motivos').replace('=', ': n=')})"
            + f"\nEstudios incluidos en la revisión: {f['prisma_included']}"
            + f"\nEstudios incluidos en el metaanálisis: {f['prisma_reports_included']}"
        )

    studies = db.query(Study).filter(Study.review_id == review_id).all()
    all_studies = [
        {c.name: getattr(s, c.name) for c in s.__table__.columns}
        for s in studies
    ]
    studies_list = [s for s in all_studies if s["included"] and s["screening_reviewed"]]
    excluded_list = [s for s in all_studies if not s["included"] and s["screening_reviewed"]]

    # Load latest meta-analysis results
    meta_results = None
    if payload.include_meta_results or section_key == "plot_interpretation":
        latest = (
            db.query(Analysis)
            .filter(Analysis.review_id == review_id)
            .order_by(Analysis.created_at.desc())
            .first()
        )
        if latest and latest.results_json:
            try:
                meta_results = json.loads(latest.results_json)
            except json.JSONDecodeError:
                pass

    # For plot_interpretation, meta_results is required
    if section_key == "plot_interpretation" and not meta_results:
        raise HTTPException(
            status_code=422,
            detail="Primero ejecuta el metaanálisis para poder interpretar los gráficos.",
        )

    citation_style = review_dict.get("citation_style") or "vancouver"

    try:
        text = generate_section(
            section_key, review_dict, studies_list, meta_results, citation_style, excluded_list
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en generación IA: {exc}")

    # Persist to review
    field = _SECTION_FIELD[section_key]
    setattr(review, field, text)
    db.commit()

    return GenerateResponse(section=section_key, text=text)
