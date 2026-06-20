"""
Forest plot and funnel plot generation using matplotlib.
Returns base64-encoded PNG strings for API responses.
"""
import gc
import io
import math
import base64
from typing import Optional
import numpy as np
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams['figure.max_open_warning'] = 5
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory

from typing import Optional as _Opt

from .statistics import MetaResult, back_transform


def _b64(fig, dpi: int = 80) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    buf.close()
    plt.close(fig)
    plt.close("all")
    gc.collect()
    return encoded


def generate_forest_plot(result: MetaResult, title: str = "",
                          null_value: Optional[float] = None) -> str:
    """Return base64 PNG of the forest plot."""
    plt.close("all")
    gc.collect()
    try:
        return _forest_plot_inner(result, title, null_value, fig_width=13)
    except (MemoryError, Exception) as exc:
        if "bad_alloc" in str(exc) or isinstance(exc, MemoryError):
            plt.close("all")
            gc.collect()
            return _forest_plot_inner(result, title, null_value, fig_width=10.5)
        raise


def _forest_plot_inner(result: MetaResult, title: str,
                        null_value: Optional[float], fig_width: float = 13) -> str:
    """Render the forest plot.

    Font sizes here are deliberately large (14-19pt) relative to a typical
    matplotlib chart. This image is always embedded in the Cochrane PDF at a
    fixed physical width (~16.5cm, close to the page's full text width) —
    roughly 0.6x this figure's design width — so whatever size is set here
    is what actually reaches paper. Anything tuned to "look right" only in a
    full-screen browser preview will print unreadably small.
    """
    bt = lambda v: back_transform(v, result.effect_measure)
    is_log = result.effect_measure in ("OR", "RR")
    null = null_value if null_value is not None else (1.0 if is_log else 0.0)
    # "PRECALCULATED" is a long internal code name, not a real effect-measure
    # abbreviation like OR/RR/MD — too wide for the header column at this font
    # size, so it gets a short display label instead.
    measure_label = "TE" if result.effect_measure == "PRECALCULATED" else result.effect_measure

    F_HEADER = 17.5
    F_LABEL  = 15.5
    F_DATA   = 15
    F_POOLED = 17
    F_HET    = 14.5
    F_AXIS   = 14.5
    F_TITLE  = 20

    studies = result.studies
    k = len(studies)
    fig_height = max(5.5, min(k * 0.62 + 3.4, 26))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    # Fixed margins set explicitly (instead of plt.tight_layout()) so the plot
    # area's own width never changes. The study-label / CI / weight columns
    # are anchored to the FIGURE (not the axes) via a blended transform, so
    # their gaps stay constant in absolute terms regardless of how wide the
    # data axis ends up — tight_layout() used to shrink the axes box to make
    # room for this overhanging text, which silently compressed the axes-
    # fraction gaps between columns until long values started overlapping.
    LEFT, RIGHT, TOP, BOTTOM = 0.30, 0.60, 0.91, 0.10
    fig.subplots_adjust(left=LEFT, right=RIGHT, top=TOP, bottom=BOTTOM)
    figx = blended_transform_factory(fig.transFigure, ax.transData)
    LABEL_X, CI_X, WEIGHT_X = LEFT - 0.012, RIGHT + 0.018, 0.975

    y_positions = list(range(k, 0, -1))

    # Column headers
    ax.text(LABEL_X, k + 1.5, "Estudio", fontsize=F_HEADER, fontweight="bold",
            ha="right", va="center", transform=figx)
    ax.text(CI_X, k + 1.5, f"{measure_label} (IC 95%)", fontsize=F_HEADER,
            fontweight="bold", ha="left", va="center", transform=figx)
    ax.text(WEIGHT_X, k + 1.5, "Peso (%)", fontsize=F_HEADER, fontweight="bold",
            ha="right", va="center", transform=figx)

    # X-axis limits
    all_vals = []
    for s in studies:
        all_vals.extend([bt(s.ci_lower), bt(s.ci_upper)])
    all_vals.extend([bt(result.pooled_lower), bt(result.pooled_upper)])
    if is_log:
        x_lo = max(0.01, min(all_vals) * 0.7)
        x_hi = max(all_vals) * 1.4
        ax.set_xscale("log")
    else:
        span = max(all_vals) - min(all_vals)
        x_lo = min(all_vals) - span * 0.15
        x_hi = max(all_vals) + span * 0.15

    # Null line
    ax.axvline(x=null, color="black", linewidth=1.1, linestyle="--", alpha=0.6)

    # Study rows
    for i, (s, y) in enumerate(zip(studies, y_positions)):
        effect = bt(s.effect)
        lo = bt(s.ci_lower)
        hi = bt(s.ci_upper)
        weight = s.weight_re if result.model == "random" else s.weight_fe
        box_size = max(0.06, weight / 100 * 0.7)

        # CI line
        ax.plot([lo, hi], [y, y], color="#2c3e50", linewidth=1.8, zorder=2)
        # Square
        rect = mpatches.FancyBboxPatch(
            (effect - box_size / 2, y - box_size / 4),
            box_size, box_size / 2,
            boxstyle="square,pad=0",
            facecolor="#2980b9", edgecolor="#1a252f", linewidth=0.7, zorder=3,
        )
        ax.add_patch(rect)

        # Labels
        ax.text(LABEL_X, y, s.study_label, fontsize=F_LABEL, ha="right", va="center",
                transform=figx)
        ci_text = f"{effect:.2f} [{lo:.2f}, {hi:.2f}]"
        ax.text(CI_X, y, ci_text, fontsize=F_DATA, ha="left", va="center",
                transform=figx)
        ax.text(WEIGHT_X, y, f"{weight:.1f}", fontsize=F_DATA, ha="right", va="center",
                transform=figx)

    # Pooled diamond
    p_eff = bt(result.pooled_effect)
    p_lo = bt(result.pooled_lower)
    p_hi = bt(result.pooled_upper)
    diamond_y = 0
    diamond_pts = np.array([
        [p_lo, diamond_y],
        [p_eff, diamond_y + 0.32],
        [p_hi, diamond_y],
        [p_eff, diamond_y - 0.32],
    ])
    diamond_patch = plt.Polygon(diamond_pts, closed=True,
                                facecolor="#c0392b", edgecolor="#922b21", linewidth=1.0, zorder=4)
    ax.add_patch(diamond_patch)

    # Separator line
    ax.axhline(y=0.6, color="black", linewidth=1.1)

    # Pooled label
    model_es = "aleatorios" if result.model == "random" else "fijos"
    ax.text(LABEL_X, diamond_y, f"Total (efectos {model_es}, k={result.k})",
            fontsize=F_POOLED, fontweight="bold", ha="right", va="center",
            transform=figx)
    ci_pooled = f"{p_eff:.2f} [{p_lo:.2f}, {p_hi:.2f}]"
    ax.text(CI_X, diamond_y, ci_pooled, fontsize=F_POOLED, fontweight="bold",
            ha="left", va="center", transform=figx)

    # Heterogeneity box — centered under the plot area itself (stays inside
    # the fixed axes box, so the regular axes-fraction transform is fine here)
    het = (f"Heterogeneidad: Q={result.Q:.1f} (df={result.Q_df}, "
           f"p={result.Q_pvalue:.3f}),  I²={result.I2:.0f}%,  τ²={result.tau2:.3f}")
    ax.text(0.5, -1.15, het, fontsize=F_HET, ha="center", va="center",
            transform=ax.get_yaxis_transform(),
            bbox=dict(facecolor="#ecf0f1", edgecolor="gray", boxstyle="round,pad=0.4"))

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(-2.0, k + 2)
    ax.set_yticks([])
    ax.set_xlabel(f"Favorece control  ←  {measure_label}  →  Favorece intervención",
                  fontsize=F_AXIS)
    ax.tick_params(axis="x", labelsize=F_AXIS)
    if title:
        ax.set_title(title, fontsize=F_TITLE, fontweight="bold", pad=16)
    ax.spines["left"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    # No plt.tight_layout() here on purpose — see the comment by `subplots_adjust`
    # above. bbox_inches="tight" in _b64()'s savefig still trims the outer
    # whitespace around the final content without touching internal proportions.
    return _b64(fig, dpi=130)


def generate_funnel_plot(result: MetaResult, title: str = "") -> str:
    """Return base64 PNG of the funnel plot (SE vs effect)."""
    plt.close("all")
    gc.collect()
    bt = lambda v: back_transform(v, result.effect_measure)
    is_log = result.effect_measure in ("OR", "RR")
    null = 1.0 if is_log else 0.0
    pooled = bt(result.pooled_effect)

    effects = [bt(s.effect) for s in result.studies]
    se_values = [math.sqrt(s.variance) for s in result.studies]
    if is_log:
        # se on log scale, effect on original scale — keep effect on log for funnel
        effects = [math.log(max(e, 1e-10)) for e in effects]
        pooled_log = result.pooled_effect
        null_log = math.log(null)
    else:
        pooled_log = result.pooled_effect
        null_log = null

    fig, ax = plt.subplots(figsize=(7, 6))

    max_se = max(se_values) * 1.1
    # Funnel lines
    for z in [1.96]:
        x_lo = [null_log - z * se for se in np.linspace(0, max_se, 100)]
        x_hi = [null_log + z * se for se in np.linspace(0, max_se, 100)]
        se_range = np.linspace(0, max_se, 100)
        ax.plot(x_lo, se_range, "b--", linewidth=0.8, alpha=0.5)
        ax.plot(x_hi, se_range, "b--", linewidth=0.8, alpha=0.5)

    ax.axvline(x=null_log, color="gray", linewidth=0.8, linestyle=":")
    ax.axvline(x=pooled_log, color="#c0392b", linewidth=1.2, linestyle="--",
               label=f"Pooled {result.effect_measure}")

    ax.scatter(effects, se_values, color="#2980b9", s=40, alpha=0.8, zorder=3)

    ax.invert_yaxis()
    ax.set_ylabel("Standard Error", fontsize=9)
    label = f"log({result.effect_measure})" if is_log else result.effect_measure
    ax.set_xlabel(label, fontsize=9)
    ax.set_title(title or "Funnel Plot", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)

    # Add Egger's test note
    if len(effects) >= 3:
        try:
            from scipy.stats import linregress
            slopes = linregress(np.array(effects) / np.array(se_values), np.array(se_values))
            ax.text(0.05, 0.95,
                    f"Egger: intercept={slopes.intercept:.2f}, p={slopes.pvalue:.3f}",
                    transform=ax.transAxes, fontsize=7.5, va="top",
                    bbox=dict(facecolor="white", edgecolor="gray", alpha=0.8))
        except Exception:
            pass

    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    plt.tight_layout()
    return _b64(fig)


def generate_prisma_2020(
    db_names: _Opt[str] = None,          # "PubMed=45,Scopus=32"
    other_sources: _Opt[int] = None,
    duplicates_removed: _Opt[int] = None,
    other_removed: _Opt[int] = None,
    screened: _Opt[int] = None,
    excluded_screening: _Opt[int] = None,
    sought: _Opt[int] = None,
    not_retrieved: _Opt[int] = None,
    assessed: _Opt[int] = None,
    excluded_eligibility: _Opt[int] = None,
    exclusion_reasons: _Opt[str] = None,  # "Wrong population=5,No outcome=3"
    included: _Opt[int] = None,
    reports_included: _Opt[int] = None,
) -> str:
    """Generate a publication-quality PRISMA 2020 flow diagram, base64 PNG.

    Every box's height is derived from its actual (pre-wrapped) text, and the
    figure's total height is computed from the sum of all boxes before a
    single pixel is drawn — so the diagram never clips or overlaps text
    regardless of how many databases or exclusion reasons are listed, and
    never wastes space when there are few.
    """
    import textwrap

    def _n(v) -> str:
        return str(v) if v is not None else "?"

    def _parse_kv_list(s: _Opt[str]):
        """'PubMed=45,Scopus=32' -> (['PubMed (n = 45)', 'Scopus (n = 32)'], 77)."""
        items, total = [], 0
        for part in (s or "").split(","):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                nm, cnt = part.rsplit("=", 1)
                try:
                    cnt_i = int(cnt.strip())
                    total += cnt_i
                    items.append(f"{nm.strip()} (n = {cnt_i})")
                    continue
                except ValueError:
                    pass
            items.append(part)
        return items, total

    # ── Cochrane-aligned palette ─────────────────────────────────────────────
    NAVY         = "#1B2A4A"
    BLUE_BORDER  = "#0B5FA5"
    BLUE_FILL    = "#EAF3FB"
    RED_BORDER   = "#C0392B"
    RED_FILL     = "#FDEDED"
    AMBER_BORDER = "#C2840C"
    AMBER_FILL   = "#FFF6E3"
    GREEN_BORDER = "#1E8449"
    GREEN_FILL   = "#EAF8EF"
    TEXT         = NAVY
    TEXT_MUTED   = "#5B6B82"

    FIG_W = 13.0
    MAIN_X, MAIN_W = 0.115, 0.40
    GAP_COL        = 0.045
    SIDE_X         = MAIN_X + MAIN_W + GAP_COL
    SIDE_W         = 0.345
    FULL_W         = (SIDE_X + SIDE_W) - MAIN_X

    PAD_TOP_PT, PAD_BOTTOM_PT = 10, 10
    LEADING        = 1.32
    GAP_PT         = 16   # vertical gap between stacked boxes within a stage
    GAP_SECTION_PT = 26   # extra gap between PRISMA stages
    HEADER_PT      = 70
    FOOTER_PT      = 26

    def _wrap(text, fontsize, w_axes, bullet=False):
        box_w_pt = w_axes * FIG_W * 72
        avg_char_pt = fontsize * 0.52
        pad_x_pt = 16
        chars = max(10, int((box_w_pt - 2 * pad_x_pt) / avg_char_pt))
        kwargs = {"width": chars}
        if bullet:
            kwargs["initial_indent"] = "•  "
            kwargs["subsequent_indent"] = "    "
        return textwrap.wrap(text, **kwargs) or [text]

    def _block(text, fontsize, w_axes, bold=False, color=TEXT, bullet=False):
        return [(ln, fontsize, bold, color) for ln in _wrap(text, fontsize, w_axes, bullet)]

    def _height_pt(lines) -> float:
        h = PAD_TOP_PT + PAD_BOTTOM_PT
        for _, fs, *_rest in lines:
            h += fs * LEADING
        return h

    # ── Phase 1: build every text block and measure heights in points ───────
    # (independent of final figure height, so the sizing decision below is exact)
    db_src, db_total = _parse_kv_list(db_names)
    db_lines = _block("Registros identificados de bases de datos y registros", 9.3, MAIN_W)
    db_lines.append((f"n = {db_total if db_total else _n(None)}", 11.5, True, BLUE_BORDER))
    for d in db_src:
        db_lines += _block(d, 8.2, MAIN_W, color=TEXT_MUTED, bullet=True)
    db_h = _height_pt(db_lines)

    other_lines, other_h = None, 0
    if other_sources is not None:
        other_lines = _block("Registros identificados de otros métodos", 9.3, SIDE_W)
        other_lines.append((f"n = {_n(other_sources)}", 11.5, True, BLUE_BORDER))
        other_h = _height_pt(other_lines)
    row1_h = max(db_h, other_h)

    removed_w = FULL_W if other_sources is not None else MAIN_W
    removed_src = []
    if duplicates_removed is not None:
        removed_src.append(f"Registros duplicados eliminados (n = {duplicates_removed})")
    if other_removed is not None:
        removed_src.append(f"Registros eliminados por otras razones (n = {other_removed})")
    removed_lines = _block("Registros eliminados antes del cribado", 9.5, removed_w, bold=True, color=NAVY)
    for r in (removed_src or ["(n = ?)"]):
        removed_lines += _block(r, 8.2, removed_w, color=TEXT_MUTED, bullet=True)
    removed_h = _height_pt(removed_lines)

    def _row_blocks(main_text, main_n, side_text, side_n, side_extra=None):
        m_lines = _block(main_text, 9.3, MAIN_W)
        m_lines.append((f"n = {_n(main_n)}", 11.5, True, BLUE_BORDER))
        s_lines = _block(side_text, 9.3, SIDE_W, color=RED_BORDER)
        s_lines.append((f"n = {_n(side_n)}", 11.5, True, RED_BORDER))
        for r in (side_extra or []):
            s_lines += _block(r, 8.0, SIDE_W, color=TEXT_MUTED, bullet=True)
        return m_lines, s_lines, max(_height_pt(m_lines), _height_pt(s_lines))

    scr_m, scr_s, scr_h = _row_blocks(
        "Registros cribados", screened, "Registros excluidos", excluded_screening)
    snr_m, snr_s, snr_h = _row_blocks(
        "Informes buscados para recuperación", sought, "Informes no recuperados", not_retrieved)
    excl_reasons_list, _ = _parse_kv_list(exclusion_reasons)
    elg_m, elg_s, elg_h = _row_blocks(
        "Informes evaluados para elegibilidad", assessed,
        "Informes excluidos", excluded_eligibility, side_extra=excl_reasons_list)

    inc_lines = _block("Estudios incluidos en la revisión", 10.5, FULL_W, bold=True, color=GREEN_BORDER)
    inc_lines.append((f"n = {_n(included)}", 13.5, True, GREEN_BORDER))
    if reports_included is not None:
        inc_lines += _block("Informes de estudios incluidos (en el meta-análisis)", 9.3, FULL_W, color=NAVY)
        inc_lines.append((f"n = {reports_included}", 11.5, True, NAVY))
    inc_h = _height_pt(inc_lines)

    # ── Total height drives the figure size — guarantees no clipping ────────
    total_pt = (
        HEADER_PT
        + row1_h + GAP_PT + removed_h + GAP_SECTION_PT
        + scr_h + GAP_PT + snr_h + GAP_PT + elg_h + GAP_SECTION_PT
        + inc_h + FOOTER_PT
    )
    FIG_H = total_pt / 72 * 1.015

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    TOTAL_PT = FIG_H * 72

    def _ax(pt: float) -> float:
        return pt / TOTAL_PT

    def _draw(x, top_y, w, lines, fill, border, lw=1.3, radius=0.011):
        h = _ax(_height_pt(lines))
        bottom_y = top_y - h
        rect = mpatches.FancyBboxPatch(
            (x, bottom_y), w, h,
            boxstyle=f"round,pad=0.004,rounding_size={radius}",
            facecolor=fill, edgecolor=border, linewidth=lw, zorder=2,
        )
        ax.add_patch(rect)
        cursor = top_y - _ax(PAD_TOP_PT)
        for text, fs, bold, color in lines:
            lh = _ax(fs * LEADING)
            cursor -= lh / 2
            ax.text(x + w / 2, cursor, text, ha="center", va="center",
                     fontsize=fs, fontweight="bold" if bold else "normal",
                     color=color, zorder=3)
            cursor -= lh / 2
        return top_y, bottom_y

    def _varrow(x, y1, y2, color=BLUE_BORDER, lw=1.6):
        ax.annotate("", xy=(x, y2), xytext=(x, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=15),
                    zorder=4)

    def _harrow(x1, y, x2, color=BLUE_BORDER, lw=1.6):
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=15),
                    zorder=4)

    main_cx = MAIN_X + MAIN_W / 2

    # ── Header ────────────────────────────────────────────────────────────
    ax.text(0.5, 1 - _ax(20), "Diagrama de Flujo PRISMA 2020", ha="center", va="center",
            fontsize=17, fontweight="bold", color=NAVY, zorder=5)
    ax.text(0.5, 1 - _ax(38),
            "Identificación de estudios mediante bases de datos y registros",
            ha="center", va="center", fontsize=9, color=TEXT_MUTED, style="italic", zorder=5)
    rule_y = 1 - _ax(50)
    ax.plot([MAIN_X, SIDE_X + SIDE_W], [rule_y, rule_y], color=BLUE_BORDER, lw=1.6, zorder=5)
    cursor_y = rule_y - _ax(GAP_PT)

    # ── Identification ────────────────────────────────────────────────────
    db_top, db_bottom = _draw(MAIN_X, cursor_y, MAIN_W, db_lines, BLUE_FILL, BLUE_BORDER)
    other_top = other_bottom = None
    if other_lines is not None:
        other_top, other_bottom = _draw(SIDE_X, cursor_y, SIDE_W, other_lines, BLUE_FILL, BLUE_BORDER)
    row1_bottom = min(db_bottom, other_bottom) if other_bottom is not None else db_bottom
    cursor_y = row1_bottom - _ax(GAP_PT)

    removed_top, removed_bottom = _draw(MAIN_X, cursor_y, removed_w, removed_lines, AMBER_FILL, AMBER_BORDER)
    _varrow(main_cx, db_bottom, removed_top)
    if other_top is not None:
        _varrow(SIDE_X + SIDE_W / 2, other_bottom, removed_top)
    id_top, id_bottom = db_top, removed_bottom
    cursor_y = removed_bottom - _ax(GAP_SECTION_PT)

    # ── Screening ─────────────────────────────────────────────────────────
    scr_m_top, scr_m_bottom = _draw(MAIN_X, cursor_y, MAIN_W, scr_m, BLUE_FILL, BLUE_BORDER)
    _, scr_s_bottom = _draw(SIDE_X, cursor_y, SIDE_W, scr_s, RED_FILL, RED_BORDER)
    _varrow(main_cx, removed_bottom, scr_m_top)
    _harrow(MAIN_X + MAIN_W, (scr_m_top + scr_m_bottom) / 2, SIDE_X)
    cursor_y = min(scr_m_bottom, scr_s_bottom) - _ax(GAP_PT)

    snr_m_top, snr_m_bottom = _draw(MAIN_X, cursor_y, MAIN_W, snr_m, BLUE_FILL, BLUE_BORDER)
    _, snr_s_bottom = _draw(SIDE_X, cursor_y, SIDE_W, snr_s, RED_FILL, RED_BORDER)
    _varrow(main_cx, scr_m_bottom, snr_m_top)
    _harrow(MAIN_X + MAIN_W, (snr_m_top + snr_m_bottom) / 2, SIDE_X)
    cursor_y = min(snr_m_bottom, snr_s_bottom) - _ax(GAP_PT)

    elg_m_top, elg_m_bottom = _draw(MAIN_X, cursor_y, MAIN_W, elg_m, BLUE_FILL, BLUE_BORDER)
    _, elg_s_bottom = _draw(SIDE_X, cursor_y, SIDE_W, elg_s, RED_FILL, RED_BORDER)
    _varrow(main_cx, snr_m_bottom, elg_m_top)
    _harrow(MAIN_X + MAIN_W, (elg_m_top + elg_m_bottom) / 2, SIDE_X)
    screening_top, screening_bottom = scr_m_top, min(elg_m_bottom, elg_s_bottom)
    cursor_y = screening_bottom - _ax(GAP_SECTION_PT)

    # ── Included ──────────────────────────────────────────────────────────
    inc_top, inc_bottom = _draw(MAIN_X, cursor_y, FULL_W, inc_lines, GREEN_FILL, GREEN_BORDER, lw=1.8)
    _varrow(main_cx, elg_m_bottom, inc_top, color=GREEN_BORDER)

    # ── Section tabs (sized to each stage's actual extent) ───────────────
    TAB_FS = 9.5

    def _section_tab(y_top, y_bottom, label):
        cy = (y_top + y_bottom) / 2
        tab_w = 0.052
        # The rotated label's own footprint (rough avg-char-width heuristic,
        # generous so the leading/trailing letter is never clipped by the
        # tight bbox when savefig(bbox_inches="tight") crops the PNG) sets a
        # hard floor — a short section must never be drawn shorter than the
        # text it has to hold, regardless of how little content it contains.
        text_min_pt = len(label) * TAB_FS * 0.62 + 16
        tab_h = max(y_top - y_bottom, _ax(text_min_pt))
        rect = mpatches.FancyBboxPatch(
            (0.018, cy - tab_h / 2), tab_w, tab_h,
            boxstyle="round,pad=0.003,rounding_size=0.01",
            facecolor=NAVY, edgecolor="none", zorder=2,
        )
        ax.add_patch(rect)
        ax.text(0.018 + tab_w / 2, cy, label, ha="center", va="center",
                fontsize=TAB_FS, fontweight="bold", color="white", rotation=90, zorder=3)

    _section_tab(id_top, id_bottom, "Identificación")
    _section_tab(screening_top, screening_bottom, "Cribado")
    _section_tab(inc_top, inc_bottom, "Incluidos")

    # ── Cita al pie (obligatoria al reportar un diagrama PRISMA 2020) ────
    ax.text(0.5, max(inc_bottom - _ax(16), 0.005),
            "Page MJ, et al. The PRISMA 2020 statement. BMJ 2021;372:n71. "
            "doi:10.1136/bmj.n71  •  prisma-statement.org",
            ha="center", va="top", fontsize=7, color=TEXT_MUTED, style="italic", zorder=5)

    return _b64(fig, dpi=160)


