"""PROSPERO registration form answers, written in English from the review's research question."""
import hashlib
import json

from .ai_generator import _get_client, eligibility_block
from .prisma import search_summary

PLACEHOLDER = "[To be completed by the review team]"

# (key, PROSPERO field label, guidance for the writer)
PROSPERO_FIELDS = [
    ("review_title", "Review title",
     "Concise English title stating intervention, comparator, population and outcome; end with "
     "'a systematic review and meta-analysis' when a meta-analysis is planned."),
    ("original_language_title", "Original language title",
     "The review title as written by the authors in its original language, verbatim; "
     "'Not applicable' if it is already in English."),
    ("condition", "Condition or domain being studied",
     "Brief description of the condition, its burden and why it matters."),
    ("review_question", "Review question",
     "The primary question in PICO form, plus secondary questions for the additional outcomes."),
    ("searches", "Searches",
     "Databases, registers and other sources, date limits, language restrictions and any filters, "
     "using only the searches and restrictions stated by the authors."),
    ("participants", "Participants/population",
     "'Inclusion:' and 'Exclusion:' statements for the population."),
    ("intervention", "Intervention(s), exposure(s)", "Interventions eligible for inclusion."),
    ("comparator", "Comparator(s)/control", "Eligible comparators."),
    ("study_types", "Types of study to be included",
     "Eligible study designs and designs that will be excluded."),
    ("context", "Context", "Setting (e.g., emergency department) and other contextual restrictions."),
    ("main_outcomes", "Main outcome(s)",
     "Primary outcome(s), timing of measurement and 'Measures of effect' (e.g., odds ratio)."),
    ("additional_outcomes", "Additional outcome(s)",
     "Secondary outcomes with their measures of effect, or 'None'."),
    ("data_extraction", "Data extraction (selection and coding)",
     "How records are screened and selected, how many reviewers, how disagreements are resolved, "
     "and which data items are extracted."),
    ("risk_of_bias", "Risk of bias (quality) assessment",
     "Tools by study design (e.g., RoB 2 for randomised trials, ROBINS-I for non-randomised studies) "
     "and how assessments will be used; GRADE for certainty of evidence."),
    ("data_synthesis", "Strategy for data synthesis",
     "Effect measures, statistical model, heterogeneity assessment (I², Cochran Q), publication bias "
     "assessment, and narrative synthesis when pooling is not appropriate."),
    ("subgroups", "Analysis of subgroups or subsets",
     "Planned subgroup and sensitivity analyses (e.g., by study design), or 'None planned'."),
    ("review_type", "Type and method of review",
     "e.g., 'Intervention, Meta-analysis, Systematic review' and the health area."),
    ("language", "Language", "Language(s) of the review report and of eligible publications."),
    ("country", "Country", "Country of the review team, if stated; otherwise the placeholder."),
    ("anticipated_dates", "Anticipated or actual start and completion dates",
     "Use the placeholder unless dates are stated."),
    ("stage_of_review", "Stage of review at time of this submission",
     "State which stages have started or been completed (preliminary searches, piloting, formal "
     "screening, data extraction, risk of bias assessment, data analysis) based on the progress facts."),
    ("review_team", "Named contact and review team members", "Use the placeholder."),
    ("funding", "Funding sources/sponsors", "Use the placeholder unless funding is stated."),
    ("conflicts", "Conflicts of interest", "Use the placeholder unless stated."),
    ("dissemination", "Dissemination plans",
     "Planned publication in a peer-reviewed journal and conference presentation."),
    ("keywords", "Keywords", "5–8 English keywords separated by semicolons, MeSH terms where possible."),
]
FIELD_KEYS = [k for k, _, _ in PROSPERO_FIELDS]
FIELD_LABELS = {k: label for k, label, _ in PROSPERO_FIELDS}

_QUESTION_FIELDS = [
    "title", "population", "intervention", "comparison", "outcomes", "study_design",
    "types_of_studies", "types_of_participants", "types_of_interventions", "types_of_outcomes",
    "primary_outcomes", "secondary_outcomes", "inclusion_criteria", "exclusion_criteria",
    "subgroup_study_types", "effect_measure", "model_type",
]

