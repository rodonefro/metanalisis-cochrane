"""
Full-text PDFs: text extraction (no AI) and matching a PDF to the record it belongs to.

Only the extracted text is kept and sent to the AI, never the PDF itself: a PDF sent as a
document is billed for its page images as well, several times the tokens of its text. The
reference list is dropped because it is long and never needed for eligibility, data
extraction or risk of bias.
"""
import io
import re
import unicodedata

MAX_CHARS = 400_000   # ~100k tokens: far beyond a normal article; larger files are refused, not cut

_REFERENCES_HEADING = re.compile(
    r"\n\s*(references|reference list|bibliography|literature cited|referencias|"
    r"referencias bibliogr[aá]ficas|bibliograf[ií]a)\s*\n",
    re.IGNORECASE,
)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)


def extract_pdf_text(content: bytes) -> str:
    """Plain text of a PDF without its reference list. Raises ValueError when there is no text."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"no se pudo leer el PDF ({exc})")
    text = "\n".join(pages)
    text = re.sub(r"-\n(?=[a-záéíóúñ])", "", text)          # words split across lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 500:
        raise ValueError("el PDF no tiene texto seleccionable (parece escaneado); pásalo por OCR y vuelve a subirlo")
    # Cut at the last references heading, if it is in the second half of the document.
    matches = [m for m in _REFERENCES_HEADING.finditer(text) if m.start() > len(text) * 0.5]
    if matches:
        text = text[:matches[-1].start()].rstrip()
    if len(text) > MAX_CHARS:
        raise ValueError(f"el texto del PDF es demasiado largo ({len(text):,} caracteres); sube solo el artículo")
    return text


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _clean_doi(doi: str) -> str:
    return doi.lower().rstrip(".,;)]}").removeprefix("https://doi.org/")


def match_study(text: str, filename: str, studies: list):
    """The record a PDF belongs to: DOI first, then PMID, then the title on its first pages."""
    head = text[:8000]
    dois = {_clean_doi(d) for d in _DOI.findall(head + " " + filename.replace("_", "/"))}
    by_doi = {_clean_doi(s.doi): s for s in studies if s.doi}
    for d in dois:
        if d in by_doi:
            return by_doi[d]
    for s in studies:
        if s.pmid and re.search(rf"\b{re.escape(str(s.pmid).strip())}\b", head + " " + filename):
            return s
    head_norm = f" {_norm(head)} "
    name_norm = f" {_norm(filename)} "
    best, best_len = None, 0
    for s in studies:
        title = _norm(s.title or "")
        if len(title) < 25:
            continue
        # Zotero-style file names ("Autor - 2020 - Título…") carry a shortened title.
        for probe, haystack in ((title[:90], head_norm), (title[:50], name_norm)):
            if f" {probe}" in haystack and len(probe) > best_len:
                best, best_len = s, len(probe)
    return best
