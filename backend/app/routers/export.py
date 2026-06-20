import json
import base64
import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, HRFlowable,
    PageBreak, Table, TableStyle, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

from ..database import get_db
from ..models import Review, Study, Analysis
from ..services.plots import generate_prisma_2020, generate_grade_table

router = APIRouter(prefix="/reviews/{review_id}/export", tags=["export"])

# ── Cochrane colour palette ──────────────────────────────────────────────────
C_BLUE   = colors.HexColor("#005A9C")   # Cochrane primary blue
C_LBLUE  = colors.HexColor("#E8F1F8")   # light blue (section bg)
C_DBLUE  = colors.HexColor("#003366")   # dark blue (cover)
C_GREY   = colors.HexColor("#555555")
C_LGREY  = colors.HexColor("#F4F4F4")
C_WHITE  = colors.white
C_BLACK  = colors.black
C_GREEN  = colors.HexColor("#2ecc71")
C_ORANGE = colors.HexColor("#f39c12")
C_RED    = colors.HexColor("#e74c3c")


def _safe(text) -> str:
    s = str(text or "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _para(text, style) -> Paragraph:
    return Paragraph(_safe(text), style)


def _trunc(text, max_chars: int) -> str:
    """Hard-cap free-text fields before they go into a fixed-width table cell.

    A single Table row that can't fit on one page raises an unrecoverable
    reportlab.LayoutError (no page is tall enough to hold it, so it can't even
    be split across pages). Any field imported from Excel/CSV or written by the
    AI extraction step is free text with no length guarantee, so every value
    placed in a narrow table column must be capped here — not just the ones
    that happened to be sliced when this table was first written.
    """
    s = str(text or "").strip()
    if not s:
        return "—"
    s = " ".join(s.split())  # collapse newlines/extra whitespace so length reflects rendered width
    return s if len(s) <= max_chars else s[: max_chars - 1].rstrip() + "…"


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


def _styles():
    """Return a dict of all custom paragraph styles."""
    base = getSampleStyleSheet()

    def s(name, **kw):
        parent = kw.pop("parent", base["Normal"])
        return ParagraphStyle(name, parent=parent, **kw)

    return {
        "title":     s("Title",    fontSize=18, textColor=C_WHITE,   alignment=TA_CENTER,
                        fontName="Helvetica-Bold", leading=22, spaceAfter=4),
        "subtitle":  s("Subtitle", fontSize=11, textColor=C_WHITE,   alignment=TA_CENTER,
                        fontName="Helvetica", leading=14),
        "meta":      s("Meta",     fontSize=8,  textColor=C_WHITE,   alignment=TA_CENTER,
                        fontName="Helvetica"),
        # Abstract sub-headings (bold inline label)
        "abs_label": s("AbsLabel", fontSize=9,  textColor=C_BLUE, fontName="Helvetica-Bold",
                        spaceBefore=6, spaceAfter=0),
        "abs_body":  s("AbsBody",  fontSize=9,  leading=13, spaceAfter=3, alignment=TA_JUSTIFY),
        # Section headings  H1 = numbered (1. Background)
        "h1":        s("H1",  fontSize=13, textColor=C_WHITE, fontName="Helvetica-Bold",
                        parent=base["Heading1"], spaceBefore=14, spaceAfter=0,
                        leftIndent=0, leading=16),
        # Sub-section  H2 = 1.1
        "h2":        s("H2",  fontSize=11, textColor=C_BLUE, fontName="Helvetica-Bold",
                        parent=base["Heading2"], spaceBefore=10, spaceAfter=2, leading=14),
        # Sub-sub-section H3 = 1.1.1
        "h3":        s("H3",  fontSize=10, textColor=C_DBLUE, fontName="Helvetica-Bold",
                        parent=base["Heading3"], spaceBefore=7, spaceAfter=1, leading=12),
        # Body text
        "body":      s("Body", fontSize=10, leading=14, spaceAfter=5, alignment=TA_JUSTIFY),
        "body_sm":   s("BodySm", fontSize=9, leading=13, spaceAfter=3, alignment=TA_JUSTIFY),
        "small":     s("Small", fontSize=8,  textColor=C_GREY, spaceAfter=2),
        "label":     s("Label", fontSize=9,  fontName="Helvetica-Bold", spaceAfter=1),
        "caption":   s("Caption", fontSize=8, textColor=C_GREY, alignment=TA_CENTER, spaceAfter=4),
        "toc_entry": s("Toc", fontSize=9, leading=13, spaceAfter=1),
        "note":      s("Note", fontSize=8.5, textColor=C_GREY, leading=12,
                        leftIndent=10, spaceAfter=3),
    }


def _h1_block(story, number: str, title: str, st: dict):
    """Render a numbered H1 as a full-width blue banner."""
    tbl = Table(
        [[Paragraph(f"{number}   {_safe(title)}", st["h1"])]],
        colWidths=[16 * cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [3]),
    ]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(tbl)
    story.append(Spacer(1, 0.15 * cm))


def _sub(story, num: str, title: str, text: str | None, st: dict, level: int = 2):
    """Add a sub-section heading and optional body text."""
    style = st["h2"] if level == 2 else st["h3"]
    story.append(_para(f"{num}  {title}", style))
    if text:
        story.append(_para(text, st["body"]))


def _field(story, label: str, value: str | None, st: dict):
    if value:
        story.append(_para(f"<b>{label}:</b> {_safe(value)}", st["body_sm"]))


def _hr(story, color=C_LBLUE):
    story.append(HRFlowable(width="100%", thickness=1, color=color, spaceAfter=4, spaceBefore=4))


# ── Study characteristics table ──────────────────────────────────────────────

def _study_table(studies: list, st: dict):
    """Return a ReportLab Table with characteristics of included studies."""
    headers = ["Study", "Design", "N", "Intervention", "Control", "Outcome", "RoB"]
    data = [headers]
    for s in studies:
        label = s.study_label or f"{s.authors or '?'} {s.year or ''}"
        n = (s.total_intervention or 0) + (s.total_control or 0) or (s.sample_size or "—")
        design = s.study_design or "—"
        interv = s.patient_population or s.inclusion_criteria or "—"
        ctrl   = s.group_comparison or "—"
        outc   = s.survival_outcomes or s.key_findings or "—"
        rob_val = _trunc(s.rob_overall or "—", 20)
        rob_color = {"low": "#2ecc71", "some_concerns": "#f39c12", "high": "#e74c3c"}.get(s.rob_overall, "#aaaaaa")
        data.append([
            Paragraph(_safe(_trunc(label, 40)),  ParagraphStyle("tc", fontSize=8, leading=10)),
            Paragraph(_safe(_trunc(design, 30)), ParagraphStyle("tc2", fontSize=8, leading=10)),
            str(n),
            Paragraph(_safe(_trunc(interv, 60)), ParagraphStyle("tc3", fontSize=7.5, leading=10)),
            Paragraph(_safe(_trunc(ctrl, 50)),   ParagraphStyle("tc4", fontSize=7.5, leading=10)),
            Paragraph(_safe(_trunc(outc, 60)),   ParagraphStyle("tc5", fontSize=7.5, leading=10)),
            Paragraph(_safe(rob_val), ParagraphStyle("tc6", fontSize=8, leading=10,
                                                     textColor=colors.HexColor(rob_color))),
        ])

    col_w = [3.2*cm, 2*cm, 1.2*cm, 3.2*cm, 2.8*cm, 3.2*cm, 1.4*cm]
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    style = [
        ("BACKGROUND",    (0, 0), (-1,  0), C_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1,  0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1,  0), 8),
        ("BOTTOMPADDING", (0, 0), (-1,  0), 5),
        ("TOPPADDING",    (0, 0), (-1,  0), 5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_LGREY]),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("TOPPADDING",    (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]
    tbl.setStyle(TableStyle(style))
    return tbl


# ── Cover page ───────────────────────────────────────────────────────────────

def _cover(story, review: Review, st: dict, n_studies: int):
    # Dark blue header bar
    cover_tbl = Table(
        [[
            Paragraph("COCHRANE", ParagraphStyle("CL", fontSize=28, textColor=C_WHITE,
                                                  fontName="Helvetica-Bold", leading=32)),
            Paragraph("Systematic Review", ParagraphStyle("CR", fontSize=14, textColor=C_WHITE,
                                                           fontName="Helvetica", leading=18)),
        ]],
        colWidths=[5*cm, 11*cm],
    )
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_DBLUE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("LINEBELOW",     (0, 0), (-1, -1), 3, C_BLUE),
    ]))
    story.append(cover_tbl)
    story.append(Spacer(1, 1.2 * cm))

    # Title
    story.append(_para(review.title or "Systematic Review", ParagraphStyle(
        "CoverTitle", fontSize=20, fontName="Helvetica-Bold", textColor=C_DBLUE,
        alignment=TA_LEFT, leading=26, spaceAfter=10,
    )))

    _hr(story, C_BLUE)
    story.append(Spacer(1, 0.4 * cm))

    # Metadata grid
    meta_items = [
        ("Registration", review.prospero_id or "Not registered"),
        ("Status",       (review.status or "draft").title()),
        ("Studies included", str(n_studies)),
        ("Effect measure",   review.effect_measure or "OR"),
        ("Model",            (review.model_type or "random").title() + " effects"),
        ("Date generated",   datetime.utcnow().strftime("%d %B %Y")),
    ]
    meta_data = [[
        Paragraph(f"<b>{k}</b>", ParagraphStyle("mk", fontSize=9, textColor=C_GREY)),
        Paragraph(_safe(v), ParagraphStyle("mv", fontSize=9)),
    ] for k, v in meta_items]
    meta_tbl = Table(meta_data, colWidths=[4.5*cm, 11.5*cm])
    meta_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_LGREY, C_WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 0.8 * cm))

    # PICO box
    if any([review.population, review.intervention, review.comparison, review.outcomes]):
        pico_rows = []
        for label, val in [
            ("P – Population",   review.population),
            ("I – Intervention", review.intervention),
            ("C – Comparison",   review.comparison),
            ("O – Outcomes",     review.outcomes),
        ]:
            if val:
                pico_rows.append([
                    Paragraph(f"<b>{label}</b>", ParagraphStyle("pl", fontSize=9, textColor=C_BLUE)),
                    Paragraph(_safe(_trunc(val, 600)), ParagraphStyle("pv", fontSize=9, leading=13)),
                ])
        if pico_rows:
            pico_tbl = Table(pico_rows, colWidths=[4*cm, 12*cm])
            pico_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (0, -1), C_LBLUE),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                ("BOX",           (0, 0), (-1, -1), 1, C_BLUE),
                ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
            ]))
            story.append(Paragraph("PICO Framework", ParagraphStyle(
                "picoH", fontSize=10, fontName="Helvetica-Bold", textColor=C_BLUE, spaceAfter=4)))
            story.append(pico_tbl)

    story.append(PageBreak())


