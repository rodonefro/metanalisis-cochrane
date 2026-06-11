"""
AI text generation service using Anthropic Claude.
Generates Cochrane-format review sections based on review context and study data.
"""
import anthropic

from ..config import settings

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _study_summary(studies: list[dict]) -> str:
    if not studies:
        return "No studies provided."
    lines = []
    for s in studies[:20]:
        label = s.get("study_label") or f"{s.get('authors','?')} {s.get('year','')}"
        n = (s.get("total_intervention") or 0) + (s.get("total_control") or 0)
        design = s.get("study_design", "RCT")
        lines.append(f"- {label} (n={n}, {design})")
    if len(studies) > 20:
        lines.append(f"  ... and {len(studies) - 20} more studies")
    return "\n".join(lines)


def _meta_summary(meta_results: dict | None) -> str:
    if not meta_results:
        return ""
    p = meta_results.get("pooled", {})
    h = meta_results.get("heterogeneity", {})
    em = meta_results.get("effect_measure", "")
    model = meta_results.get("model", "random")
    k = meta_results.get("k", 0)
    n = meta_results.get("total_n", 0)
    effect = p.get("effect", "N/A")
    lo = p.get("ci_lower", "N/A")
    hi = p.get("ci_upper", "N/A")
    i2 = h.get("I2", "N/A")
    q_p = h.get("Q_pvalue", "N/A")
    tau2 = h.get("tau2", "N/A")
    return (
        f"Meta-analysis results ({model}-effects model, k={k}, N={n}):\n"
        f"  Pooled {em}: {effect:.2f} [95% CI: {lo:.2f}, {hi:.2f}]\n"
        f"  Heterogeneity: I²={i2:.0f}%, Q p-value={q_p:.3f}, τ²={tau2:.3f}"
    )


def _base_context(review: dict, studies: list[dict]) -> str:
    population = review.get("population", "")
    intervention = review.get("intervention", "")
    comparison = review.get("comparison", "")
    outcomes = review.get("outcomes", "")
    effect_measure = review.get("effect_measure", "OR")
    model_type = review.get("model_type", "random")
    return (
        f"REVIEW TITLE: {review.get('title', 'Systematic Review')}\n\n"
        f"PICO:\n"
        f"  Population: {population}\n"
        f"  Intervention: {intervention}\n"
        f"  Comparison: {comparison}\n"
        f"  Outcomes: {outcomes}\n\n"
        f"EFFECT MEASURE: {effect_measure} | MODEL: {model_type}\n\n"
        f"INCLUDED STUDIES ({len(studies)} total):\n{_study_summary(studies)}"
    )


def _call_claude(system: str, user: str) -> str:
    client = _get_client()
    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()
    parts = [b.text for b in message.content if b.type == "text"]
    return "\n".join(parts).strip()


SYSTEM_COCHRANE = (
    "You are an expert systematic reviewer trained in Cochrane methodology. "
    "Write academic, evidence-based content for a Cochrane-style systematic review. "
    "Use precise scientific language, cite study findings appropriately, and follow "
    "PRISMA and Cochrane standards. Write in the third person, present tense where "
    "appropriate for methods, past tense for results. Output only the requested section "
    "text — no headings, no preamble, no markdown formatting."
)


