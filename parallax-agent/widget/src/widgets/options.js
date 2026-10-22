/* ECharts option builders, one per widget type. Mark specs follow the dataviz rules:
   bars <= 24px with a 4px rounded data end, 2px lines, >= 8px markers with a surface
   ring, ~10% area wash, hairline recessive grid, one axis, a legend whenever there are
   two or more series, text in ink tokens (never the series colour), and a tooltip on
   every chart. */

import { fmt, humanize } from "../format.js";
import { categorical, domain, heatmap } from "./transform.js";
import { CATEGORICAL, FONT, INK, MONO, MUTED_MARK, OTHER, SEQUENTIAL, SURFACE, colorMap, inkOn, sequentialColor } from "./palette.js";


const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/* tooltip rows: value strong, then a line-key and the series name */
function tipRow(color, name, value) {
  return `<div style="display:flex;align-items:center;gap:8px;margin-top:3px">` +
    `<span style="display:inline-block;width:10px;height:2px;background:${color}"></span>` +
    `<b style="color:${INK.primary};font-weight:600">${esc(value)}</b>` +
    `<span style="color:${INK.muted}">${esc(name)}</span></div>`;
}

const tooltipBase = {
  backgroundColor: "#202024",
  borderColor: "#3a3a40",
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: INK.secondary, fontFamily: FONT, fontSize: 12 },
  extraCssText: "box-shadow:0 8px 24px rgba(0,0,0,.45);border-radius:2px;",
};

function axisStyle(type, extra = {}) {
  return {
    type,
    axisLine: { lineStyle: { color: INK.axis } },
    axisTick: { show: false },
    splitLine: { show: type === "value", lineStyle: { color: INK.grid, width: 1, type: "solid" } },
    axisLabel: { color: INK.muted, fontFamily: MONO, fontSize: 10.5, hideOverlap: true },
    nameTextStyle: { color: INK.muted, fontFamily: MONO, fontSize: 10.5 },
    ...extra,
  };
}

function legend(names, colors, icon) {
  if (names.length < 2) return { show: false };
  return {
    show: true,
    top: 0,
    left: 0,
    type: "scroll",
    icon,
    itemWidth: 12,
    itemHeight: icon === "roundRect" ? 8 : 2,
    textStyle: { color: INK.secondary, fontFamily: FONT, fontSize: 11.5 },
    pageTextStyle: { color: INK.muted },
    pageIconColor: INK.secondary,
    data: names.map((n) => ({ name: n, itemStyle: { color: colors[n] } })),
  };
}

const seriesLabel = (w, name) => (w.series ? name : humanize(name));

