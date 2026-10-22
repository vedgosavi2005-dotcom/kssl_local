/* D3 renderers for the two rich forms ECharts does not do as well: a force-directed
   network (who is connected to whom) and a treemap (part-to-whole over two levels).
   Same visual rules as every other chart: product palette and ink tokens, surface gaps
   instead of strokes, labels in ink (never the series colour), a tooltip on every mark. */
import { drag } from "d3-drag";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";
import { select } from "d3-selection";
import { zoom } from "d3-zoom";
import { fmt, humanize } from "../format.js";
import { FONT, INK, MONO, OTHER, SURFACE, colorMap, inkOn } from "./palette.js";


function tooltip(container) {
  const tip = document.createElement("div");
  tip.className = "pa-d3-tip";
  tip.style.display = "none";
  container.appendChild(tip);
  return {
    show(ev, lines) {
      tip.replaceChildren(
        ...lines.map(([strong, rest], i) => {
          const row = document.createElement("div");
          if (i === 0) row.className = "h";
          const b = document.createElement("b");
          b.textContent = strong;
          row.appendChild(b);
          if (rest) {
            const s = document.createElement("span");
            s.textContent = ` ${rest}`;
            row.appendChild(s);
          }
          return row;
        }),
      );
      const r = container.getBoundingClientRect();
      tip.style.display = "block";
      const x = Math.min(ev.clientX - r.left + 14, r.width - tip.offsetWidth - 6);
      tip.style.left = `${Math.max(4, x)}px`;
      tip.style.top = `${Math.max(4, ev.clientY - r.top + 12)}px`;
    },
    hide() {
      tip.style.display = "none";
    },
    el: tip,
  };
}

const weightOf = (w, r) => (w.y && w.y.length ? Number(r[w.y[0]]) || 0 : 1);

