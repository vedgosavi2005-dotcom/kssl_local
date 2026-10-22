/* Number formatting for KPI tiles, axes, tooltips and tables. */

const UNIT = { kva: " kVA", kw: " kW", liters_per_hour: " L/h", kg: " kg" };

export function compact(n) {
  if (n == null || Number.isNaN(Number(n))) return "–";
  const v = Number(n);
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(a >= 1e10 ? 0 : 1)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e4) return `${(v / 1e3).toFixed(a >= 1e5 ? 0 : 1)}K`;
  return v.toLocaleString("en-US", { maximumFractionDigits: a < 10 ? 2 : 1 });
}

export function full(n) {
  if (n == null || Number.isNaN(Number(n))) return "–";
  const v = Number(n);
  return v.toLocaleString("en-US", { maximumFractionDigits: Math.abs(v) < 10 ? 3 : Math.abs(v) < 1000 ? 2 : 0 });
}

/* `short` for tiles and axes (1.2M), long for tables and tooltips (1,204,553). */
export function fmt(value, format = "number", short = true) {
  if (value == null || value === "") return "–";
  if (format === "text" || typeof value !== "number") return String(value);
  const body = short ? compact(value) : full(value);
  if (format === "usd") return `${value < 0 ? "-" : ""}$${short ? compact(Math.abs(value)) : full(Math.abs(value))}`;
  if (format === "percent") return `${Number(value).toFixed(Math.abs(value) < 10 ? 1 : 0)}%`;
  return body + (UNIT[format] || "");
}

/* "total_value_usd" -> "Total value USD" */
export function humanize(name) {
  const s = String(name || "")
    .replace(/_/g, " ")
    .replace(/\busd\b/gi, "USD")
    .replace(/\bkva\b/gi, "kVA")
    .replace(/\bkw\b/gi, "kW")
    .replace(/\bpct\b/gi, "%")
    .replace(/\bid\b/gi, "ID")
    .trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatCell(value, type) {
  if (value == null) return "–";
  if (type === "number") return full(value);
  if (type === "boolean") return value ? "Yes" : "No";
  return String(value);
}
