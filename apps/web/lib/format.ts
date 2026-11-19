// Indian formatting rules from CLAUDE.md: money is stored as integer paise,
// shown with Indian digit grouping (Rs 1,23,45,678) and lakh/crore labels;
// timestamps are stored in UTC and shown in IST.

const LAKH = 100_000;
const CRORE = 10_000_000;

function assertPaise(paise: number): void {
  if (!Number.isSafeInteger(paise)) {
    throw new RangeError(`paise must be a safe integer, got ${paise}`);
  }
}

/** ₹1,23,45,678.00 from integer paise. */
export function formatPaise(paise: number, fractionDigits = 2): string {
  assertPaise(paise);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(paise / 100);
}

/** Indian digit grouping without a currency sign: 1,23,45,678. */
export function formatIndianNumber(value: number, fractionDigits = 0): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/** Compact rupees from paise: "₹12.35 cr", "₹4.50 lakh", or "₹45,678" below a lakh. */
export function formatLakhCrore(paise: number): string {
  assertPaise(paise);
  const rupees = paise / 100;
  const sign = rupees < 0 ? "-" : "";
  const abs = Math.abs(rupees);
  if (abs >= CRORE) return `${sign}₹${formatIndianNumber(abs / CRORE, 2)} cr`;
  if (abs >= LAKH) return `${sign}₹${formatIndianNumber(abs / LAKH, 2)} lakh`;
  return `${sign}₹${formatIndianNumber(abs, 0)}`;
}

/** "18-Nov-2026 21:00 IST" for any instant. */
export function formatIST(instant: Date): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")}-${get("month")}-${get("year")} ${get("hour")}:${get("minute")} IST`;
}
