import json
import base64
import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, Paragraph, Spacer, Image,
    HRFlowable, PageBreak, Table, TableStyle, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

from ..database import get_db
from ..models import Review, Study, Analysis
from ..services.plots import (
    generate_prisma_2020, generate_grade_table, generate_forest_plot,
    generate_funnel_plot, generate_rob_traffic_light, _short_label,
)
from ..services.eligibility import eligible_studies, excluded_studies
from ..services.prospero import PROSPERO_FIELDS, load_answers
from ..services.statistics import meta_result_from_dict
from ..services.prisma import sync_prisma, prisma_plot_kwargs

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


_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_MD_BULLET = re.compile(r"^\s*[-*•]\s+")
_MD_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
_MD_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")


def _md(text) -> str:
    """Escape text and turn the Markdown the AI writes (headings, bold, italics, bullets,
    line breaks) into ReportLab paragraph markup, so no stray asterisks reach the PDF."""
    lines = []
    for line in _safe(text).replace("\r\n", "\n").split("\n"):
        h = _MD_HEADING.match(line)
        if h:
            line = f"**{h.group(1)}**"
        line = _MD_BULLET.sub("• ", line)
        line = _MD_BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", line)
        line = _MD_ITALIC.sub(r"<i>\1</i>", line)
        lines.append(line.replace("**", ""))
    html = re.sub(r"(<br/>){3,}", "<br/><br/>", "<br/>".join(lines))
    return re.sub(r"^(\s|<br/>)+|(\s|<br/>)+$", "", html)


def _para(text, style) -> Paragraph:
    return Paragraph(_md(text), style)


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


PDF_MARGIN = 2.2 * cm
_CAPTION_RESERVE = 1.6 * cm


def _figure_page(story, b64: str | None, caption: str, st: dict) -> bool:
    """Put a figure on its own page, landscape or portrait — whichever prints it larger."""
    if not b64:
        return False
    img = _b64_to_image(b64)
    if img is None:
        return False
    iw, ih = img.imageWidth, img.imageHeight

    def fit(page):
        w, h = page[0] - 2 * PDF_MARGIN, page[1] - 2 * PDF_MARGIN - _CAPTION_RESERVE
        return min(w / iw, h / ih)

    orient = "landscape" if fit(landscape(A4)) > fit(A4) else "portrait"
    scale = fit(landscape(A4) if orient == "landscape" else A4)
    img.drawWidth, img.drawHeight = iw * scale, ih * scale
    img.hAlign = "CENTER"
    story += [
        NextPageTemplate(orient), PageBreak(),
        img, Spacer(1, 0.25 * cm), _para(caption, st["caption"]),
        NextPageTemplate("portrait"), PageBreak(),
    ]
    return True


def _pdf_doc(buf, title: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=PDF_MARGIN, rightMargin=PDF_MARGIN,
        topMargin=PDF_MARGIN, bottomMargin=PDF_MARGIN,
        title=title, author="MetaAnalysis Cochrane Platform",
    )
    templates = []
    for name, size in (("portrait", A4), ("landscape", landscape(A4))):
        frame = Frame(PDF_MARGIN, PDF_MARGIN, size[0] - 2 * PDF_MARGIN, size[1] - 2 * PDF_MARGIN,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=name)
        templates.append(PageTemplate(id=name, frames=[frame], pagesize=size))
    doc.addPageTemplates(templates)
    return doc


def _fresh_plots(review: Review, analysis: Analysis | None, studies: list) -> dict:
    """Re-render plots with the current layout code; fall back to the stored PNGs."""
    plots = {
        "forest": analysis.forest_plot_b64 if analysis else None,
        "funnel": analysis.funnel_plot_b64 if analysis else None,
        "rob": analysis.rob_plot_b64 if analysis else None,
    }
    if not analysis or not analysis.results_json:
        return plots
    study_dicts = [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in studies]
    try:
        result = meta_result_from_dict(json.loads(analysis.results_json))
        plots["forest"] = generate_forest_plot(result, title=review.title or "") or plots["forest"]
        plots["funnel"] = generate_funnel_plot(result, title="Funnel Plot") or plots["funnel"]
    except Exception:
        pass
    if plots["rob"] and study_dicts:
        try:
            plots["rob"] = generate_rob_traffic_light(study_dicts) or plots["rob"]
        except Exception:
            pass
    return plots


