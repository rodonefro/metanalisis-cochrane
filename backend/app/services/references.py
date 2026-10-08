"""
Reference-manager import/export (Rayyan / Zotero / EndNote / Mendeley compatible).

Import:  RIS (.ris), BibTeX (.bib), PubMed MEDLINE (.nbib / .txt), and CSV/Excel
         (Rayyan CSV export, Zotero CSV export, Elicit/SciSpace, own template).
Export:  RIS, BibTeX and Rayyan-style CSV, carrying the screening decision so the
         library can be round-tripped through Rayyan or Zotero.
"""
import csv
import io
import re
from typing import Iterable

from .file_parser import parse_file


# ── Record normalisation ───────────────────────────────────────────────────────

def _clean(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def _year(v) -> int | None:
    m = re.search(r"(1[89]\d{2}|20\d{2})", str(v or ""))
    return int(m.group(1)) if m else None


def _doi(v) -> str | None:
    s = _clean(v)
    if not s:
        return None
    s = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", s, flags=re.I)
    m = re.search(r"10\.\d{4,9}/\S+", s)
    return m.group(0).rstrip(".,;") if m else None


def _first_author_surname(authors: str | None) -> str:
    if not authors:
        return ""
    first = re.split(r";| and |\|", authors)[0].strip()
    if "," in first:
        return first.split(",")[0].strip()
    parts = first.split()
    return parts[0] if parts else ""


def _finalise(rec: dict) -> dict | None:
    """Turn a raw parsed record into Study-model fields."""
    out: dict = {}
    for k, v in rec.items():
        if isinstance(v, list):
            v = "; ".join(x for x in (_clean(i) for i in v) if x)
        v = _clean(v) if k != "year" else v
        if v not in (None, ""):
            out[k] = v
    if "year" in out:
        out["year"] = _year(out["year"])
        if out["year"] is None:
            out.pop("year")
    if "doi" in out:
        d = _doi(out["doi"])
        if d:
            out["doi"] = d
        else:
            out.pop("doi")
    if "pages" in out:
        pages = out.pop("pages")
        m = re.match(r"\s*([A-Za-z]?\d+)\s*[-–]\s*([A-Za-z]?\d+)", pages)
        if m:
            out["first_page"], out["last_page"] = m.group(1), m.group(2)
        else:
            out["first_page"] = pages[:20]
    if not out.get("title") and not out.get("doi"):
        return None
    if not out.get("study_label"):
        surname = _first_author_surname(out.get("authors"))
        label = f"{surname} {out.get('year', '')}".strip()
        out["study_label"] = label or (out.get("title") or "")[:60]
    return out


# ── RIS ────────────────────────────────────────────────────────────────────────

_RIS_MAP = {
    "TI": "title", "T1": "title", "CT": "title",
    "AB": "abstract_text", "N2": "abstract_text",
    "AU": "authors", "A1": "authors", "A2": None,
    "PY": "year", "Y1": "year", "DA": None,
    "JO": "journal", "JF": "journal", "T2": "journal", "JA": None, "J2": None,
    "VL": "volume", "IS": "issue",
    "SP": "first_page", "EP": "last_page",
    "DO": "doi", "UR": "url", "L1": None,
    "KW": "keywords", "N1": "notes",
    "TY": "publication_type", "AN": "pmid", "DB": "source_database", "DP": None,
}
_RIS_LIST = {"authors", "keywords", "notes"}


def parse_ris(text: str) -> list[dict]:
    records, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", line)
        if not m:
            if cur is not None and line.strip() and cur.get("_last"):
                key = cur["_last"]
                if isinstance(cur.get(key), list):
                    cur[key][-1] += " " + line.strip()
                elif key in cur:
                    cur[key] += " " + line.strip()
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {"publication_type": val, "_last": None}
            continue
        if tag == "ER":
            if cur is not None:
                cur.pop("_last", None)
                records.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        field = _RIS_MAP.get(tag)
        if not field:
            cur["_last"] = None
            continue
        if field == "pmid" and not val.isdigit():
            cur["_last"] = None
            continue
        if field in _RIS_LIST:
            cur.setdefault(field, []).append(val)
        elif field not in cur:
            cur[field] = val
        cur["_last"] = field
    if cur:
        cur.pop("_last", None)
        records.append(cur)
    return [r for r in (_finalise(r) for r in records) if r]


# ── PubMed MEDLINE / .nbib ─────────────────────────────────────────────────────

_NBIB_MAP = {
    "PMID": "pmid", "TI": "title", "AB": "abstract_text", "FAU": "authors",
    "DP": "year", "JT": "journal", "VI": "volume", "IP": "issue", "PG": "pages",
    "PT": "publication_type", "MH": "keywords", "OT": "keywords",
}


def parse_nbib(text: str) -> list[dict]:
    records, cur, last = [], {}, None
    for line in text.splitlines() + [""]:
        if not line.strip():
            if cur:
                records.append(cur)
            cur, last = {}, None
            continue
        m = re.match(r"^([A-Z]{2,4})\s*- (.*)$", line)
        if m:
            tag, val = m.group(1), m.group(2).strip()
            if tag == "LID" or tag == "AID":
                if "[doi]" in val and "doi" not in cur:
                    cur["doi"] = val.replace("[doi]", "").strip()
                last = None
                continue
            field = _NBIB_MAP.get(tag)
            last = field
            if not field:
                continue
            if field in ("authors", "keywords"):
                cur.setdefault(field, []).append(val)
            elif field == "publication_type":
                cur.setdefault(field, val)
            elif field not in cur:
                cur[field] = val
        elif last and line.startswith("      "):
            if isinstance(cur.get(last), list):
                cur[last][-1] += " " + line.strip()
            elif last in cur:
                cur[last] += " " + line.strip()
    out = []
    for r in records:
        if r.get("pmid") and not r.get("url"):
            r["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/"
        f = _finalise(r)
        if f:
            out.append(f)
    return out


# ── BibTeX ─────────────────────────────────────────────────────────────────────

_BIB_MAP = {
    "title": "title", "abstract": "abstract_text", "author": "authors", "year": "year",
    "journal": "journal", "journaltitle": "journal", "booktitle": "journal",
    "volume": "volume", "number": "issue", "pages": "pages", "doi": "doi", "url": "url",
    "keywords": "keywords", "note": "notes", "annote": "notes", "pmid": "pmid",
}


def _bib_value(body: str, i: int) -> tuple[str, int]:
    while i < len(body) and body[i] in " \t\r\n":
        i += 1
    if i >= len(body):
        return "", i
    if body[i] == "{":
        depth, j = 0, i
        while j < len(body):
            if body[j] == "{":
                depth += 1
            elif body[j] == "}":
                depth -= 1
                if depth == 0:
                    return body[i + 1:j], j + 1
            j += 1
        return body[i + 1:], len(body)
    if body[i] == '"':
        j = i + 1
        while j < len(body) and not (body[j] == '"' and body[j - 1] != "\\"):
            j += 1
        return body[i + 1:j], j + 1
    m = re.match(r"[^,}\s]+", body[i:])
    tok = m.group(0) if m else ""
    return tok, i + len(tok)


def parse_bibtex(text: str) -> list[dict]:
    records = []
    for m in re.finditer(r"@(\w+)\s*\{", text):
        etype = m.group(1).lower()
        if etype in ("comment", "string", "preamble"):
            continue
        # entry body: up to the matching closing brace
        depth, j = 1, m.end()
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        key, _, rest = body.partition(",")
        rec: dict = {"publication_type": etype}
        i = 0
        while i < len(rest):
            fm = re.compile(r"\s*,?\s*([A-Za-z_-]+)\s*=").match(rest, i)
            if not fm:
                break
            name = fm.group(1).lower()
            val, i = _bib_value(rest, fm.end())
            val = re.sub(r"[{}]", "", val)
            field = _BIB_MAP.get(name)
            if field and field not in rec:
                if field == "authors":
                    val = "; ".join(a.strip() for a in re.split(r"\s+and\s+", val) if a.strip())
                rec[field] = val
        f = _finalise(rec)
        if f:
            records.append(f)
    return records


# ── Dispatcher ─────────────────────────────────────────────────────────────────

def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def detect_format(filename: str, content: bytes) -> str:
    name = filename.lower()
    if name.endswith((".ris", ".enw")):
        return "ris"
    if name.endswith(".bib"):
        return "bibtex"
    if name.endswith(".nbib"):
        return "nbib"
    if name.endswith((".csv", ".xlsx", ".xls", ".xlsm")):
        return "table"
    head = _decode(content[:4000])
    if re.search(r"^TY  - ", head, re.M):
        return "ris"
    if re.search(r"^PMID- ", head, re.M):
        return "nbib"
    if re.search(r"@\w+\s*\{", head):
        return "bibtex"
    raise ValueError(
        f"Formato no reconocido: '{filename}'. Usa RIS (.ris), BibTeX (.bib), "
        "PubMed (.nbib/.txt), CSV o Excel."
    )


def parse_references(content: bytes, filename: str) -> tuple[str, list[dict]]:
    fmt = detect_format(filename, content)
    if fmt == "table":
        rows = parse_file(content, filename)
        return fmt, [r for r in (_finalise(dict(r)) for r in rows) if r]
    text = _decode(content)
    parser = {"ris": parse_ris, "nbib": parse_nbib, "bibtex": parse_bibtex}[fmt]
    records = parser(text)
    if not records:
        raise ValueError(f"No se encontraron referencias en '{filename}'.")
    return fmt, records


# ── Deduplication keys ─────────────────────────────────────────────────────────

def norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def dedup_keys(rec: dict) -> list[str]:
    keys = []
    if rec.get("doi"):
        keys.append("doi:" + rec["doi"].strip().lower())
    if rec.get("pmid"):
        keys.append("pmid:" + str(rec["pmid"]).strip())
    t = norm_title(rec.get("title"))
    if len(t) >= 20:
        keys.append("ti:" + t)
    return keys


def split_sources(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def add_source(existing: str | None, source: str) -> str:
    items = split_sources(existing)
    if source and source.lower() not in {i.lower() for i in items}:
        items.append(source)
    return "; ".join(items)


# ── Export ─────────────────────────────────────────────────────────────────────

def _decision_label(s) -> str:
    d = effective_decision(s)
    return {"include": "Included", "exclude": "Excluded", "maybe": "Maybe"}.get(d, "Undecided")


def effective_decision(s) -> str | None:
    """Screening decision, derived for records screened before the field existed."""
    if getattr(s, "screening_decision", None):
        return s.screening_decision
    if not getattr(s, "screening_reviewed", False):
        return None
    if s.included:
        return "include"
    if (s.exclusion_reason or "").startswith("Requiere revisión a texto completo"):
        return "maybe"
    return "exclude"


def _authors_list(s) -> list[str]:
    return [a.strip() for a in re.split(r";|\|", s.authors or "") if a.strip()]


def to_ris(studies: Iterable) -> str:
    out = []
    for s in studies:
        ty = "JOUR"
        lines = [f"TY  - {ty}"]
        if s.title:
            lines.append(f"TI  - {s.title}")
        for a in _authors_list(s):
            lines.append(f"AU  - {a}")
        if s.year:
            lines.append(f"PY  - {s.year}")
        if s.journal:
            lines.append(f"JO  - {s.journal}")
        for tag, val in (("VL", s.volume), ("IS", s.issue), ("SP", s.first_page),
                         ("EP", s.last_page), ("DO", s.doi), ("UR", s.url), ("AN", s.pmid)):
            if val:
                lines.append(f"{tag}  - {val}")
        if s.abstract_text:
            lines.append(f"AB  - {s.abstract_text}")
        for kw in split_sources(s.keywords):
            lines.append(f"KW  - {kw}")
        sources = s.all_sources or s.source_database
        if sources:
            lines.append(f"DB  - {sources}")
        note = f"Screening: {_decision_label(s)}"
        if s.exclusion_reason and effective_decision(s) != "include":
            note += f" | Reason: {s.exclusion_reason}"
        lines.append(f"N1  - {note}")
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"


def _bib_escape(v) -> str:
    return str(v).replace("{", "(").replace("}", ")")


def to_bibtex(studies: Iterable) -> str:
    out, used = [], set()
    for s in studies:
        base = re.sub(r"[^A-Za-z0-9]", "", _first_author_surname(s.authors)) or "ref"
        key = f"{base}{s.year or ''}"
        k, n = key, 1
        while k in used:
            n += 1
            k = f"{key}{chr(96 + n)}"
        used.add(k)
        fields = [
            ("title", s.title), ("author", " and ".join(_authors_list(s)) or None),
            ("year", s.year), ("journal", s.journal), ("volume", s.volume), ("number", s.issue),
            ("pages", f"{s.first_page}--{s.last_page}" if s.first_page and s.last_page else s.first_page),
            ("doi", s.doi), ("url", s.url), ("pmid", s.pmid), ("keywords", s.keywords),
            ("abstract", s.abstract_text),
            ("note", f"Screening: {_decision_label(s)}"
                     + (f"; Reason: {s.exclusion_reason}" if s.exclusion_reason and effective_decision(s) != "include" else "")),
        ]
        body = ",\n".join(f"  {name} = {{{_bib_escape(v)}}}" for name, v in fields if v not in (None, ""))
        out.append(f"@article{{{k},\n{body}\n}}")
    return "\n\n".join(out) + "\n"


def to_rayyan_csv(studies: Iterable) -> str:
    """CSV with the column names Rayyan uses for import/export."""
    buf = io.StringIO()
    cols = ["key", "title", "authors", "journal", "issn", "volume", "issue", "pages", "year",
            "publisher", "url", "abstract", "notes", "doi", "keywords", "pmid", "source_database"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for s in studies:
        decision = {"include": "Included", "exclude": "Excluded", "maybe": "Maybe"}.get(effective_decision(s))
        notes = f'RAYYAN-INCLUSION: {{"Reviewer"=>"{decision}"}}' if decision else ""
        if s.exclusion_reason and effective_decision(s) != "include":
            notes += f" | RAYYAN-EXCLUSION-REASONS: {s.exclusion_reason}"
        w.writerow({
            "key": s.id, "title": s.title or "", "authors": s.authors or "",
            "journal": s.journal or "", "issn": "", "volume": s.volume or "", "issue": s.issue or "",
            "pages": f"{s.first_page}-{s.last_page}" if s.first_page and s.last_page else (s.first_page or ""),
            "year": s.year or "", "publisher": "", "url": s.url or "", "abstract": s.abstract_text or "",
            "notes": notes.strip(" |"), "doi": s.doi or "", "keywords": s.keywords or "",
            "pmid": s.pmid or "", "source_database": s.all_sources or s.source_database or "",
        })
    return "﻿" + buf.getvalue()
