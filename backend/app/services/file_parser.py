"""
Parse uploaded Excel / CSV files into a list of study dicts
compatible with the Study model fields.
"""
import io
import math
from typing import Any

import pandas as pd


# Column aliases: user-visible name (normalised) → internal field name
_COLUMN_MAP = {
    # ── Bibliographic (user-requested headers) ──────────────────────────────
    "publication_type":       "publication_type",
    "publication type":       "publication_type",
    "pub_type":               "publication_type",
    "type":                   "publication_type",

    "title":                  "title",

    "volume":                 "volume",
    "vol":                    "volume",

    "number":                 "issue",
    "issue":                  "issue",
    "num":                    "issue",

    "doi":                    "doi",

    "abstract":               "abstract_text",
    "abstract_text":          "abstract_text",
    "resumen":                "abstract_text",

    "year":                   "year",
    "año":                    "year",

    "journal":                "journal",
    "journals":               "journal",
    "revista":                "journal",
    "source":                 "journal",

    "first_page":             "first_page",
    "first page":             "first_page",
    "page_start":             "first_page",
    "start_page":             "first_page",

    "last_page":              "last_page",
    "last page":              "last_page",
    "page_end":               "last_page",
    "end_page":               "last_page",

    "insights":               "insights",

    "results":                "study_results",
    "study_results":          "study_results",
    "resultados":             "study_results",

    "methods_used":           "methods_used",
    "methods use":            "methods_used",
    "methods":                "methods_used",
    "method":                 "methods_used",
    "methodology":            "methods_used",
    "metodo":                 "methods_used",

    "objective":              "objective_text",
    "objetive":               "objective_text",
    "objetivo":               "objective_text",
    "objectives":             "objective_text",
    "objective_text":         "objective_text",

    "findings":               "findings",
    "hallazgos":              "findings",

    "practical_implications": "practical_implications",
    "practical implications": "practical_implications",
    "implications":           "practical_implications",
    "implicaciones":          "practical_implications",

    "research_gap":           "research_gap",
    "research gap":           "research_gap",
    "gap":                    "research_gap",
    "brecha":                 "research_gap",

    "authors":                "authors",
    "author":                 "authors",
    "autores":                "authors",
    "autor":                  "authors",

    "url":                    "url",
    "link":                   "url",
    "enlace":                 "url",

    # ── Identification ───────────────────────────────────────────────────────
    "study_label":            "study_label",
    "study label":            "study_label",

    "country":                "country",
    "pais":                   "country",

    "setting":                "setting",

    "study_design":           "study_design",
    "design":                 "study_design",
    "diseño":                 "study_design",

    "follow_up":              "follow_up",
    "follow up":              "follow_up",
    "follow_up_weeks":        "follow_up",

    # ── Participants ─────────────────────────────────────────────────────────
    "sample_size":            "sample_size",
    "sample size":            "sample_size",

    "mean_age":               "age_mean",
    "age_mean":               "age_mean",
    "age":                    "age_mean",

    "percent_female":         "percent_female",
    "female":                 "percent_female",

    "inclusion_criteria":     "inclusion_criteria",

    # ── Binary outcomes – intervention ───────────────────────────────────────
    "events_intervention":    "events_intervention",
    "events_i":               "events_intervention",
    "n_events_i":             "events_intervention",

    "total_intervention":     "total_intervention",
    "total_i":                "total_intervention",
    "n_i":                    "total_intervention",

    # ── Binary outcomes – control ────────────────────────────────────────────
    "events_control":         "events_control",
    "events_c":               "events_control",
    "n_events_c":             "events_control",

    "total_control":          "total_control",
    "total_c":                "total_control",
    "n_c":                    "total_control",

    # ── Continuous outcomes – intervention ───────────────────────────────────
    "mean_intervention":      "mean_intervention",
    "mean_i":                 "mean_intervention",

    "sd_intervention":        "sd_intervention",
    "sd_i":                   "sd_intervention",

    "n_intervention":         "n_intervention",
    "n_cont_i":               "n_intervention",

    # ── Continuous outcomes – control ────────────────────────────────────────
    "mean_control":           "mean_control",
    "mean_c":                 "mean_control",

    "sd_control":             "sd_control",
    "sd_c":                   "sd_control",

    "n_control":              "n_control",
    "n_cont_c":               "n_control",

    # ── Pre-calculated effect sizes ──────────────────────────────────────────
    "effect_size":            "effect_size",
    "es":                     "effect_size",

    "effect_size_lower":      "effect_size_lower",
    "ci_lower":               "effect_size_lower",

    "effect_size_upper":      "effect_size_upper",
    "ci_upper":               "effect_size_upper",

    # ── Risk of Bias 2 ───────────────────────────────────────────────────────
    "rob_random_sequence":        "rob_random_sequence",
    "rob_allocation_concealment": "rob_allocation_concealment",
    "rob_blinding_participants":  "rob_blinding_participants",
    "rob_blinding_outcome":       "rob_blinding_outcome",
    "rob_incomplete_data":        "rob_incomplete_data",
    "rob_selective_reporting":    "rob_selective_reporting",
    "rob_other":                  "rob_other",
    "rob_overall":                "rob_overall",

    # ── Clinical meta-analysis fields ────────────────────────────────────────
    "patient_population":     "patient_population",
    "patient population":     "patient_population",
    "poblacion":              "patient_population",
    "poblacion_pacientes":    "patient_population",
    "population":             "patient_population",

    "group_comparison":       "group_comparison",
    "group comparison":       "group_comparison",
    "comparacion_grupos":     "group_comparison",
    "comparacion":            "group_comparison",
    "grupos":                 "group_comparison",

    "survival_outcomes":      "survival_outcomes",
    "survival outcomes":      "survival_outcomes",
    "supervivencia":          "survival_outcomes",
    "sobrevida":              "survival_outcomes",

    "mortality_factors":      "mortality_factors",
    "mortality factors":      "mortality_factors",
    "mortalidad":             "mortality_factors",
    "factores_mortalidad":    "mortality_factors",

    "key_findings":           "key_findings",
    "key findings":           "key_findings",
    "hallazgos_clave":        "key_findings",
    "principales_hallazgos":  "key_findings",

    "reasoning_study_design": "reasoning_study_design",
    "reasoning study design": "reasoning_study_design",
    "razonamiento_diseño":    "reasoning_study_design",
    "justificacion_diseño":   "reasoning_study_design",
    "razonamiento":           "reasoning_study_design",

    "source_database":        "source_database",
    "source database":        "source_database",
    "base_datos":             "source_database",
    "database":               "source_database",
    "fuente":                 "source_database",

    # ── Notes ────────────────────────────────────────────────────────────────
    "notes":                  "notes",
    "notas":                  "notes",

    # ── ELICIT (elicit.com) export columns ───────────────────────────────────
    "number_of_participants":       "sample_size",
    "number of participants":       "sample_size",
    "n_participants":               "sample_size",
    "participants":                 "sample_size",
    "total_n":                      "sample_size",
    "sample_n":                     "sample_size",

    "journal/conference":           "journal",
    "conference/journal":           "journal",
    "conference":                   "journal",
    "venue":                        "journal",
    "published_in":                 "journal",

    "first_author":                 "authors",
    "first author":                 "authors",
    "lead_author":                  "authors",

    "outcome_measured":             "study_results",
    "outcome measured":             "study_results",
    "outcome":                      "study_results",
    "outcomes":                     "study_results",
    "primary_outcome":              "objective_text",
    "primary outcome":              "objective_text",
    "primary_outcomes":             "objective_text",
    "primary outcomes":             "objective_text",
    "secondary_outcome":            "study_results",
    "secondary outcome":            "study_results",

    "background":                   "objective_text",
    "introduction":                 "objective_text",

    "conclusion":                   "findings",
    "conclusions":                  "findings",
    "authors'_conclusions":         "findings",
    "authors' conclusions":         "findings",
    "author_conclusions":           "findings",

    "intervention_group":           "group_comparison",
    "intervention group":           "group_comparison",
    "intervention":                 "group_comparison",
    "control_group":                "group_comparison",
    "control group":                "group_comparison",
    "treatment":                    "group_comparison",
    "comparison":                   "group_comparison",

    "effect_sizes":                 "effect_size",
    "effect sizes":                 "effect_size",
    "effect size (95% ci)":         "effect_size",
    "estimate":                     "effect_size",

    "study_type":                   "study_design",
    "study type":                   "study_design",
    "research_design":              "study_design",
    "research design":              "study_design",
    "trial_design":                 "study_design",
    "trial design":                 "study_design",

    "city":                         "setting",
    "location":                     "setting",

    "funding":                      "notes",
    "funding_source":               "notes",
    "conflicts_of_interest":        "notes",
    "citation":                     "notes",
    "cite_key":                     "study_label",
    "cite key":                     "study_label",
    "citation_key":                 "study_label",
    "bibtex_key":                   "study_label",

    "pages":                        "first_page",

    # ── SciSpace (scispace.com / typeset.io) export columns ──────────────────
    "paper_type":                   "publication_type",
    "paper type":                   "publication_type",
    "document_type":                "publication_type",
    "document type":                "publication_type",

    "publication_date":             "year",
    "publication date":             "year",
    "pub_date":                     "year",
    "date":                         "year",
    "published":                    "year",

    "research_topics":              "key_findings",
    "research topics":              "key_findings",
    "topics":                       "key_findings",
    "keywords":                     "key_findings",
    "keyword":                      "key_findings",

    "tldr":                         "findings",
    "tl;dr":                        "findings",
    "summary":                      "findings",
    "resumen_ejecutivo":            "findings",

    "citations":                    "notes",
    "cited_by":                     "notes",
    "num_citations":                "notes",
    "citation_count":               "notes",

    "arxiv_id":                     "doi",
    "pmid":                         "doi",
    "pubmed_id":                    "doi",
    "semantic_scholar_id":          "notes",

    "open_access":                  "notes",
    "pdf_url":                      "url",
    "pdf url":                      "url",
    "semantic_url":                 "url",
}

