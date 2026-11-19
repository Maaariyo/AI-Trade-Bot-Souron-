from datetime import date

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.ingest.csvfiles import HeaderError
from services.ingest.security_master import (
    Listing,
    apply_surveillance,
    merge_listings,
    parse_bse_list,
    parse_nse_list,
    parse_surveillance_list,
    universe_counts,
    upsert_securities,
)
from tests.conftest import FIXTURES

Conn = psycopg.Connection[TupleRow]


def _snapshot() -> list[Listing]:
    return [
        *parse_nse_list(FIXTURES / "nse_equity_l.csv", is_sme=False),
        *parse_nse_list(FIXTURES / "nse_sme_equity_l.csv", is_sme=True),
        *parse_bse_list(FIXTURES / "bse_scrips.csv"),
    ]


def test_parse_nse_handles_spaced_and_underscored_headers() -> None:
    main = parse_nse_list(FIXTURES / "nse_equity_l.csv", is_sme=False)
    sme = parse_nse_list(FIXTURES / "nse_sme_equity_l.csv", is_sme=True)
    assert [x.symbol for x in main] == ["RELIANCE", "INFY", "NSEONLY"]
    assert main[0].listed_on == date(1995, 11, 29)
    assert sme[0].is_sme and sme[0].series == "SM"


def test_parse_bse_drops_debt_and_flags_sme_group() -> None:
    bse = {x.bse_code: x for x in parse_bse_list(FIXTURES / "bse_scrips.csv")}
    assert set(bse) == {"500325", "500209", "543000", "544000"}
    assert bse["543000"].status == "SUSPENDED"
    assert bse["544000"].is_sme


def test_unknown_layout_fails_with_headers() -> None:
    with pytest.raises(HeaderError, match="headers found"):
        parse_nse_list("TICKER,COMPANY\nABC,Abc Ltd\n", is_sme=False)


def test_merge_by_isin() -> None:
    merged = merge_listings(_snapshot())
    assert len(merged) == 6
    rel = merged["INE002A01018"]
    assert rel.exchanges == {"NSE", "BSE"}
    assert rel.name == "Reliance Industries Limited"  # NSE name wins
    assert (rel.nse_symbol, rel.bse_code) == ("RELIANCE", "500325")
    assert merged["INE333C01015"].status == "SUSPENDED"


@pytest.mark.integration
def test_upsert_counts_and_delisting(db: Conn) -> None:
    first = upsert_securities(db, merge_listings(_snapshot()), as_of=date(2026, 11, 1), source="t")
    assert (first.inserted, first.updated, first.marked_delisted) == (6, 0, 0)
    c = universe_counts(db)
    assert (c.active_total, c.nse_main, c.nse_sme, c.bse, c.both, c.suspended) == (5, 3, 1, 3, 2, 1)

    # Next snapshot: Infosys gone from both exchanges.
    later = [x for x in _snapshot() if x.isin != "INE009A01021"]
    second = upsert_securities(db, merge_listings(later), as_of=date(2026, 11, 8), source="t")
    assert second.marked_delisted == 1
    row = db.execute(
        "SELECT status, delisted_detected_on, nse_symbol FROM securities WHERE isin = %s",
        ("INE009A01021",),
    ).fetchone()
    assert row == ("DELISTED", date(2026, 11, 8), "INFY")  # kept, with its last symbol
    history = db.execute(
        "SELECT as_of, status FROM security_status_history WHERE isin = %s ORDER BY as_of",
        ("INE009A01021",),
    ).fetchall()
    assert history == [(date(2026, 11, 1), "ACTIVE"), (date(2026, 11, 8), "DELISTED")]


@pytest.mark.integration
def test_surveillance_replace_and_gsm_precedence(db: Conn) -> None:
    upsert_securities(db, merge_listings(_snapshot()), as_of=date(2026, 11, 1), source="t")
    entries = parse_surveillance_list(FIXTURES / "nse_asm.csv")
    count, unmatched = apply_surveillance(db, "ASM", entries, as_of=date(2026, 11, 2), source="t")
    assert count == 1 and unmatched == ["INE999Z01013"]

    def state(isin: str) -> tuple[str, str | None]:
        row = db.execute(
            "SELECT surveillance, surveillance_stage FROM securities WHERE isin = %s", (isin,)
        ).fetchone()
        assert row is not None
        return row[0], row[1]

    assert state("INE111A01019") == ("ASM", "Stage I")
    apply_surveillance(db, "GSM", entries[:1], as_of=date(2026, 11, 3), source="t")
    apply_surveillance(db, "ASM", entries[:1], as_of=date(2026, 11, 4), source="t")
    assert state("INE111A01019")[0] == "GSM"  # ASM never downgrades GSM
    apply_surveillance(db, "GSM", [], as_of=date(2026, 11, 5), source="t")
    assert state("INE111A01019") == ("NONE", None)  # dropped from the full GSM list