def generate_rob_traffic_light(studies_rob: list) -> str:
    """Generate a Risk of Bias traffic-light summary figure."""
    domains = [
        "Random sequence", "Allocation concealment", "Blinding (participants)",
        "Blinding (outcomes)", "Incomplete data", "Selective reporting", "Other"
    ]
    keys = [
        "rob_random_sequence", "rob_allocation_concealment",
        "rob_blinding_participants", "rob_blinding_outcome",
        "rob_incomplete_data", "rob_selective_reporting", "rob_other",
    ]
    color_map = {
        "low": "#2ecc71", "some_concerns": "#f39c12",
        "high": "#e74c3c", None: "#bdc3c7", "": "#bdc3c7",
    }
    symbol_map = {"low": "+", "some_concerns": "?", "high": "−", None: "?", "": "?"}

    n_studies = len(studies_rob)
    n_domains = len(domains)
    fig, ax = plt.subplots(figsize=(n_domains * 1.4 + 2, n_studies * 0.55 + 2))
    ax.axis("off")

    # Headers
    for j, domain in enumerate(domains):
        ax.text(j + 1, n_studies + 0.5, domain, ha="center", va="bottom",
                fontsize=7.5, fontweight="bold", rotation=45)

    for i, study in enumerate(studies_rob):
        label = f"{study.get('authors', '?')} {study.get('year', '')}"
        ax.text(0, n_studies - i, label, ha="right", va="center", fontsize=8)
        for j, key in enumerate(keys):
            val = study.get(key, None)
            color = color_map.get(val, "#bdc3c7")
            symbol = symbol_map.get(val, "?")
            circle = plt.Circle((j + 1, n_studies - i), 0.3,
                                 color=color, zorder=2)
            ax.add_patch(circle)
            ax.text(j + 1, n_studies - i, symbol, ha="center", va="center",
                    fontsize=9, fontweight="bold", color="white", zorder=3)

    ax.set_xlim(-0.5, n_domains + 0.5)
    ax.set_ylim(0, n_studies + 1.5)

    # Legend
    legend_elements = [
        mpatches.Patch(color="#2ecc71", label="Low risk"),
        mpatches.Patch(color="#f39c12", label="Some concerns"),
        mpatches.Patch(color="#e74c3c", label="High risk"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)
    ax.set_title("Risk of Bias Assessment (Cochrane RoB 2)", fontsize=11,
                 fontweight="bold", pad=10)
    plt.tight_layout()
    return _b64(fig)


def generate_grade_table(result_dict: dict, studies: list, outcome: str = "") -> str:
    """Generate a GRADE evidence profile as a vertical two-column card layout."""
    plt.close("all")
    gc.collect()

    het = result_dict.get("heterogeneity", {}) or {}
    pooled = result_dict.get("pooled", {}) or {}
    k = result_dict.get("k", len(studies))
    total_n = result_dict.get("total_n", 0)
    i2 = het.get("I2", 0) or 0
    effect = pooled.get("effect")
    ci_lo = pooled.get("ci_lower")
    ci_hi = pooled.get("ci_upper")
    em = result_dict.get("effect_measure", "ES")

    # Auto-rate GRADE domains
    high_risk = sum(
        1 for s in studies
        for k_ in ["rob_random_sequence", "rob_allocation_concealment",
                   "rob_blinding_participants", "rob_blinding_outcome",
                   "rob_incomplete_data", "rob_selective_reporting"]
        if s.get(k_) == "high"
    )
    if high_risk == 0:
        rob_rating, rob_color = "Not serious", "#27ae60"
    elif high_risk <= 2:
        rob_rating, rob_color = "Serious", "#f39c12"
    else:
        rob_rating, rob_color = "Very serious", "#e74c3c"

    if i2 < 25:
        incon_rating, incon_color = "Not serious", "#27ae60"
    elif i2 < 50:
        incon_rating, incon_color = "Serious", "#f39c12"
    else:
        incon_rating, incon_color = "Very serious", "#e74c3c"

    indir_rating, indir_color = "Not serious", "#27ae60"

    if effect and ci_lo is not None and ci_hi is not None and effect != 0:
        rel_width = abs((ci_hi - ci_lo) / effect)
        if rel_width < 0.5 and total_n >= 300:
            impr_rating, impr_color = "Not serious", "#27ae60"
        elif rel_width < 1.0 or total_n >= 100:
            impr_rating, impr_color = "Serious", "#f39c12"
        else:
            impr_rating, impr_color = "Very serious", "#e74c3c"
    else:
        impr_rating, impr_color = "Serious", "#f39c12"

    pub_rating, pub_color = ("Undetected", "#27ae60") if k >= 5 else ("Undetected*", "#f39c12")

    downgrades = sum([
        1 if rob_rating == "Serious" else (2 if rob_rating == "Very serious" else 0),
        1 if incon_rating == "Serious" else (2 if incon_rating == "Very serious" else 0),
        0,  # indirectness = not serious
        1 if impr_rating == "Serious" else (2 if impr_rating == "Very serious" else 0),
    ])
    quality_labels = ["⊕⊕⊕⊕  HIGH", "⊕⊕⊕◯  MODERATE", "⊕⊕◯◯  LOW", "⊕◯◯◯  VERY LOW"]
    quality_colors = ["#27ae60", "#2980b9", "#f39c12", "#e74c3c"]
    q_idx = min(downgrades, 3)
    quality_label = quality_labels[q_idx]
    quality_color = quality_colors[q_idx]

    effect_str = "—"
    if effect is not None and ci_lo is not None and ci_hi is not None:
        effect_str = f"{em} {effect:.2f}  (95% CI  {ci_lo:.2f} – {ci_hi:.2f})"

    # ── Draw figure ───────────────────────────────────────────────────────────
    FIG_W, FIG_H = 12.0, 8.2
    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.axis("off")

    # Title
    ax.text(FIG_W / 2, FIG_H - 0.25,
            "GRADE Evidence Profile — Certainty of Evidence",
            ha="center", va="top", fontsize=13, fontweight="bold", color="#1a3a5c")
    ax.text(FIG_W / 2, FIG_H - 0.72,
            outcome or "Primary outcome",
            ha="center", va="top", fontsize=11, style="italic", color="#444444")

    # Layout constants
    X_L = 0.3          # left edge of label column
    W_L = 4.2          # label column width
    X_V = X_L + W_L + 0.2   # left edge of value column
    W_V = FIG_W - X_V - 0.3  # value column width
    ROW_H = 0.68        # height per row
    Y_START = FIG_H - 1.35  # y of TOP of first row

    def _row(y_top, label, value, val_bg, label_bg="#1a3a5c", label_fg="white", val_fg="#111111"):
        y = y_top - ROW_H
        ax.add_patch(mpatches.FancyBboxPatch(
            (X_L, y + 0.04), W_L, ROW_H - 0.08,
            boxstyle="round,pad=0.04", facecolor=label_bg, edgecolor="none", zorder=2))
        ax.text(X_L + W_L / 2, y + ROW_H / 2, label,
                ha="center", va="center", fontsize=9.5, fontweight="bold",
                color=label_fg, multialignment="center", zorder=3)

        ax.add_patch(mpatches.FancyBboxPatch(
            (X_V, y + 0.04), W_V, ROW_H - 0.08,
            boxstyle="round,pad=0.04", facecolor=val_bg, edgecolor="#cccccc",
            linewidth=0.8, zorder=2))
        ax.text(X_V + W_V / 2, y + ROW_H / 2, value,
                ha="center", va="center", fontsize=10, color=val_fg,
                multialignment="center", zorder=3)
        return y  # returns bottom y of this row

    rows = [
        ("Studies (k)  /  Participants (N)",
         f"{k} studies     N = {total_n}",
         "#eef2fb"),
        ("Effect estimate",
         effect_str,
         "#eef2fb"),
        ("Risk of bias",
         rob_rating,
         rob_color + "33"),
        (f"Inconsistency  (I² = {i2:.0f}%)",
         incon_rating,
         incon_color + "33"),
        ("Indirectness",
         indir_rating,
         indir_color + "33"),
        ("Imprecision",
         impr_rating,
         impr_color + "33"),
        ("Publication bias",
         pub_rating,
         pub_color + "33"),
    ]

    y_cursor = Y_START
    for label, value, val_bg in rows:
        y_cursor = _row(y_cursor, label, value, val_bg)

    # GRADE certainty summary strip
    grade_y = y_cursor - 0.18
    ax.add_patch(mpatches.FancyBboxPatch(
        (X_L, grade_y), W_L + 0.2 + W_V, 0.78,
        boxstyle="round,pad=0.06", facecolor=quality_color,
        edgecolor="#333333", linewidth=1.5, zorder=2))
    ax.text(FIG_W / 2, grade_y + 0.39,
            f"GRADE Certainty of Evidence:   {quality_label}",
            ha="center", va="center", fontsize=13, fontweight="bold",
            color="white", zorder=3)

    # Footer note
    ax.text(0.25, 0.18,
            "* <5 studies — publication bias assessment limited  |  "
            "Indirectness default: Not serious (manual upgrade/downgrade as needed)  |  "
            "GRADE: Grading of Recommendations Assessment, Development and Evaluation",
            fontsize=6.8, color="#888888", ha="left", va="bottom")

    return _b64(fig)