_INT_FIELDS = {
    "year", "total_intervention", "total_control",
    "events_intervention", "events_control",
    "n_intervention", "n_control", "sample_size",
}
_FLOAT_FIELDS = {
    "age_mean", "percent_female",
    "mean_intervention", "sd_intervention",
    "mean_control", "sd_control",
    "effect_size", "effect_size_lower", "effect_size_upper",
}
_ROB_FIELDS = {
    "rob_random_sequence", "rob_allocation_concealment",
    "rob_blinding_participants", "rob_blinding_outcome",
    "rob_incomplete_data", "rob_selective_reporting",
    "rob_other", "rob_overall",
}
_ROB_VALUES = {"low", "some_concerns", "high", ""}


def _normalise_col(col: str) -> str:
    return col.strip().lower().replace(" ", "_").replace("-", "_")


def _coerce(value: Any, field: str) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "iloc"):
        value = value.iloc[0]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if field in _INT_FIELDS:
        try:
            # Handle date strings like "2020-01-01" for year field
            s = str(value).strip()
            if field == "year" and len(s) >= 4 and s[:4].isdigit():
                return int(s[:4])
            return int(float(value))
        except (ValueError, TypeError):
            return None
    if field in _FLOAT_FIELDS:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    if field in _ROB_FIELDS:
        s = str(value).strip().lower().replace(" ", "_")
        return s if s in _ROB_VALUES else None
    return str(value).strip() if str(value).strip() else None