def _ascii_filename(title: str) -> str:
    import unicodedata
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", plain).strip("_")[:60] or "review"


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
        story.append(_para(f"**{label}:** {value}", st["body_sm"]))


def _hr(story, color=C_LBLUE):
    story.append(HRFlowable(width="100%", thickness=1, color=color, spaceAfter=4, spaceBefore=4))


# ── Study characteristics table ──────────────────────────────────────────────

_ROB_LABEL_ES = {"low": "Bajo", "some_concerns": "Algunas preocupaciones", "high": "Alto"}
_ROB_COLOR = {"low": C_GREEN, "some_concerns": C_ORANGE, "high": C_RED}


def _study_name(s) -> str:
    label = s.study_label or f"{s.authors or '—'} {s.year or ''}"
    name = _short_label(label)
    if s.year and str(s.year) not in name:
        name = f"{name} {s.year}"
    return name


def _rule_table(rows: list, col_widths: list, font_size: float = 7.2) -> Table:
    """Journal-style table: header rule, light zebra rows, no vertical lines."""
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("LINEABOVE",     (0, 0), (-1, 0), 1.2, C_BLACK),
        ("LINEBELOW",     (0, 0), (-1, 0), 0.7, C_BLACK),
        ("LINEBELOW",     (0, -1), (-1, -1), 1.2, C_BLACK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, colors.HexColor("#F3F6F9")]),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _characteristics_table(studies: list, st: dict) -> list:
    """'Characteristics of included studies': one compact row per study, landscape page."""
    cell = ParagraphStyle("ctCell", fontSize=7.2, leading=8.6)
    head = ParagraphStyle("ctHead", parent=cell, fontName="Helvetica-Bold")
    rob_style = {k: ParagraphStyle(f"ctRob{k}", parent=cell, fontName="Helvetica-Bold", textColor=c)
                 for k, c in _ROB_COLOR.items()}

    def P(text, style=cell, limit=None):
        text = _trunc(text, limit) if limit else (str(text) if text not in (None, "") else "—")
        return Paragraph(_safe(text), style)

    header = [P(h, head) for h in (
        "Estudio", "País / ámbito", "Diseño", "N", "Población",
        "Intervención vs. comparador", "Resultados principales", "RoB")]
    rows = [header]
    for s in studies:
        n = (s.total_intervention or 0) + (s.total_control or 0) or s.sample_size
        population = s.patient_population or s.inclusion_criteria
        if s.age_mean and population:
            population = f"{population} (edad media {s.age_mean:g})"
        results = s.key_findings or s.survival_outcomes or s.study_results or s.findings
        rows.append([
            P(_study_name(s), head),
            P(s.country or s.setting, limit=40),
            P(s.study_design, limit=60),
            P(n),
            P(population, limit=150),
            P(s.group_comparison, limit=150),
            P(results, limit=260),
            P(_ROB_LABEL_ES.get(s.rob_overall, "Sin evaluar"), rob_style.get(s.rob_overall, cell)),
        ])

    widths = [c * cm for c in (3.3, 2.0, 2.4, 1.1, 4.2, 4.2, 5.6, 2.5)]  # 25.3 cm landscape frame
    foot = ParagraphStyle("ctFoot", fontSize=6.8, leading=8.5, textColor=C_GREY)
    return [
        _para("Table 1. Characteristics of included studies", st["label"]),
        Spacer(1, 0.15 * cm),
        _rule_table(rows, widths),
        Spacer(1, 0.15 * cm),
        Paragraph(
            "N: participantes analizados; RoB: riesgo de sesgo global (Bajo / Algunas preocupaciones / Alto); "
            "—: no reportado en la información disponible. Textos abreviados; el detalle completo de cada "
            "estudio está en la base de datos de la revisión.", foot),
    ]


