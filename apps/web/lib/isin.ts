// ISIN checks for the /stock/[isin] route. Indian equity ISINs start with "IN".

const ISIN_SHAPE = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;

/** True when `value` has a valid ISIN shape and check digit (ISO 6166). */
export function isValidIsin(value: string): boolean {
  if (!ISIN_SHAPE.test(value)) return false;
  const digits = value
    .slice(0, 11)
    .split("")
    .map((ch) => (ch >= "A" && ch <= "Z" ? String(ch.charCodeAt(0) - 55) : ch))
    .join("");
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let d = Number(digits[digits.length - 1 - i]);
    if (i % 2 === 0) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
  }
  const check = (10 - (sum % 10)) % 10;
  return check === Number(value[11]);
}
