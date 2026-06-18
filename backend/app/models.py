from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    prospero_id = Column(String(100), nullable=True)
    status = Column(String(50), default="draft")  # draft, in_progress, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # PICO
    population = Column(Text, nullable=True)
    intervention = Column(Text, nullable=True)
    comparison = Column(Text, nullable=True)
    outcomes = Column(Text, nullable=True)
    study_design = Column(Text, nullable=True)

    # Sections (stored as text/markdown)
    abstract = Column(Text, nullable=True)
    background_condition = Column(Text, nullable=True)
    background_intervention = Column(Text, nullable=True)
    background_mechanism = Column(Text, nullable=True)
    background_importance = Column(Text, nullable=True)
    objectives = Column(Text, nullable=True)

    # Methods
    inclusion_criteria = Column(Text, nullable=True)
    exclusion_criteria = Column(Text, nullable=True)
    types_of_studies = Column(Text, nullable=True)
    subgroup_study_types = Column(Text, nullable=True)
    types_of_participants = Column(Text, nullable=True)
    types_of_interventions = Column(Text, nullable=True)
    types_of_outcomes = Column(Text, nullable=True)
    primary_outcomes = Column(Text, nullable=True)
    secondary_outcomes = Column(Text, nullable=True)
    search_strategy = Column(Text, nullable=True)  # PubMed, Scopus, etc.
    study_selection_method = Column(Text, nullable=True)
    data_extraction_method = Column(Text, nullable=True)
    risk_of_bias_method = Column(Text, nullable=True)
    effect_measures = Column(Text, nullable=True)  # OR, RR, MD, SMD
    heterogeneity_method = Column(Text, nullable=True)

    # Results
    description_of_studies = Column(Text, nullable=True)
    risk_of_bias_results = Column(Text, nullable=True)
    intervention_effects = Column(Text, nullable=True)

    # Discussion
    discussion = Column(Text, nullable=True)
    authors_conclusions = Column(Text, nullable=True)

    # Combined AI-generated section text (full sections)
    background_text = Column(Text, nullable=True)
    methods_text = Column(Text, nullable=True)
    results_text = Column(Text, nullable=True)
    references = Column(Text, nullable=True)
    plot_interpretation = Column(Text, nullable=True)

    # Bibliography style: vancouver, apa, nlm, harvard, cochrane
    citation_style = Column(String(20), default="vancouver")

    # Settings
    effect_measure = Column(String(20), default="OR")  # OR, RR, MD, SMD
    model_type = Column(String(20), default="random")  # fixed, random

    # PRISMA 2020 flowchart data
    prisma_db_names = Column(Text, nullable=True)          # "PubMed=45,Scopus=32,EMBASE=28"
    prisma_other_sources = Column(Integer, nullable=True)  # n from registers/other
    prisma_duplicates_removed = Column(Integer, nullable=True)
    prisma_other_removed = Column(Integer, nullable=True)  # ineligible before screening
    prisma_screened = Column(Integer, nullable=True)
    prisma_excluded_screening = Column(Integer, nullable=True)
    prisma_sought = Column(Integer, nullable=True)         # reports sought for retrieval
    prisma_not_retrieved = Column(Integer, nullable=True)
    prisma_assessed = Column(Integer, nullable=True)       # assessed for eligibility
    prisma_excluded_eligibility = Column(Integer, nullable=True)
    prisma_exclusion_reasons = Column(Text, nullable=True) # "Wrong population=5,No outcome=3"
    prisma_included = Column(Integer, nullable=True)
    prisma_reports_included = Column(Integer, nullable=True)

    studies = relationship("Study", back_populates="review", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="review", cascade="all, delete-orphan")


