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
        n = (s.get("total_intervention") or 0) + (s.get("total_control") or 0) or s.get("sample_size") or "no reportado"
        design = s.get("study_design") or "diseño no especificado"
        lines.append(f"- {label} (n={n}, {design})")
    if len(studies) > 20:
        lines.append(f"  ... and {len(studies) - 20} more studies")
    return "\n".join(lines)


def _excluded_summary(excluded: list[dict]) -> str:
    if not excluded:
        return "No hay estudios excluidos registrados."
    lines = []
    for s in excluded[:40]:
        label = s.get("study_label") or f"{s.get('authors', '?')} {s.get('year', '')}"
        lines.append(f"- {label}: {s.get('exclusion_reason') or 'motivo no registrado'}")
    if len(excluded) > 40:
        lines.append(f"  ... y {len(excluded) - 40} estudios excluidos más")
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
    criteria = eligibility_block(review)
    return (
        f"REVIEW TITLE: {review.get('title', 'Systematic Review')}\n\n"
        f"PICO:\n"
        f"  Population: {population}\n"
        f"  Intervention: {intervention}\n"
        f"  Comparison: {comparison}\n"
        f"  Outcomes: {outcomes}\n\n"
        + (f"AUTHOR-DEFINED ELIGIBILITY CRITERIA (use verbatim, do not invent others):\n{criteria}\n\n" if criteria else "")
        + f"EFFECT MEASURE: {effect_measure} | MODEL: {model_type}\n\n"
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
    "Eres un experto en revisiones sistemáticas con formación en metodología Cochrane. "
    "SIEMPRE escribe TODO el contenido en ESPAÑOL (castellano). "
    "Usa lenguaje científico preciso y académico, cita hallazgos de estudios apropiadamente, "
    "y sigue los estándares PRISMA y Cochrane. Escribe en tercera persona, tiempo presente "
    "para métodos y tiempo pasado para resultados. "
    "Genera únicamente el texto de la sección solicitada — sin encabezados, sin preámbulo, "
    "sin formato markdown. IMPORTANTE: responde exclusivamente en español."
)


