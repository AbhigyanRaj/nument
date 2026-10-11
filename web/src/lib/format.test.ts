// Tests that numbers are formatted the same way as the backend's facts.

import { describe, expect, it } from "vitest";

import { csvCell, fmtMoney, fmtPct, fmtTonnes, toCsv } from "./format";

describe("formatters match the backend facts", () => {
  it("formats money, tonnes and percents", () => {
    expect(fmtMoney(1840000.4)).toBe("1,840,000");
    expect(fmtTonnes(410.24)).toBe("410.2");
    expect(fmtPct(7.3)).toBe("7.3");
  });
});

describe("CSV export", () => {
  it("neutralises formula injection in text but keeps negative numbers", () => {
    expect(csvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(csvCell("-cmd")).toBe("'-cmd");
    expect(csvCell(-12.5)).toBe("-12.5");
    expect(csvCell('say "hi", ok')).toBe('"say ""hi"", ok"');
  });

  it("writes a header and rows", () => {
    expect(toCsv([{ a: 1, b: "x" }], ["a", "b"])).toBe("a,b\n1,x\n");
  });
});
