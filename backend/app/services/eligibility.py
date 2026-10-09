"""Which studies may enter the analysis, the generated text and the exports."""
import re

from ..models import Study


def eligible_studies(db, review_id: int) -> list[Study]:
    """Studies with an explicit include decision; never-screened records are left out."""
    return (
        db.query(Study)
        .filter(Study.review_id == review_id, Study.included == True, Study.screening_reviewed == True)  # noqa: E712
        .order_by(Study.id)
        .all()
    )


def excluded_studies(db, review_id: int) -> list[Study]:
    return (
        db.query(Study)
        .filter(Study.review_id == review_id, Study.included == False, Study.screening_reviewed == True)  # noqa: E712
        .order_by(Study.id)
        .all()
    )


def pending_count(db, review_id: int) -> int:
    return (
        db.query(Study)
        .filter(Study.review_id == review_id, Study.screening_reviewed == False)  # noqa: E712
        .count()
    )


def _doi_key(doi: str | None) -> str:
    d = (doi or "").strip().lower()
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)


def _title_key(title: str | None) -> str:
    t = re.sub(r"[^a-z0-9]", "", (title or "").lower())
    return t if len(t) >= 25 else ""


def find_duplicates(all_studies: list[Study], candidates: list[Study]) -> dict[int, Study]:
    """Map each candidate id to the earlier record it duplicates (same DOI or same title).

    Records that already have a decision act as the originals, so a pending copy is the
    one marked as duplicate.
    """
    candidate_ids = {s.id for s in candidates}
    ordered = sorted(all_studies, key=lambda s: (s.id in candidate_ids, s.id))
    seen: dict[str, Study] = {}
    duplicates: dict[int, Study] = {}
    for s in ordered:
        keys = [k for k in (("doi:" + _doi_key(s.doi)) if _doi_key(s.doi) else "",
                            ("title:" + _title_key(s.title)) if _title_key(s.title) else "") if k]
        original = next((seen[k] for k in keys if k in seen), None)
        if original is not None and s.id in candidate_ids:
            duplicates[s.id] = original
            continue
        for k in keys:
            seen.setdefault(k, s)
    return duplicates
