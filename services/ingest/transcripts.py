"""Earnings-call transcripts and investor presentations (Phase 1b).

Free path (decision D1): the owner downloads PDFs from company or exchange
websites and loads them with `make ingest ARGS="transcript ..."`. A single URL
the owner supplies can also be fetched, except on the exchange and aggregator
sites CLAUDE.md non-negotiable 5 rules out; files from those are downloaded by
hand. Text is extracted per page and stored, so the quote check can search it.
"""

import hashlib
import io
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Literal
from urllib.parse import urlparse

import psycopg
from psycopg.rows import TupleRow
from pypdf import PdfReader
from pypdf.errors import PdfReadError

DocType = Literal["TRANSCRIPT", "PRESENTATION", "ANNUAL_REPORT"]

MAX_PDF_BYTES = 25_000_000
# CLAUDE.md non-negotiable 5: never fetch from these programmatically.
BLOCKED_HOSTS = ("nseindia.com", "bseindia.com", "screener.in", "moneycontrol.com")


class DocumentError(ValueError):
    pass


def extract_pages(pdf: bytes) -> list[str]:
    """Text of each page; an image-only page yields ''. OCR is not attempted."""
    if not pdf.startswith(b"%PDF"):
        raise DocumentError("not a PDF file")
    try:
        reader = PdfReader(io.BytesIO(pdf))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except PdfReadError as exc:
        raise DocumentError(f"unreadable PDF: {exc}") from exc


def _blocked(host: str) -> bool:
    host = host.lower()
    return any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def fetch_pdf(url: str, *, timeout: float = 30.0) -> bytes:
    """Fetch one owner-supplied PDF URL. Exchange and aggregator sites are refused."""
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.hostname:
        raise DocumentError(f"URL must be https: {url}")
    if _blocked(parts.hostname):
        raise DocumentError(
            f"{parts.hostname} is not fetched automatically (CLAUDE.md rule 5). "
            "Download the PDF yourself and pass --file."
        )
    req = urllib.request.Request(url, headers={"User-Agent": "NiveshCouncil/0.1 (personal)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data: bytes = resp.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise DocumentError(f"PDF larger than {MAX_PDF_BYTES} bytes")
    return data


@dataclass(frozen=True)
class AddResult:
    document_id: int
    created: bool
    pages: int
    empty_pages: int


def add_document(
    conn: psycopg.Connection[TupleRow],
    *,
    isin: str,
    doc_type: DocType,
    doc_date: date,
    pdf: bytes,
    period_label: str | None = None,
    source_url: str | None = None,
) -> AddResult:
    """Store a PDF's text once. The same file loaded again returns the existing row."""
    if len(pdf) > MAX_PDF_BYTES:
        raise DocumentError(f"PDF larger than {MAX_PDF_BYTES} bytes")
    if conn.execute("SELECT 1 FROM securities WHERE isin = %s", (isin,)).fetchone() is None:
        raise DocumentError(f"unknown ISIN {isin}; import the security master first")
    digest = hashlib.sha256(pdf).hexdigest()
    existing = conn.execute(
        "SELECT id, page_count FROM documents WHERE sha256 = %s", (digest,)
    ).fetchone()
    if existing:
        empty = conn.execute(
            "SELECT count(*) FROM document_pages WHERE document_id = %s AND text = ''",
            (existing[0],),
        ).fetchone()
        return AddResult(existing[0], False, existing[1], empty[0] if empty else 0)

    pages = extract_pages(pdf)
    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO documents (isin, doc_type, doc_date, period_label, source_url, sha256,
                page_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (isin, doc_type, doc_date, period_label, source_url, digest, len(pages)),
        ).fetchone()
        assert row is not None
        doc_id = int(row[0])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO document_pages (document_id, page_no, text) VALUES (%s, %s, %s)",
                [(doc_id, i, text) for i, text in enumerate(pages, start=1)],
            )
    return AddResult(doc_id, True, len(pages), sum(1 for p in pages if not p))


def document_pages(conn: psycopg.Connection[TupleRow], document_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT text FROM document_pages WHERE document_id = %s ORDER BY page_no", (document_id,)
    ).fetchall()
    return [r[0] for r in rows]
