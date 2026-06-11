from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review, Study
from ..schemas import ReviewCreate, ReviewUpdate, ReviewOut, ReviewSummary

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/", response_model=list[ReviewSummary])
def list_reviews(db: Session = Depends(get_db)):
    reviews = db.query(Review).order_by(Review.created_at.desc()).all()
    result = []
    for r in reviews:
        summary = ReviewSummary.model_validate(r)
        summary.study_count = db.query(Study).filter(Study.review_id == r.id).count()
        result.append(summary)
    return result


@router.post("/", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    review = Review(**payload.model_dump())
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.put("/{review_id}", response_model=ReviewOut)
def update_review(review_id: int, payload: ReviewUpdate, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(review, field, value)
    db.commit()
    db.refresh(review)
    return review


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(review)
    db.commit()