def generate_abstract(review: dict, studies: list[dict], meta_results: dict | None = None) -> str:
    ctx = _base_context(review, studies)
    meta = _meta_summary(meta_results)
    user = (
        f"{ctx}\n\n{meta}\n\n"
        "Write a structured abstract for this Cochrane systematic review with the following "
        "subsections: Background, Objectives, Search methods, Selection criteria, "
        "Data collection and analysis, Main results, Authors' conclusions. "
        "Be concise (300-400 words total)."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_background(review: dict, studies: list[dict]) -> str:
    ctx = _base_context(review, studies)
    user = (
        f"{ctx}\n\n"
        "Write the Background section for this Cochrane systematic review. "
        "Include: (1) Description of the condition/disease and its epidemiology, "
        "(2) Description of the intervention and how it works, "
        "(3) Why the intervention may work (mechanism of action), "
        "(4) Why it is important to do this review. "
        "Write approximately 600-800 words."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_objectives(review: dict) -> str:
    pico = (
        f"Population: {review.get('population', '')}\n"
        f"Intervention: {review.get('intervention', '')}\n"
        f"Comparison: {review.get('comparison', '')}\n"
        f"Outcomes: {review.get('outcomes', '')}"
    )
    user = (
        f"REVIEW TITLE: {review.get('title', 'Systematic Review')}\n\n"
        f"PICO:\n{pico}\n\n"
        "Write a concise Objectives section for this Cochrane systematic review. "
        "Start with 'To assess the effects of [intervention] on [outcomes] in [population].' "
        "Then state any secondary objectives. Write 80-120 words."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_methods(review: dict, studies: list[dict]) -> str:
    ctx = _base_context(review, studies)
    effect_measure = review.get("effect_measure", "OR")
    model_type = review.get("model_type", "random")
    user = (
        f"{ctx}\n\n"
        "Write the Methods section for this Cochrane systematic review. Include:\n"
        "1. Criteria for considering studies for this review:\n"
        "   a) Types of studies\n"
        "   b) Types of participants\n"
        "   c) Types of interventions\n"
        "   d) Types of outcome measures (primary and secondary outcomes)\n"
        "2. Search methods for identification of studies (databases: PubMed, Embase, "
        "Cochrane CENTRAL, Scopus, Web of Science; grey literature)\n"
        "3. Data collection and analysis:\n"
        "   - Selection of studies\n"
        "   - Data extraction and management\n"
        "   - Assessment of risk of bias (Cochrane RoB 2 tool)\n"
        f"   - Measures of treatment effect ({effect_measure})\n"
        f"   - Unit of analysis issues\n"
        "   - Dealing with missing data\n"
        f"   - Assessment of heterogeneity (Cochran's Q, I², {model_type}-effects model)\n"
        "   - Assessment of reporting biases (funnel plot, Egger's test)\n"
        "   - Data synthesis\n"
        "Write approximately 800-1000 words."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_results(review: dict, studies: list[dict], meta_results: dict | None = None) -> str:
    ctx = _base_context(review, studies)
    meta = _meta_summary(meta_results)
    study_count = len(studies)
    user = (
        f"{ctx}\n\n{meta}\n\n"
        "Write the Results section for this Cochrane systematic review. Include:\n"
        "1. Description of studies:\n"
        f"   - Study flow (number screened, eligible, included: {study_count} studies)\n"
        "   - Characteristics of included studies (design, participants, interventions)\n"
        "   - Excluded studies (briefly)\n"
        "   - Risk of bias assessment summary\n"
        "2. Effects of interventions:\n"
        "   - Primary outcome(s) with meta-analysis results\n"
        "   - Secondary outcome(s)\n"
        "   - Heterogeneity findings and explanation\n"
        "   - Subgroup analyses (if applicable)\n"
        "   - Reporting biases\n"
        "Reference specific study findings and the pooled estimates. "
        "Write approximately 700-900 words."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_discussion(review: dict, studies: list[dict], meta_results: dict | None = None) -> str:
    ctx = _base_context(review, studies)
    meta = _meta_summary(meta_results)
    user = (
        f"{ctx}\n\n{meta}\n\n"
        "Write the Discussion section for this Cochrane systematic review. Include:\n"
        "1. Summary of main results\n"
        "2. Overall completeness and applicability of evidence\n"
        "3. Quality of the evidence (risk of bias, heterogeneity)\n"
        "4. Potential biases in the review process\n"
        "5. Agreements and disagreements with other studies or reviews\n"
        "6. Authors' conclusions:\n"
        "   a) Implications for practice\n"
        "   b) Implications for research\n"
        "Write approximately 600-800 words."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


_CITATION_FORMATS = {
    "vancouver": (
        "Vancouver (numbered superscript, used in Cochrane/PubMed): "
        "Authors. Title. Journal. Year;Volume(Issue):Pages. DOI."
    ),
    "apa": (
        "APA 7th edition: Authors (Year). Title. Journal, Volume(Issue), Pages. DOI."
    ),
    "nlm": (
        "NLM/MEDLINE (National Library of Medicine): "
        "Authors. Title. Abbreviated Journal. Year Mon DD;Volume(Issue):Pages. DOI."
    ),
    "harvard": (
        "Harvard: Authors (Year) 'Title', Journal, Volume(Issue), pp. Pages."
    ),
    "cochrane": (
        "Cochrane standard: Authors Year. Title [study design]. "
        "In: Cochrane Database of Systematic Reviews."
    ),
}


def generate_references(
    review: dict,
    studies: list[dict],
    citation_style: str = "vancouver",
) -> str:
    fmt = _CITATION_FORMATS.get(citation_style, _CITATION_FORMATS["vancouver"])
    study_lines = []
    for s in studies:
        label = s.get("study_label") or f"{s.get('authors', '?')} {s.get('year', '')}"
        authors = s.get("authors", "")
        year = s.get("year", "")
        title = s.get("title", "")
        journal = s.get("journal", "")
        doi = s.get("doi", "")
        n = (s.get("total_intervention") or 0) + (s.get("total_control") or 0)
        study_lines.append(
            f"- {label}: authors={authors!r}, year={year}, title={title!r}, "
            f"journal={journal!r}, doi={doi!r}, n={n}"
        )
    studies_block = "\n".join(study_lines) if study_lines else "No study metadata available."
    user = (
        f"REVIEW TITLE: {review.get('title', '')}\n\n"
        f"INCLUDED STUDIES:\n{studies_block}\n\n"
        f"FORMAT REQUIRED: {fmt}\n\n"
        "Generate a complete, properly formatted reference list for all included studies "
        "using the format specified above. Number each reference sequentially. "
        "If specific metadata (volume, pages, DOI) is missing, use the available information "
        "and mark missing fields with '[datos no disponibles]'. "
        "Output only the numbered reference list, no headings or preamble."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_plot_interpretation(
    review: dict,
    meta_results: dict,
) -> str:
    p = meta_results.get("pooled", {})
    h = meta_results.get("heterogeneity", {})
    em = meta_results.get("effect_measure", "OR")
    model = meta_results.get("model", "random")
    k = meta_results.get("k", 0)
    n = meta_results.get("total_n", 0)
    pi = meta_results.get("prediction_interval", {})
    studies = meta_results.get("studies", [])

    study_lines = "\n".join(
        f"  {s['label']}: {em}={s.get('effect', 'N/A'):.2f} "
        f"[{s.get('ci_lower', 'N/A'):.2f}, {s.get('ci_upper', 'N/A'):.2f}], "
        f"weight={s.get('weight_re' if model == 'random' else 'weight_fe', 'N/A'):.1f}%"
        for s in studies
    )

    user = (
        f"REVIEW: {review.get('title', '')}\n"
        f"Population: {review.get('population', '')} | "
        f"Intervention: {review.get('intervention', '')}\n\n"
        f"META-ANALYSIS RESULTS ({model}-effects model, k={k} studies, N={n} participants):\n"
        f"Pooled {em}: {p.get('effect', 'N/A'):.2f} "
        f"[95% CI: {p.get('ci_lower', 'N/A'):.2f}, {p.get('ci_upper', 'N/A'):.2f}]\n"
        f"Heterogeneity: Q={h.get('Q', 'N/A'):.1f} (df={h.get('Q_df')}, "
        f"p={h.get('Q_pvalue', 'N/A'):.3f}), I²={h.get('I2', 'N/A'):.0f}%, "
        f"τ²={h.get('tau2', 'N/A'):.4f}\n"
        + (f"Prediction interval: [{pi.get('lower', 'N/A'):.2f}, {pi.get('upper', 'N/A'):.2f}]\n"
           if pi.get("lower") is not None else "")
        + f"\nIndividual studies:\n{study_lines}\n\n"
        "Write a detailed Cochrane-style interpretation of:\n"
        "1. The forest plot: describe the pooled estimate, direction and magnitude of effect, "
        "confidence interval, which studies drive the result, any notable outliers.\n"
        "2. The funnel plot: interpret symmetry/asymmetry, what this implies about "
        "publication bias (reference Egger's test if available).\n"
        "3. Heterogeneity: explain the I² value clinically, discuss possible sources, "
        "interpret the prediction interval if available.\n"
        "4. Overall conclusion from the statistical analysis.\n"
        "Write approximately 400-500 words in formal academic style."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_section(
    section: str,
    review: dict,
    studies: list[dict],
    meta_results: dict | None = None,
    citation_style: str = "vancouver",
) -> str:
    """Dispatch to the appropriate generator function by section name."""
    generators = {
        "abstract": generate_abstract,
        "background": generate_background,
        "objectives": generate_objectives,
        "methods": generate_methods,
        "results": generate_results,
        "discussion": generate_discussion,
        "references": None,
        "plot_interpretation": None,
    }
    section_key = section.lower().strip()
    if section_key not in generators:
        raise ValueError(
            f"Unknown section '{section}'. Valid sections: {list(generators)}"
        )
    if section_key == "references":
        return generate_references(review, studies, citation_style)
    if section_key == "plot_interpretation":
        if not meta_results:
            raise ValueError("Se requieren resultados del metaanálisis para interpretar los gráficos.")
        return generate_plot_interpretation(review, meta_results)
    fn = generators[section_key]
    if section_key == "objectives":
        return fn(review)
    return fn(review, studies, meta_results) if section_key in ("abstract", "results", "discussion") else fn(review, studies)
