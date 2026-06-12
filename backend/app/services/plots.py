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

from typing import Optional as _Opt

from .statistics import MetaResult, back_transform


def _b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
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
    bt = lambda v: back_transform(v, result.effect_measure)
    is_log = result.effect_measure in ("OR", "RR")
    null = null_value if null_value is not None else (1.0 if is_log else 0.0)

    studies = result.studies
    k = len(studies)
    fig_height = max(5, min(k * 0.45 + 3, 24))
    fig, ax = plt.subplots(figsize=(10, fig_height))

    y_positions = list(range(k, 0, -1))
    colors = {"low": "#2ecc71", "some_concerns": "#f39c12", "high": "#e74c3c"}

    # Column headers
    ax.text(0, k + 1.5, "Study", fontsize=9, fontweight="bold", ha="left", va="center")
    ax.text(0.62, k + 1.5, f"{result.effect_measure} (95% CI)", fontsize=9,
            fontweight="bold", ha="center", va="center", transform=ax.transAxes)
    ax.text(0.90, k + 1.5, "Weight (%)", fontsize=9, fontweight="bold",
            ha="center", va="center", transform=ax.transAxes)

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
    ax.axvline(x=null, color="black", linewidth=0.8, linestyle="--", alpha=0.6)

    # Study rows
    for i, (s, y) in enumerate(zip(studies, y_positions)):
        effect = bt(s.effect)
        lo = bt(s.ci_lower)
        hi = bt(s.ci_upper)
        weight = s.weight_re if result.model == "random" else s.weight_fe
        box_size = max(0.04, weight / 100 * 0.6)

        # CI line
        ax.plot([lo, hi], [y, y], color="#2c3e50", linewidth=1.2, zorder=2)
        # Square
        rect = mpatches.FancyBboxPatch(
            (effect - box_size / 2, y - box_size / 4),
            box_size, box_size / 2,
            boxstyle="square,pad=0",
            facecolor="#2980b9", edgecolor="#1a252f", linewidth=0.5, zorder=3,
        )
        ax.add_patch(rect)

        # Labels
        ax.text(-0.02, y, s.study_label, fontsize=8, ha="right", va="center",
                transform=ax.get_yaxis_transform())
        ci_text = f"{effect:.2f} [{lo:.2f}, {hi:.2f}]"
        ax.text(1.01, y, ci_text, fontsize=7.5, ha="left", va="center",
                transform=ax.get_yaxis_transform())
        ax.text(1.25, y, f"{weight:.1f}", fontsize=7.5, ha="right", va="center",
                transform=ax.get_yaxis_transform())

    # Pooled diamond
    p_eff = bt(result.pooled_effect)
    p_lo = bt(result.pooled_lower)
    p_hi = bt(result.pooled_upper)
    diamond_y = 0
    diamond = mpatches.FancyArrow(
        (p_lo + p_hi) / 2, diamond_y, 0, 0,
        width=0.35, head_width=0, head_length=0,
        facecolor="#c0392b", edgecolor="#922b21", linewidth=0.8,
    )
    # Use Polygon for proper diamond shape
    diamond_pts = np.array([
        [p_lo, diamond_y],
        [p_eff, diamond_y + 0.28],
        [p_hi, diamond_y],
        [p_eff, diamond_y - 0.28],
    ])
    diamond_patch = plt.Polygon(diamond_pts, closed=True,
                                facecolor="#c0392b", edgecolor="#922b21", linewidth=0.8, zorder=4)
    ax.add_patch(diamond_patch)

    # Separator line
    ax.axhline(y=0.6, color="black", linewidth=0.8)

    # Pooled label
    ax.text(-0.02, diamond_y, f"Total ({result.model.capitalize()} effects, k={result.k})",
            fontsize=8.5, fontweight="bold", ha="right", va="center",
            transform=ax.get_yaxis_transform())
    ci_pooled = f"{p_eff:.2f} [{p_lo:.2f}, {p_hi:.2f}]"
    ax.text(1.01, diamond_y, ci_pooled, fontsize=8, fontweight="bold",
            ha="left", va="center", transform=ax.get_yaxis_transform())

    # Heterogeneity box
    het = (f"Heterogeneity: Q={result.Q:.1f} (df={result.Q_df}, "
           f"p={result.Q_pvalue:.3f}), I²={result.I2:.0f}%, τ²={result.tau2:.3f}")
    ax.text(0.5, -1.0, het, fontsize=7.5, ha="center", va="center",
            transform=ax.get_yaxis_transform(),
            bbox=dict(facecolor="#ecf0f1", edgecolor="gray", boxstyle="round,pad=0.3"))

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(-1.8, k + 2)
    ax.set_yticks([])
    ax.set_xlabel(f"Favours control  ←  {result.effect_measure}  →  Favours intervention",
                  fontsize=8)
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
    ax.spines["left"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    plt.tight_layout()
    return _b64(fig)


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
    """Generate PRISMA 2020 flowchart and return base64 PNG."""

    def _n(v) -> str:
        return str(v) if v is not None else "?"

    def _box(ax, x, y, w, h, text, color="#DDEEFF", fontsize=8.5, bold=False):
        rect = mpatches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.015",
            facecolor=color, edgecolor="#4a6fa5", linewidth=1.2, zorder=2,
        )
        ax.add_patch(rect)
        ax.text(
            x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=fontsize,
            fontweight="bold" if bold else "normal",
            wrap=True, zorder=3,
            multialignment="center",
        )

    def _arrow(ax, x1, y1, x2, y2):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="-|>", color="#4a6fa5", lw=1.3),
            zorder=4,
        )

    def _section_label(ax, y, label):
        ax.text(
            0.01, y, label,
            ha="left", va="center", fontsize=9, fontweight="bold",
            color="#2c3e50",
            bbox=dict(facecolor="#2c3e50", edgecolor="none", alpha=0.12,
                      boxstyle="round,pad=0.3"),
        )

    # Parse db_names: "PubMed=45,Scopus=32"
    db_lines = []
    db_total = 0
    if db_names:
        for part in db_names.split(","):
            part = part.strip()
            if "=" in part:
                nm, cnt = part.rsplit("=", 1)
                try:
                    cnt_i = int(cnt.strip())
                    db_total += cnt_i
                    db_lines.append(f"• {nm.strip()} (n = {cnt_i})")
                except ValueError:
                    db_lines.append(f"• {part}")
            elif part:
                db_lines.append(f"• {part}")

    db_text = f"Records identified from databases\n(n = {db_total if db_total else '?'})\n"
    db_text += "\n".join(db_lines) if db_lines else ""

    removed_lines = []
    if duplicates_removed is not None:
        removed_lines.append(f"Duplicate records (n = {duplicates_removed})")
    if other_removed is not None:
        removed_lines.append(f"Other reasons (n = {other_removed})")
    removed_text = "Records removed before screening:\n" + (
        "\n".join(f"• {l}" for l in removed_lines) if removed_lines
        else "• (n = ?)"
    )

    excl_text = (
        f"Reports excluded\n(n = {_n(excluded_eligibility)})"
        + (("\nReasons:\n" + "\n".join(
            f"• {r.strip()}"
            for r in exclusion_reasons.split(",") if r.strip()
        )) if exclusion_reasons else "")
    )

    # Canvas
    fig, ax = plt.subplots(figsize=(13, 16))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # ── Section labels (left strip) ─────────────────────────────────────────
    for label, yc in [
        ("Identification", 0.865),
        ("Screening", 0.595),
        ("Included", 0.105),
    ]:
        rect = mpatches.FancyBboxPatch(
            (0.01, yc - 0.035), 0.065, 0.07,
            boxstyle="round,pad=0.01",
            facecolor="#2c3e50", edgecolor="none", zorder=1,
        )
        ax.add_patch(rect)
        ax.text(
            0.043, yc, label,
            ha="center", va="center", fontsize=8, fontweight="bold",
            color="white", rotation=90, zorder=2,
        )

    # ── Row 1: Databases + Other sources ──────────────────────────────────
    _box(ax, 0.09, 0.84, 0.38, 0.085,
         db_text, color="#ddeeff")
    if other_sources is not None:
        _box(ax, 0.53, 0.84, 0.38, 0.085,
             f"Records identified from other sources\n(registers, grey lit., etc.)\n(n = {_n(other_sources)})",
             color="#ddeeff")

    # Arrow down from databases
    _arrow(ax, 0.28, 0.84, 0.28, 0.80)

    # ── Row 2: Removed before screening ───────────────────────────────────
    _box(ax, 0.09, 0.75, 0.38, 0.075,
         removed_text, color="#fff3cd")

    # Arrow down
    _arrow(ax, 0.28, 0.75, 0.28, 0.705)

    # ── Row 3: Screened ───────────────────────────────────────────────────
    _box(ax, 0.09, 0.655, 0.34, 0.065,
         f"Records screened\n(n = {_n(screened)})", color="#ddeeff")
    _arrow(ax, 0.43, 0.6875, 0.53, 0.6875)
    _box(ax, 0.53, 0.655, 0.38, 0.065,
         f"Records excluded\n(n = {_n(excluded_screening)})", color="#fde8e8")

    # Arrow down
    _arrow(ax, 0.26, 0.655, 0.26, 0.61)

    # ── Row 4: Reports sought ─────────────────────────────────────────────
    _box(ax, 0.09, 0.555, 0.34, 0.065,
         f"Reports sought for retrieval\n(n = {_n(sought)})", color="#ddeeff")
    _arrow(ax, 0.43, 0.5875, 0.53, 0.5875)
    _box(ax, 0.53, 0.555, 0.38, 0.065,
         f"Reports not retrieved\n(n = {_n(not_retrieved)})", color="#fde8e8")

    # Arrow down
    _arrow(ax, 0.26, 0.555, 0.26, 0.51)

    # ── Row 5: Eligibility ────────────────────────────────────────────────
    _box(ax, 0.09, 0.44, 0.34, 0.08,
         f"Reports assessed\nfor eligibility\n(n = {_n(assessed)})", color="#ddeeff")
    _arrow(ax, 0.43, 0.48, 0.53, 0.48)
    _box(ax, 0.53, 0.44, 0.38, 0.08,
         excl_text, color="#fde8e8", fontsize=8)

    # Arrow down
    _arrow(ax, 0.26, 0.44, 0.26, 0.22)

    # ── Row 6: Included ───────────────────────────────────────────────────
    inc_text = f"Studies included in review\n(n = {_n(included)})"
    if reports_included is not None:
        inc_text += f"\nReports of included studies\n(n = {reports_included})"
    _box(ax, 0.09, 0.13, 0.38, 0.09,
         inc_text, color="#d4edda", bold=True, fontsize=9.5)

    ax.set_title("PRISMA 2020 Flow Diagram", fontsize=13, fontweight="bold",
                 pad=12, color="#2c3e50")
    plt.tight_layout(pad=1.5)
    return _b64(fig)


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
    """Generate a GRADE evidence profile table as base64 PNG."""
    plt.close("all")
    gc.collect()
    import math as _math

    het = result_dict.get("heterogeneity", {}) or {}
    pooled = result_dict.get("pooled", {}) or {}
    k = result_dict.get("k", len(studies))
    total_n = result_dict.get("total_n", 0)
    i2 = het.get("I2", 0) or 0
    effect = pooled.get("effect")
    ci_lo = pooled.get("ci_lower")
    ci_hi = pooled.get("ci_upper")
    em = result_dict.get("effect_measure", "ES")

    # --- Auto-rate GRADE domains ---
    # Risk of bias: count RoB fields
    high_risk = sum(
        1 for s in studies
        for k_ in ["rob_random_sequence","rob_allocation_concealment",
                   "rob_blinding_participants","rob_blinding_outcome",
                   "rob_incomplete_data","rob_selective_reporting"]
        if s.get(k_) == "high"
    )
    if high_risk == 0:
        rob_rating, rob_color = "Not serious", "#27ae60"
    elif high_risk <= 2:
        rob_rating, rob_color = "Serious", "#f39c12"
    else:
        rob_rating, rob_color = "Very serious", "#e74c3c"

    # Inconsistency (I²)
    if i2 < 25:
        incon_rating, incon_color = "Not serious", "#27ae60"
    elif i2 < 50:
        incon_rating, incon_color = "Serious", "#f39c12"
    else:
        incon_rating, incon_color = "Very serious", "#e74c3c"

    # Indirectness (manual → default)
    indir_rating, indir_color = "Not serious", "#27ae60"

    # Imprecision: CI width relative to effect
    if effect and ci_lo is not None and ci_hi is not None and effect != 0:
        ci_width = ci_hi - ci_lo
        rel_width = abs(ci_width / effect) if effect else 999
        if rel_width < 0.5 and total_n >= 300:
            impr_rating, impr_color = "Not serious", "#27ae60"
        elif rel_width < 1.0 or total_n >= 100:
            impr_rating, impr_color = "Serious", "#f39c12"
        else:
            impr_rating, impr_color = "Very serious", "#e74c3c"
    else:
        impr_rating, impr_color = "Serious", "#f39c12"

    # Publication bias
    if k >= 10:
        pub_rating, pub_color = "Undetected", "#27ae60"
    elif k >= 5:
        pub_rating, pub_color = "Undetected", "#27ae60"
    else:
        pub_rating, pub_color = "Undetected*", "#f39c12"

    # Overall quality
    downgrades = sum([
        1 if rob_rating == "Serious" else (2 if rob_rating == "Very serious" else 0),
        1 if incon_rating == "Serious" else (2 if incon_rating == "Very serious" else 0),
        1 if indir_rating == "Serious" else (2 if indir_rating == "Very serious" else 0),
        1 if impr_rating == "Serious" else (2 if impr_rating == "Very serious" else 0),
    ])
    quality_labels = ["⊕⊕⊕⊕ HIGH", "⊕⊕⊕◯ MODERATE", "⊕⊕◯◯ LOW", "⊕◯◯◯ VERY LOW"]
    quality_colors = ["#27ae60", "#2980b9", "#f39c12", "#e74c3c"]
    q_idx = min(downgrades, 3)
    quality_label = quality_labels[q_idx]
    quality_color = quality_colors[q_idx]

    effect_str = "—"
    if effect is not None and ci_lo is not None and ci_hi is not None:
        effect_str = f"{em} {effect:.2f} (95% CI {ci_lo:.2f}–{ci_hi:.2f})"

    # --- Build figure ---
    fig, ax = plt.subplots(figsize=(14, 4.5))
    ax.axis("off")

    cols = ["Outcome", "Studies (k)", "Participants (N)", "Risk of\nbias",
            "Inconsistency\n(I²)", "Indirectness", "Imprecision",
            "Publication\nbias", "GRADE\nCertainty", "Effect estimate"]
    row = [
        outcome or "Primary outcome",
        str(k),
        str(total_n),
        rob_rating,
        f"{incon_rating}\n(I²={i2:.0f}%)",
        indir_rating,
        impr_rating,
        pub_rating,
        quality_label,
        effect_str,
    ]
    # cellColours must match cellText shape: (n_data_rows, n_cols) = (1, 10)
    cell_colors = [[
        "#f0f4ff",           # outcome
        "#f0f4ff",           # k
        "#f0f4ff",           # N
        rob_color + "55",
        incon_color + "55",
        indir_color + "55",
        impr_color + "55",
        pub_color + "55",
        quality_color + "44",
        "#f0f4ff",           # effect estimate
    ]]

    tbl = ax.table(
        cellText=[row],
        colLabels=cols,
        cellLoc="center",
        loc="center",
        cellColours=cell_colors,
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 3.5)

    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if r == 0:
            cell.set_facecolor("#1a3a5c")
            cell.set_text_props(color="white", fontweight="bold", fontsize=8.5)

    ax.set_title(
        "GRADE Evidence Profile — Certainty of Evidence",
        fontsize=12, fontweight="bold", pad=14, color="#1a3a5c",
    )
    fig.text(
        0.01, 0.02,
        "* <10 studies — publication bias assessment limited  |  "
        "Indirectness rated manually (default: Not serious)  |  "
        "GRADE: Grading of Recommendations Assessment, Development and Evaluation",
        fontsize=6.5, color="#666666",
    )
    plt.tight_layout(rect=[0, 0.06, 1, 1])
    return _b64(fig)
