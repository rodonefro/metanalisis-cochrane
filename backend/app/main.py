import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect as sa_inspect

from .database import engine, Base
from .config import settings
from .routers import reviews, studies, analysis, generate, export

Base.metadata.create_all(bind=engine)


def _migrate_db():
    """Add new columns to existing tables without dropping data.
    Uses SQLAlchemy inspect() so it works on both SQLite and PostgreSQL.
    """
    import sqlalchemy as sa

    new_study_cols = [
        ("publication_type", "VARCHAR(100)"),
        ("volume", "VARCHAR(50)"),
        ("issue", "VARCHAR(50)"),
        ("doi", "VARCHAR(300)"),
        ("abstract_text", "TEXT"),
        ("first_page", "VARCHAR(20)"),
        ("last_page", "VARCHAR(20)"),
        ("url", "VARCHAR(1000)"),
        ("objective_text", "TEXT"),
        ("methods_used", "TEXT"),
        ("study_results", "TEXT"),
        ("findings", "TEXT"),
        ("insights", "TEXT"),
        ("practical_implications", "TEXT"),
        ("research_gap", "TEXT"),
        ("patient_population", "TEXT"),
        ("group_comparison", "TEXT"),
        ("survival_outcomes", "TEXT"),
        ("mortality_factors", "TEXT"),
        ("key_findings", "TEXT"),
        ("reasoning_study_design", "TEXT"),
        ("source_database", "VARCHAR(200)"),
    ]
    new_review_cols = [
        ("prisma_db_names", "TEXT"),
        ("prisma_other_sources", "INTEGER"),
        ("prisma_duplicates_removed", "INTEGER"),
        ("prisma_other_removed", "INTEGER"),
        ("prisma_screened", "INTEGER"),
        ("prisma_excluded_screening", "INTEGER"),
        ("prisma_sought", "INTEGER"),
        ("prisma_not_retrieved", "INTEGER"),
        ("prisma_assessed", "INTEGER"),
        ("prisma_excluded_eligibility", "INTEGER"),
        ("prisma_exclusion_reasons", "TEXT"),
        ("prisma_included", "INTEGER"),
        ("prisma_reports_included", "INTEGER"),
    ]

    inspector = sa_inspect(engine)

    # If the tables don't exist yet (fresh deploy), create_all already handles them
    if not inspector.has_table("studies") or not inspector.has_table("reviews"):
        return

    existing_study = {col["name"] for col in inspector.get_columns("studies")}
    existing_review = {col["name"] for col in inspector.get_columns("reviews")}

    with engine.connect() as conn:
        for col, typ in new_study_cols:
            if col not in existing_study:
                conn.execute(sa.text(f"ALTER TABLE studies ADD COLUMN {col} {typ}"))
        for col, typ in new_review_cols:
            if col not in existing_review:
                conn.execute(sa.text(f"ALTER TABLE reviews ADD COLUMN {col} {typ}"))
        conn.commit()


_migrate_db()

app = FastAPI(
    title="MetaAnalysis Cochrane API",
    description="Full-stack Cochrane-style systematic review and meta-analysis platform",
    version="1.0.0",
)

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reviews.router)
app.include_router(studies.router)
app.include_router(analysis.router)
app.include_router(generate.router)
app.include_router(export.router)

_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}
