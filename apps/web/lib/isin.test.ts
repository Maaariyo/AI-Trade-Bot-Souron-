import { describe, expect, it } from "vitest";

import { isValidIsin } from "./isin";

describe("isValidIsin", () => {
  it("accepts real ISINs", () => {
    expect(isValidIsin("INE002A01018")).toBe(true); // Reliance Industries
    expect(isValidIsin("INE009A01021")).toBe(true); // Infosys
    expect(isValidIsin("US0378331005")).toBe(true); // Apple
  });

  it("rejects a wrong check digit", () => {
    expect(isValidIsin("INE002A01019")).toBe(false);
  });

  it("rejects bad shapes", () => {
    expect(isValidIsin("ine002a01018")).toBe(false);
    expect(isValidIsin("INE002A0101")).toBe(false);
    expect(isValidIsin("")).toBe(false);
  });
});
