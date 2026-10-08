"""
Exact PRISMA 2020 flow computed from the review's own records.

Nothing here is estimated: every box is a count over the studies table and the
search log (SearchDatabase), and each record lands in exactly one terminal box,
so the arithmetic always closes:

    identified (databases + other sources)
      − duplicates − other removed           = screened
    screened  − excluded at title/abstract   = sought for retrieval
    sought    − not retrieved                = assessed for eligibility
    assessed  − excluded at full text        = included
"""
import json
from collections import Counter, OrderedDict

from ..models import Review, Study, SearchDatabase, Analysis
from .references import effective_decision, split_sources

UNSPECIFIED_SOURCE = "Fuente no especificada"


def classify(s: Study) -> str:
    """Terminal PRISMA box for one record."""
    if s.full_text_status == "not_retrieved":
        return "not_retrieved"
    decision = effective_decision(s)
    if decision is None:
        # Never screened: the app's default keeps it in the analysis (included=True).
        return "included" if s.included is not False else "excluded_screening"
    if decision == "include":
        return "included"
    if decision == "maybe" or s.screening_stage == "full_text":
        return "excluded_eligibility"
    return "excluded_screening"


def _reason(s: Study) -> str:
    if effective_decision(s) == "maybe":
        return "Sin decisión final tras texto completo"
    r = (s.exclusion_reason or "").strip()
    if not r:
        return "Motivo no registrado"
    return r.split(":", 1)[0].strip()[:80]


