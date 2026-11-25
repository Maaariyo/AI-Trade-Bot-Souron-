"""Security master: merge NSE and BSE equity lists into one row per ISIN.

Inputs are files the owner downloads from the exchanges (CLAUDE.md
non-negotiable 5: no scrapers). Header layouts are matched loosely and must
be checked against a real file on the first import; unknown layouts fail
with the headers found.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import psycopg
from psycopg.rows import TupleRow

from services.factors.definitions import classify_financial_type
from services.ingest.csvfiles import parse_date, read_rows

Exchange = Literal["NSE", "BSE"]
Status = Literal["ACTIVE", "SUSPENDED", "DELISTED"]
Surveillance = Literal["NONE", "ASM", "GSM"]

# BSE group codes treated as SME. An assumption to verify on the first real import.
DEFAULT_BSE_SME_GROUPS = frozenset({"M", "MT", "MS"})


@dataclass(frozen=True)
class Listing:
    exchange: Exchange
    isin: str
    name: str
    symbol: str
    status: Status
    is_sme: bool = False
    series: str | None = None
    bse_code: str | None = None
    listed_on: date | None = None
    industry: str | None = None
    sector: str | None = None


@dataclass
class MergedSecurity:
    isin: str
    name: str
    status: Status
    is_sme: bool = False
    nse_symbol: str | None = None
    nse_series: str | None = None
    bse_code: str | None = None
    bse_symbol: str | None = None
    listed_on: date | None = None
    industry: str | None = None
    sector: str | None = None
    exchanges: set[Exchange] = field(default_factory=set)


_NSE_ALIASES = {
    "symbol": ("SYMBOL",),
    "name": ("NAMEOFCOMPANY", "COMPANYNAME", "NAME"),
    "series": ("SERIES",),
    "listed_on": ("DATEOFLISTING", "LISTINGDATE"),
    "isin": ("ISINNUMBER", "ISIN", "ISINNO"),
}

_BSE_ALIASES = {
    "code": ("SECURITYCODE", "SCRIPCODE", "CODE"),
    "symbol": ("SECURITYID", "SCRIPID"),
    "name": ("ISSUERNAME", "SECURITYNAME", "COMPANYNAME"),
    "status": ("STATUS",),
    "group": ("GROUP",),
    "isin": ("ISINNO", "ISIN", "ISINNUMBER"),
    "instrument": ("INSTRUMENT",),
    "industry": ("INDUSTRYNEWNAME", "INDUSTRY", "IGROUPNAME"),
    "sector": ("SECTORNAME", "SECTOR"),
}

_BSE_STATUS: dict[str, Status] = {
    "ACTIVE": "ACTIVE",
    "SUSPENDED": "SUSPENDED",
    "DELISTED": "DELISTED",
}


def parse_nse_list(source: Path | str, *, is_sme: bool) -> list[Listing]:
    """NSE's equity list (main board) or SME list. Every row on it is active."""
    rows = read_rows(source, _NSE_ALIASES, {"symbol", "name", "isin"})
    return [
        Listing(
            exchange="NSE",
            isin=r["isin"].upper(),
            name=r["name"],
            symbol=r["symbol"].upper(),
            status="ACTIVE",
            is_sme=is_sme,
            series=r.get("series") or None,
            listed_on=parse_date(r.get("listed_on", "")),
        )
        for r in rows
        if r["isin"]
    ]


def parse_bse_list(
    source: Path | str, *, sme_groups: frozenset[str] = DEFAULT_BSE_SME_GROUPS
) -> list[Listing]:
    """BSE's list of scrips. Non-equity instruments are dropped."""
    rows = read_rows(source, _BSE_ALIASES, {"code", "name", "status", "isin"})
    out: list[Listing] = []
    for r in rows:
        if not r["isin"] or r.get("instrument", "Equity").upper() not in {"EQUITY", ""}:
            continue
        status = _BSE_STATUS.get(r["status"].upper())
        if status is None:
            raise ValueError(f"unknown BSE status {r['status']!r} for {r['code']}")
        out.append(
            Listing(
                exchange="BSE",
                isin=r["isin"].upper(),
                name=r["name"],
                symbol=(r.get("symbol") or r["code"]).upper(),
                status=status,
                is_sme=r.get("group", "").upper() in sme_groups,
                bse_code=r["code"],
                industry=r.get("industry") or None,
                sector=r.get("sector") or None,
            )
        )
    return out


def merge_listings(listings: Iterable[Listing]) -> dict[str, MergedSecurity]:
    """One record per ISIN. NSE supplies the name when both list the company.

    Status is ACTIVE if any exchange lists it as active, else SUSPENDED if any
    lists it as suspended, else DELISTED.
    """
    merged: dict[str, MergedSecurity] = {}
    statuses: dict[str, set[Status]] = {}
    for lst in sorted(listings, key=lambda x: x.exchange != "NSE"):  # NSE first
        sec = merged.get(lst.isin)
        if sec is None:
            sec = merged[lst.isin] = MergedSecurity(isin=lst.isin, name=lst.name, status=lst.status)
        sec.exchanges.add(lst.exchange)
        sec.is_sme = sec.is_sme or lst.is_sme
        sec.listed_on = sec.listed_on or lst.listed_on
        sec.industry = sec.industry or lst.industry
        sec.sector = sec.sector or lst.sector
        if lst.exchange == "NSE":
            sec.nse_symbol, sec.nse_series = lst.symbol, lst.series
        else:
            sec.bse_code, sec.bse_symbol = lst.bse_code, lst.symbol
        statuses.setdefault(lst.isin, set()).add(lst.status)
    for isin, seen in statuses.items():
        merged[isin].status = (
            "ACTIVE" if "ACTIVE" in seen else "SUSPENDED" if "SUSPENDED" in seen else "DELISTED"
        )
    return merged


