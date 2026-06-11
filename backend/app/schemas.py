from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ── Study ──────────────────────────────────────────────────────────────────────

class StudyBase(BaseModel):
    study_label: Optional[str] = None
    study_id: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    title: Optional[str] = None
    journal: Optional[str] = None
    country: Optional[str] = None
    study_design: Optional[str] = None
    sample_size: Optional[int] = None
    follow_up: Optional[str] = None
    setting: Optional[str] = None
    age_mean: Optional[float] = None
    age_sd: Optional[float] = None
    percent_female: Optional[float] = None
    inclusion_criteria: Optional[str] = None
    events_intervention: Optional[int] = None
    total_intervention: Optional[int] = None
    events_control: Optional[int] = None
    total_control: Optional[int] = None
    mean_intervention: Optional[float] = None
    sd_intervention: Optional[float] = None
    n_intervention: Optional[int] = None
    mean_control: Optional[float] = None
    sd_control: Optional[float] = None
    n_control: Optional[int] = None
    effect_size: Optional[float] = None
    effect_size_lower: Optional[float] = None
    effect_size_upper: Optional[float] = None
    effect_size_type: Optional[str] = None
    rob_random_sequence: Optional[str] = None
    rob_allocation_concealment: Optional[str] = None
    rob_blinding_participants: Optional[str] = None
    rob_blinding_outcome: Optional[str] = None
    rob_incomplete_data: Optional[str] = None
    rob_selective_reporting: Optional[str] = None
    rob_other: Optional[str] = None
    rob_overall: Optional[str] = None
    rob_notes: Optional[str] = None
    # Bibliographic metadata
    publication_type: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    doi: Optional[str] = None
    abstract_text: Optional[str] = None
    first_page: Optional[str] = None
    last_page: Optional[str] = None
    url: Optional[str] = None
    # Data extraction
    objective_text: Optional[str] = None
    methods_used: Optional[str] = None
    study_results: Optional[str] = None
    findings: Optional[str] = None
    insights: Optional[str] = None
    practical_implications: Optional[str] = None
    research_gap: Optional[str] = None
    # Clinical meta-analysis fields
    patient_population: Optional[str] = None
    group_comparison: Optional[str] = None
    survival_outcomes: Optional[str] = None
    mortality_factors: Optional[str] = None
    key_findings: Optional[str] = None
    reasoning_study_design: Optional[str] = None
    source_database: Optional[str] = None
    included: Optional[bool] = True
    exclusion_reason: Optional[str] = None
    notes: Optional[str] = None


class StudyCreate(StudyBase):
    pass


class StudyUpdate(StudyBase):
    pass


class StudyOut(StudyBase):
    id: int
    review_id: int

    class Config:
        from_attributes = True


# ── Review ─────────────────────────────────────────────────────────────────────

class ReviewBase(BaseModel):
    title: str
    prospero_id: Optional[str] = None
    status: Optional[str] = "draft"
    population: Optional[str] = None
    intervention: Optional[str] = None
    comparison: Optional[str] = None
    outcomes: Optional[str] = None
    study_design: Optional[str] = None
    abstract: Optional[str] = None
    background_condition: Optional[str] = None
    background_intervention: Optional[str] = None
    background_mechanism: Optional[str] = None
    background_importance: Optional[str] = None
    objectives: Optional[str] = None
    inclusion_criteria: Optional[str] = None
    exclusion_criteria: Optional[str] = None
    types_of_studies: Optional[str] = None
    types_of_participants: Optional[str] = None
    types_of_interventions: Optional[str] = None
    types_of_outcomes: Optional[str] = None
    primary_outcomes: Optional[str] = None
    secondary_outcomes: Optional[str] = None
    search_strategy: Optional[str] = None
    study_selection_method: Optional[str] = None
    data_extraction_method: Optional[str] = None
    risk_of_bias_method: Optional[str] = None
    effect_measures: Optional[str] = None
    heterogeneity_method: Optional[str] = None
    description_of_studies: Optional[str] = None
    risk_of_bias_results: Optional[str] = None
    intervention_effects: Optional[str] = None
    discussion: Optional[str] = None
    authors_conclusions: Optional[str] = None
    background_text: Optional[str] = None
    methods_text: Optional[str] = None
    results_text: Optional[str] = None
    references: Optional[str] = None
    plot_interpretation: Optional[str] = None
    citation_style: Optional[str] = "vancouver"
    effect_measure: Optional[str] = "OR"
    model_type: Optional[str] = "random"
    # PRISMA 2020
    prisma_db_names: Optional[str] = None
    prisma_other_sources: Optional[int] = None
    prisma_duplicates_removed: Optional[int] = None
    prisma_other_removed: Optional[int] = None
    prisma_screened: Optional[int] = None
    prisma_excluded_screening: Optional[int] = None
    prisma_sought: Optional[int] = None
    prisma_not_retrieved: Optional[int] = None
    prisma_assessed: Optional[int] = None
    prisma_excluded_eligibility: Optional[int] = None
    prisma_exclusion_reasons: Optional[str] = None
    prisma_included: Optional[int] = None
    prisma_reports_included: Optional[int] = None


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(ReviewBase):
    title: Optional[str] = None


class ReviewOut(ReviewBase):
    id: int
    created_at: datetime
    updated_at: datetime
    studies: List[StudyOut] = []

    class Config:
        from_attributes = True


class ReviewSummary(BaseModel):
    id: int
    title: str
    prospero_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    study_count: int = 0

    class Config:
        from_attributes = True


# ── Analysis ───────────────────────────────────────────────────────────────────

class AnalysisCreate(BaseModel):
    name: str
    outcome_label: Optional[str] = None
    effect_measure: str = "OR"
    model_type: str = "random"
    study_ids: Optional[List[int]] = None


class AnalysisOut(BaseModel):
    id: int
    review_id: int
    name: Optional[str]
    outcome_label: Optional[str]
    effect_measure: Optional[str]
    model_type: Optional[str]
    created_at: datetime
    results_json: Optional[str] = None
    forest_plot_b64: Optional[str] = None
    funnel_plot_b64: Optional[str] = None
    rob_plot_b64: Optional[str] = None

    class Config:
        from_attributes = True


# ── AI Generation ──────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    include_meta_results: bool = True


class GenerateResponse(BaseModel):
    section: str
    text: str


# ── Search Databases ───────────────────────────────────────────────────────────

class SearchDatabaseCreate(BaseModel):
    database_name: str
    search_string: Optional[str] = None
    search_date: Optional[str] = None
    results_count: Optional[int] = None


class SearchDatabaseOut(SearchDatabaseCreate):
    id: int
    review_id: int

    class Config:
        from_attributes = True
