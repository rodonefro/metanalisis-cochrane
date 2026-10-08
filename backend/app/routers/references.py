"""
Reference manager (Rayyan / Zotero style): search log, import with
deduplication, screening decisions and export.
"""
import re
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study, SearchDatabase
from ..schemas import SearchDatabaseCreate, SearchDatabaseUpdate, SearchDatabaseOut, StudyOut
from ..services.references import (
    parse_references, dedup_keys, add_source, to_ris, to_bibtex, to_rayyan_csv, effective_decision,
)
from ..services.prisma import sync_prisma

router = APIRouter(prefix="/reviews/{review_id}", tags=["references"])

_VALID_SOURCE_TYPES = {"database", "register", "other"}


def _review_or_404(review_id: int, db: Session) -> Review:
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


def _get_or_create_search(db: Session, review_id: int, name: str, source_type: str = "database") -> SearchDatabase:
    sd = (db.query(SearchDatabase)
          .filter(SearchDatabase.review_id == review_id)
          .all())
    for s in sd:
        if s.database_name.strip().lower() == name.strip().lower():
            return s
    s = SearchDatabase(review_id=review_id, database_name=name.strip(), source_type=source_type,
                       records_imported=0, duplicates_found=0)
    db.add(s)
    db.flush()
    return s


def _rayyan_decision(notes: str | None) -> str | None:
    m = re.search(r'RAYYAN-INCLUSION:\s*\{[^}]*=>"?(Included|Excluded|Maybe)', notes or "", re.I)
    return {"included": "include", "excluded": "exclude", "maybe": "maybe"}[m.group(1).lower()] if m else None


def import_records(db: Session, review_id: int, records: list[dict], default_source: str,
                   source_type: str = "database") -> dict:
    """Add records to the review, merging duplicates (DOI → PMID → normalised title).

    Every imported record is logged against its search source so the PRISMA
    identification and duplicate counts are exact.
    """
    valid = {c.key for c in Study.__table__.columns} - {"id", "review_id"}
    existing = db.query(Study).filter(Study.review_id == review_id).all()
    index: dict[str, Study] = {}
    for s in existing:
        for k in dedup_keys({"doi": s.doi, "pmid": s.pmid, "title": s.title}):
            index.setdefault(k, s)

    imported, dups = Counter(), Counter()
    added = merged = 0
    for rec in records:
        source = (rec.pop("source_database", None) or default_source or "").strip() or default_source
        rec = {k: v for k, v in rec.items() if k in valid}
        decision = _rayyan_decision(rec.get("notes"))
        imported[source] += 1
        match = next((index[k] for k in dedup_keys(rec) if k in index), None)
        if match:
            dups[source] += 1
            merged += 1
            for k, v in rec.items():
                if v not in (None, "") and getattr(match, k, None) in (None, ""):
                    setattr(match, k, v)
            match.all_sources = add_source(match.all_sources or match.source_database, source)
            continue
        study = Study(review_id=review_id, **rec)
        study.source_database = source
        study.all_sources = source
        if decision:
            study.screening_decision = decision
            study.screening_reviewed = True
            study.screening_stage = "title_abstract"
            study.included = decision == "include"
        db.add(study)
        for k in dedup_keys(rec):
            index.setdefault(k, study)
        added += 1

    for source, n in imported.items():
        sd = _get_or_create_search(db, review_id, source, source_type)
        sd.records_imported = (sd.records_imported or 0) + n
        sd.duplicates_found = (sd.duplicates_found or 0) + dups[source]

    db.commit()
    return {"records": sum(imported.values()), "added": added, "duplicates_merged": merged,
            "by_source": dict(imported)}


# ── Search log ─────────────────────────────────────────────────────────────────

@router.get("/searches", response_model=list[SearchDatabaseOut])
def list_searches(review_id: int, db: Session = Depends(get_db)):
    _review_or_404(review_id, db)
    return db.query(SearchDatabase).filter(SearchDatabase.review_id == review_id).order_by(SearchDatabase.id).all()


@router.post("/searches", response_model=SearchDatabaseOut, status_code=status.HTTP_201_CREATED)
def create_search(review_id: int, payload: SearchDatabaseCreate, db: Session = Depends(get_db)):
    _review_or_404(review_id, db)
    if payload.source_type and payload.source_type not in _VALID_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="source_type debe ser database, register u other")
    sd = _get_or_create_search(db, review_id, payload.database_name, payload.source_type or "database")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sd, k, v)
    db.commit()
    db.refresh(sd)
    return sd


@router.put("/searches/{search_id}", response_model=SearchDatabaseOut)
def update_search(review_id: int, search_id: int, payload: SearchDatabaseUpdate, db: Session = Depends(get_db)):
    sd = db.query(SearchDatabase).filter(SearchDatabase.id == search_id, SearchDatabase.review_id == review_id).first()
    if not sd:
        raise HTTPException(status_code=404, detail="Búsqueda no encontrada")
    data = payload.model_dump(exclude_unset=True)
    if data.get("source_type") and data["source_type"] not in _VALID_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="source_type debe ser database, register u other")
    new_name = data.get("database_name")
    if new_name and new_name != sd.database_name:
        # Keep the records' source labels in step with the renamed search.
        for s in db.query(Study).filter(Study.review_id == review_id).all():
            for attr in ("all_sources", "source_database"):
                val = getattr(s, attr)
                if val:
                    parts = [new_name if p.strip() == sd.database_name else p.strip() for p in val.split(";")]
                    setattr(s, attr, "; ".join(p for p in parts if p))
    for k, v in data.items():
        setattr(sd, k, v)
    db.commit()
    db.refresh(sd)
    return sd