@dataclass(frozen=True)
class UpsertResult:
    inserted: int
    updated: int
    marked_delisted: int


def upsert_securities(
    conn: psycopg.Connection[TupleRow],
    merged: dict[str, MergedSecurity],
    *,
    as_of: date,
    source: str,
) -> UpsertResult:
    """Write a complete snapshot (NSE main, NSE SME and BSE lists) and record changes.

    Listing fields are replaced by the snapshot's values. Any ISIN still marked
    ACTIVE or SUSPENDED but missing from the snapshot is marked DELISTED and
    keeps its last symbols. Rows are never deleted.
    """
    inserted = updated = 0
    with conn.transaction():
        existing = {
            row[0]: (row[1], row[2], row[3])
            for row in conn.execute(
                "SELECT isin, status, surveillance, surveillance_stage FROM securities"
            )
        }
        for sec in merged.values():
            conn.execute(
                """
                INSERT INTO securities (isin, name, nse_symbol, nse_series, bse_code, bse_symbol,
                    is_sme, status, listed_on, first_seen, last_seen, industry, sector,
                    financial_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (isin) DO UPDATE SET
                    name = EXCLUDED.name,
                    nse_symbol = EXCLUDED.nse_symbol,
                    nse_series = EXCLUDED.nse_series,
                    bse_code = EXCLUDED.bse_code,
                    bse_symbol = EXCLUDED.bse_symbol,
                    is_sme = EXCLUDED.is_sme,
                    status = EXCLUDED.status,
                    listed_on = COALESCE(securities.listed_on, EXCLUDED.listed_on),
                    last_seen = EXCLUDED.last_seen,
                    -- an owner classification (make ingest classification) is kept
                    financial_type = CASE WHEN securities.industry IS NULL
                        THEN EXCLUDED.financial_type ELSE securities.financial_type END,
                    industry = COALESCE(securities.industry, EXCLUDED.industry),
                    sector = COALESCE(securities.sector, EXCLUDED.sector),
                    delisted_detected_on = CASE WHEN EXCLUDED.status = 'DELISTED'
                        THEN COALESCE(securities.delisted_detected_on, EXCLUDED.last_seen)
                        ELSE NULL END,
                    updated_at = now()
                """,
                (
                    sec.isin,
                    sec.name,
                    sec.nse_symbol,
                    sec.nse_series,
                    sec.bse_code,
                    sec.bse_symbol,
                    sec.is_sme,
                    sec.status,
                    sec.listed_on,
                    as_of,
                    as_of,
                    sec.industry,
                    sec.sector,
                    classify_financial_type(sec.industry, sec.sector),
                ),
            )
            before = existing.get(sec.isin)
            if before is None:
                inserted += 1
            else:
                updated += 1
            if before is None or before[0] != sec.status:
                surveillance, stage = (before[1], before[2]) if before else ("NONE", None)
                _record_status(conn, sec.isin, as_of, sec.status, surveillance, stage, source)

        marked = 0
        for isin, (status, surveillance, stage) in existing.items():
            if isin in merged or status == "DELISTED":
                continue
            conn.execute(
                "UPDATE securities SET status = 'DELISTED', delisted_detected_on = %s, "
                "updated_at = now() WHERE isin = %s",
                (as_of, isin),
            )
            _record_status(conn, isin, as_of, "DELISTED", surveillance, stage, source)
            marked += 1
    return UpsertResult(inserted=inserted, updated=updated, marked_delisted=marked)


def _record_status(
    conn: psycopg.Connection[TupleRow],
    isin: str,
    as_of: date,
    status: str,
    surveillance: str,
    stage: str | None,
    source: str,
) -> None:
    conn.execute(
        """
        INSERT INTO security_status_history
            (isin, as_of, status, surveillance, surveillance_stage, source)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (isin, as_of, source) DO UPDATE SET
            status = EXCLUDED.status,
            surveillance = EXCLUDED.surveillance,
            surveillance_stage = EXCLUDED.surveillance_stage
        """,
        (isin, as_of, status, surveillance, stage, source),
    )


# --- Surveillance (ASM / GSM) ---------------------------------------------------

_SURVEILLANCE_ALIASES = {
    "isin": ("ISIN", "ISINNUMBER", "ISINNO"),
    "symbol": ("SYMBOL", "SECURITYID", "SCRIPID"),
    "stage": ("STAGE", "ASMSTAGE", "GSMSTAGE", "SURVEILLANCESTAGE"),
}


