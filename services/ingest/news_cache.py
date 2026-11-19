"""News cache: publisher RSS headlines for the watchlist, and a daily digest.

Only headlines and links are stored, never article text (SPEC section 14).
Feeds are parsed with defusedxml because they are untrusted input. The digest
built here is the 'headlines' method; LLM digests via Claude web search arrive
with the council phases.
"""

import re
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import psycopg
from defusedxml import ElementTree
from psycopg.rows import TupleRow

MAX_FEED_BYTES = 2_000_000
_ATOM = "{http://www.w3.org/2005/Atom}"
_NAME_SUFFIXES = re.compile(r"\b(limited|ltd\.?|india|industries|corporation|corp\.?)\b", re.I)


@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    published_at: datetime | None
    publisher: str | None


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else None


def parse_feed(xml: bytes | str) -> list[Headline]:
    """RSS 2.0 or Atom headlines. Items without an https link are dropped."""
    root = ElementTree.fromstring(xml)
    out: list[Headline] = []
    channel_title = root.findtext("channel/title") or root.findtext(f"{_ATOM}title")
    for item in root.iter("item"):
        out.append(
            Headline(
                title=(item.findtext("title") or "").strip(),
                url=(item.findtext("link") or "").strip(),
                published_at=_parse_time(item.findtext("pubDate")),
                publisher=channel_title,
            )
        )
    for entry in root.iter(f"{_ATOM}entry"):
        link = entry.find(f"{_ATOM}link")
        out.append(
            Headline(
                title=(entry.findtext(f"{_ATOM}title") or "").strip(),
                url=(link.get("href", "") if link is not None else "").strip(),
                published_at=_parse_time(
                    entry.findtext(f"{_ATOM}updated") or entry.findtext(f"{_ATOM}published")
                ),
                publisher=channel_title,
            )
        )
    return [h for h in out if h.title and urlparse(h.url).scheme == "https"]


def fetch_feed(url: str, *, timeout: float = 20.0) -> bytes:
    if urlparse(url).scheme != "https":
        raise ValueError(f"feeds must be https: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "NiveshCouncil/0.1 (personal)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data: bytes = resp.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError(f"feed larger than {MAX_FEED_BYTES} bytes: {url}")
    return data


@dataclass(frozen=True)
class WatchItem:
    isin: str
    name: str
    nse_symbol: str | None


def name_key(name: str) -> str:
    """'Reliance Industries Limited' -> 'reliance'. Used for headline matching."""
    core = _NAME_SUFFIXES.sub(" ", name.lower())
    return " ".join(core.split())


def match_headline(headline: Headline, watch: Iterable[WatchItem]) -> tuple[str, str] | None:
    """(isin, matched_by) for the first watchlist stock the headline names, if any."""
    title = headline.title
    lowered = title.lower()
    for w in watch:
        if w.nse_symbol and re.search(rf"\b{re.escape(w.nse_symbol)}\b", title):
            return w.isin, "symbol"
        key = name_key(w.name)
        if len(key) >= 4 and re.search(rf"\b{re.escape(key)}\b", lowered):
            return w.isin, "name"
    return None


def watchlist(conn: psycopg.Connection[TupleRow]) -> list[WatchItem]:
    rows = conn.execute(
        "SELECT s.isin, s.name, s.nse_symbol FROM watchlist w JOIN securities s USING (isin)"
    ).fetchall()
    return [WatchItem(*r) for r in rows]


def store_headlines(
    conn: psycopg.Connection[TupleRow],
    headlines: Iterable[Headline],
    watch: list[WatchItem],
    *,
    feed: str,
) -> tuple[int, int]:
    """Store matched headlines. Returns (new rows, matched headlines seen)."""
    matched = new = 0
    with conn.transaction():
        for h in headlines:
            m = match_headline(h, watch)
            if m is None:
                continue
            matched += 1
            cur = conn.execute(
                """
                INSERT INTO news_items (url, title, publisher, feed, published_at, isin,
                    matched_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (h.url, h.title, h.publisher, feed, h.published_at, m[0], m[1]),
            )
            new += cur.rowcount
    return new, matched


def build_headline_digests(
    conn: psycopg.Connection[TupleRow], digest_date: date, *, max_items: int = 5
) -> int:
    """One 'headlines' digest per stock with news published on `digest_date` (IST)."""
    rows = conn.execute(
        """
        SELECT isin, array_agg(title ORDER BY published_at DESC),
               array_agg(url ORDER BY published_at DESC)
        FROM news_items
        WHERE isin IS NOT NULL
          AND (published_at AT TIME ZONE 'Asia/Kolkata')::date = %s
        GROUP BY isin
        """,
        (digest_date,),
    ).fetchall()
    with conn.transaction():
        for isin, titles, urls in rows:
            titles, urls = titles[:max_items], urls[:max_items]
            summary = f"{len(titles)} headline(s): " + "; ".join(titles)
            conn.execute(
                """
                INSERT INTO news_digests (isin, digest_date, summary, item_urls, method)
                VALUES (%s, %s, %s, %s, 'headlines')
                ON CONFLICT (isin, digest_date) DO UPDATE SET
                    summary = EXCLUDED.summary, item_urls = EXCLUDED.item_urls,
                    method = EXCLUDED.method, created_at = now()
                WHERE news_digests.method = 'headlines'
                """,
                (isin, digest_date, summary, urls),
            )
    return len(rows)