def generate_abstract(review: dict, studies: list[dict], meta_results: dict | None = None) -> str:
    ctx = _base_context(review, studies)
    meta = _meta_summary(meta_results)
    user = (
        f"{ctx}\n\n{meta}\n\n"
        "Escribe un resumen estructurado en ESPAÑOL para esta revisión sistemática Cochrane "
        "con las siguientes subsecciones: Antecedentes, Objetivos, Métodos de búsqueda, "
        "Criterios de selección, Obtención y análisis de datos, Resultados principales, "
        "Conclusiones de los autores. Sé conciso (300-400 palabras en total). En Métodos de "
        "búsqueda nombra solo las fuentes del REGISTRO DE BÚSQUEDAS y en Resultados usa los números "
        "exactos del FLUJO PRISMA.\n\n"
        f"REGISTRO DE BÚSQUEDAS:\n{review.get('_search_log') or 'No registrado.'}\n\n"
        f"FLUJO PRISMA 2020 (exacto):\n{review.get('_prisma_flow') or 'No disponible.'}"
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_background(review: dict, studies: list[dict]) -> str:
    ctx = _base_context(review, studies)
    user = (
        f"{ctx}\n\n"
        "Escribe la sección de Antecedentes en ESPAÑOL para esta revisión sistemática Cochrane. "
        "Incluye: (1) Descripción de la condición/enfermedad y su epidemiología, "
        "(2) Descripción de la intervención y cómo funciona, "
        "(3) Por qué la intervención puede funcionar (mecanismo de acción), "
        "(4) Por qué es importante realizar esta revisión. "
        "Escribe aproximadamente 600-800 palabras."
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
        "Escribe una sección de Objetivos concisa en ESPAÑOL para esta revisión sistemática Cochrane. "
        "Comienza con: 'Evaluar los efectos de [intervención] sobre [desenlaces] en [población].' "
        "Luego indica los objetivos secundarios. Escribe 80-120 palabras."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_methods(review: dict, studies: list[dict]) -> str:
    ctx = _base_context(review, studies)
    effect_measure = review.get("effect_measure", "OR")
    model_type = review.get("model_type", "random")
    user = (
        f"{ctx}\n\n"
        "Escribe la sección de Métodos en ESPAÑOL para esta revisión sistemática Cochrane. Incluye:\n"
        "1. Criterios para considerar estudios en esta revisión:\n"
        "   a) Tipos de estudios\n"
        "   b) Tipos de participantes\n"
        "   c) Tipos de intervenciones\n"
        "   d) Tipos de medidas de resultado (desenlaces primarios y secundarios)\n"
        "   e) Criterios de exclusión\n"
        "   (Para el punto 1 usa EXACTAMENTE los criterios de elegibilidad definidos por el autor "
        "arriba; no agregues criterios que no estén definidos.)\n"
        "2. Métodos de búsqueda para identificar estudios. Describe ÚNICAMENTE las fuentes del "
        "REGISTRO DE BÚSQUEDAS de abajo, con su fecha y estrategia tal como están registradas; no "
        "menciones ninguna base de datos, registro o literatura gris que no aparezca en él.\n"
        "3. Obtención y análisis de datos:\n"
        "   - Selección de estudios\n"
        "   - Extracción de datos y gestión\n"
        "   - Evaluación del riesgo de sesgo (herramienta Cochrane RoB 2)\n"
        f"   - Medidas del efecto del tratamiento ({effect_measure})\n"
        "   - Problemas de unidad de análisis\n"
        "   - Manejo de datos faltantes\n"
        f"   - Evaluación de heterogeneidad (Q de Cochran, I², modelo de efectos {model_type})\n"
        "   - Evaluación de sesgos de publicación (gráfico de embudo, prueba de Egger)\n"
        "   - Síntesis de datos\n"
        "Escribe aproximadamente 800-1000 palabras.\n\n"
        f"REGISTRO DE BÚSQUEDAS (fuentes realmente consultadas):\n{review.get('_search_log') or 'No registrado.'}"
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_results(
    review: dict,
    studies: list[dict],
    meta_results: dict | None = None,
    excluded: list[dict] | None = None,
) -> str:
    ctx = _base_context(review, studies)
    meta = _meta_summary(meta_results)
    study_count = len(studies)
    excluded = excluded or []
    user = (
        f"{ctx}\n\n{meta}\n\n"
        f"EXCLUDED STUDIES ({len(excluded)} total, con el motivo registrado en el cribado):\n"
        f"{_excluded_summary(excluded)}\n\n"
        "Escribe la sección de Resultados en ESPAÑOL para esta revisión sistemática Cochrane. Incluye:\n"
        "1. Descripción de los estudios:\n"
        "   - Flujo de estudios: usa EXACTAMENTE los números del FLUJO PRISMA de abajo (son los del "
        "diagrama); no calcules ni redondees otros\n"
        "   - Características de los estudios incluidos (diseño, participantes, intervenciones)\n"
        f"   - Estudios excluidos ({len(excluded)}): resume los motivos de exclusión usando "
        "únicamente los motivos listados arriba\n"
        "   - Resumen de evaluación del riesgo de sesgo\n"
        "2. Efectos de las intervenciones:\n"
        "   - Desenlace(s) primario(s) con resultados del metaanálisis\n"
        "   - Desenlace(s) secundario(s)\n"
        "   - Hallazgos de heterogeneidad y explicación\n"
        "   - Análisis de subgrupos (si aplica)\n"
        "   - Sesgos de publicación\n"
        "Referencia hallazgos específicos de estudios y las estimaciones agrupadas. "
        "Escribe aproximadamente 700-900 palabras.\n\n"
        f"FLUJO PRISMA 2020 (exacto):\n{review.get('_prisma_flow') or f'{study_count} estudios incluidos.'}"
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_discussion(review: dict, studies: list[dict], meta_results: dict | None = None) -> str:
    ctx = _base_context(review, studies)
    meta = _meta_summary(meta_results)
    user = (
        f"{ctx}\n\n{meta}\n\n"
        "Escribe la sección de Discusión en ESPAÑOL para esta revisión sistemática Cochrane. Incluye:\n"
        "1. Resumen de los resultados principales\n"
        "2. Completitud y aplicabilidad general de la evidencia\n"
        "3. Calidad de la evidencia (riesgo de sesgo, heterogeneidad)\n"
        "4. Posibles sesgos en el proceso de revisión\n"
        "5. Acuerdos y desacuerdos con otros estudios o revisiones\n"
        "6. Conclusiones de los autores:\n"
        "   a) Implicaciones para la práctica\n"
        "   b) Implicaciones para la investigación\n"
        "Escribe aproximadamente 600-800 palabras."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


_ROB_DOMAINS = [
    ("rob_random_sequence",       "Generación de la secuencia aleatoria (sesgo de selección)"),
    ("rob_allocation_concealment", "Ocultamiento de la asignación (sesgo de selección)"),
    ("rob_blinding_participants",  "Cegamiento de participantes y personal (sesgo de realización)"),
    ("rob_blinding_outcome",       "Cegamiento de la evaluación de resultados (sesgo de detección)"),
    ("rob_incomplete_data",        "Datos de resultado incompletos (sesgo de desgaste)"),
    ("rob_selective_reporting",    "Notificación selectiva de resultados (sesgo de notificación)"),
    ("rob_other",                  "Otros sesgos"),
]


def _rob_domain_tally(studies: list[dict]) -> str:
    """Count low/some_concerns/high per RoB domain across studies — computed
    directly from the data (not left for the model to guess) so the narrative
    the AI writes cites real tallies, not hallucinated ones."""
    lines = []
    for key, label in _ROB_DOMAINS:
        low = sum(1 for s in studies if s.get(key) == "low")
        some = sum(1 for s in studies if s.get(key) == "some_concerns")
        high = sum(1 for s in studies if s.get(key) == "high")
        unrated = len(studies) - low - some - high
        lines.append(
            f"- {label}: bajo riesgo={low}, algunas preocupaciones={some}, "
            f"alto riesgo={high}, sin evaluar={unrated}"
        )
    return "\n".join(lines)


def generate_risk_of_bias_results(review: dict, studies: list[dict]) -> str:
    """Cochrane-style 'Risk of bias in included studies' narrative (section 4.1.4)."""
    ctx = _base_context(review, studies)
    tally = _rob_domain_tally(studies)
    k = len(studies)
    level_es = {"low": "bajo", "some_concerns": "algunas preocupaciones", "high": "alto"}
    per_study = "\n".join(
        f"- {s.get('study_label') or s.get('authors') or s.get('id')}: global "
        f"{level_es.get(s.get('rob_overall'), 'sin evaluar')}"
        for s in studies[:40]
    )
    ai_rated = sum(1 for s in studies if ROB_AI_TAG in (s.get("rob_notes") or ""))
    provenance = (
        f"\nNOTA: {ai_rated} de {k} evaluaciones fueron sugeridas por IA a partir de la información "
        "disponible (título/resumen) y están pendientes de verificación con el texto completo; "
        "menciónalo explícitamente como limitación.\n"
        if ai_rated else ""
    )
    user = (
        f"{ctx}\n\n"
        f"EVALUACIÓN DEL RIESGO DE SESGO (herramienta Cochrane), {k} estudios incluidos, "
        f"por dominio:\n{tally}\n\nRIESGO GLOBAL POR ESTUDIO:\n{per_study}\n{provenance}\n"
        "Escribe la sección 'Riesgo de sesgo en los estudios incluidos' en ESPAÑOL para esta "
        "revisión sistemática Cochrane, usando ÚNICAMENTE los números reales proporcionados arriba "
        "(no inventes cifras). Estructura:\n"
        "1. Un párrafo introductorio resumiendo el panorama general de riesgo de sesgo "
        "(cuántos estudios con bajo riesgo, algunas preocupaciones o alto riesgo en conjunto).\n"
        "2. Un párrafo por cada uno de los 7 dominios de RoB 2, citando los conteos reales "
        "y, si aplica, qué estudios contribuyeron al alto riesgo o las preocupaciones "
        "(usa las etiquetas de los estudios cuando sea relevante).\n"
        "3. Un párrafo final de síntesis sobre cómo el riesgo de sesgo general podría "
        "afectar la confianza en las estimaciones del efecto.\n"
        "Escribe aproximadamente 400-600 palabras, en prosa académica, sin encabezados ni viñetas."
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
        "Genera en ESPAÑOL una lista de referencias completa y correctamente formateada "
        "para todos los estudios incluidos usando el formato especificado arriba. "
        "Numera cada referencia secuencialmente. "
        "IMPORTANTE: cada referencia debe ir en su PROPIA línea, separada de la siguiente "
        "por un salto de línea — nunca pongas dos o más referencias en la misma línea. "
        "Si falta metadato específico (volumen, páginas, DOI), usa la información disponible "
        "y marca los campos faltantes con '[datos no disponibles]'. "
        "Genera únicamente la lista numerada de referencias (una por línea), sin encabezados ni preámbulo."
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
        "Escribe en ESPAÑOL una interpretación detallada estilo Cochrane de:\n"
        "1. El diagrama de bosque (forest plot): describe la estimación agrupada, dirección "
        "y magnitud del efecto, intervalo de confianza, qué estudios impulsan el resultado, "
        "valores atípicos notables.\n"
        "2. El gráfico de embudo (funnel plot): interpreta simetría/asimetría, qué implica "
        "respecto al sesgo de publicación (referencia a la prueba de Egger si está disponible).\n"
        "3. Heterogeneidad: explica el valor de I² clínicamente, discute posibles fuentes, "
        "interpreta el intervalo de predicción si está disponible.\n"
        "4. Conclusión general del análisis estadístico.\n"
        "Escribe aproximadamente 400-500 palabras en estilo académico formal."
    )
    return _call_claude(SYSTEM_COCHRANE, user)


def generate_section(
    section: str,
    review: dict,
    studies: list[dict],
    meta_results: dict | None = None,
    citation_style: str = "vancouver",
    excluded: list[dict] | None = None,
) -> str:
    """Dispatch to the appropriate generator function by section name."""
    generators = {
        "abstract": generate_abstract,
        "background": generate_background,
        "objectives": generate_objectives,
        "methods": generate_methods,
        "results": generate_results,
        "discussion": generate_discussion,
        "risk_of_bias": generate_risk_of_bias_results,
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
    if section_key == "results":
        return fn(review, studies, meta_results, excluded)
    return fn(review, studies, meta_results) if section_key in ("abstract", "results", "discussion") else fn(review, studies)


_ELIGIBILITY_FIELDS = [
    ("population", "Población (PICO)"),
    ("intervention", "Intervención (PICO)"),
    ("comparison", "Comparación (PICO)"),
    ("outcomes", "Desenlaces (PICO)"),
    ("study_design", "Diseño de estudio (PICO)"),
    ("types_of_studies", "Tipos de estudios"),
    ("types_of_participants", "Tipos de participantes"),
    ("types_of_interventions", "Tipos de intervenciones"),
    ("types_of_outcomes", "Tipos de medidas de resultado"),
    ("primary_outcomes", "Desenlaces primarios"),
    ("secondary_outcomes", "Desenlaces secundarios"),
    ("inclusion_criteria", "CRITERIOS DE INCLUSIÓN"),
    ("exclusion_criteria", "CRITERIOS DE EXCLUSIÓN"),
]


def eligibility_block(review: dict) -> str:
    """Author-defined eligibility criteria, verbatim, omitting empty fields."""
    parts = []
    for key, label in _ELIGIBILITY_FIELDS:
        value = (review.get(key) or "").strip()
        if value:
            parts.append(f"{label}:\n{value}")
    return "\n\n".join(parts)


_SCREEN_STUDY_FIELDS = [
    "study_label", "authors", "year", "title", "publication_type", "journal",
    "study_design", "reasoning_study_design", "country", "setting", "sample_size",
    "age_mean", "percent_female", "patient_population", "inclusion_criteria",
    "group_comparison", "objective_text", "methods_used", "abstract_text",
    "study_results", "survival_outcomes", "mortality_factors", "key_findings",
    "findings", "notes",
]

_SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["include", "exclude", "uncertain"]},
                    "criterion": {"type": "string"},
                    "reason": {"type": "string"},
                    "suitability": {"type": "string", "enum": ["quantitative", "narrative", "not_applicable"]},
                    "suitability_note": {"type": "string"},
                },
                "required": ["id", "decision", "criterion", "reason", "suitability", "suitability_note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decisions"],
    "additionalProperties": False,
}

_SCREEN_SYSTEM = (
    "Eres un revisor metodológico experto en revisiones sistemáticas Cochrane (Manual Cochrane, "
    "estándares MECIR y PRISMA 2020). Tu tarea es aplicar de forma estricta, reproducible y "
    "trazable los criterios de elegibilidad definidos por el autor de la revisión. "
    "Nunca inventas criterios propios ni usas conocimiento externo sobre un estudio: decides "
    "únicamente con la información proporcionada de cada estudio."
)


def screen_studies_with_ai(review: dict, studies: list[dict]) -> dict:
    """
    Apply the review's eligibility criteria to each study.
    Returns {study_id: {"decision": "include"|"exclude"|"uncertain", "criterion": str, "reason": str}}.
    Raises on a refusal or an unparseable response instead of guessing a decision.
    """
    import json

    criteria = eligibility_block(review)
    title = review.get("title") or "Revisión sistemática"
    client = _get_client()
    results: dict = {}
    batch_size = 15

    for i in range(0, len(studies), batch_size):
        batch = studies[i:i + batch_size]
        payload = []
        for s in batch:
            entry = {"id": s["id"]}
            for field in _SCREEN_STUDY_FIELDS:
                value = s.get(field)
                if value not in (None, ""):
                    entry[field] = value
            payload.append(entry)

        user = (
            f"REVISIÓN SISTEMÁTICA: {title}\n\n"
            "CRITERIOS DE ELEGIBILIDAD DEFINIDOS POR EL AUTOR (aplícalos tal cual):\n"
            f"{criteria}\n\n"
            "ESTUDIOS A EVALUAR (JSON; cada campo proviene de la base de datos del autor):\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=1)}\n\n"
            "Para CADA estudio, verifica uno por uno todos los criterios de inclusión y todos los "
            "criterios de exclusión anteriores, y asigna una decisión:\n"
            "- \"include\": la información disponible muestra que cumple TODOS los criterios de "
            "inclusión y NO cumple ningún criterio de exclusión.\n"
            "- \"exclude\": hay evidencia explícita en la información del estudio de que incumple al "
            "menos un criterio de inclusión o cumple al menos un criterio de exclusión.\n"
            "- \"uncertain\": la información disponible no permite verificar al menos un criterio "
            "obligatorio (requiere revisión a texto completo). No adivines.\n\n"
            "Reglas:\n"
            "1. Tipo de estudio: acepta exactamente los diseños que el autor definió. Si el autor "
            "admite estudios observacionales (cohorte, casos y controles, transversales, etc.), NO "
            "los excluyas por no ser ensayos aleatorizados. Si el autor no restringió el diseño, "
            "acepta cualquier diseño que responda la pregunta PICO.\n"
            "2. No excluyas un estudio solo porque el resumen no presente datos numéricos del "
            "desenlace: eso se resuelve en la extracción de datos. Sí exclúyelo si claramente no "
            "evalúa ningún desenlace de interés.\n"
            "3. Revisiones sistemáticas, metaanálisis, editoriales, cartas, protocolos sin resultados "
            "y estudios en animales o in vitro se excluyen, salvo que el autor los admita "
            "explícitamente.\n"
            "4. No agregues criterios que el autor no haya definido.\n"
            "5. Analizabilidad (solo para \"include\"): en \"suitability\" indica \"quantitative\" "
            "ÚNICAMENTE si el texto disponible escribe, para AMBOS grupos que compara la revisión, los "
            "números de al menos un desenlace: eventos y total de cada grupo, o media, DE y n de cada "
            "grupo, o un efecto comparativo (OR, RR, diferencia) con su IC 95 %. NO son cuantitativos: "
            "un valor p, una prevalencia global del estudio, porcentajes sin el tamaño de cada grupo o "
            "frases como «fue más frecuente en…»; en esos casos indica \"narrative\" y explica en la "
            "nota qué datos habría que obtener del texto completo. Para \"exclude\" "
            "e \"uncertain\" usa \"not_applicable\". En \"suitability_note\" indica en español qué "
            "datos cuantitativos aporta y para qué desenlace, o qué falta. La analizabilidad NUNCA "
            "cambia la decisión: un estudio elegible sin datos numéricos se incluye igualmente.\n\n"
            "En \"criterion\" escribe el criterio concreto que determinó la decisión (para "
            "\"include\", escribe \"Cumple todos los criterios\"). En \"reason\" explica en español, "
            "en una o dos frases, la evidencia del estudio que sustenta la decisión. "
            "Devuelve exactamente una decisión por cada id recibido."
        )

        with client.messages.stream(
            model="claude-opus-5",
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": _SCREEN_SCHEMA},
            },
            system=_SCREEN_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            raise RuntimeError("El modelo declinó evaluar este lote de estudios.")
        if message.stop_reason == "max_tokens":
            raise RuntimeError("La respuesta del cribado quedó truncada; reintenta.")

        text = next(b.text for b in message.content if b.type == "text")
        batch_ids = {s["id"] for s in batch}
        for d in json.loads(text)["decisions"]:
            if d["id"] in batch_ids:
                results[d["id"]] = {
                    "decision": d["decision"],
                    "criterion": d["criterion"].strip(),
                    "reason": d["reason"].strip(),
                    "suitability": d["suitability"],
                    "suitability_note": d["suitability_note"].strip(),
                }

    return results


_EXTRACT_SOURCE_FIELDS = [
    ("abstract_text", "Resumen"),
    ("study_results", "Resultados"),
    ("key_findings", "Hallazgos clave"),
    ("findings", "Hallazgos"),
    ("survival_outcomes", "Desenlaces de supervivencia"),
    ("mortality_factors", "Mortalidad"),
    ("group_comparison", "Comparación de grupos"),
    ("methods_used", "Métodos"),
    ("notes", "Notas"),
]

_EXTRACT_FIELDS_BY_MEASURE = {
    "binary": ["events_intervention", "total_intervention", "events_control", "total_control"],
    "continuous": ["mean_intervention", "sd_intervention", "n_intervention",
                   "mean_control", "sd_control", "n_control"],
    "precalculated": ["effect_size", "effect_size_lower", "effect_size_upper",
                      "total_intervention", "total_control"],
}

_INT_EXTRACT_FIELDS = {"events_intervention", "total_intervention", "events_control",
                       "total_control", "n_intervention", "n_control", "sample_size"}

_EXTRACT_SYSTEM = (
    "Eres un extractor de datos para revisiones sistemáticas Cochrane que trabaja en doble "
    "verificación. Solo registras un número si aparece escrito en el texto del estudio que se te "
    "entrega, y para cada número copias literalmente la frase de donde sale. Nunca calculas, "
    "estimas, imputas, conviertes unidades, ni usas conocimiento externo sobre el estudio. Si un "
    "dato no está escrito de forma explícita, lo dejas en null."
)


def _extract_schema(fields: list[str]) -> dict:
    item = {
        "type": "object",
        "properties": {
            "field": {"type": "string", "enum": fields + ["sample_size"]},
            "value": {"type": "number"},
            "quote": {"type": "string"},
            "source": {"type": "string", "enum": [f for f, _ in _EXTRACT_SOURCE_FIELDS]},
        },
        "required": ["field", "value", "quote", "source"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "studies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "outcome_reported": {"type": "string"},
                        "values": {"type": "array", "items": item},
                    },
                    "required": ["id", "outcome_reported", "values"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["studies"],
        "additionalProperties": False,
    }


def _norm_text(t: str) -> str:
    import re, unicodedata
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = t.replace("−", "-").replace("–", "-").replace("—", "-").replace("·", ".")
    return re.sub(r"\s+", " ", t).strip()


def _number_in_quote(value: float, quote: str) -> bool:
    """The extracted number must be written in the quoted sentence (no derived numbers)."""
    import re
    for tok in re.findall(r"\d+(?:[.,]\d+)?", quote):
        try:
            if abs(float(tok.replace(",", ".")) - float(value)) < 1e-9:
                return True
        except ValueError:
            continue
    return False


def _check_consistency(fields: dict) -> list[str]:
    """Plausibility checks between extracted values; returns the fields to reject."""
    bad = set()
    for e, t in (("events_intervention", "total_intervention"), ("events_control", "total_control")):
        if e in fields and t in fields and not (0 <= fields[e] <= fields[t]):
            bad.update({e, t})
    for k in ("total_intervention", "total_control", "n_intervention", "n_control", "sample_size"):
        if k in fields and fields[k] <= 0:
            bad.add(k)
    for k in ("sd_intervention", "sd_control"):
        if k in fields and fields[k] <= 0:
            bad.add(k)
    es, lo, hi = (fields.get(k) for k in ("effect_size", "effect_size_lower", "effect_size_upper"))
    if None not in (es, lo, hi) and not (lo <= es <= hi):
        bad.update({"effect_size", "effect_size_lower", "effect_size_upper"})
    return sorted(bad)


ROB_DOMAIN_KEYS = [
    "rob_random_sequence", "rob_allocation_concealment", "rob_blinding_participants",
    "rob_blinding_outcome", "rob_incomplete_data", "rob_selective_reporting", "rob_other",
]
ROB_AI_TAG = "[Evaluación sugerida por IA a partir de la información disponible — verificar con el texto completo]"

_ROB_LEVEL = {"type": "string", "enum": ["low", "some_concerns", "high"]}
_ROB_SCHEMA = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "design": {"type": "string"},
                    **{k: _ROB_LEVEL for k in ROB_DOMAIN_KEYS},
                    "justification": {"type": "string"},
                },
                "required": ["id", "design", *ROB_DOMAIN_KEYS, "justification"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assessments"],
    "additionalProperties": False,
}


def assess_risk_of_bias(review: dict, studies: list[dict]) -> dict:
    """
    Rate the 7 Cochrane risk-of-bias domains for each study from its stored information.
    Returns {study_id: {rob_*: level, "rob_overall": level, "rob_notes": str}}.
    """
    import json

    client = _get_client()
    results: dict = {}
    batch_size = 10
    domain_guide = (
        "- rob_random_sequence: generación de la secuencia aleatoria.\n"
        "- rob_allocation_concealment: ocultamiento de la asignación.\n"
        "- rob_blinding_participants: cegamiento de participantes y personal.\n"
        "- rob_blinding_outcome: cegamiento de la evaluación de desenlaces.\n"
        "- rob_incomplete_data: datos de desenlace incompletos (pérdidas, exclusiones).\n"
        "- rob_selective_reporting: notificación selectiva de resultados.\n"
        "- rob_other: otras fuentes de sesgo (p. ej., confusión en estudios observacionales, "
        "diseño antes-después, finalización temprana, desequilibrios basales)."
    )

    for i in range(0, len(studies), batch_size):
        batch = studies[i:i + batch_size]
        payload = []
        for s in batch:
            entry = {"id": s["id"]}
            for field in _SCREEN_STUDY_FIELDS:
                value = s.get(field)
                if value not in (None, ""):
                    entry[field] = value
            payload.append(entry)

        user = (
            f"REVISIÓN SISTEMÁTICA: {review.get('title') or ''}\n"
            f"Desenlaces de interés: {review.get('outcomes') or ''}\n\n"
            "Evalúa el riesgo de sesgo de cada estudio en los 7 dominios de la herramienta Cochrane:\n"
            f"{domain_guide}\n\n"
            f"ESTUDIOS (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n\n"
            "Reglas:\n"
            "1. Juzga ÚNICAMENTE con la información proporcionada de cada estudio; no uses "
            "conocimiento externo sobre el artículo.\n"
            "2. \"low\" solo si la información describe explícitamente un método adecuado para ese "
            "dominio. \"high\" si describe un método inadecuado o el diseño lo implica. "
            "\"some_concerns\" si el dominio no se describe o la información es insuficiente.\n"
            "3. Estudios no aleatorizados (cohortes, casos y controles, antes-después, "
            "transversales): secuencia aleatoria y ocultamiento de la asignación son \"high\" "
            "porque no hubo asignación aleatoria; evalúa la confusión en \"rob_other\".\n"
            "4. Ensayos abiertos (sin cegamiento declarado) son \"high\" en cegamiento de "
            "participantes; para el cegamiento de la evaluación considera si el desenlace es "
            "objetivo (p. ej., mortalidad).\n"
            "5. En \"design\" indica el diseño identificado (p. ej., \"ECA\", \"cohorte "
            "retrospectiva\", \"no identificable\").\n"
            "6. En \"justification\" escribe en español una frase breve por dominio, con la "
            "evidencia usada o indicando que no se reporta.\n"
            "Devuelve exactamente una evaluación por cada id recibido."
        )

        with client.messages.stream(
            model="claude-opus-5",
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": _ROB_SCHEMA},
            },
            system=_SCREEN_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            raise RuntimeError("El modelo declinó evaluar este lote de estudios.")
        if message.stop_reason == "max_tokens":
            raise RuntimeError("La respuesta de la evaluación quedó truncada; reintenta.")

        text = next(b.text for b in message.content if b.type == "text")
        batch_ids = {s["id"] for s in batch}
        for a in json.loads(text)["assessments"]:
            if a["id"] not in batch_ids:
                continue
            levels = [a[k] for k in ROB_DOMAIN_KEYS]
            overall = "high" if "high" in levels else "some_concerns" if "some_concerns" in levels else "low"
            results[a["id"]] = {
                **{k: a[k] for k in ROB_DOMAIN_KEYS},
                "rob_overall": overall,
                "rob_notes": f"{ROB_AI_TAG}\nDiseño: {a['design'].strip()}\n{a['justification'].strip()}",
            }

    return results


def extract_quantitative_data(review: dict, studies: list[dict]) -> dict:
    """
    Exact, auditable extraction of the outcome data needed for the meta-analysis.

    For every number the model must return the verbatim sentence it comes from. A
    value is accepted only if that sentence is literally present in the study's
    text AND the number is written in it, and the values of a study pass the
    plausibility checks (events <= total, SD > 0, lower <= effect <= upper).

    Returns {study_id: {"values": {field: value}, "evidence": {field: {...}},
                        "rejected": [{"field", "value", "reason"}], "outcome": str}}.
    """
    import json

    effect_measure = (review.get("effect_measure") or "OR").upper()
    kind = ("binary" if effect_measure in ("OR", "RR", "RD")
            else "continuous" if effect_measure in ("MD", "SMD") else "precalculated")
    fields = _EXTRACT_FIELDS_BY_MEASURE[kind]
    outcome = (review.get("primary_outcomes") or review.get("outcomes") or "").strip()

    candidates = [
        s for s in studies
        if s.get("included") is not False
        and any(s.get(f) for f, _ in _EXTRACT_SOURCE_FIELDS)
        and not any(s.get(f) is not None for f in fields)
    ]

    client = _get_client()
    schema = _extract_schema(fields)
    results: dict = {}
    batch_size = 5

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        payload = []
        for s in batch:
            texts = {f: s[f] for f, _ in _EXTRACT_SOURCE_FIELDS if s.get(f)}
            payload.append({
                "id": s["id"],
                "estudio": s.get("study_label") or s.get("authors") or f"ID {s['id']}",
                "diseño": s.get("study_design"),
                "textos": texts,
            })

        user = (
            f"REVISIÓN: {review.get('title', '')}\n"
            f"MEDIDA DE EFECTO: {effect_measure}\n"
            f"DESENLACE A EXTRAER (definido por el autor): {outcome or 'desenlace principal de la revisión'}\n"
            f"Intervención: {review.get('intervention', '')} | Comparador: {review.get('comparison', '')}\n\n"
            f"CAMPOS: {', '.join(fields)} (y sample_size si se reporta el N total del estudio).\n"
            "- *_intervention = grupo de la intervención de la revisión; *_control = grupo comparador.\n"
            "- events_* = número de participantes con el evento; total_* = participantes analizados en ese grupo.\n"
            "- effect_size/effect_size_lower/effect_size_upper = medida e IC95% tal como se reporta.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. Cada valor debe estar escrito en los textos del estudio. En \"quote\" copia, carácter "
            "por carácter, la frase o fragmento (máx. ~300 caracteres) que contiene el número, y en "
            "\"source\" indica de qué texto lo copiaste.\n"
            "2. No calcules nada: si solo hay un porcentaje, no derives el número de eventos; si hay "
            "error estándar o rango, no lo conviertas en DE; si hay mediana, no la uses como media.\n"
            "3. Extrae solo el desenlace indicado. Si el estudio no lo reporta para ambos grupos, "
            "devuelve values vacío. Si hay varios momentos de seguimiento, usa el principal declarado "
            "y escribe cuál en \"outcome_reported\".\n"
            "4. No asignes un grupo a intervención o control si el texto no permite saberlo.\n\n"
            f"ESTUDIOS (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n\n"
            "Devuelve una entrada por cada id recibido."
        )

        with client.messages.stream(
            model="claude-opus-5-5",
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": schema},
            },
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            raise RuntimeError("El modelo declinó extraer datos de este lote de estudios.")
        if message.stop_reason == "max_tokens":
            raise RuntimeError("La respuesta de extracción quedó truncada; reintenta.")

        text = next(b.text for b in message.content if b.type == "text")
        by_id = {s["id"]: s for s in batch}
        for entry in json.loads(text)["studies"]:
            study = by_id.get(entry["id"])
            if not study:
                continue
            accepted, evidence, rejected = {}, {}, []
            for v in entry["values"]:
                field, value, quote, src = v["field"], v["value"], v["quote"].strip(), v["source"]
                source_text = study.get(src) or ""
                if not quote or _norm_text(quote) not in _norm_text(source_text):
                    rejected.append({"field": field, "value": value,
                                     "reason": "la cita no aparece textualmente en el estudio"})
                    continue
                if not _number_in_quote(value, quote):
                    rejected.append({"field": field, "value": value,
                                     "reason": "el número no está escrito en la cita (valor derivado)"})
                    continue
                if field in _INT_EXTRACT_FIELDS:
                    if float(value) != int(value):
                        rejected.append({"field": field, "value": value, "reason": "debe ser un entero"})
                        continue
                    value = int(value)
                if field in accepted and accepted[field] != value:
                    rejected.append({"field": field, "value": value, "reason": "valores contradictorios"})
                    accepted.pop(field)
                    evidence.pop(field, None)
                    continue
                accepted[field] = value
                evidence[field] = {"value": value, "quote": quote, "source": src,
                                   "outcome": entry["outcome_reported"]}
            for field in _check_consistency(accepted):
                rejected.append({"field": field, "value": accepted.pop(field),
                                 "reason": "inconsistente con los demás datos del estudio"})
                evidence.pop(field, None)
            # A group is only usable with all its numbers: drop incomplete arms.
            groups = ([("events_intervention", "total_intervention"), ("events_control", "total_control")]
                      if kind == "binary" else
                      [("mean_intervention", "sd_intervention", "n_intervention"),
                       ("mean_control", "sd_control", "n_control")]
                      if kind == "continuous" else
                      [("effect_size", "effect_size_lower", "effect_size_upper")])
            for g in groups:
                present = [f for f in g if f in accepted]
                if present and len(present) < len(g):
                    for f in present:
                        rejected.append({"field": f, "value": accepted.pop(f),
                                         "reason": "grupo incompleto (faltan datos verificables del mismo brazo)"})
                        evidence.pop(f, None)
            results[entry["id"]] = {"values": accepted, "evidence": evidence, "rejected": rejected,
                                    "outcome": entry["outcome_reported"]}

    return results


def interpret_forest_plot(review: dict, result_dict: dict) -> str:
    """Auto-interpretation of forest plot results in Spanish (Haiku, fast)."""
    p = result_dict.get("pooled", {})
    h = result_dict.get("heterogeneity", {})
    em = result_dict.get("effect_measure", "ES")
    model = result_dict.get("model", "random")
    k = result_dict.get("k", 0)
    total_n = result_dict.get("total_n", 0)
    pi = result_dict.get("prediction_interval", {}) or {}
    studies = result_dict.get("studies", [])

    study_lines = "\n".join(
        f"  {s['label']}: {em}={s.get('effect', 0):.2f} "
        f"[{s.get('ci_lower', 0):.2f}, {s.get('ci_upper', 0):.2f}], "
        f"peso={s.get('weight_re' if model == 'random' else 'weight_fe', 0):.1f}%"
        for s in studies[:20]
    )
    pi_text = ""
    if pi.get("lower") is not None:
        pi_text = f"\nIntervalo de predicción: [{pi['lower']:.2f}, {pi['upper']:.2f}]"

    user = (
        f"REVISIÓN: {review.get('title', '')}\n"
        f"Población: {review.get('population', '')} | Intervención: {review.get('intervention', '')}\n\n"
        f"RESULTADOS (modelo {model}, k={k}, N={total_n}):\n"
        f"  {em} combinado: {p.get('effect', 0):.2f} [IC95% {p.get('ci_lower', 0):.2f}–{p.get('ci_upper', 0):.2f}]\n"
        f"  I²={h.get('I2', 0):.0f}%, Q={h.get('Q', 0):.1f} (p={h.get('Q_pvalue', 1):.3f}), τ²={h.get('tau2', 0):.4f}"
        f"{pi_text}\n\n"
        f"Estudios individuales:\n{study_lines}\n\n"
        "Escribe en ESPAÑOL una interpretación concisa del diagrama de bosque (250–350 palabras), estilo Cochrane:\n"
        "1) Estimación agrupada: magnitud, dirección, significado clínico del IC95%.\n"
        "2) Estudios que más contribuyen al resultado y por qué.\n"
        "3) Heterogeneidad: nivel de I², implicaciones, posibles fuentes.\n"
        "4) Intervalo de predicción si disponible.\n"
        "5) Conclusión estadística general."
    )
    client = _get_client()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_COCHRANE,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


def interpret_funnel_plot(review: dict, result_dict: dict) -> str:
    """Auto-interpretation of funnel plot in Spanish (Haiku, fast)."""
    p = result_dict.get("pooled", {})
    h = result_dict.get("heterogeneity", {})
    em = result_dict.get("effect_measure", "ES")
    k = result_dict.get("k", 0)
    user = (
        f"REVISIÓN: {review.get('title', '')}\n"
        f"k={k} estudios, {em} combinado={p.get('effect', 0):.2f} "
        f"[{p.get('ci_lower', 0):.2f}–{p.get('ci_upper', 0):.2f}], "
        f"I²={h.get('I2', 0):.0f}%\n\n"
        "Escribe en ESPAÑOL una interpretación del gráfico de embudo (150–200 palabras), estilo Cochrane: "
        "simetría o asimetría observada, lo que implica sobre el sesgo de publicación, "
        "referencia a la prueba de Egger si el número de estudios lo permite (k≥10), "
        "y qué significa para la validez de las conclusiones del metaanálisis."
    )
    client = _get_client()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SYSTEM_COCHRANE,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


def interpret_grade_table(review: dict, result_dict: dict, studies: list) -> str:
    """Auto-interpretation of GRADE evidence table in Spanish (Haiku, fast)."""
    p = result_dict.get("pooled", {})
    h = result_dict.get("heterogeneity", {})
    em = result_dict.get("effect_measure", "ES")
    k = result_dict.get("k", 0)
    total_n = result_dict.get("total_n", 0)
    i2 = h.get("I2", 0)
    effect = p.get("effect")
    ci_lo = p.get("ci_lower")
    ci_hi = p.get("ci_upper")
    effect_str = f"{em}={effect:.2f} (IC95% {ci_lo:.2f}–{ci_hi:.2f})" if effect is not None else "no disponible"

    high_risk = sum(
        1 for s in studies
        for rob_key in [
            "rob_random_sequence", "rob_allocation_concealment",
            "rob_blinding_participants", "rob_blinding_outcome",
            "rob_incomplete_data", "rob_selective_reporting",
        ]
        if s.get(rob_key) == "high"
    )

    user = (
        f"REVISIÓN: {review.get('title', '')}\n"
        f"k={k} estudios, N={total_n}, {effect_str}, I²={i2:.0f}%, "
        f"dominios con alto riesgo de sesgo: {high_risk}\n\n"
        "Escribe en ESPAÑOL una interpretación de la tabla GRADE de certeza de la evidencia (200–250 palabras): "
        "nivel de certeza alcanzado (ALTA/MODERADA/BAJA/MUY BAJA), principales razones de degradación "
        "(riesgo de sesgo, inconsistencia, indirectness, imprecisión, sesgo de publicación), "
        "implicaciones clínicas del nivel de certeza y recomendaciones para la práctica."
    )
    client = _get_client()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=768,
        system=SYSTEM_COCHRANE,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()


def interpret_rob_plot(review: dict, studies: list) -> str:
    """Auto-interpretation of the RoB 2 traffic-light plot in Spanish (Haiku, fast)."""
    tally = _rob_domain_tally(studies)
    k = len(studies)
    user = (
        f"REVISIÓN: {review.get('title', '')}\n"
        f"Evaluación Cochrane RoB 2 de {k} estudios incluidos, por dominio:\n{tally}\n\n"
        "Escribe en ESPAÑOL una interpretación breve (120-180 palabras) del gráfico de semáforo de "
        "riesgo de sesgo: qué dominio(s) concentran más preocupaciones, el juicio de riesgo de sesgo "
        "general, y cómo esto debería matizar la confianza en los resultados del metaanálisis."
    )
    client = _get_client()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SYSTEM_COCHRANE,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()
