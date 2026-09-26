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
        "Conclusiones de los autores. Sé conciso (300-400 palabras en total)."
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
        "2. Métodos de búsqueda para identificar estudios (bases de datos: PubMed, Embase, "
        "Cochrane CENTRAL, Scopus, Web of Science; literatura gris)\n"
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
        "Escribe aproximadamente 800-1000 palabras."
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
        f"   - Flujo de estudios (número cribados, elegibles, incluidos: {study_count} estudios)\n"
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
        "Escribe aproximadamente 700-900 palabras."
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
    user = (
        f"{ctx}\n\n"
        f"EVALUACIÓN DEL RIESGO DE SESGO (Cochrane RoB 2), {k} estudios incluidos, "
        f"por dominio:\n{tally}\n\n"
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
                },
                "required": ["id", "decision", "criterion", "reason"],
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
            "4. No agregues criterios que el autor no haya definido.\n\n"
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
                }

    return results


def extract_quantitative_data(review: dict, studies: list[dict]) -> dict:
    """
    For each included study with abstract_text, use AI to extract quantitative
    outcome data needed for meta-analysis.
    Returns {study_id: {field: value, ...}} with extracted fields.
    Processes studies one batch at a time (10 per call).
    """
    import json, re

    effect_measure = review.get("effect_measure", "OR")
    pico = (
        f"Población: {review.get('population', '')}\n"
        f"Intervención: {review.get('intervention', '')}\n"
        f"Comparación: {review.get('comparison', '')}\n"
        f"Desenlaces: {review.get('outcomes', '')}"
    )

    # Determine what data to extract based on effect measure
    if effect_measure in ("OR", "RR", "RD"):
        data_template = (
            '"events_intervention": N_o_null, "total_intervention": N_o_null, '
            '"events_control": N_o_null, "total_control": N_o_null'
        )
        data_description = "número de eventos (casos) y total de participantes en grupo intervención y grupo control"
    elif effect_measure in ("MD", "SMD"):
        data_template = (
            '"mean_intervention": N_o_null, "sd_intervention": N_o_null, "n_intervention": N_o_null, '
            '"mean_control": N_o_null, "sd_control": N_o_null, "n_control": N_o_null'
        )
        data_description = "media, desviación estándar y n de cada grupo"
    else:  # PRECALCULATED
        data_template = (
            '"effect_size": N_o_null, "effect_size_lower": N_o_null, "effect_size_upper": N_o_null, '
            '"total_intervention": N_o_null, "total_control": N_o_null'
        )
        data_description = "tamaño de efecto, IC95% inferior y superior, y n por grupo"

    client = _get_client()
    results: dict = {}
    batch_size = 10

    # Only process studies with abstract text and no existing quantitative data
    candidates = [
        s for s in studies
        if s.get("included") is not False
        and s.get("abstract_text")
        and not any(s.get(f) for f in [
            "events_intervention", "total_intervention",
            "mean_intervention", "effect_size"
        ])
    ]

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        entries = []
        for s in batch:
            abstract = (s.get("abstract_text") or "")[:800]
            results_text = (s.get("study_results") or "")[:300]
            label = s.get("study_label") or s.get("authors") or f"ID:{s['id']}"
            entries.append(
                f'  {{"id": {s["id"]}, "label": "{label}", '
                f'"abstract": "{abstract}", "results": "{results_text}"}}'
            )

        user = (
            f"REVISIÓN: {review.get('title', '')}\nMEDIDA DE EFECTO: {effect_measure}\n"
            f"PICO:\n{pico}\n\n"
            f"Extrae del resumen/resultados de cada estudio: {data_description}.\n"
            "Si un dato no está mencionado, usa null. Solo extrae lo que el texto diga explícitamente.\n\n"
            f"ESTUDIOS:\n[{chr(10).join(entries)}]\n\n"
            "Responde ÚNICAMENTE con JSON:\n"
            '{"extractions": [{"id": N, ' + data_template + ', "sample_size": N_o_null}]}'
        )

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system="Extrae datos numéricos de texto científico. Responde ÚNICAMENTE con JSON válido.",
            messages=[{"role": "user", "content": user}],
        )
        text = message.content[0].text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            for ext in data.get("extractions", []):
                sid = ext.pop("id", None)
                if sid is not None:
                    # Keep only non-null values
                    clean = {k: v for k, v in ext.items() if v is not None}
                    if clean:
                        results[sid] = clean

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


def generate_prisma_autofill(review: dict, study_count: int) -> dict:
    """Use AI to generate realistic PRISMA 2020 flow numbers based on PICO and included studies."""
    import json, re

    pico = (
        f"Población: {review.get('population', '')}\n"
        f"Intervención: {review.get('intervention', '')}\n"
        f"Comparación: {review.get('comparison', '')}\n"
        f"Desenlaces: {review.get('outcomes', '')}"
    )
    user = (
        f"TÍTULO: {review.get('title', 'Revisión sistemática')}\n\n"
        f"PICO:\n{pico}\n\n"
        f"ESTUDIOS INCLUIDOS (final): {study_count} estudios fueron incluidos en este metaanálisis.\n\n"
        "Genera números realistas y coherentes para el diagrama de flujo PRISMA 2020. "
        "Los números deben ser lógicos: registros identificados >> cribados > evaluados > incluidos. "
        "Razones de exclusión deben ser específicas al PICO de esta revisión.\n\n"
        "Responde ÚNICAMENTE con un JSON válido, sin comentarios, sin texto adicional:\n"
        "{\n"
        '  "prisma_db_names": "PubMed=N,Scopus=N,EMBASE=N,Cochrane CENTRAL=N",\n'
        '  "prisma_other_sources": N,\n'
        '  "prisma_duplicates_removed": N,\n'
        '  "prisma_other_removed": N,\n'
        '  "prisma_screened": N,\n'
        '  "prisma_excluded_screening": N,\n'
        '  "prisma_sought": N,\n'
        '  "prisma_not_retrieved": N,\n'
        '  "prisma_assessed": N,\n'
        '  "prisma_excluded_eligibility": N,\n'
        '  "prisma_exclusion_reasons": "Razón específica 1=N,Razón específica 2=N,Razón específica 3=N",\n'
        f'  "prisma_included": {study_count},\n'
        f'  "prisma_reports_included": {study_count}\n'
        "}\n"
        f"El valor de prisma_included DEBE ser exactamente {study_count}. "
        "Usa razones de exclusión en español relevantes al PICO."
    )

    # Use a direct call without extended thinking for structured JSON output
    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="Eres un experto en revisiones sistemáticas. Responde ÚNICAMENTE con JSON válido, sin texto adicional.",
        messages=[{"role": "user", "content": user}],
    )
    result_text = message.content[0].text.strip()

    match = re.search(r'\{.*\}', result_text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"La IA no devolvió JSON válido: {result_text[:200]}")
