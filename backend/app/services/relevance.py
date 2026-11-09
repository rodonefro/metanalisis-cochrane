"""
Relevance ranking of records against the review's eligibility criteria, without AI per record.

One cheap AI call (cached on the review until its criteria change) turns the criteria into
concept groups of search terms in English and Spanish; every record is then scored locally
(TF-IDF over title, keywords and abstract, rewarding records that match more concepts).
The AI screener reads records in this order, so the records most likely to be eligible are
screened first and the long tail of clearly unrelated search results costs no credits.
"""
import hashlib
import json
import math
import re
import unicodedata

from .ai_generator import eligibility_block, _get_client

_TERMS_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "terms": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "terms"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["concepts"],
    "additionalProperties": False,
}

_STOPWORDS = set("""
a al and are as at be by con de del el en for from in is la las los of on or para por que the to
un una y with without sin study studies estudio estudios patients pacientes paciente patient
""".split())


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _criteria_key(review: dict) -> str:
    return hashlib.sha256(eligibility_block(review).encode()).hexdigest()


def _fallback_concepts(review: dict) -> list[list[str]]:
    """Without the AI terms: each PICO field is a concept made of its own words."""
    concepts = []
    for field in ("population", "intervention", "outcomes"):
        words = [w for w in _norm(review.get(field) or "").split() if len(w) >= 4 and w not in _STOPWORDS]
        if words:
            concepts.append(list(dict.fromkeys(words)))
    return concepts


def generate_concepts(review: dict) -> list[list[str]]:
    """Concept groups of search terms (English + Spanish) for the review's criteria."""
    client = _get_client()
    msg = client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=8000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _TERMS_SCHEMA}},
        messages=[{"role": "user", "content": (
            "Criterios de elegibilidad de una revisión sistemática:\n\n"
            f"TÍTULO: {review.get('title') or ''}\n{eligibility_block(review)}\n\n"
            "Devuelve los conceptos que un registro debe mencionar para ser candidato (población, "
            "intervención o exposición, desenlace y cualquier otro concepto obligatorio; 2 a 5 "
            "conceptos). Para cada concepto da de 5 a 25 términos de búsqueda en INGLÉS y en ESPAÑOL "
            "tal como aparecerían en títulos y resúmenes: sinónimos, términos MeSH, abreviaturas y "
            "variantes. Cada término de 1 a 4 palabras, en minúsculas. No incluyas palabras genéricas "
            "como study, patients, estudio o pacientes, ni términos de diseño de estudio."
        )}],
    )
    if msg.stop_reason == "refusal":
        raise RuntimeError("El modelo declinó generar los términos de relevancia.")
    text = next(b.text for b in msg.content if b.type == "text")
    concepts = []
    for c in json.loads(text)["concepts"]:
        terms = [t for t in dict.fromkeys(_norm(t) for t in c["terms"]) if t and t not in _STOPWORDS]
        if terms:
            concepts.append(terms)
    return concepts


def concepts_for(review_obj) -> list[list[str]]:
    """The review's concept groups, generated once and stored until the criteria change."""
    review = {c.name: getattr(review_obj, c.name) for c in review_obj.__table__.columns}
    key = _criteria_key(review)
    try:
        stored = json.loads(review_obj.relevance_terms or "{}")
    except ValueError:
        stored = {}
    if stored.get("key") == key and stored.get("concepts"):
        return stored["concepts"]
    try:
        concepts = generate_concepts(review)
    except Exception:
        return _fallback_concepts(review)
    if concepts:
        review_obj.relevance_terms = json.dumps({"key": key, "concepts": concepts}, ensure_ascii=False)
    return concepts or _fallback_concepts(review)


_TEXT_FIELDS = ("keywords", "abstract_text", "objective_text", "patient_population", "methods_used")


def rank_by_relevance(studies: list, concepts: list[list[str]]) -> list[tuple]:
    """[(study, score)] from most to least relevant. Title matches weigh triple."""
    if not studies:
        return []
    titles = [f" {_norm(s.title or s.study_label or '')} " for s in studies]
    bodies = [f" {_norm(' '.join(str(getattr(s, f, '') or '') for f in _TEXT_FIELDS))} " for s in studies]
    n = len(studies)
    scores = [0.0] * n
    matched = [0] * n
    for group in concepts:
        group_score = [0.0] * n
        for term in group:
            needle = f" {term}"
            pattern = re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"[a-z0-9]{0,3}(?![a-z0-9])")
            tfs = {}
            for i in range(n):
                if needle not in titles[i] and needle not in bodies[i]:
                    continue
                tf = 3 * len(pattern.findall(titles[i])) + len(pattern.findall(bodies[i]))
                if tf:
                    tfs[i] = tf
            if not tfs:
                continue
            idf = math.log((n + 1) / (len(tfs) + 0.5))
            for i, tf in tfs.items():
                group_score[i] += idf * (1 + math.log(tf))
        for i in range(n):
            if group_score[i] > 0:
                scores[i] += group_score[i]
                matched[i] += 1
    groups = max(1, len(concepts))
    ranked = [(s, scores[i] * (matched[i] / groups) ** 2) for i, s in enumerate(studies)]
    ranked.sort(key=lambda p: (-p[1], p[0].id))
    return ranked