export function buildOption(w, rows) {
  const fmtShort = (v) => fmt(v, w.format, true);
  const fmtLong = (v) => fmt(v, w.format, false);

  if (w.type === "bar" || w.type === "line" || w.type === "area") {
    const { categories, series } = categorical(w, rows);
    const names = series.map((s) => seriesLabel(w, s.name));
    const colors = colorMap(names);
    const horizontal = w.type === "bar" && w.orientation === "horizontal";
    const single = series.length === 1;
    const hl = w.highlight ? String(w.highlight) : "";
    const catAxis = axisStyle("category", { data: categories, axisLabel: { ...axisStyle("category").axisLabel, interval: horizontal ? 0 : "auto", width: horizontal ? 190 : 96, overflow: "truncate" } });
    const valAxis = axisStyle("value", { axisLabel: { ...axisStyle("value").axisLabel, formatter: fmtShort } });
    const out = {
      backgroundColor: "transparent",
      textStyle: { fontFamily: FONT },
      animationDuration: 350,
      grid: { left: 4, right: 18, top: series.length > 1 ? 34 : 12, bottom: 4, containLabel: true },
      legend: legend(names, colors, w.type === "bar" ? "roundRect" : "rect"),
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        axisPointer: w.type === "bar" ? { type: "shadow", shadowStyle: { color: "rgba(255,255,255,0.04)" } } : { type: "line", lineStyle: { color: INK.axis } },
        formatter: (params) => {
          const ps = Array.isArray(params) ? params : [params];
          const head = `<div style="color:${INK.primary};font-weight:600;margin-bottom:2px">${esc(ps[0] && ps[0].axisValue)}</div>`;
          return head + ps.filter((p) => p.value != null).map((p) => tipRow(colors[p.seriesName] || p.color, single ? humanize(w.y[0] || "value") : p.seriesName, fmtLong(p.value))).join("");
        },
      },
      xAxis: horizontal ? valAxis : catAxis,
      yAxis: horizontal ? { ...catAxis, inverse: true } : valAxis,
      series: series.map((s, si) => {
        const name = names[si];
        const color = colors[name];
        const base = { name, type: w.type === "area" ? "line" : w.type, data: s.values, emphasis: { focus: "series" } };
        if (w.type === "bar") {
          const data = s.values.map((v, i) => {
            // single series with a highlighted category: the highlight keeps the hue, the rest recede
            if (single && hl) return { value: v, itemStyle: { color: categories[i] === hl ? colorMap([hl])[hl] : MUTED_MARK } };
            return v;
          });
          return {
            ...base,
            data,
            barMaxWidth: 24,
            barGap: "15%",
            stack: w.stacked ? "total" : undefined,
            itemStyle: {
              color,
              borderRadius: w.stacked ? 0 : horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
              borderColor: w.stacked ? SURFACE : undefined,
              borderWidth: w.stacked ? 1 : 0,
            },
          };
        }
        return {
          ...base,
          smooth: false,
          stack: w.type === "area" && w.stacked ? "total" : undefined,
          lineStyle: { width: 2, color, cap: "round", join: "round" },
          itemStyle: { color, borderColor: SURFACE, borderWidth: 2 },
          symbol: "circle",
          symbolSize: 8,
          showSymbol: categories.length <= 24,
          areaStyle: w.type === "area" ? { color, opacity: 0.12 } : undefined,
          endLabel: series.length > 1 && series.length <= 4 ? { show: true, formatter: "{a}", color: INK.secondary, fontFamily: FONT, fontSize: 11 } : undefined,
        };
      }),
    };
    if (series.length > 1 && series.length <= 4 && w.type !== "bar") out.grid.right = 110;
    return out;
  }

  if (w.type === "donut") {
    const { categories, series } = categorical({ ...w, series: "", sort: w.sort === "none" ? "value_desc" : w.sort }, rows);
    let items = categories.map((c, i) => ({ name: c, value: series[0].values[i] })).filter((d) => d.value > 0);
    if (items.length > 7) {
      const rest = items.slice(6).reduce((a, d) => a + d.value, 0);
      items = [...items.slice(0, 6), { name: "Other", value: rest }];
    }
    const colors = colorMap(items.filter((d) => d.name !== "Other").map((d) => d.name));
    colors.Other = OTHER;
    const total = items.reduce((a, d) => a + d.value, 0);
    return {
      backgroundColor: "transparent",
      animationDuration: 350,
      legend: { ...legend(items.map((d) => d.name), colors, "roundRect"), orient: "vertical", left: "58%", top: "middle", type: "scroll",
        formatter: (n) => { const d = items.find((x) => x.name === n); return `${n}  ${total ? ((100 * d.value) / total).toFixed(0) : 0}%`; } },
      tooltip: { ...tooltipBase, trigger: "item", formatter: (p) => tipRow(p.color, `${p.name} · ${p.percent}%`, fmtLong(p.value)) },
      series: [{
        type: "pie",
        radius: ["52%", "78%"],
        center: ["30%", "52%"],
        avoidLabelOverlap: true,
        label: { show: false },
        itemStyle: { borderColor: SURFACE, borderWidth: 2 },
        data: items.map((d) => ({ ...d, itemStyle: { color: colors[d.name] } })),
      }],
    };
  }

  if (w.type === "scatter") {
    const y = w.y[0];
    const groups = w.series ? domain(rows, w.series, "x_asc") : ["all"];
    // all-pairs colour rule: at most 3 hues on a scatter; a highlight reduces it to accent vs rest
    let colorOf;
    let legendNames;
    if (!w.series) {
      colorOf = () => CATEGORICAL[0];
      legendNames = [];
    } else if (w.highlight && groups.includes(String(w.highlight))) {
      colorOf = (g) => (g === String(w.highlight) ? CATEGORICAL[0] : OTHER);
      legendNames = groups;
    } else if (groups.length <= 3) {
      const m = colorMap(groups);
      colorOf = (g) => m[g];
      legendNames = groups;
    } else {
      const counts = groups.map((g) => [g, rows.filter((r) => String(r[w.series]) === g).length]).sort((a, b) => b[1] - a[1]);
      const top = counts.slice(0, 3).map((c) => c[0]);
      const m = colorMap(top);
      colorOf = (g) => m[g] || OTHER;
      legendNames = groups;
    }
    const colors = Object.fromEntries(groups.map((g) => [g, colorOf(g)]));
    const sizeField = w.size;
    const sizes = sizeField ? rows.map((r) => Number(r[sizeField]) || 0) : [];
    const smax = Math.max(1, ...sizes);
    return {
      backgroundColor: "transparent",
      animationDuration: 350,
      grid: { left: 8, right: 22, top: legendNames.length > 1 ? 34 : 14, bottom: 26, containLabel: true },
      legend: legend(legendNames, colors, "circle"),
      tooltip: {
        ...tooltipBase,
        trigger: "item",
        formatter: (p) => {
          const r = p.data.row;
          const head = w.label ? `<div style="color:${INK.primary};font-weight:600">${esc(r[w.label])}</div>` : "";
          return head + (w.series ? `<div style="color:${INK.muted}">${esc(r[w.series])}</div>` : "") +
            tipRow(p.color, humanize(w.x), fmt(r[w.x], "number", false)) + tipRow(p.color, humanize(y), fmtLong(r[y]));
        },
      },
      xAxis: axisStyle("value", { name: humanize(w.x), nameLocation: "middle", nameGap: 24, scale: true,
        splitLine: { show: true, lineStyle: { color: INK.grid } }, axisLabel: { ...axisStyle("value").axisLabel, formatter: (v) => fmt(v, "number", true) } }),
      yAxis: axisStyle("value", { name: humanize(y), scale: true, axisLabel: { ...axisStyle("value").axisLabel, formatter: fmtShort } }),
      series: groups.map((g) => ({
        name: g,
        type: "scatter",
        z: w.highlight && g === String(w.highlight) ? 5 : 2,
        symbolSize: (val, p) => (sizeField ? 8 + 16 * Math.sqrt((Number(p.data.row[sizeField]) || 0) / smax) : w.highlight && g === String(w.highlight) ? 11 : 9),
        itemStyle: { color: colors[g], borderColor: SURFACE, borderWidth: 1.5, opacity: 0.95 },
        emphasis: { scale: 1.3 },
        data: rows
          .filter((r) => (w.series ? String(r[w.series]) === g : true) && r[w.x] != null && r[y] != null)
          .map((r) => ({ value: [Number(r[w.x]), Number(r[y])], row: r })),
      })),
    };
  }

  if (w.type === "sankey") {
    const agg = w.aggregate || "sum";
    const flows = new Map();
    for (const r of rows) {
      const a = r[w.x] == null ? "(none)" : String(r[w.x]);
      const b = r[w.series] == null ? "(none)" : String(r[w.series]);
      if (a === b) continue;
      const k = `${a}\u0000${b}`;
      const v = agg === "count" || !w.y.length ? 1 : Number(r[w.y[0]]) || 0;
      flows.set(k, (flows.get(k) || 0) + v);
    }
    const links = [...flows.entries()].filter(([, v]) => v > 0).sort((x, y) => y[1] - x[1]).slice(0, 60)
      .map(([k, v]) => { const [a, b] = k.split("\u0000"); return { source: `${a} `, target: b, value: v }; });
    const left = [...new Set(links.map((l) => l.source))];
    const right = [...new Set(links.map((l) => l.target))];
    const colors = colorMap(left.map((n) => n.trim()));
    return {
      backgroundColor: "transparent",
      animationDuration: 350,
      tooltip: { ...tooltipBase, trigger: "item", formatter: (p) => (p.dataType === "edge"
        ? tipRow(colors[String(p.data.source).trim()] || OTHER, `${String(p.data.source).trim()} → ${p.data.target}`, fmtLong(p.data.value))
        : tipRow(p.color, String(p.name).trim(), fmtLong(p.value))) },
      series: [{
        type: "sankey",
        left: 4, right: 150, top: 8, bottom: 8,
        nodeWidth: 10, nodeGap: 8, draggable: false,
        emphasis: { focus: "adjacency" },
        data: [...left.map((n) => ({ name: n, itemStyle: { color: colors[n.trim()] || OTHER, borderWidth: 0 } })),
               ...right.map((n) => ({ name: n, itemStyle: { color: "#5c5c63", borderWidth: 0 } }))],
        links,
        lineStyle: { color: "gradient", opacity: 0.32, curveness: 0.5 },
        label: { color: INK.secondary, fontFamily: FONT, fontSize: 11, formatter: (p) => String(p.name).trim() },
      }],
    };
  }

  if (w.type === "heatmap") {
    const { xs, ys, cells, max } = heatmap(w, rows);
    return {
      backgroundColor: "transparent",
      animationDuration: 300,
      grid: { left: 4, right: 8, top: 8, bottom: 40, containLabel: true },
      tooltip: { ...tooltipBase, trigger: "item", formatter: (p) => `<div style="color:${INK.primary};font-weight:600">${esc(ys[p.value[1]])} · ${esc(xs[p.value[0]])}</div>` + tipRow(p.color, humanize(w.y[0] || "count"), fmtLong(p.value[2])) },
      xAxis: axisStyle("category", { data: xs, splitArea: { show: false }, axisLabel: { ...axisStyle("category").axisLabel, interval: 0, rotate: xs.length > 6 ? 30 : 0 } }),
      yAxis: axisStyle("category", { data: ys, axisLabel: { ...axisStyle("category").axisLabel, interval: 0 } }),
      visualMap: { show: false, min: 0, max: max || 1, inRange: { color: SEQUENTIAL } },
      series: [{
        type: "heatmap",
        data: cells.map(([xi, yi, v]) => {
          const c = sequentialColor(max ? v / max : 0);
          return { value: [xi, yi, v], label: { color: inkOn(c) } };
        }),
        label: { show: cells.length <= 80, fontFamily: MONO, fontSize: 10.5, formatter: (p) => fmtShort(p.value[2]) },
        itemStyle: { borderColor: SURFACE, borderWidth: 2 },
        emphasis: { itemStyle: { borderColor: INK.primary, borderWidth: 1 } },
      }],
    };
  }
  return null;
}