@router.delete("/searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search(review_id: int, search_id: int, db: Session = Depends(get_db)):
    sd = db.query(SearchDatabase).filter(SearchDatabase.id == search_id, SearchDatabase.review_id == review_id).first()
    if not sd:
        raise HTTPException(status_code=404, detail="Búsqueda no encontrada")
    db.delete(sd)
    db.commit()


# ── Import / export ────────────────────────────────────────────────────────────

@router.post("/references/import", status_code=status.HTTP_201_CREATED)
async def import_references(
    review_id: int,
    file: UploadFile = File(...),
    database_name: str = Form(...),
    source_type: str = Form("database"),
    search_string: Optional[str] = Form(None),
    search_date: Optional[str] = Form(None),
    results_count: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Import a RIS / BibTeX / PubMed / CSV / Excel export from one search source."""
    review = _review_or_404(review_id, db)
    if not database_name.strip():
        raise HTTPException(status_code=422, detail="Indica la base de datos donde se hizo la búsqueda.")
    if source_type not in _VALID_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="source_type debe ser database, register u other")
    content = await file.read()
    try:
        fmt, records = parse_references(content, file.filename or "refs.ris")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # One search = one source: ignore per-row source labels in a database export.
    for r in records:
        r.pop("source_database", None)
    result = import_records(db, review_id, records, database_name.strip(), source_type)

    sd = _get_or_create_search(db, review_id, database_name.strip(), source_type)
    if search_string:
        sd.search_string = search_string
    if search_date:
        sd.search_date = search_date
    if results_count is not None:
        sd.results_count = results_count
    db.commit()
    prisma = sync_prisma(db, review)
    return {**result, "format": fmt, "prisma_warnings": prisma["warnings"]}


_SCOPES = {"all", "included", "excluded", "maybe", "pending"}


@router.get("/references/export")
def export_references(
    review_id: int,
    fmt: str = Query("ris", pattern="^(ris|bib|csv)$"),
    scope: str = Query("all"),
    db: Session = Depends(get_db),
):
    review = _review_or_404(review_id, db)
    if scope not in _SCOPES:
        raise HTTPException(status_code=422, detail=f"scope debe ser uno de {sorted(_SCOPES)}")
    studies = db.query(Study).filter(Study.review_id == review_id).order_by(Study.id).all()
    want = {"included": "include", "excluded": "exclude", "maybe": "maybe", "pending": None}
    if scope != "all":
        studies = [s for s in studies if effective_decision(s) == want[scope]]
    writer, media, ext = {
        "ris": (to_ris, "application/x-research-info-systems", "ris"),
        "bib": (to_bibtex, "application/x-bibtex", "bib"),
        "csv": (to_rayyan_csv, "text/csv", "csv"),
    }[fmt]
    body = writer(studies)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", review.title)[:40] or "referencias"
    return Response(
        content=body.encode("utf-8"),
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe}_{scope}.{ext}"'},
    )


# ── Screening decisions ────────────────────────────────────────────────────────

class DecisionIn(BaseModel):
    decision: Optional[str] = None           # include | exclude | maybe | None (reset to pending)
    stage: Optional[str] = None              # title_abstract | full_text
    reason: Optional[str] = None
    full_text_status: Optional[str] = None   # retrieved | not_retrieved | "" to clear
    notes: Optional[str] = None
    source_database: Optional[str] = None


@router.post("/references/{study_id}/decision", response_model=StudyOut)
def set_decision(review_id: int, study_id: int, payload: DecisionIn, db: Session = Depends(get_db)):
    study = db.query(Study).filter(Study.id == study_id, Study.review_id == review_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    data = payload.model_dump(exclude_unset=True)

    if "decision" in data:
        d = data["decision"]
        if d not in (None, "include", "exclude", "maybe"):
            raise HTTPException(status_code=422, detail="decision debe ser include, exclude o maybe")
        if d == "exclude" and not (data.get("reason") or "").strip():
            raise HTTPException(status_code=422, detail="Indica el motivo de exclusión (PRISMA lo exige).")
        study.screening_decision = d
        study.screening_reviewed = d is not None
        study.included = d in (None, "include")
        study.exclusion_reason = None if d in (None, "include") else (data.get("reason") or study.exclusion_reason)
        if d is None:
            study.screening_stage = None
    elif "reason" in data:
        study.exclusion_reason = data["reason"]

    if "stage" in data:
        if data["stage"] not in (None, "title_abstract", "full_text"):
            raise HTTPException(status_code=422, detail="stage debe ser title_abstract o full_text")
        study.screening_stage = data["stage"]
    elif "decision" in data and data["decision"] and not study.screening_stage:
        study.screening_stage = "title_abstract"

    if "full_text_status" in data:
        fts = data["full_text_status"] or None
        if fts not in (None, "retrieved", "not_retrieved"):
            raise HTTPException(status_code=422, detail="full_text_status debe ser retrieved o not_retrieved")
        study.full_text_status = fts
    if "notes" in data:
        study.notes = data["notes"]
    if data.get("source_database"):
        src = data["source_database"].strip()
        if not (study.all_sources or study.source_database):
            # A record with no origin is being attributed to a search: log it there.
            sd = _get_or_create_search(db, review_id, src)
            sd.records_imported = (sd.records_imported or 0) + 1
        study.source_database = src
        study.all_sources = src
    db.commit()
    db.refresh(study)
    return study
