import re
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study
from ..schemas import StudyCreate, StudyUpdate, StudyOut
from ..services.file_parser import parse_file

router = APIRouter(prefix="/reviews/{review_id}/studies", tags=["studies"])


def _get_review_or_404(review_id: int, db: Session) -> Review:
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.get("/", response_model=list[StudyOut])
def list_studies(review_id: int, db: Session = Depends(get_db)):
    _get_review_or_404(review_id, db)
    return db.query(Study).filter(Study.review_id == review_id).order_by(Study.id).all()


@router.post("/", response_model=StudyOut, status_code=status.HTTP_201_CREATED)
def create_study(review_id: int, payload: StudyCreate, db: Session = Depends(get_db)):
    _get_review_or_404(review_id, db)
    study = Study(review_id=review_id, **payload.model_dump())
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_studies(
    review_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload an Excel or CSV file to bulk-add studies to a review."""
    _get_review_or_404(review_id, db)
    content = await file.read()
    try:
        studies_data = parse_file(content, file.filename or "upload.csv")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Get valid column names from the Study model to filter unknown fields
    valid_columns = {c.key for c in Study.__table__.columns} - {"id", "review_id"}

    created = []
    for s in studies_data:
        filtered = {k: v for k, v in s.items() if k in valid_columns}
        study = Study(review_id=review_id, **filtered)
        db.add(study)
        created.append(study)
    db.commit()
    for s in created:
        db.refresh(s)
    return {"created": len(created), "studies": [StudyOut.model_validate(s) for s in created]}


def _norm_title(t: str) -> str:
    """Lowercase, remove non-alphanumeric characters for fuzzy title matching."""
    return re.sub(r"[^a-z0-9]", "", t.lower()) if t else ""


def _merge_into(existing: Study, incoming: dict, valid_columns: set) -> bool:
    """Fill empty fields in existing study with non-empty values from incoming. Returns True if any field was updated."""
    changed = False
    for field, value in incoming.items():
        if field not in valid_columns:
            continue
        if value is None:
            continue
        current = getattr(existing, field, None)
        if current is None or current == "":
            setattr(existing, field, value)
            changed = True
    return changed


@router.post("/upload-merge", status_code=status.HTTP_201_CREATED)
async def upload_merge_studies(
    review_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload one or more Excel/CSV files from different search databases.
    Studies are deduplicated by DOI (exact) or normalized title.
    Existing studies are enriched with new data; truly new studies are added.
    """
    _get_review_or_404(review_id, db)
    valid_columns = {c.key for c in Study.__table__.columns} - {"id", "review_id"}

    # Build lookup indexes from existing studies
    existing_studies = db.query(Study).filter(Study.review_id == review_id).all()
    doi_index: dict[str, Study] = {
        s.doi.strip().lower(): s for s in existing_studies if s.doi and s.doi.strip()
    }
    title_index: dict[str, Study] = {
        _norm_title(s.title): s for s in existing_studies if s.title and _norm_title(s.title)
    }

    total_added = 0
    total_merged = 0
    total_skipped = 0
    errors = []

    for upload_file in files:
        content = await upload_file.read()
        filename = upload_file.filename or "upload.csv"
        # Infer source_database from filename (strip extension)
        source_db_name = re.sub(r"\.[^.]+$", "", filename)

        try:
            studies_data = parse_file(content, filename)
        except ValueError as exc:
            errors.append(f"{filename}: {exc}")
            continue

        for s in studies_data:
            filtered = {k: v for k, v in s.items() if k in valid_columns}
            # Stamp the source database if not already set in the data
            if not filtered.get("source_database"):
                filtered["source_database"] = source_db_name

            # --- Duplicate detection ---
            doi_key = (filtered.get("doi") or "").strip().lower()
            title_key = _norm_title(filtered.get("title") or "")

            matched: Study | None = None
            if doi_key and doi_key in doi_index:
                matched = doi_index[doi_key]
            elif title_key and title_key in title_index:
                matched = title_index[title_key]

            if matched:
                changed = _merge_into(matched, filtered, valid_columns)
                if changed:
                    total_merged += 1
                else:
                    total_skipped += 1
            else:
                new_study = Study(review_id=review_id, **filtered)
                db.add(new_study)
                # Add to indexes so subsequent files in this batch don't re-add
                if doi_key:
                    doi_index[doi_key] = new_study
                if title_key:
                    title_index[title_key] = new_study
                total_added += 1

    db.commit()

    result = {
        "files_processed": len(files) - len(errors),
        "added": total_added,
        "merged": total_merged,
        "skipped_exact_duplicates": total_skipped,
    }
    if errors:
        result["errors"] = errors
    return result


@router.get("/{study_id}", response_model=StudyOut)
def get_study(review_id: int, study_id: int, db: Session = Depends(get_db)):
    study = db.query(Study).filter(Study.id == study_id, Study.review_id == review_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


@router.put("/{study_id}", response_model=StudyOut)
def update_study(
    review_id: int, study_id: int, payload: StudyUpdate, db: Session = Depends(get_db)
):
    study = db.query(Study).filter(Study.id == study_id, Study.review_id == review_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(study, field, value)
    db.commit()
    db.refresh(study)
    return study


@router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_study(review_id: int, study_id: int, db: Session = Depends(get_db)):
    study = db.query(Study).filter(Study.id == study_id, Study.review_id == review_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    db.delete(study)
    db.commit()