@dataclass(frozen=True)
class SurveillanceEntry:
    isin: str | None
    symbol: str | None
    stage: str | None


def parse_surveillance_list(source: Path | str) -> list[SurveillanceEntry]:
    rows = list(read_rows(source, _SURVEILLANCE_ALIASES, set()))
    if rows and not ({"isin", "symbol"} & rows[0].keys()):
        raise ValueError("surveillance list needs an ISIN or SYMBOL column")
    return [
        SurveillanceEntry(
            isin=(r.get("isin") or "").upper() or None,
            symbol=(r.get("symbol") or "").upper() or None,
            stage=r.get("stage") or None,
        )
        for r in rows
    ]


def apply_surveillance(
    conn: psycopg.Connection[TupleRow],
    kind: Literal["ASM", "GSM"],
    entries: Iterable[SurveillanceEntry],
    *,
    as_of: date,
    source: str,
) -> tuple[int, list[str]]:
    """Replace the full `kind` list. GSM outranks ASM.

    Returns (securities now under `kind`, entries that matched no security).
    """
    unmatched: list[str] = []
    with conn.transaction():
        targets: dict[str, str | None] = {}
        for e in entries:
            row = None
            if e.isin:
                row = conn.execute(
                    "SELECT isin FROM securities WHERE isin = %s", (e.isin,)
                ).fetchone()
            elif e.symbol:
                row = conn.execute(
                    "SELECT isin FROM securities WHERE status <> 'DELISTED' "
                    "AND (nse_symbol = %s OR bse_symbol = %s) LIMIT 1",
                    (e.symbol, e.symbol),
                ).fetchone()
            if row is None:
                unmatched.append(e.isin or e.symbol or "?")
            else:
                targets[row[0]] = e.stage

        current = conn.execute(
            "SELECT isin, status, surveillance, surveillance_stage FROM securities"
        ).fetchall()
        for isin, status, surveillance, stage in current:
            new: str
            new_stage: str | None
            if isin in targets:
                if surveillance == "GSM" and kind == "ASM":
                    continue
                new, new_stage = kind, targets[isin]
            elif surveillance == kind:
                new, new_stage = "NONE", None
            else:
                continue
            if (new, new_stage) == (surveillance, stage):
                continue
            conn.execute(
                "UPDATE securities SET surveillance = %s, surveillance_stage = %s, "
                "updated_at = now() WHERE isin = %s",
                (new, new_stage, isin),
            )
            _record_status(conn, isin, as_of, status, new, new_stage, source)
    return len(targets), unmatched


# --- Counts -----------------------------------------------------------------------


@dataclass(frozen=True)
class UniverseCounts:
    active_total: int
    nse_main: int
    nse_sme: int
    bse: int
    both: int
    suspended: int
    delisted: int


def universe_counts(conn: psycopg.Connection[TupleRow]) -> UniverseCounts:
    row = conn.execute(
        """
        SELECT
          count(*) FILTER (WHERE status = 'ACTIVE'),
          count(*) FILTER (WHERE status = 'ACTIVE' AND nse_symbol IS NOT NULL AND NOT is_sme),
          count(*) FILTER (WHERE status = 'ACTIVE' AND nse_symbol IS NOT NULL AND is_sme),
          count(*) FILTER (WHERE status = 'ACTIVE' AND bse_code IS NOT NULL),
          count(*) FILTER (WHERE status = 'ACTIVE' AND nse_symbol IS NOT NULL
                                                   AND bse_code IS NOT NULL),
          count(*) FILTER (WHERE status = 'SUSPENDED'),
          count(*) FILTER (WHERE status = 'DELISTED')
        FROM securities
        """
    ).fetchone()
    assert row is not None
    return UniverseCounts(*row)


# --- Classification (owner file) -----------------------------------------------------

_CLASS_ALIASES = {
    "isin": ("ISIN",),
    "industry": ("INDUSTRY",),
    "sector": ("SECTOR",),
    "financial_type": ("FINANCIALTYPE",),
}


def apply_classification(
    conn: psycopg.Connection[TupleRow], source: Path | str
) -> tuple[int, list[str]]:
    """isin,industry,sector[,financial_type] rows overwrite the stored classification.

    financial_type (BANK, NBFC or NONE) is derived from the text when left blank.
    Returns (rows applied, ISINs not in the security master).
    """
    unknown: list[str] = []
    applied = 0
    with conn.transaction():
        for r in read_rows(source, _CLASS_ALIASES, {"isin", "industry", "sector"}):
            ftype = (r.get("financial_type") or "").upper() or classify_financial_type(
                r["industry"], r["sector"]
            )
            if ftype not in ("NONE", "BANK", "NBFC"):
                raise ValueError(f"{r['isin']}: financial_type must be NONE, BANK or NBFC")
            cur = conn.execute(
                "UPDATE securities SET industry = %s, sector = %s, financial_type = %s, "
                "updated_at = now() WHERE isin = %s",
                (r["industry"] or None, r["sector"] or None, ftype, r["isin"].upper()),
            )
            if cur.rowcount:
                applied += 1
            else:
                unknown.append(r["isin"])
    return applied, unknown