def _excluded_table(studies: list, st: dict) -> list:
    """'Characteristics of excluded studies': study and reason for exclusion."""
    cell = ParagraphStyle("exCell", fontSize=7.8, leading=9.6)
    head = ParagraphStyle("exHead", parent=cell, fontName="Helvetica-Bold")
    rows = [[Paragraph("Estudio", head), Paragraph("Motivo de exclusión", head)]]
    for s in studies:
        reason = s.exclusion_reason or "Motivo no registrado"
        rows.append([Paragraph(_safe(_study_name(s)), head), Paragraph(_safe(_trunc(reason, 300)), cell)])
    return [
        _para("Table 2. Characteristics of excluded studies", st["label"]),
        Spacer(1, 0.15 * cm),
        _rule_table(rows, [4.6 * cm, 12.0 * cm]),
    ]


def _exclusion_summary(studies: list) -> str:
    from collections import Counter
    if not studies:
        return "No se excluyeron estudios tras el cribado."
    reasons = Counter(
        (s.exclusion_reason or "Motivo no registrado").split(":", 1)[0].split("—", 1)[0].strip()[:90]
        for s in studies
    )
    parts = "; ".join(f"{r} (n = {n})" for r, n in reasons.most_common())
    return (f"Se excluyeron {len(studies)} estudios tras aplicar los criterios de elegibilidad. "
            f"Motivos: {parts}. El detalle de cada estudio se presenta en la Tabla 2.")


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

def _prospero_section(story, review: Review, st: dict):
    """PROSPERO registration answers (English), placed before the abstract."""
    answers = load_answers(review)
    if not answers:
        return
    _h1_block(story, "", "PROSPERO registration", st)
    if review.prospero_id:
        story.append(_para(f"**Registration number:** {review.prospero_id}", st["body_sm"]))
    for key, label, _ in PROSPERO_FIELDS:
        story.append(_para(label, st["h3"]))
        story.append(_para(answers.get(key) or "[Not provided]", st["body_sm"]))
    story.append(PageBreak())


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

    studies = eligible_studies(db, review_id)
    excluded = excluded_studies(db, review_id)
    analysis = (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )

    buf = io.BytesIO()
    doc = _pdf_doc(buf, review.title or "Systematic Review")
    plots = _fresh_plots(review, analysis, studies)

    st = _styles()
    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    _cover(story, review, st, len(studies))
    _prospero_section(story, review, st)

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
            story.append(_para("Primary outcomes", st["label"]))
            story.append(_para(review.primary_outcomes, st["body"]))
        if review.secondary_outcomes:
            story.append(_para("Secondary outcomes", st["label"]))
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
    has_prisma = bool(review.studies)
    if has_prisma:
        try:
            prisma_b64 = generate_prisma_2020(**prisma_plot_kwargs(sync_prisma(db, review)["fields"]))
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

    if studies:
        story += [NextPageTemplate("landscape"), PageBreak(),
                  *_characteristics_table(studies, st),
                  NextPageTemplate("portrait"), PageBreak()]

    _sub(story, "4.1.3", "Excluded studies", _exclusion_summary(excluded), st, level=3)
    if excluded:
        story += _excluded_table(excluded, st)
        story.append(Spacer(1, 0.3 * cm))

    _sub(story, "4.1.4", "Risk of bias in included studies",
         review.risk_of_bias_results, st, level=3)

    _figure_page(story, plots["rob"], "Figure 2. Risk of bias summary (Cochrane RoB 2).", st)

    _sub(story, "4.2", "Effects of interventions", None, st)
    _sub(story, "4.2.1", "Primary outcomes",
         review.intervention_effects or review.results_text, st, level=3)

    _figure_page(story, plots["forest"], "Figure 3. Forest plot — pooled effect estimate.", st)

    _sub(story, "4.2.2", "Secondary outcomes",
         review.secondary_outcomes, st, level=3)

    if plots["funnel"]:
        img = _b64_to_image(plots["funnel"], 14)
        if img:
            img.hAlign = "CENTER"
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
            _figure_page(story, grade_b64,
                         "Table A1. GRADE evidence profile — certainty of evidence summary.", st)
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

    safe_title = _ascii_filename(review.title or "review")
    filename = f"Cochrane_Review_{safe_title}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Word DOCX export ─────────────────────────────────────────────────────────

