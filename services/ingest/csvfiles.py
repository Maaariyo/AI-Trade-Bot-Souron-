"""Reading owner-downloaded CSV files with loosely specified headers.

Exchange and vendor files differ in header spelling ("ISIN NUMBER", "ISIN_NUMBER",
"ISIN No"). Headers are normalised to upper-case letters and digits, then
matched against aliases. Unknown layouts fail loudly with the headers found.
"""

import csv
import io
import re
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from pathlib import Path


class HeaderError(ValueError):
    pass


def normalise_header(header: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", header.upper())


def read_rows(
    source: Path | str, aliases: Mapping[str, tuple[str, ...]], required: set[str]
) -> Iterator[dict[str, str]]:
    """Yield rows keyed by logical field name. `source` is a path or CSV text."""
    text = source.read_text(encoding="utf-8-sig") if isinstance(source, Path) else source
    reader = csv.reader(io.StringIO(text))
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise HeaderError("empty file") from None
    found = [normalise_header(h) for h in raw_headers]
    index: dict[str, int] = {}
    for logical, names in aliases.items():
        for name in names:
            if name in found:
                index[logical] = found.index(name)
                break
    missing = required - index.keys()
    if missing:
        raise HeaderError(
            f"missing columns {sorted(missing)}; headers found: {[h.strip() for h in raw_headers]}"
        )
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        yield {k: row[i].strip() if i < len(row) else "" for k, i in index.items()}


_DATE_FORMATS = ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%B-%Y")


def parse_date(value: str) -> date | None:
    value = value.strip()
    if not value or value in {"-", "NA", "N.A."}:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.title() if "%b" in fmt else value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value!r}")
