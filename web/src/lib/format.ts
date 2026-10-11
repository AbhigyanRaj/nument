// Number formatting (money, tonnes, percent) that matches the backend exactly.

// Number formatting that mirrors the backend's fact formatters (app/core/numbers.py), so KPI
// tiles always show the same figures as the number-checked summary text.

/** Thousands separators, no decimals: 1840000 -> "1,840,000". */
export function fmtMoney(x: number): string {
  return Math.round(x).toLocaleString("en-US");
}

/** Tonnes with one decimal: 410.24 -> "410.2". */
export function fmtTonnes(x: number): string {
  return x.toFixed(1);
}

/** Percent with one decimal, no sign: 7.31 -> "7.3". */
export function fmtPct(x: number): string {
  return x.toFixed(1);
}

export function fmtInt(x: number): string {
  return Math.round(x).toLocaleString("en-US");
}

export function fmtSigned(x: number, format: (n: number) => string): string {
  if (x === 0) return format(0);
  return `${x > 0 ? "+" : "−"}${format(Math.abs(x))}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Neutralise spreadsheet formula injection in text cells; numbers stay numbers. */
export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  let text = String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  if (/[",\n]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function toCsv(rows: Record<string, unknown>[], columns: string[]): string {
  const lines = [columns.join(",")];
  for (const row of rows) lines.push(columns.map((c) => csvCell(row[c])).join(","));
  return `${lines.join("\n")}\n`;
}