def compute_prisma(review: Review, studies: list[Study], searches: list[SearchDatabase],
                   latest: Analysis | None = None) -> dict:
    warnings: list[str] = []

    # ── Identification ────────────────────────────────────────────────────────
    # Records per source, counted from the records themselves (a record merged
    # from two databases counts once in each).
    per_source: Counter = Counter()
    for s in studies:
        srcs = split_sources(s.all_sources) or split_sources(s.source_database)
        for src in srcs or [UNSPECIFIED_SOURCE]:
            per_source[src] += 1

    search_by_name = {sd.database_name.strip().lower(): sd for sd in searches}
    db_counts: "OrderedDict[str, int]" = OrderedDict()
    other_counts: "OrderedDict[str, int]" = OrderedDict()

    for sd in searches:
        imported_unique = per_source.get(sd.database_name, 0)
        # The log keeps the raw number of records imported (duplicates included);
        # the number the database reported for the search wins when the author typed it.
        n = sd.results_count if sd.results_count is not None else (sd.records_imported or imported_unique)
        target = db_counts if (sd.source_type or "database") in ("database", "register") else other_counts
        target[sd.database_name] = n
        if sd.results_count is not None and sd.records_imported and sd.results_count != sd.records_imported:
            warnings.append(
                f"{sd.database_name}: la búsqueda reportó {sd.results_count} registros pero se importaron "
                f"{sd.records_imported}. El diagrama usa {sd.results_count}; la diferencia cuenta como "
                "registros no importados. Importa la exportación completa o corrige el número."
            )
        if not sd.search_date:
            warnings.append(f"{sd.database_name}: falta la fecha de búsqueda (requerida por PRISMA-S).")
        if not sd.search_string and target is db_counts:
            warnings.append(f"{sd.database_name}: falta la estrategia/cadena de búsqueda.")

    # Sources that appear on records but were never registered as a search.
    for src, n in per_source.items():
        if src.strip().lower() in search_by_name:
            continue
        if src == UNSPECIFIED_SOURCE:
            other_counts[src] = n
            warnings.append(
                f"{n} registro(s) no tienen base de datos de origen; se cuentan en 'otros métodos'. "
                "Asígnales la fuente en el Gestor de referencias."
            )
        else:
            db_counts[src] = n
            warnings.append(
                f"'{src}' aparece como fuente en {n} registro(s) pero no está en el registro de búsquedas: "
                "agrégala con su cadena y fecha."
            )

    identified_db = sum(db_counts.values())
    identified_other = sum(other_counts.values())
    identified = identified_db + identified_other

    # ── Screening ─────────────────────────────────────────────────────────────
    boxes = Counter(classify(s) for s in studies)
    screened = len(studies)
    other_removed = review.prisma_other_removed or 0
    duplicates = identified - other_removed - screened
    if duplicates < 0:
        warnings.append(
            f"Hay {screened} registros únicos pero solo {identified - other_removed} identificados en las "
            "búsquedas registradas: faltan búsquedas o sus conteos. Se muestran 0 duplicados."
        )
        duplicates = 0

    excluded_screening = boxes["excluded_screening"]
    sought = screened - excluded_screening
    not_retrieved = boxes["not_retrieved"]
    assessed = sought - not_retrieved
    excluded_eligibility = boxes["excluded_eligibility"]
    included = boxes["included"]

    reasons = Counter(_reason(s) for s in studies if classify(s) == "excluded_eligibility")

    pending = sum(1 for s in studies if effective_decision(s) is None)
    if pending:
        warnings.append(
            f"{pending} registro(s) aún no se han cribado y se cuentan como incluidos. "
            "Criba todos los registros antes de publicar el diagrama."
        )
    maybes = sum(1 for s in studies if effective_decision(s) == "maybe")
    if maybes:
        warnings.append(
            f"{maybes} registro(s) marcados 'Quizás' se cuentan como excluidos en texto completo hasta que "
            "tengan una decisión final."
        )
    if reasons.get("Motivo no registrado"):
        warnings.append(f"{reasons['Motivo no registrado']} exclusión(es) a texto completo no tienen motivo.")

    reports_included = included
    if latest and latest.results_json:
        try:
            reports_included = json.loads(latest.results_json).get("k", included)
        except (ValueError, TypeError):
            pass

    fields = {
        "prisma_db_names": ",".join(f"{n.replace(',', ' ')}={c}" for n, c in db_counts.items()) or None,
        "prisma_other_sources": identified_other if other_counts else None,
        "prisma_duplicates_removed": duplicates,
        "prisma_other_removed": other_removed,
        "prisma_screened": screened,
        "prisma_excluded_screening": excluded_screening,
        "prisma_sought": sought,
        "prisma_not_retrieved": not_retrieved,
        "prisma_assessed": assessed,
        "prisma_excluded_eligibility": excluded_eligibility,
        "prisma_exclusion_reasons": ",".join(
            f"{r.replace(',', ' ').replace('=', ' ')}={n}" for r, n in reasons.most_common()
        ) or None,
        "prisma_included": included,
        "prisma_reports_included": reports_included,
    }
    return {
        "fields": fields,
        "sources": [{"name": n, "n": c, "type": "database"} for n, c in db_counts.items()]
                   + [{"name": n, "n": c, "type": "other"} for n, c in other_counts.items()],
        "identified": identified,
        "warnings": warnings,
    }


def prisma_plot_kwargs(fields: dict) -> dict:
    return {k.removeprefix("prisma_"): v for k, v in fields.items()}


def sync_prisma(db, review: Review) -> dict:
    """Recompute the PRISMA flow, persist it on the review, and return the full result."""
    studies = db.query(Study).filter(Study.review_id == review.id).all()
    searches = (db.query(SearchDatabase).filter(SearchDatabase.review_id == review.id)
                .order_by(SearchDatabase.id).all())
    latest = (db.query(Analysis).filter(Analysis.review_id == review.id)
              .order_by(Analysis.created_at.desc()).first())
    result = compute_prisma(review, studies, searches, latest)
    for k, v in result["fields"].items():
        setattr(review, k, v)
    db.commit()
    return result


def search_summary(searches: list[SearchDatabase]) -> str:
    """Plain-text list of the searches actually run, for the AI text generators."""
    if not searches:
        return "No se registraron búsquedas en bases de datos."
    lines = []
    for sd in searches:
        kind = {"register": "registro", "other": "otro método"}.get(sd.source_type or "", "base de datos")
        n = sd.results_count if sd.results_count is not None else sd.records_imported
        line = f"- {sd.database_name} ({kind}); fecha: {sd.search_date or 'no registrada'}; registros: {n}"
        if sd.search_string:
            line += f"; estrategia: {sd.search_string}"
        lines.append(line)
    return "\n".join(lines)