# ── Structured abstract ──────────────────────────────────────────────────────

def _abstract_section(story, review: Review, st: dict):
    _h1_block(story, "", "Abstract", st)

    abstract_text = review.abstract or ""
    if abstract_text:
        # Try to detect Cochrane sub-sections already in the text
        story.append(_para(abstract_text, st["abs_body"]))
    else:
        # Render PICO as minimal abstract placeholder
        for label, val in [
            ("Background",   None),
            ("Objectives",   review.objectives),
            ("Search methods", review.search_strategy),
            ("Selection criteria", review.inclusion_criteria),
            ("Main results", review.intervention_effects),
            ("Authors' conclusions", review.authors_conclusions),
        ]:
            story.append(_para(label, st["abs_label"]))
            story.append(_para(val or "[Not yet generated — use AI generation]", st["abs_body"]))

    story.append(Spacer(1, 0.3 * cm))


# ── Main builder ─────────────────────────────────────────────────────────────

@router.get("/pdf")
def export_pdf(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    studies = db.query(Study).filter(Study.review_id == review_id, Study.included == True).all()
    analysis = (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )

    buf = io.BytesIO()
    PAGE_W, PAGE_H = A4
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2.2*cm, bottomMargin=2.2*cm,
        title=review.title or "Systematic Review",
        author="MetaAnalysis Cochrane Platform",
    )

    st = _styles()
    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    _cover(story, review, st, len(studies))

    # ── Abstract ─────────────────────────────────────────────────────────────
    _abstract_section(story, review, st)
    story.append(PageBreak())

    # ── 1. Background ────────────────────────────────────────────────────────
    _h1_block(story, "1.", "Background", st)

    if review.background_text:
        story.append(_para(review.background_text, st["body"]))
    else:
        _sub(story, "1.1", "Description of the condition",
             review.background_condition, st)
        _sub(story, "1.2", "Description of the intervention",
             review.background_intervention, st)
        _sub(story, "1.3", "How the intervention might work",
             review.background_mechanism, st)
        _sub(story, "1.4", "Why it is important to do this review",
             review.background_importance, st)

    if not any([review.background_text, review.background_condition,
                review.background_intervention, review.background_mechanism,
                review.background_importance]):
        story.append(_para("[Not yet generated — use AI section generation]", st["note"]))

    # ── 2. Objectives ────────────────────────────────────────────────────────
    _h1_block(story, "2.", "Objectives", st)
    story.append(_para(review.objectives or "[Not yet generated — use AI section generation]", st["body"]))

    # ── 3. Methods ───────────────────────────────────────────────────────────
    _h1_block(story, "3.", "Methods", st)

    if review.methods_text:
        story.append(_para(review.methods_text, st["body"]))
    else:
        _sub(story, "3.1", "Criteria for considering studies for this review", None, st)
        _sub(story, "3.1.1", "Types of studies",
             review.types_of_studies, st, level=3)
        _sub(story, "3.1.2", "Types of participants",
             review.types_of_participants, st, level=3)
        _sub(story, "3.1.3", "Types of interventions",
             review.types_of_interventions, st, level=3)
        _sub(story, "3.1.4", "Types of outcome measures", None, st, level=3)

        if review.primary_outcomes:
            story.append(_para("<b>Primary outcomes</b>", st["label"]))
            story.append(_para(review.primary_outcomes, st["body"]))
        if review.secondary_outcomes:
            story.append(_para("<b>Secondary outcomes</b>", st["label"]))
            story.append(_para(review.secondary_outcomes, st["body"]))

        _sub(story, "3.2", "Search methods for identification of studies", None, st)
        _sub(story, "3.2.1", "Electronic searches",
             review.search_strategy, st, level=3)
        story.append(_para(
            "Databases searched: PubMed/MEDLINE, Embase, Cochrane Central Register of "
            "Controlled Trials (CENTRAL), Scopus, Web of Science. No language or date restrictions.",
            st["body_sm"]))

        _sub(story, "3.3", "Data collection and analysis", None, st)
        _sub(story, "3.3.1", "Selection of studies",
             review.study_selection_method, st, level=3)
        _sub(story, "3.3.2", "Data extraction and management",
             review.data_extraction_method, st, level=3)
        _sub(story, "3.3.3", "Assessment of risk of bias in included studies",
             review.risk_of_bias_method or
             "Risk of bias was assessed using the Cochrane Risk of Bias 2 (RoB 2) tool "
             "across five domains: randomisation process, deviations from intended "
             "interventions, missing outcome data, measurement of the outcome, and "
             "selection of the reported result.",
             st, level=3)
        _sub(story, "3.3.4", "Measures of treatment effect",
             f"The primary effect measure was {review.effect_measure or 'OR'} "
             "(odds ratio). Continuous outcomes were expressed as mean difference (MD) "
             "or standardised mean difference (SMD) with 95% confidence intervals.",
             st, level=3)
        _sub(story, "3.3.5", "Unit of analysis issues",
             "The unit of analysis was the individual participant. Cluster-randomised "
             "trials were adjusted using the intracluster correlation coefficient (ICC) "
             "where available.",
             st, level=3)
        _sub(story, "3.3.6", "Dealing with missing data",
             "Intention-to-treat analysis was used where possible. Missing data were "
             "handled using available case analysis; sensitivity analyses explored the "
             "impact of different assumptions.",
             st, level=3)
        _sub(story, "3.3.7", "Assessment of heterogeneity",
             review.heterogeneity_method or
             f"Statistical heterogeneity was assessed using the Chi² test (P < 0.10) "
             f"and the I² statistic. A {review.model_type or 'random'}-effects "
             f"meta-analysis model (DerSimonian and Laird) was applied. I² values of "
             f"25%, 50%, and 75% were considered to represent low, moderate, and high "
             f"heterogeneity, respectively.",
             st, level=3)
        _sub(story, "3.3.8", "Assessment of reporting biases",
             "Reporting bias was assessed using funnel plots when ≥ 10 studies were "
             "available. Funnel plot asymmetry was evaluated using Egger's test.",
             st, level=3)
        _sub(story, "3.3.9", "Data synthesis",
             f"Meta-analysis was conducted using a {review.model_type or 'random'}-effects "
             f"model. The pooled estimate, 95% confidence interval and prediction interval "
             f"were calculated. All analyses were performed using Python (pymare library).",
             st, level=3)
        _sub(story, "3.3.10", "Subgroup analysis and investigation of heterogeneity",
             "Pre-specified subgroup analyses were planned by study design, "
             "geographical region, and risk of bias level where data permitted.",
             st, level=3)
        _sub(story, "3.3.11", "Sensitivity analysis",
             "Sensitivity analyses excluded studies with high risk of bias and used "
             "fixed-effects models to assess robustness of pooled estimates.",
             st, level=3)

    # ── 4. Results ───────────────────────────────────────────────────────────
    story.append(PageBreak())
    _h1_block(story, "4.", "Results", st)

    _sub(story, "4.1", "Description of studies", None, st)
    _sub(story, "4.1.1", "Results of the search", None, st, level=3)

    # PRISMA diagram
    has_prisma = any([review.prisma_db_names, review.prisma_screened,
                      review.prisma_assessed, review.prisma_included])
    if has_prisma:
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
            img = _b64_to_image(prisma_b64, 13)
            if img:
                story.append(img)
                story.append(_para("Figure 1. PRISMA 2020 flow diagram.", st["caption"]))
        except Exception:
            pass

    _sub(story, "4.1.2", "Included studies",
         review.description_of_studies or
         (f"A total of {len(studies)} studies were included in this review." if studies else None),
         st, level=3)

    # Study characteristics table
    if studies:
        story.append(_para("Table 1. Characteristics of included studies", st["label"]))
        story.append(Spacer(1, 0.1*cm))
        story.append(_study_table(studies, st))
        story.append(Spacer(1, 0.3*cm))

    _sub(story, "4.1.3", "Excluded studies",
         "Studies were excluded due to: wrong population, wrong intervention, "
         "wrong outcome, wrong study design, or duplicate publication. "
         "See Appendix for full list of excluded studies.",
         st, level=3)

    _sub(story, "4.1.4", "Risk of bias in included studies",
         review.risk_of_bias_results, st, level=3)

    if analysis and analysis.rob_plot_b64:
        img = _b64_to_image(analysis.rob_plot_b64, 14)
        if img:
            story.append(img)
            story.append(_para("Figure 2. Risk of bias summary (Cochrane RoB 2).", st["caption"]))

    _sub(story, "4.2", "Effects of interventions", None, st)
    _sub(story, "4.2.1", "Primary outcomes",
         review.intervention_effects or review.results_text, st, level=3)

    # Forest plot — embedded near the page's full text width (A4 minus 2.2cm
    # margins each side = 16.6cm) so the large fonts rendered in plots.py
    # reach paper at a legible size instead of being shrunk down ~40%.
    if analysis and analysis.forest_plot_b64:
        img = _b64_to_image(analysis.forest_plot_b64, 16.5)
        if img:
            story.append(KeepTogether([
                img,
                _para("Figure 3. Forest plot — pooled effect estimate.", st["caption"]),
            ]))
            story.append(Spacer(1, 0.3*cm))

    _sub(story, "4.2.2", "Secondary outcomes",
         review.secondary_outcomes, st, level=3)

    # Funnel plot
    if analysis and analysis.funnel_plot_b64:
        img = _b64_to_image(analysis.funnel_plot_b64, 10)
        if img:
            story.append(KeepTogether([
                img,
                _para("Figure 4. Funnel plot — assessment of publication bias.", st["caption"]),
            ]))
            story.append(Spacer(1, 0.3*cm))

    # Statistical summary box
    if analysis and analysis.results_json:
        try:
            res = json.loads(analysis.results_json)
            p  = res.get("pooled", {}) or {}
            h  = res.get("heterogeneity", {}) or {}
            em = res.get("effect_measure", review.effect_measure or "OR")
            eff = p.get("effect")
            lo  = p.get("ci_lower")
            hi  = p.get("ci_upper")
            pi  = res.get("prediction_interval", {}) or {}

            stat_rows = [
                ["Parameter", "Value"],
                ["Effect measure", em],
                ["Studies (k)", str(res.get("k", "—"))],
                ["Participants (N)", str(res.get("total_n", "—"))],
                ["Pooled effect (95% CI)",
                 f"{eff:.3f} [{lo:.3f}, {hi:.3f}]" if eff is not None else "—"],
                ["Prediction interval",
                 f"[{pi.get('lower'):.3f}, {pi.get('upper'):.3f}]"
                 if pi.get("lower") is not None else "—"],
                ["I²",  f"{h.get('I2', 0):.1f}%"],
                ["τ²",  f"{h.get('tau2', 0):.4f}"],
                ["Q (p-value)", f"{h.get('Q', 0):.2f} (p={h.get('Q_pvalue', 0):.3f})"],
                ["Model", f"{res.get('model', 'random')}-effects"],
            ]
            st_tbl = Table(stat_rows, colWidths=[6*cm, 10*cm])
            st_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
                ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_LGREY]),
                ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ]))
            story.append(_para("Table 2. Summary of meta-analysis results", st["label"]))
            story.append(Spacer(1, 0.1*cm))
            story.append(st_tbl)
            story.append(Spacer(1, 0.3*cm))
        except Exception:
            pass

    # ── 5. Discussion ────────────────────────────────────────────────────────
    story.append(PageBreak())
    _h1_block(story, "5.", "Discussion", st)

    if review.discussion:
        story.append(_para(review.discussion, st["body"]))
    else:
        for num, title in [
            ("5.1", "Summary of main results"),
            ("5.2", "Overall completeness and applicability of evidence"),
            ("5.3", "Quality of the evidence"),
            ("5.4", "Potential biases in the review process"),
            ("5.5", "Agreements and disagreements with other studies or reviews"),
        ]:
            story.append(_para(num + "  " + title, st["h2"]))
            story.append(_para("[Not yet generated — use AI section generation]", st["note"]))

    # ── 6. Authors' conclusions ──────────────────────────────────────────────
    _h1_block(story, "6.", "Authors' conclusions", st)

    if review.authors_conclusions:
        _sub(story, "6.1", "Implications for practice",
             review.authors_conclusions, st)
    else:
        _sub(story, "6.1", "Implications for practice",
             "[Not yet generated]", st)
    _sub(story, "6.2", "Implications for research",
         "[Not yet generated — describe gaps identified by this review]", st)

    # ── Declarations of interest ─────────────────────────────────────────────
    _h1_block(story, "", "Declarations of interest", st)
    story.append(_para("None declared.", st["body"]))

    # ── References ───────────────────────────────────────────────────────────
    story.append(PageBreak())
    _h1_block(story, "", "References", st)

    story.append(_para("References to studies included in this review", st["h2"]))
    story.append(_para("Included studies", st["h3"]))

    if review.references:
        # AI-generated references come as one numbered list; a single Paragraph
        # collapses all newlines into running prose (ReportLab ignores literal
        # "\n" unless it's an explicit <br/>), so each reference must be its own
        # Paragraph to render as a proper list, one per line.
        ref_lines = [ln.strip() for ln in review.references.splitlines() if ln.strip()]
        if len(ref_lines) <= 1:
            # The AI returned everything on one line — split right before each
            # reference-number marker ("2. Author...", "3. Author..."). The
            # lookbehind keeps this from also matching digits inside a DOI or
            # page range (e.g. "...0000002485." or "145-150."), and requiring
            # a capital letter right after avoids splitting on "150. doi:...".
            ref_lines = [
                m.strip() for m in re.split(r"(?<![\d.])(?=\d{1,3}\.\s[A-ZÁÉÍÓÚÑ])", review.references)
                if m.strip()
            ]
        for ln in ref_lines:
            story.append(_para(ln, st["body_sm"]))
            story.append(Spacer(1, 0.12 * cm))
    elif studies:
        for i, s in enumerate(studies, 1):
            authors  = s.authors or "Authors unknown"
            year     = s.year or "n.d."
            title    = s.title or s.study_label or "Untitled"
            journal  = s.journal or ""
            vol      = s.volume or ""
            issue_   = s.issue or ""
            fp       = s.first_page or ""
            lp       = s.last_page or ""
            doi_     = s.doi or ""
            pages    = f"{fp}–{lp}" if fp and lp else fp
            vol_iss  = f"{vol}({issue_})" if issue_ else vol
            ref_line = f"{i}. {authors} {year}. {title}. <i>{journal}</i>"
            if vol_iss:
                ref_line += f" {vol_iss}"
            if pages:
                ref_line += f":{pages}"
            if doi_:
                ref_line += f". doi:{doi_}"
            story.append(_para(ref_line + ".", st["body_sm"]))
    else:
        story.append(_para("[No studies added yet]", st["note"]))

    story.append(Spacer(1, 0.3*cm))
    story.append(_para("Additional references", st["h3"]))
    story.append(_para("[Additional methodological and background references not yet added]", st["note"]))

    # ── Appendices ───────────────────────────────────────────────────────────
    story.append(PageBreak())
    _h1_block(story, "", "Appendices", st)

    # Appendix 1 – GRADE evidence profile
    story.append(_para("Appendix 1. GRADE Evidence Profile", st["h2"]))
    if analysis and analysis.results_json:
        try:
            result_dict = json.loads(analysis.results_json)
            study_dicts = [
                {c.name: getattr(s, c.name) for c in s.__table__.columns}
                for s in studies
            ]
            grade_b64 = generate_grade_table(result_dict, study_dicts, outcome=review.title or "")
            img = _b64_to_image(grade_b64, 15.5)
            if img:
                story.append(img)
                story.append(_para(
                    "Table A1. GRADE evidence profile — certainty of evidence summary.",
                    st["caption"]))
        except Exception:
            story.append(_para("[GRADE table could not be generated — run meta-analysis first]", st["note"]))
    else:
        story.append(_para("[Run meta-analysis to generate GRADE evidence profile]", st["note"]))

    # Appendix 2 – Search strategies
    story.append(Spacer(1, 0.4*cm))
    story.append(_para("Appendix 2. Search Strategies", st["h2"]))
    story.append(_para(
        review.search_strategy or "[Search strategy not yet documented]", st["body_sm"]))

    try:
        doc.build(story)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el PDF: {exc}. Revisa si algún campo de texto de los estudios "
                    "(p. ej. diseño de estudio) tiene contenido inusualmente largo.",
        )
    buf.seek(0)

    safe_title = (review.title or "review").replace(" ", "_")[:60]
    filename = f"Cochrane_Review_{safe_title}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