def _docx_add_heading(doc_obj, text: str, level: int, color_hex: str = "005A9C"):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    h = doc_obj.add_heading(text, level=level)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in h.runs:
        run.font.color.rgb = RGBColor(
            int(color_hex[0:2], 16),
            int(color_hex[2:4], 16),
            int(color_hex[4:6], 16),
        )
        run.font.size = Pt({1: 16, 2: 13, 3: 11}.get(level, 11))
    return h


def _docx_add_body(doc_obj, text: str, italic: bool = False, size_pt: int = 10):
    """Add text as Word paragraphs, rendering the AI's Markdown (headings, **bold**, bullets)."""
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    if not text:
        return
    for line in str(text).splitlines():
        if not line.strip():
            continue
        h = _MD_HEADING.match(line)
        if h:
            line = f"**{h.group(1)}**"
        line = _MD_BULLET.sub("• ", line)
        p = doc_obj.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for part in re.split(r"(\*\*.+?\*\*)", line):
            if not part:
                continue
            bold = part.startswith("**") and part.endswith("**") and len(part) > 4
            run = p.add_run(_MD_ITALIC.sub(r"\1", part[2:-2] if bold else part).replace("**", ""))
            run.bold = bold
            run.italic = italic
            run.font.size = Pt(size_pt)


def _docx_embed_b64_image(doc_obj, b64: str, width_cm: float, caption: str):
    """Decode a base64 PNG, write to temp buffer and embed in document."""
    import tempfile, os
    from docx.shared import Cm
    try:
        data = base64.b64decode(b64)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        doc_obj.add_picture(tmp_path, width=Cm(width_cm))
        os.unlink(tmp_path)
        if caption:
            cap = doc_obj.add_paragraph(caption)
            cap.style = "Caption" if "Caption" in [s.name for s in doc_obj.styles] else cap.style
            from docx.shared import Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cap.runs:
                run.font.size = Pt(8)
    except Exception:
        doc_obj.add_paragraph(f"[{caption} — no disponible]")


def _docx_set_orientation(doc_obj, landscape_page: bool):
    from docx.enum.section import WD_ORIENT, WD_SECTION
    sec = doc_obj.add_section(WD_SECTION.NEW_PAGE)
    w, h = sec.page_width, sec.page_height
    if landscape_page != (w > h):
        sec.page_width, sec.page_height = h, w
    sec.orientation = WD_ORIENT.LANDSCAPE if landscape_page else WD_ORIENT.PORTRAIT


def _docx_rule_table(doc_obj, rows: list, widths_cm: list, size_pt: float):
    from docx.shared import Pt, Cm
    tbl = doc_obj.add_table(rows=len(rows), cols=len(widths_cm))
    tbl.style = "Table Grid"
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            cell = tbl.rows[r].cells[c]
            cell.width = Cm(widths_cm[c])
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(value))
            run.font.size = Pt(size_pt)
            run.bold = r == 0 or c == 0
    return tbl


def _docx_study_table(doc_obj, studies: list):
    """Compact 'Characteristics of included studies' table on its own landscape page."""
    _docx_set_orientation(doc_obj, True)
    _docx_add_body(doc_obj, "**Tabla 1. Características de los estudios incluidos**", size_pt=10)
    rows = [["Estudio", "País / ámbito", "Diseño", "N", "Población",
             "Intervención vs. comparador", "Resultados principales", "RoB"]]
    for s in studies:
        n = (s.total_intervention or 0) + (s.total_control or 0) or s.sample_size
        rows.append([
            _study_name(s),
            _trunc(s.country or s.setting, 40),
            _trunc(s.study_design, 60),
            str(n) if n else "—",
            _trunc(s.patient_population or s.inclusion_criteria, 150),
            _trunc(s.group_comparison, 150),
            _trunc(s.key_findings or s.survival_outcomes or s.study_results or s.findings, 260),
            _ROB_LABEL_ES.get(s.rob_overall, "Sin evaluar"),
        ])
    _docx_rule_table(doc_obj, rows, [3.3, 2.0, 2.4, 1.1, 4.2, 4.2, 5.6, 2.5], 7)
    _docx_add_body(doc_obj, "N: participantes analizados; RoB: riesgo de sesgo global; "
                            "—: no reportado en la información disponible.", italic=True, size_pt=7)
    _docx_set_orientation(doc_obj, False)


