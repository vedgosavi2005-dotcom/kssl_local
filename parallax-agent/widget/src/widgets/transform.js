/* Pure data shaping for the canvas: result sets -> filtered rows -> chart series.
   All aggregation happens here, on the rows the server sent, so a filter re-renders
   instantly without another round trip to the model. */

export function records(result) {
  if (!result) return [];
  const names = result.columns.map((c) => c.name);
  return result.rows.map((r) => {
    const o = {};
    names.forEach((n, i) => {
      o[n] = r[i];
    });
    return o;
  });
}

export const colType = (result, name) => (result && result.columns.find((c) => c.name === name) || {}).type;

/* filters: { field: value } from the filter row; cross: [{ field, value }] from clicks.
   A filter only applies to results that carry its column. */
export function applyFilters(rows, result, filters, cross) {
  const names = new Set((result && result.columns.map((c) => c.name)) || []);
  const active = [
    ...Object.entries(filters || {}).filter(([f, v]) => v != null && v !== "" && names.has(f)),
    ...(cross || []).filter((c) => names.has(c.field)).map((c) => [c.field, c.value]),
  ];
  if (!active.length) return rows;
  return rows.filter((r) => active.every(([f, v]) => String(r[f]) === String(v)));
}

function reduce(values, agg) {
  const nums = values.filter((v) => v != null && !Number.isNaN(Number(v))).map(Number);
  switch (agg) {
    case "count":
      return values.length;
    case "avg":
      return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
    case "min":
      return nums.length ? Math.min(...nums) : null;
    case "max":
      return nums.length ? Math.max(...nums) : null;
    case "none":
      return nums.length ? nums[0] : null;
    case "sum":
    default:
      return nums.length ? nums.reduce((a, b) => a + b, 0) : null;
  }
}

const cmp = (a, b) => {
  const na = Number(a);
  const nb = Number(b);
  if (!Number.isNaN(na) && !Number.isNaN(nb) && a !== "" && b !== "") return na - nb;
  return String(a).localeCompare(String(b));
};

/* Distinct values of a column over ALL rows (unfiltered), in a stable order -- the domain
   colours are assigned from, so a filter never repaints the survivors. */
export function domain(rows, field, sortKey = "x_asc") {
  const seen = [];
  const set = new Set();
  for (const r of rows) {
    const v = r[field] == null ? "(none)" : String(r[field]);
    if (!set.has(v)) {
      set.add(v);
      seen.push(v);
    }
  }
  return sortKey === "x_asc" ? seen.sort(cmp) : seen;
}

/* Categorical series for bar / line / area / donut.
   Long format (series column): one series per series value, y[0] aggregated per x.
   Wide format (no series): one series per y column. aggregate "count" counts rows. */
export function categorical(w, rows) {
  const x = w.x;
  const ys = w.y && w.y.length ? w.y : [];
  const agg = w.aggregate || "sum";
  const byX = new Map();
  for (const r of rows) {
    const k = r[x] == null ? "(none)" : String(r[x]);
    if (!byX.has(k)) byX.set(k, []);
    byX.get(k).push(r);
  }
  let cats = [...byX.keys()];
  let series;
  if (w.series) {
    const names = domain(rows, w.series, "x_asc");
    series = names.map((s) => ({
      name: s,
      values: cats.map((c) => {
        const group = byX.get(c).filter((r) => String(r[w.series] == null ? "(none)" : r[w.series]) === s);
        if (!group.length) return null;
        return agg === "count" ? group.length : reduce(group.map((r) => r[ys[0]]), agg);
      }),
    }));
  } else if (ys.length) {
    series = ys.map((y) => ({ name: y, values: cats.map((c) => reduce(byX.get(c).map((r) => r[y]), agg)) }));
  } else {
    series = [{ name: "count", values: cats.map((c) => byX.get(c).length) }];
  }

  // order the categories
  const total = (i) => series.reduce((a, s) => a + (Number(s.values[i]) || 0), 0);
  let order = cats.map((_, i) => i);
  if (w.sort === "value_desc") order.sort((a, b) => total(b) - total(a));
  else if (w.sort === "value_asc") order.sort((a, b) => total(a) - total(b));
  else if (w.sort === "x_asc" || w.type === "line" || w.type === "area") order.sort((a, b) => cmp(cats[a], cats[b]));
  if (w.limit && w.limit > 0 && order.length > w.limit) order = order.slice(0, w.limit);
  cats = order.map((i) => cats[i]);
  series = series.map((s) => ({ ...s, values: order.map((i) => s.values[i]) }));
  return { categories: cats, series };
}

/* Heatmap cells: x by series (rows), value = aggregate of y[0] (or count). */
export function heatmap(w, rows) {
  const xs = domain(rows, w.x, "x_asc");
  const ysCats = domain(rows, w.series, "x_asc");
  const agg = w.aggregate || "sum";
  const cells = [];
  let max = 0;
  ysCats.forEach((yc, yi) => {
    xs.forEach((xc, xi) => {
      const group = rows.filter((r) => String(r[w.x] ?? "(none)") === xc && String(r[w.series] ?? "(none)") === yc);
      if (!group.length) return;
      const v = agg === "count" || !w.y.length ? group.length : reduce(group.map((r) => r[w.y[0]]), agg);
      if (v == null) return;
      max = Math.max(max, Number(v));
      cells.push([xi, yi, v]);
    });
  });
  return { xs, ys: ysCats, cells, max };
}

export function aggregateField(rows, field, agg) {
  if (agg === "count" && !field) return rows.length;
  return reduce(rows.map((r) => r[field]), agg || "sum");
}

/* The row behind a clicked mark, to read an id column for navigate. */
export function rowFor(rows, w, category, seriesName) {
  return (
    rows.find(
      (r) =>
        String(r[w.x] ?? "(none)") === String(category) &&
        (!w.series || seriesName == null || String(r[w.series] ?? "(none)") === String(seriesName)),
    ) || null
  );
}
