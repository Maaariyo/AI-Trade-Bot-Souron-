import { describe, expect, it } from "vitest";

import { formatIndianNumber, formatIST, formatLakhCrore, formatPaise } from "./format";

describe("formatPaise", () => {
  it("uses Indian digit grouping", () => {
    expect(formatPaise(12_345_678_00)).toBe("₹1,23,45,678.00");
  });

  it("handles small and negative amounts", () => {
    expect(formatPaise(5)).toBe("₹0.05");
    expect(formatPaise(-150_00)).toBe("-₹150.00");
  });

  it("rejects non-integer paise", () => {
    expect(() => formatPaise(1.5)).toThrow(RangeError);
  });
});

describe("formatIndianNumber", () => {
  it("groups by lakh and crore", () => {
    expect(formatIndianNumber(123_456_789)).toBe("12,34,56,789");
  });
});

describe("formatLakhCrore", () => {
  it("labels crore, lakh and smaller amounts", () => {
    expect(formatLakhCrore(1_234_500_000_00)).toBe("₹123.45 cr");
    expect(formatLakhCrore(12_345 * 10_000_000 * 100)).toBe("₹12,345.00 cr");
    expect(formatLakhCrore(4_50_000_00)).toBe("₹4.50 lakh");
    expect(formatLakhCrore(45_678_00)).toBe("₹45,678");
    expect(formatLakhCrore(-2_00_00_000_00)).toBe("-₹2.00 cr");
  });
});

describe("formatIST", () => {
  it("converts UTC to IST", () => {
    expect(formatIST(new Date("2026-11-18T15:30:00Z"))).toBe("18-Nov-2026 21:00 IST");
  });

  it("rolls over midnight", () => {
    expect(formatIST(new Date("2026-11-18T18:45:00Z"))).toBe("19-Nov-2026 00:15 IST");
  });
});
