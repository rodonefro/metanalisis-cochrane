import json
import base64
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, HRFlowable, PageBreak,
)

from ..database import get_db
from ..models import Review, Study, Analysis
from ..services.plots import generate_prisma_2020

router = APIRouter(prefix="/reviews/{review_id}/export", tags=["export"])


def _para(text: str, style) -> Paragraph:
    # Escape any HTML-like content for ReportLab
    safe = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def _b64_to_image(b64: str, width_cm: float = 14) -> Image | None:
    try:
        data = base64.b64decode(b64)
        buf = io.BytesIO(data)
        img = Image(buf)
        aspect = img.imageHeight / img.imageWidth
        w = width_cm * cm
        img.drawWidth = w
        img.drawHeight = w * aspect
        return img
    except Exception:
        return None


@router.get("/pdf")
def export_pdf(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    analysis = (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=4)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=6)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    story = []

    # Title
    story.append(_para(review.title or "Systematic Review", h1))
    if review.prospero_id:
        story.append(_para(f"PROSPERO: {review.prospero_id}", small))
    story.append(_para(f"Status: {review.status} | Generated: {datetime.utcnow().strftime('%Y-%m-%d')}", small))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 0.3 * cm))

    def section(heading: str, text: str | None, level=h2):
        if text:
            story.append(_para(heading, level))
            story.append(_para(text, body))
            story.append(Spacer(1, 0.2 * cm))

    # Abstract
    section("Abstract", review.abstract)

    # PICO
    if any([review.population, review.intervention, review.comparison, review.outcomes]):
        story.append(_para("PICO Framework", h2))
        for label, val in [
            ("Population", review.population),
            ("Intervention", review.intervention),
            ("Comparison", review.comparison),
            ("Outcomes", review.outcomes),
        ]:
            if val:
                story.append(_para(f"<b>{label}:</b> {val}", body))
        story.append(Spacer(1, 0.2 * cm))

    # Background
    section("Background", review.background_text)
    if not review.background_text:
        for sub_label, sub_val in [
            ("Description of the condition", review.background_condition),
            ("Description of the intervention", review.background_intervention),
            ("How the intervention might work", review.background_mechanism),
            ("Why it is important to do this review", review.background_importance),
        ]:
            section(sub_label, sub_val, h3)

    # Objectives
    section("Objectives", review.objectives)

    # Methods
    section("Methods", review.methods_text)
    if not review.methods_text:
        for sub_label, sub_val in [
            ("Criteria for considering studies", review.inclusion_criteria),
            ("Types of studies", review.types_of_studies),
            ("Types of participants", review.types_of_participants),
            ("Types of interventions", review.types_of_interventions),
            ("Types of outcome measures", review.types_of_outcomes),
            ("Primary outcomes", review.primary_outcomes),
            ("Secondary outcomes", review.secondary_outcomes),
            ("Search strategy", review.search_strategy),
            ("Study selection", review.study_selection_method),
            ("Data extraction", review.data_extraction_method),
            ("Risk of bias assessment", review.risk_of_bias_method),
            ("Assessment of heterogeneity", review.heterogeneity_method),
        ]:
            section(sub_label, sub_val, h3)

    # Results
    section("Results", review.results_text)
    if not review.results_text:
        section("Description of studies", review.description_of_studies, h3)
        section("Risk of bias in included studies", review.risk_of_bias_results, h3)
        section("Effects of interventions", review.intervention_effects, h3)

    # PRISMA 2020
    has_prisma = any([
        review.prisma_db_names, review.prisma_screened,
        review.prisma_assessed, review.prisma_included,
    ])
    if has_prisma:
        story.append(PageBreak())
        story.append(_para("PRISMA 2020 Flow Diagram", h2))
        try:
            prisma_b64 = generate_prisma_2020(
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
            img = _b64_to_image(prisma_b64, 14)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.3 * cm))
        except Exception:
            pass

    # Plots
    if analysis:
        story.append(PageBreak())
        story.append(_para("Statistical Analysis", h2))
        if analysis.forest_plot_b64:
            story.append(_para("Forest Plot", h3))
            img = _b64_to_image(analysis.forest_plot_b64, 14)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.3 * cm))
        if analysis.funnel_plot_b64:
            story.append(_para("Funnel Plot", h3))
            img = _b64_to_image(analysis.funnel_plot_b64, 10)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.3 * cm))
        if analysis.rob_plot_b64:
            story.append(_para("Risk of Bias Assessment", h3))
            img = _b64_to_image(analysis.rob_plot_b64, 14)
            if img:
                story.append(img)
                story.append(Spacer(1, 0.3 * cm))
        if analysis.results_json:
            try:
                res = json.loads(analysis.results_json)
                p = res.get("pooled", {})
                h = res.get("heterogeneity", {})
                em = res.get("effect_measure", "")
                summary = (
                    f"Pooled {em}: {p.get('effect', 'N/A'):.2f} "
                    f"[95% CI: {p.get('ci_lower', 'N/A'):.2f}, {p.get('ci_upper', 'N/A'):.2f}] | "
                    f"k={res.get('k')}, N={res.get('total_n')} | "
                    f"I²={h.get('I2', 'N/A'):.0f}%, τ²={h.get('tau2', 'N/A'):.4f}"
                )
                story.append(_para(summary, small))
            except Exception:
                pass

    # Discussion
    section("Discussion", review.discussion)
    section("Authors' conclusions", review.authors_conclusions, h3)

    doc.build(story)
    buf.seek(0)

    safe_title = (review.title or "review").replace(" ", "_")[:60]
    filename = f"{safe_title}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