export function renderNetwork(container, w, rows, width, height, onMark) {
  const sources = new Map();
  const targets = new Map();
  const links = [];
  for (const r of rows.slice(0, 400)) {
    const s = r[w.x];
    const t = r[w.series];
    if (s == null || t == null) continue;
    const sk = `s:${s}`;
    const tk = String(s) === String(t) ? sk : `t:${t}`;
    if (!sources.has(sk)) sources.set(sk, { id: sk, name: String(s), kind: "source", degree: 0, row: r });
    if (tk !== sk && !targets.has(tk)) targets.set(tk, { id: tk, name: String(t), kind: "target", degree: 0, row: r });
    links.push({ source: sk, target: tk, weight: weightOf(w, r), row: r });
  }
  const nodes = [...sources.values(), ...targets.values()];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  links.forEach((l) => {
    byId.get(l.source).degree += 1;
    byId.get(l.target).degree += 1;
  });
  const colors = colorMap([...sources.values()].map((n) => n.name));
  const hl = w.highlight ? String(w.highlight) : "";
  const maxW = Math.max(1, ...links.map((l) => l.weight));
  const radius = (n) => (n.kind === "source" ? 7 + Math.min(9, Math.sqrt(n.degree) * 1.6) : 3.5 + Math.min(5, n.degree));

  const sim = forceSimulation(nodes)
    .force("link", forceLink(links).id((d) => d.id).distance((l) => 40 + 30 / Math.sqrt(byId.get(l.source.id || l.source).degree || 1)).strength(0.6))
    .force("charge", forceManyBody().strength((d) => (d.kind === "source" ? -320 : -60)))
    .force("collide", forceCollide().radius((d) => radius(d) + 3))
    .force("center", forceCenter(width / 2, height / 2))
    .force("x", forceX(width / 2).strength(0.05))
    .force("y", forceY(height / 2).strength(0.08))
    .stop();
  for (let i = 0; i < 320; i += 1) sim.tick();

  const svg = select(container).append("svg").attr("width", width).attr("height", height).attr("role", "img")
    .attr("aria-label", `network of ${sources.size} ${humanize(w.x)} and ${targets.size} ${humanize(w.series)}`);
  const g = svg.append("g");
  svg.call(zoom().scaleExtent([0.4, 4]).on("zoom", (ev) => g.attr("transform", ev.transform)));

  const tip = tooltip(container);
  const link = g.append("g").selectAll("line").data(links).join("line")
    .attr("stroke", INK.axis).attr("stroke-opacity", 0.75)
    .attr("stroke-width", (l) => 1 + 2 * (l.weight / maxW));
  const node = g.append("g").selectAll("circle").data(nodes).join("circle")
    .attr("r", (n) => radius(n) + (hl && n.name === hl ? 3 : 0))
    .attr("fill", (n) => (n.kind === "source" ? colors[n.name] || OTHER : "#5c5c63"))
    .attr("stroke", SURFACE).attr("stroke-width", 2)
    .style("cursor", onMark ? "pointer" : "default");
  const labelled = nodes.filter((n) => n.kind === "source" || n.degree >= 2 || nodes.length <= 36);
  const label = g.append("g").selectAll("text").data(labelled).join("text")
    .text((n) => (n.name.length > 28 ? `${n.name.slice(0, 27)}…` : n.name))
    .attr("font-family", (n) => (n.kind === "source" ? MONO : FONT))
    .attr("font-size", (n) => (n.kind === "source" ? 11 : 10))
    .attr("fill", (n) => (n.kind === "source" ? INK.primary : INK.muted))
    .attr("paint-order", "stroke").attr("stroke", SURFACE).attr("stroke-width", 3)
    .style("pointer-events", "none");

  const place = () => {
    link.attr("x1", (l) => l.source.x).attr("y1", (l) => l.source.y).attr("x2", (l) => l.target.x).attr("y2", (l) => l.target.y);
    node.attr("cx", (n) => n.x).attr("cy", (n) => n.y);
    label.attr("x", (n) => n.x + radius(n) + 4).attr("y", (n) => n.y + 3.5);
  };
  place();

  const neighbours = (n) => new Set(links.filter((l) => l.source === n || l.target === n).flatMap((l) => [l.source.id, l.target.id]));
  node
    .on("pointermove", (ev, n) => {
      const nb = neighbours(n);
      node.attr("opacity", (m) => (nb.has(m.id) ? 1 : 0.25));
      link.attr("stroke-opacity", (l) => (l.source === n || l.target === n ? 1 : 0.15));
      const partners = links.filter((l) => l.source === n || l.target === n).map((l) => (l.source === n ? l.target.name : l.source.name));
      tip.show(ev, [[n.name, n.kind === "source" ? humanize(w.x) : humanize(w.series)], [String(n.degree), n.degree === 1 ? "connection" : "connections"],
        ...partners.slice(0, 6).map((p) => [p, ""]), ...(partners.length > 6 ? [[`+${partners.length - 6} more`, ""]] : [])]);
    })
    .on("pointerleave", () => {
      node.attr("opacity", 1);
      link.attr("stroke-opacity", 0.75);
      tip.hide();
    })
    .on("click", (ev, n) => {
      if (!onMark) return;
      onMark({ category: n.kind === "source" ? n.name : null, seriesName: n.kind === "target" ? n.name : null, row: n.row });
    })
    .call(drag()
      .on("drag", (ev, n) => {
        n.x = ev.x;
        n.y = ev.y;
        place();
      }));
  return () => {
    sim.stop();
    tip.el.remove();
  };
}