class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=False)

    # Identification
    study_label = Column(String(200), nullable=True)
    study_id = Column(String(100), nullable=True)
    authors = Column(String(500), nullable=True)
    year = Column(Integer, nullable=True)
    title = Column(String(1000), nullable=True)
    journal = Column(String(300), nullable=True)
    country = Column(String(100), nullable=True)

    # Study characteristics
    study_design = Column(String(100), nullable=True)
    sample_size = Column(Integer, nullable=True)
    follow_up = Column(String(100), nullable=True)
    setting = Column(String(200), nullable=True)

    # Participants
    age_mean = Column(Float, nullable=True)
    age_sd = Column(Float, nullable=True)
    percent_female = Column(Float, nullable=True)
    inclusion_criteria = Column(Text, nullable=True)

    # Binary outcome data (intervention group)
    events_intervention = Column(Integer, nullable=True)
    total_intervention = Column(Integer, nullable=True)

    # Binary outcome data (control group)
    events_control = Column(Integer, nullable=True)
    total_control = Column(Integer, nullable=True)

    # Continuous outcome data (intervention group)
    mean_intervention = Column(Float, nullable=True)
    sd_intervention = Column(Float, nullable=True)
    n_intervention = Column(Integer, nullable=True)

    # Continuous outcome data (control group)
    mean_control = Column(Float, nullable=True)
    sd_control = Column(Float, nullable=True)
    n_control = Column(Integer, nullable=True)

    # Pre-calculated effect size (if provided)
    effect_size = Column(Float, nullable=True)
    effect_size_lower = Column(Float, nullable=True)
    effect_size_upper = Column(Float, nullable=True)
    effect_size_type = Column(String(20), nullable=True)

    # Risk of Bias (Cochrane RoB 2)
    rob_random_sequence = Column(String(20), nullable=True)   # low, some_concerns, high
    rob_allocation_concealment = Column(String(20), nullable=True)
    rob_blinding_participants = Column(String(20), nullable=True)
    rob_blinding_outcome = Column(String(20), nullable=True)
    rob_incomplete_data = Column(String(20), nullable=True)
    rob_selective_reporting = Column(String(20), nullable=True)
    rob_other = Column(String(20), nullable=True)
    rob_overall = Column(String(20), nullable=True)
    rob_notes = Column(Text, nullable=True)

    # Bibliographic metadata (user-requested columns)
    publication_type = Column(String(100), nullable=True)
    volume = Column(String(50), nullable=True)
    issue = Column(String(50), nullable=True)        # "number" in spreadsheet
    doi = Column(String(300), nullable=True)
    abstract_text = Column(Text, nullable=True)      # "abstract"
    first_page = Column(String(20), nullable=True)
    last_page = Column(String(20), nullable=True)
    url = Column(String(1000), nullable=True)

    # Data extraction fields
    objective_text = Column(Text, nullable=True)     # "objective"
    methods_used = Column(Text, nullable=True)
    study_results = Column(Text, nullable=True)      # "results"
    findings = Column(Text, nullable=True)
    insights = Column(Text, nullable=True)
    practical_implications = Column(Text, nullable=True)
    research_gap = Column(Text, nullable=True)

    # Clinical meta-analysis fields
    patient_population = Column(Text, nullable=True)
    group_comparison = Column(Text, nullable=True)
    survival_outcomes = Column(Text, nullable=True)
    mortality_factors = Column(Text, nullable=True)
    key_findings = Column(Text, nullable=True)
    reasoning_study_design = Column(Text, nullable=True)
    source_database = Column(String(200), nullable=True)  # e.g. "PubMed", "Scopus"

    included = Column(Boolean, default=True)
    exclusion_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # True once a human (manual checkbox) or the AI screener has made an explicit
    # inclusion/exclusion decision for this study. The AI re-screening pass skips
    # any study where this is already True, so it never overwrites a decision
    # that was already made.
    screening_reviewed = Column(Boolean, default=False)

    review = relationship("Review", back_populates="studies")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=False)
    name = Column(String(200), nullable=True, default="Analysis")
    outcome_label = Column(String(300), nullable=True)
    effect_measure = Column(String(20), default="OR")
    model_type = Column(String(20), default="random")
    created_at = Column(DateTime, default=datetime.utcnow)

    results_json = Column(Text, nullable=True)      # JSON string of meta-analysis results
    forest_plot_b64 = Column(Text, nullable=True)   # base64-encoded PNG
    funnel_plot_b64 = Column(Text, nullable=True)   # base64-encoded PNG
    rob_plot_b64 = Column(Text, nullable=True)      # base64-encoded PNG

    review = relationship("Review", back_populates="analyses")


class SearchDatabase(Base):
    __tablename__ = "search_databases"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=False)
    database_name = Column(String(100), nullable=False)
    search_string = Column(Text, nullable=True)
    search_date = Column(String(50), nullable=True)
    results_count = Column(Integer, nullable=True)