def _docx_excluded_table(doc_obj, studies: list):
    _docx_add_body(doc_obj, "**Tabla 2. Características de los estudios excluidos**", size_pt=10)
    rows = [["Estudio", "Motivo de exclusión"]]
    rows += [[_study_name(s), _trunc(s.exclusion_reason or "Motivo no registrado", 300)] for s in studies]
    _docx_rule_table(doc_obj, rows, [4.6, 12.0], 8)


@router.get("/docx")
def export_docx(review_id: int, db: Session = Depends(get_db)):
    """Export the review as an editable Word (.docx) document."""
    try:
        from docx import Document
        from docx.shared import Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        raise HTTPException(status_code=500,
                            detail="python-docx no instalado. Ejecuta: pip install python-docx")

    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    studies = eligible_studies(db, review_id)
    analysis = (
        db.query(Analysis)
        .filter(Analysis.review_id == review_id)
        .order_by(Analysis.created_at.desc())
        .first()
    )

    d = Document()

    # ── Page margins ────────────────────────────────────────────────────────
    for section in d.sections:
        section.top_margin    = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin   = Cm(3)
        section.right_margin  = Cm(2.5)

    # ── Cover ───────────────────────────────────────────────────────────────
    cover_title = d.add_paragraph(review.title or "Revisión Sistemática y Metaanálisis")
    cover_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in cover_title.runs:
        run.bold = True
        run.font.size = Pt(20)
        run.font.color.rgb = RGBColor(0x00, 0x5A, 0x9C)

    d.add_paragraph(f"Registro: {review.prospero_id or 'No registrado'} · "
                    f"Estudios incluidos: {len(studies)} · "
                    f"Fecha: {datetime.utcnow().strftime('%d/%m/%Y')}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_page_break()

    prospero_answers = load_answers(review)
    if prospero_answers:
        _docx_add_heading(d, "PROSPERO registration", 1)
        if review.prospero_id:
            _docx_add_body(d, f"**Registration number:** {review.prospero_id}")
        for key, label, _ in PROSPERO_FIELDS:
            _docx_add_heading(d, label, 3)
            _docx_add_body(d, prospero_answers.get(key) or "[Not provided]")
        d.add_page_break()

    # ── Abstract ────────────────────────────────────────────────────────────
    _docx_add_heading(d, "Resumen (Abstract)", 1)
    _docx_add_body(d, review.abstract or "[Pendiente de generar — usa la sección IA]")
    d.add_page_break()

    # ── 1. Background ───────────────────────────────────────────────────────
    _docx_add_heading(d, "1. Antecedentes (Background)", 1)
    text = (review.background_text
            or "\n".join(filter(None, [review.background_condition,
                                        review.background_intervention,
                                        review.background_mechanism,
                                        review.background_importance])))
    _docx_add_body(d, text or "[Pendiente de generar]")

    # ── PICO ────────────────────────────────────────────────────────────────
    _docx_add_heading(d, "Marco PICO", 2)
    pico_tbl = d.add_table(rows=4, cols=2)
    pico_tbl.style = "Table Grid"
    for row, (lbl, val) in zip(pico_tbl.rows, [
        ("P – Población",        review.population),
        ("I – Intervención",     review.intervention),
        ("C – Comparador",       review.comparison),
        ("O – Desenlaces",       review.outcomes),
    ]):
        row.cells[0].text = lbl
        row.cells[1].text = val or "—"
        row.cells[0].width = Cm(4)
        row.cells[1].width = Cm(13)
        for run in row.cells[0].paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(9)
        for run in row.cells[1].paragraphs[0].runs:
            run.font.size = Pt(9)

    # ── 2. Objectives ───────────────────────────────────────────────────────
    _docx_add_heading(d, "2. Objetivos (Objectives)", 1)
    _docx_add_body(d, review.objectives or "[Pendiente de generar]")

    # ── 3. Methods ──────────────────────────────────────────────────────────
    _docx_add_heading(d, "3. Métodos (Methods)", 1)
    _docx_add_body(d, review.methods_text or "")

    if not review.methods_text:
        for num, title, val in [
            ("3.1", "Criterios de inclusión",            review.inclusion_criteria),
            ("3.2", "Estrategia de búsqueda",            review.search_strategy),
            ("3.3", "Selección de estudios",             review.study_selection_method),
            ("3.4", "Extracción de datos",               review.data_extraction_method),
            ("3.5", "Evaluación de riesgo de sesgo",     review.risk_of_bias_method),
            ("3.6", "Medidas del efecto",                f"Medida de efecto: {review.effect_measure or 'OR'}"),
            ("3.7", "Evaluación de heterogeneidad",      review.heterogeneity_method),
        ]:
            _docx_add_heading(d, f"{num}  {title}", 2)
            _docx_add_body(d, val or "[Pendiente]", size_pt=9)

    # ── 4. Results ──────────────────────────────────────────────────────────
    d.add_page_break()
    _docx_add_heading(d, "4. Resultados (Results)", 1)
    _docx_add_heading(d, "4.1  Descripción de los estudios", 2)
    _docx_add_heading(d, "4.1.1  Resultados de la búsqueda", 3)
    _docx_add_body(d, review.description_of_studies
                   or (f"Se incluyeron {len(studies)} estudios en esta revisión." if studies else "[Pendiente]"))

    # PRISMA diagram
    has_prisma = bool(review.studies)
    if has_prisma:
        try:
            prisma_b64 = generate_prisma_2020(**prisma_plot_kwargs(sync_prisma(db, review)["fields"]))
            _docx_embed_b64_image(d, prisma_b64, 14, "Figura 1. Diagrama de flujo PRISMA 2020.")
        except Exception:
            pass

    # Study characteristics table
    _docx_add_heading(d, "4.1.2  Estudios incluidos", 3)
    if studies:
        _docx_study_table(d, studies)
    else:
        _docx_add_body(d, "[Sin estudios incluidos]")

    excluded = excluded_studies(db, review_id)
    _docx_add_heading(d, "Estudios excluidos", 3)
    _docx_add_body(d, _exclusion_summary(excluded))
    if excluded:
        _docx_excluded_table(d, excluded)

    _docx_add_heading(d, "4.1.3  Riesgo de sesgo en los estudios incluidos", 3)
    _docx_add_body(d, review.risk_of_bias_results or "[Pendiente de generar]")

    _docx_add_heading(d, "4.2  Efectos de las intervenciones", 2)
    _docx_add_body(d, review.intervention_effects or review.results_text or "[Pendiente de generar]")

    # Statistical summary
    if analysis and analysis.results_json:
        try:
            res = json.loads(analysis.results_json)
            p   = res.get("pooled", {}) or {}
            h   = res.get("heterogeneity", {}) or {}
            em  = res.get("effect_measure", review.effect_measure or "OR")
            eff, lo, hi = p.get("effect"), p.get("ci_lower"), p.get("ci_upper")
            pi  = res.get("prediction_interval", {}) or {}

            _docx_add_heading(d, "Tabla 2. Resumen de resultados del metaanálisis", 3)
            stat_tbl = d.add_table(rows=10, cols=2)
            stat_tbl.style = "Table Grid"
            rows_data = [
                ("Medida de efecto", em),
                ("Estudios (k)",      str(res.get("k", "—"))),
                ("Participantes (N)", str(res.get("total_n", "—"))),
                ("Efecto combinado (IC 95%)",
                 f"{eff:.3f} [{lo:.3f}, {hi:.3f}]" if eff is not None else "—"),
                ("Intervalo de predicción",
                 f"[{pi.get('lower'):.3f}, {pi.get('upper'):.3f}]"
                 if pi.get("lower") is not None else "—"),
                ("I²",               f"{h.get('I2', 0):.1f}%"),
                ("τ²",               f"{h.get('tau2', 0):.4f}"),
                ("Q (valor p)",      f"{h.get('Q', 0):.2f} (p={h.get('Q_pvalue', 0):.3f})"),
                ("Modelo",           f"{res.get('model', 'random')}-effects"),
                ("Fecha del análisis", datetime.utcnow().strftime("%d/%m/%Y")),
            ]
            for row, (k, v) in zip(stat_tbl.rows, rows_data):
                row.cells[0].text = k
                row.cells[1].text = v
                row.cells[0].width = Cm(6)
                row.cells[1].width = Cm(11)
                for run in row.cells[0].paragraphs[0].runs:
                    run.bold = True
                    run.font.size = Pt(9)
                for run in row.cells[1].paragraphs[0].runs:
                    run.font.size = Pt(9)
        except Exception:
            pass

    # Forest plot
    if analysis and analysis.forest_plot_b64:
        d.add_paragraph()
        _docx_embed_b64_image(d, analysis.forest_plot_b64, 16,
                               "Figura 2. Forest plot — estimación del efecto combinado.")

    # Funnel plot
    if analysis and analysis.funnel_plot_b64:
        _docx_embed_b64_image(d, analysis.funnel_plot_b64, 10,
                               "Figura 3. Funnel plot — evaluación del sesgo de publicación.")

    # ── 5. Discussion ───────────────────────────────────────────────────────
    d.add_page_break()
    _docx_add_heading(d, "5. Discusión (Discussion)", 1)
    _docx_add_body(d, review.discussion or "[Pendiente de generar]")

    # ── 6. Conclusions ──────────────────────────────────────────────────────
    _docx_add_heading(d, "6. Conclusiones de los autores (Authors' Conclusions)", 1)
    _docx_add_body(d, review.authors_conclusions or "[Pendiente de generar]")

    # ── References ──────────────────────────────────────────────────────────
    d.add_page_break()
    _docx_add_heading(d, "Referencias (References)", 1)
    if review.references:
        _docx_add_body(d, review.references, size_pt=9)
    elif studies:
        for i, s in enumerate(studies, 1):
            authors_ = s.authors or "Autores desconocidos"
            year_    = s.year or "s.f."
            title_   = s.title or s.study_label or "Sin título"
            journal_ = s.journal or ""
            doi_     = s.doi or ""
            ref_line = f"{i}. {authors_} ({year_}). {title_}."
            if journal_:
                ref_line += f" {journal_}."
            if doi_:
                ref_line += f" doi:{doi_}"
            _docx_add_body(d, ref_line, size_pt=9)

    # ── Appendix 1: GRADE ───────────────────────────────────────────────────
    d.add_page_break()
    _docx_add_heading(d, "Apéndice 1. Perfil de evidencia GRADE", 1)
    if analysis and analysis.results_json:
        try:
            result_dict = json.loads(analysis.results_json)
            study_dicts = [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in studies]
            grade_b64 = generate_grade_table(result_dict, study_dicts, outcome=review.title or "")
            _docx_embed_b64_image(d, grade_b64, 16,
                                   "Tabla A1. Perfil de evidencia GRADE — certeza de la evidencia.")
        except Exception:
            _docx_add_body(d, "[Tabla GRADE no disponible — ejecuta el metaanálisis primero]", italic=True)
    else:
        _docx_add_body(d, "[Ejecuta el metaanálisis para generar el perfil GRADE]", italic=True)

    # ── Appendix 2: Search strategy ─────────────────────────────────────────
    _docx_add_heading(d, "Apéndice 2. Estrategias de búsqueda", 1)
    _docx_add_body(d, review.search_strategy or "[Estrategia de búsqueda no documentada]", size_pt=9)

    # ── Stream out ──────────────────────────────────────────────────────────
    buf = io.BytesIO()
    d.save(buf)
    buf.seek(0)

    safe_title = _ascii_filename(review.title or "revision")
    filename = f"Cochrane_Review_{safe_title}_{datetime.utcnow().strftime('%Y%m%d')}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