export function renderTreemap(container, w, rows, width, height, onMark) {
  const agg = w.aggregate || "sum";
  const groups = new Map();
  for (const r of rows) {
    const p = r[w.x] == null ? "(none)" : String(r[w.x]);
    const c = w.series ? (r[w.series] == null ? "(none)" : String(r[w.series])) : p;
    if (!groups.has(p)) groups.set(p, new Map());
    const g = groups.get(p);
    const cur = g.get(c) || { value: 0, n: 0, row: r };
    cur.value += agg === "count" || !w.y.length ? 1 : Number(r[w.y[0]]) || 0;
    cur.n += 1;
    g.set(c, cur);
  }
  const data = {
    name: "root",
    children: [...groups.entries()].map(([p, kids]) => ({
      name: p,
      children: [...kids.entries()].map(([c, v]) => ({ name: c, value: agg === "avg" ? v.value / v.n : v.value, row: v.row, parent: p })),
    })),
  };
  const root = hierarchy(data).sum((d) => (d.value > 0 ? d.value : 0)).sort((a, b) => b.value - a.value);
  treemap().tile(treemapSquarify).size([width, height]).paddingInner(2).paddingOuter(0)
    .paddingTop((d) => (d.depth === 1 && w.series ? 18 : 0))(root);
  const colors = colorMap(root.children ? root.children.map((d) => d.data.name) : []);
  const total = root.value || 1;

  const svg = select(container).append("svg").attr("width", width).attr("height", height).attr("role", "img")
    .attr("aria-label", `treemap of ${humanize(w.y[0] || "count")} by ${humanize(w.x)}`);
  const tip = tooltip(container);

  if (w.series) {
    const heads = svg.append("g").selectAll("g").data(root.children || []).join("g");
    heads.append("rect").attr("x", (d) => d.x0).attr("y", (d) => d.y0).attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0)).attr("fill", "#1c1c1f");
    heads.append("text").attr("x", (d) => d.x0 + 4).attr("y", (d) => d.y0 + 12)
      .text((d) => (d.x1 - d.x0 > 60 ? `${d.data.name}  ${fmt(d.value, w.format, true)}` : ""))
      .attr("font-family", MONO).attr("font-size", 10).attr("letter-spacing", ".08em").attr("fill", INK.secondary);
  }
  const leaves = svg.append("g").selectAll("g").data(root.leaves()).join("g").attr("transform", (d) => `translate(${d.x0},${d.y0})`)
    .style("cursor", onMark ? "pointer" : "default");
  leaves.append("rect").attr("width", (d) => Math.max(0, d.x1 - d.x0)).attr("height", (d) => Math.max(0, d.y1 - d.y0))
    .attr("fill", (d) => colors[d.data.parent] || OTHER)
    .attr("fill-opacity", (d) => (w.series ? 0.55 + 0.45 * (d.value / (d.parent.value || 1)) : 0.9));
  leaves.append("text").attr("x", 5).attr("y", 14)
    .text((d) => {
      const wpx = d.x1 - d.x0;
      const hpx = d.y1 - d.y0;
      if (wpx < 46 || hpx < 18) return "";
      const n = d.data.name;
      const max = Math.floor((wpx - 8) / 6.3);
      return n.length > max ? `${n.slice(0, Math.max(1, max - 1))}…` : n;
    })
    .attr("font-family", FONT).attr("font-size", 11).attr("fill", (d) => inkOn(colors[d.data.parent] || OTHER));
  leaves.append("text").attr("x", 5).attr("y", 28)
    .text((d) => (d.x1 - d.x0 >= 46 && d.y1 - d.y0 >= 34 ? fmt(d.value, w.format, true) : ""))
    .attr("font-family", MONO).attr("font-size", 10.5).attr("fill", (d) => inkOn(colors[d.data.parent] || OTHER)).attr("fill-opacity", 0.85);
  leaves
    .on("pointermove", (ev, d) => {
      tip.show(ev, [[fmt(d.value, w.format, false), `${((100 * d.value) / total).toFixed(1)}% of total`], [d.data.name, w.series ? `in ${d.data.parent}` : ""]]);
    })
    .on("pointerleave", () => tip.hide())
    .on("click", (ev, d) => onMark && onMark({ category: d.data.parent, seriesName: w.series ? d.data.name : null, row: d.data.row }));
  return () => tip.el.remove();
}
