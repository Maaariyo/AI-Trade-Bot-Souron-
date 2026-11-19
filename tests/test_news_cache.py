from datetime import date

import psycopg
import pytest
from defusedxml import EntitiesForbidden
from psycopg.rows import TupleRow

from services.ingest.news_cache import (
    WatchItem,
    build_headline_digests,
    match_headline,
    name_key,
    parse_feed,
    store_headlines,
    watchlist,
)
from tests.conftest import FIXTURES
from tests.test_prices import _load_securities

Conn = psycopg.Connection[TupleRow]
WATCH = [
    WatchItem("INE002A01018", "Reliance Industries Limited", "RELIANCE"),
    WatchItem("INE009A01021", "Infosys Limited", "INFY"),
]


def test_parse_rss_drops_non_https_links() -> None:
    items = parse_feed((FIXTURES / "feed_rss.xml").read_bytes())
    assert [i.url for i in items] == [
        "https://news.example.com/a1",
        "https://news.example.com/a2",
        "https://news.example.com/a3",
    ]
    assert items[0].publisher == "Example Markets"
    assert items[0].published_at is not None


def test_parse_atom() -> None:
    [item] = parse_feed((FIXTURES / "feed_atom.xml").read_bytes())
    assert item.title == "Infosys raises guidance"


def test_entity_expansion_is_rejected() -> None:
    with pytest.raises(EntitiesForbidden):
        parse_feed((FIXTURES / "feed_bomb.xml").read_bytes())


def test_matching_by_symbol_and_name() -> None:
    items = parse_feed((FIXTURES / "feed_rss.xml").read_bytes())
    assert name_key("Reliance Industries Limited") == "reliance"
    assert match_headline(items[0], WATCH) == ("INE002A01018", "name")
    assert match_headline(items[1], WATCH) == ("INE009A01021", "symbol")
    assert match_headline(items[2], WATCH) is None


@pytest.mark.integration
def test_store_and_digest(db: Conn) -> None:
    _load_securities(db)
    db.execute("INSERT INTO watchlist (isin) VALUES ('INE002A01018'), ('INE009A01021')")
    watch = watchlist(db)
    items = parse_feed((FIXTURES / "feed_rss.xml").read_bytes())
    assert store_headlines(db, items, watch, feed="rss") == (2, 2)
    assert store_headlines(db, items, watch, feed="rss") == (0, 2)  # no duplicates
    assert build_headline_digests(db, date(2026, 11, 18)) == 2
    row = db.execute(
        "SELECT summary, item_urls FROM news_digests WHERE isin = 'INE002A01018'"
    ).fetchone()
    assert row == (
        "1 headline(s): Reliance Industries Q2 profit rises 9%",
        ["https://news.example.com/a1"],
    )