def parse_file(content: bytes, filename: str) -> list[dict]:
    """
    Parse Excel or CSV bytes into a list of study dicts.
    Raises ValueError with a human-readable message on failure.
    """
    fname = filename.lower()
    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
        elif fname.endswith((".xlsx", ".xls")):
            engine = "openpyxl" if fname.endswith(".xlsx") else "xlrd"
            df = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False,
                               engine=engine)
        else:
            raise ValueError(f"Tipo de archivo no soportado: '{filename}'. Use .csv, .xlsx o .xls")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo '{filename}': {exc}") from exc

    if df.empty:
        raise ValueError("El archivo no contiene filas de datos.")

    # Normalise column names and map to internal field names
    # Build rename map; if two user-columns map to the same target, keep first
    rename_map: dict[str, str] = {}
    seen_targets: set[str] = set()
    for col in df.columns:
        norm = _normalise_col(str(col))
        if norm in _COLUMN_MAP:
            target = _COLUMN_MAP[norm]
            if target not in seen_targets:
                rename_map[col] = target
                seen_targets.add(target)
    df.rename(columns=rename_map, inplace=True)

    # Drop remaining duplicate column names (keep first)
    df = df.loc[:, ~df.columns.duplicated(keep="first")]

    known_fields = [f for f in set(_COLUMN_MAP.values()) if f in df.columns]

    studies = []
    for _, row in df.iterrows():
        study: dict = {}
        for field in known_fields:
            raw = row[field]
            if raw == "" or raw is None:
                continue
            coerced = _coerce(raw, field)
            if coerced is not None:
                study[field] = coerced

        if not study:
            continue

        # Auto-build study_label if missing
        if not study.get("study_label"):
            authors = study.get("authors", "")
            year = study.get("year", "")
            title = study.get("title", "")
            if authors or year:
                study["study_label"] = f"{authors} {year}".strip()
            elif title:
                # Fallback: first 60 chars of title
                study["study_label"] = title[:60].rstrip()

        studies.append(study)

    if not studies:
        raise ValueError("No se encontraron filas válidas en el archivo.")

    return studies
