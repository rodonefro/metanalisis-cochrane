import io
import re
from typing import List
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study
from ..schemas import StudyCreate, StudyUpdate, StudyOut
from ..services.file_parser import parse_file
from .references import import_records

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


_ILLEGAL_XLSX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@router.get("/download")
def download_studies(review_id: int, fmt: str = Query("xlsx", pattern="^(xlsx|csv)$"),
                     db: Session = Depends(get_db)):
    """Whole study database of the review, one column per field (re-importable)."""
    review = _get_review_or_404(review_id, db)
    studies = db.query(Study).filter(Study.review_id == review_id).order_by(Study.id).all()
    cols = [c.name for c in Study.__table__.columns if c.name != "review_id"]
    df = pd.DataFrame([{c: getattr(s, c) for c in cols} for s in studies], columns=cols)

    buf = io.BytesIO()
    if fmt == "csv":
        buf.write(df.to_csv(index=False).encode("utf-8-sig"))
        media = "text/csv; charset=utf-8"
    else:
        # Excel rejects control characters and caps cells at 32,767 characters.
        df = df.apply(lambda col: col.map(
            lambda v: _ILLEGAL_XLSX.sub("", v)[:32767] if isinstance(v, str) else v))
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            df.to_excel(xw, index=False, sheet_name="Estudios")
            ws = xw.sheets["Estudios"]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                ws.column_dimensions[cell.column_letter].width = max(12, min(40, len(str(cell.value)) + 2))
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buf.seek(0)

    safe = re.sub(r"[^A-Za-z0-9]+", "_", review.title or "revision").strip("_")[:50] or "revision"
    return StreamingResponse(buf, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="Base_estudios_{safe}.{fmt}"'})


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
    source_database: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Upload an Excel or CSV file to bulk-add studies to a review.

    Accepts plain templates as well as exports from Elicit AI or SciSpace AI —
    columns are auto-detected by name (see file_parser._COLUMN_MAP). The optional
    source_database label (e.g. "Elicit IA", "SciSpace IA") is stamped on studies
    that don't already carry one from the file itself.
    """
    _get_review_or_404(review_id, db)
    content = await file.read()
    try:
        studies_data = parse_file(content, file.filename or "upload.csv")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Rows keep their own source column when present; otherwise the label chosen
    # in the UI, otherwise the file name. Duplicates are merged and logged so the
    # PRISMA flow stays exact.
    default_source = source_database or re.sub(r"\.[^.]+$", "", file.filename or "Importación")
    result = import_records(db, review_id, studies_data, default_source)
    return {"created": result["added"], "duplicates_merged": result["duplicates_merged"],
            "by_source": result["by_source"]}


@router.post("/upload-merge", status_code=status.HTTP_201_CREATED)
async def upload_merge_studies(
    review_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload one or more Excel/CSV files from different search databases.
    Studies are deduplicated by DOI, PMID or normalized title; each file is
    logged as a search source named after the file.
    """
    _get_review_or_404(review_id, db)
    total_added = 0
    total_merged = 0
    errors = []

    for upload_file in files:
        content = await upload_file.read()
        filename = upload_file.filename or "upload.csv"
        source_db_name = re.sub(r"\.[^.]+$", "", filename)
        try:
            studies_data = parse_file(content, filename)
        except ValueError as exc:
            errors.append(f"{filename}: {exc}")
            continue
        result = import_records(db, review_id, studies_data, source_db_name)
        total_added += result["added"]
        total_merged += result["duplicates_merged"]

    result = {
        "files_processed": len(files) - len(errors),
        "added": total_added,
        "merged": total_merged,
        "skipped_exact_duplicates": 0,
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
    payload_data = payload.model_dump(exclude_unset=True)
    for field, value in payload_data.items():
        setattr(study, field, value)
    # A manual edit to the inclusion decision counts as a reviewed decision,
    # so the AI screener won't overwrite it on a later run.
    if "included" in payload_data:
        study.screening_reviewed = True
        if "screening_decision" not in payload_data:
            study.screening_decision = "include" if study.included else "exclude"
            study.screening_stage = study.screening_stage or "title_abstract"
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
