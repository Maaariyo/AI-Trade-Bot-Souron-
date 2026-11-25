"""Code checks on every guidance row (SPEC section 6; Phase 1b).

A row is QUOTE_VERIFIED only if (1) its quote appears verbatim in the stored
PDF text and (2) its stated target number(s) appear in that quote. Matching
ignores case, whitespace and line breaks, and treats typographic quotes and
dashes as plain ones, because PDF text breaks lines and words unpredictably.
Rows that fail stay EXTRACTED with a flag saying why.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Typographic quotes, dashes, minus and no-break space -> ASCII (by code point).
_TRANSLATE = str.maketrans(
    {
        0x2018: "'",
        0x2019: "'",
        0x201C: '"',
        0x201D: '"',
        0x2013: "-",
        0x2014: "-",
        0x2212: "-",
        0x00A0: " ",
    }
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Stated unit -> (canonical unit, multiplier)
_CANONICAL: dict[str, tuple[str, Decimal]] = {
    "percent": ("percent", Decimal(1)),
    "inr_crore": ("paise", Decimal(10_000_000) * 100),
    "inr_lakh": ("paise", Decimal(100_000) * 100),
    "inr": ("paise", Decimal(100)),
    "times": ("ratio", Decimal(1)),
}


def canonical(value: Decimal, unit_stated: str) -> tuple[Decimal, str]:
    """A stated value in canonical units: percent, paise or ratio."""
    unit, factor = _CANONICAL[unit_stated]
    return value * factor, unit


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE).lower()
    return re.sub(r"\s+", "", text)


def numbers_in(text: str) -> set[Decimal]:
    out: set[Decimal] = set()
    for raw in _NUMBER.findall(unicodedata.normalize("NFKC", text)):
        try:
            out.add(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            continue
    return out


@dataclass(frozen=True)
class CheckResult:
    verified: bool
    page_no: int | None
    flag: str | None


def check_quote(
    quote: str,
    pages: list[str],
    targets: list[Decimal],
    *,
    claimed_page: int | None = None,
) -> CheckResult:
    """Verify one row against the document's page texts (page 1 is pages[0])."""
    needle = normalise(quote)
    if len(needle) < 12:
        return CheckResult(False, claimed_page, "quote too short to verify")
    found = next((i for i, p in enumerate(pages, start=1) if needle in normalise(p)), None)
    if found is None:
        # A quote can straddle a page break.
        if needle in normalise(" ".join(pages)):
            found = claimed_page
        else:
            return CheckResult(False, claimed_page, "quote not found in document")
    in_quote = numbers_in(quote)
    missing = [t for t in targets if t not in in_quote]
    if missing:
        listed = ", ".join(str(m) for m in missing)
        return CheckResult(False, found, f"target {listed} not in quote")
    note = None
    if claimed_page is not None and found is not None and found != claimed_page:
        note = f"page corrected from {claimed_page} to {found}"
    return CheckResult(True, found, note)