_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in FIELD_KEYS},
    "required": FIELD_KEYS,
    "additionalProperties": False,
}


def question_hash(review) -> str:
    """Fingerprint of the research question; a change means the answers are outdated."""
    payload = {f: " ".join(str(getattr(review, f, None) or "").split()) for f in _QUESTION_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def has_question(review) -> bool:
    return bool((review.title or "").strip() and (review.population or review.intervention
                                                  or review.inclusion_criteria))


def load_answers(review) -> dict:
    try:
        data = json.loads(review.prospero_json or "{}")
    except ValueError:
        return {}
    return {k: data.get(k, "") for k in FIELD_KEYS} if data else {}


def _progress_facts(studies, searches, has_analysis: bool) -> str:
    screened = sum(1 for s in studies if s.screening_reviewed)
    included = sum(1 for s in studies if s.screening_reviewed and s.included)
    extracted = sum(1 for s in studies if s.included and (s.events_intervention is not None
                                                          or s.mean_intervention is not None
                                                          or s.effect_size is not None))
    rob = sum(1 for s in studies if s.included and s.rob_overall)
    return (
        f"- Searches registered: {len(searches)}\n"
        f"- Records imported: {len(studies)}; screened: {screened}; included: {included}\n"
        f"- Included studies with extracted quantitative data: {extracted}\n"
        f"- Included studies with risk of bias assessed: {rob}\n"
        f"- Meta-analysis run: {'yes' if has_analysis else 'no'}"
    )


def generate_prospero(review, studies, searches, has_analysis: bool) -> dict:
    review_dict = {c.name: getattr(review, c.name) for c in review.__table__.columns}
    guidance = "\n".join(f"- {k} ({label}): {hint}" for k, label, hint in PROSPERO_FIELDS)
    user = (
        "Write the answers for the PROSPERO (International prospective register of systematic "
        "reviews) registration form of this review.\n\n"
        f"REVIEW TITLE (as written by the authors): {review.title}\n\n"
        "RESEARCH QUESTION AND ELIGIBILITY CRITERIA DEFINED BY THE AUTHORS (may be in Spanish):\n"
        f"{eligibility_block(review_dict)}\n\n"
        f"Effect measure: {review.effect_measure or 'not stated'}; statistical model: "
        f"{'random effects' if (review.model_type or 'random') == 'random' else 'fixed effect'}\n"
        f"Search strategy notes: {review.search_strategy or 'not stated'}\n"
        f"Searches registered:\n{search_summary(searches)}\n\n"
        f"PROGRESS OF THE REVIEW:\n{_progress_facts(studies, searches, has_analysis)}\n\n"
        f"FIELDS TO COMPLETE:\n{guidance}\n\n"
        "Rules:\n"
        "1. Write every answer in formal academic ENGLISH, even though the source text is in "
        "Spanish (the only exception is 'original_language_title', copied verbatim).\n"
        "2. Be faithful to the authors' question and criteria: translate and organise them, do not "
        "add eligibility criteria, outcomes, databases or analyses they did not define, except the "
        "standard methodological statements PROSPERO expects (screening by two independent "
        "reviewers, risk of bias tools, GRADE, heterogeneity and publication bias assessment).\n"
        f"3. When the information does not exist (names, dates, funding, country), write exactly "
        f"'{PLACEHOLDER}'.\n"
        "4. Plain text only, no Markdown. Use short paragraphs; 'Inclusion:' / 'Exclusion:' labels "
        "where useful."
    )
    client = _get_client()
    with client.messages.stream(
        model="claude-opus-5",
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": _SCHEMA}},
        system=(
            "You are an expert systematic reviewer who prepares PROSPERO registrations following "
            "Cochrane and PRISMA-P standards. You write precise, register-ready English."
        ),
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise RuntimeError("El modelo declinó generar el registro PROSPERO.")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("La respuesta quedó truncada; reintenta.")
    text = next(b.text for b in message.content if b.type == "text")
    data = json.loads(text)
    return {k: (data.get(k) or "").strip() for k in FIELD_KEYS}
