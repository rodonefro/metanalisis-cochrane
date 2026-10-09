import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study, SearchDatabase, Analysis
from ..services.prospero import (
    PROSPERO_FIELDS, FIELD_KEYS, generate_prospero, has_question, load_answers, question_hash,
)

router = APIRouter(prefix="/reviews/{review_id}/prospero", tags=["prospero"])


class ProsperoUpdate(BaseModel):
    answers: dict[str, str]


def _review_or_404(review_id: int, db: Session) -> Review:
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


def _state(review: Review) -> dict:
    answers = load_answers(review)
    return {
        "fields": [{"key": k, "label": label} for k, label, _ in PROSPERO_FIELDS],
        "answers": answers,
        "generated": bool(answers),
        "has_question": has_question(review),
        "stale": bool(answers) and review.prospero_question_hash != question_hash(review),
    }


@router.get("")
def get_prospero(review_id: int, db: Session = Depends(get_db)):
    return _state(_review_or_404(review_id, db))


@router.post("/generate")
def generate(review_id: int, db: Session = Depends(get_db)):
    review = _review_or_404(review_id, db)
    if not has_question(review):
        raise HTTPException(
            status_code=422,
            detail="Escribe primero el título y la pregunta de investigación (PICO o criterios).",
        )
    studies = db.query(Study).filter(Study.review_id == review_id).all()
    searches = db.query(SearchDatabase).filter(SearchDatabase.review_id == review_id).all()
    has_analysis = db.query(Analysis).filter(Analysis.review_id == review_id).count() > 0
    fingerprint = question_hash(review)
    try:
        answers = generate_prospero(review, studies, searches, has_analysis)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al generar el registro PROSPERO: {exc}")
    review.prospero_json = json.dumps(answers, ensure_ascii=False)
    review.prospero_question_hash = fingerprint
    db.commit()
    db.refresh(review)
    return _state(review)


@router.put("")
def save_edits(review_id: int, payload: ProsperoUpdate, db: Session = Depends(get_db)):
    review = _review_or_404(review_id, db)
    answers = load_answers(review) or {k: "" for k in FIELD_KEYS}
    answers.update({k: v for k, v in payload.answers.items() if k in FIELD_KEYS})
    review.prospero_json = json.dumps(answers, ensure_ascii=False)
    db.commit()
    db.refresh(review)
    return _state(review)
