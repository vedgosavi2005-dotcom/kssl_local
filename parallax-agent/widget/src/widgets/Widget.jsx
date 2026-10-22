import { useMemo, useRef, useState } from "react";
import Chart from "./Chart.jsx";
import D3Chart from "./D3Chart.jsx";
import { fmt, formatCell, humanize } from "../format.js";
import { aggregateField, applyFilters, colType, records } from "./transform.js";
import { renderMarkdown } from "../markdown.jsx";

const SPAN = { full: 12, half: 6, third: 4 };
const CATEGORY_FORMS = ["bar", "line", "area"];
const SORTS = ["value_desc", "value_asc", "x_asc"];
const SORT_LABEL = { value_desc: "Sort: high to low", value_asc: "Sort: low to high", x_asc: "Sort: by label", none: "Sort: as designed" };

/* One card on the canvas grid. Rows are filtered by the view's filter row, the click
   cross-filters and the widget's own subset (e.g. only Healthcare) before anything is
   drawn, so every widget agrees. The toolbar edits the card in place -- chart type,
   orientation, stacking, sort, table view, full screen, CSV and PNG -- without asking the
   model again. */
export default function Widget({ widget: designed, data, filters, cross, onAction, onZoom, zoomed }) {
  const [edit, setEdit] = useState({});
  const widget = useMemo(() => ({ ...designed, ...edit }), [designed, edit]);
  const result = data[widget.result_id];
  const rows = useMemo(() => {
    if (!result) return [];
    let rs = applyFilters(records(result), result, filters, cross);
    if (widget.filter_field) rs = rs.filter((r) => String(r[widget.filter_field]) === String(widget.filter_value));
    return rs;
  }, [result, filters, cross, widget.filter_field, widget.filter_value]);
  const span = SPAN[widget.width] || 12;
  const chartApi = useRef(null);
  const bodyRef = useRef(null);

  const clickable = widget.click && widget.click.action !== "none";
  const act = ({ category, seriesName, row }) => {
    if (!clickable) return;
    const c = widget.click;
    let value = null;
    if (c.field === widget.x) value = category;
    else if (c.field === widget.series) value = seriesName;
    else if (row) value = row[c.field];
    if (value == null && row) value = row[c.field];
    if (value == null) return;
    onAction(c, value);
  };

  const isChart = !["kpi", "text", "table", "comparison"].includes(designed.type);
  const showTable = !!(edit.asTable && result);
  let body;
  if (widget.type === "kpi") body = <Kpis widget={widget} data={data} filters={filters} cross={cross} />;
  else if (widget.type === "text") body = <div className="pa-w-text">{renderMarkdown(widget.text)}</div>;
  else if (!result) body = <div className="pa-w-empty">Missing data</div>;
  else if (!rows.length) body = <div className="pa-w-empty">No rows match the current filters</div>;
  else if (widget.type === "table" || showTable) body = <Table widget={widget} result={result} rows={rows} onRow={clickable ? (row) => act({ row, category: row[widget.x], seriesName: row[widget.series] }) : null} />;
  else if (widget.type === "comparison") body = <Comparison widget={widget} result={result} rows={rows} />;
  else if (widget.type === "network" || widget.type === "treemap") {
    body = <D3Chart widget={widget} rows={rows} height={zoomed ? 620 : widget.type === "network" ? 480 : 340} onMark={clickable ? act : null} />;
  } else {
    const h = zoomed ? 600 : widget.type === "sankey" ? 400 : widget.type === "bar" && widget.orientation === "horizontal"
      ? Math.max(200, Math.min(560, 26 * new Set(rows.map((r) => r[widget.x])).size + 60))
      : span === 12 ? 300 : 260;
    body = <Chart widget={widget} rows={rows} height={h} onMark={clickable ? act : null} onReady={(api) => { chartApi.current = api; }} />;
  }

  const fileName = (ext) => `${(widget.title || "parallax-view").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase()}.${ext}`;
  const downloadCsv = () => {
    const cols = result.columns.map((c) => c.name);
    const esc = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
    const csv = [cols.map(humanize).join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
    download(new Blob([csv], { type: "text/csv" }), fileName("csv"));
  };
  const downloadPng = async () => {
    if (chartApi.current) {
      const url = chartApi.current.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#161618" });
      download(await (await fetch(url)).blob(), fileName("png"));
      return;
    }
    const svg = bodyRef.current && bodyRef.current.querySelector("svg");
    if (svg) download(await svgToPng(svg), fileName("png"));
  };
  const cycleSort = () => setEdit((e) => ({ ...e, sort: SORTS[(SORTS.indexOf(e.sort || designed.sort) + 1) % SORTS.length] }));

  return (
    <section className={`pa-w${widget.type === "kpi" ? " pa-w-kpi" : ""}${zoomed ? " pa-w-zoomed" : ""}`} style={zoomed ? undefined : { gridColumn: `span ${span}` }}>
      {widget.type !== "kpi" && (
        <header className="pa-w-head">
          <div className="pa-w-headtext">
            <div className="pa-w-title">{widget.title}</div>
            {widget.subtitle ? <div className="pa-w-sub">{widget.subtitle}</div> : null}
          </div>
          {widget.type !== "text" && result ? (
            <div className="pa-w-tools" role="toolbar" aria-label="Edit this chart">
              {isChart && CATEGORY_FORMS.includes(designed.type) && !showTable
                ? CATEGORY_FORMS.map((t) => (
                    <button className={`pa-fbtn${widget.type === t ? " on" : ""}`} key={t} onClick={() => setEdit((e) => ({ ...e, type: t }))} title={`Show as ${t}`} type="button">{t}</button>
                  ))
                : null}
              {designed.type === "donut" && !showTable ? (
                <button className="pa-fbtn" onClick={() => setEdit((e) => ({ ...e, type: e.type === "bar" ? undefined : "bar", sort: "value_desc" }))} title="Switch between donut and bars" type="button">
                  {widget.type === "bar" ? "donut" : "bars"}
                </button>
              ) : null}
              {widget.type === "bar" && !showTable ? (
                <button className="pa-fbtn" onClick={() => setEdit((e) => ({ ...e, orientation: widget.orientation === "horizontal" ? "vertical" : "horizontal" }))} title="Rotate" type="button">⟲</button>
              ) : null}
              {(widget.type === "bar" || widget.type === "area") && widget.series && !showTable ? (
                <button className={`pa-fbtn${widget.stacked ? " on" : ""}`} onClick={() => setEdit((e) => ({ ...e, stacked: !widget.stacked }))} title="Stack or group the series" type="button">stack</button>
              ) : null}
              {["bar", "donut"].includes(widget.type) && !showTable ? (
                <button className="pa-fbtn" onClick={cycleSort} title={SORT_LABEL[widget.sort] || "Sort"} type="button">⇅</button>
              ) : null}
              {isChart || designed.type === "comparison" ? (
                <button className={`pa-fbtn${showTable ? " on" : ""}`} onClick={() => setEdit((e) => ({ ...e, asTable: !e.asTable }))} title="Show the numbers as a table" type="button">table</button>
              ) : null}
              <button className="pa-fbtn" onClick={downloadCsv} title="Download the data (CSV)" type="button">csv</button>
              {isChart && !showTable ? <button className="pa-fbtn" onClick={downloadPng} title="Download the chart (PNG)" type="button">png</button> : null}
              {onZoom ? (
                <button className="pa-fbtn" onClick={() => onZoom(zoomed ? null : designed.id)} title={zoomed ? "Exit full screen" : "Full screen"} type="button">{zoomed ? "✕" : "⤢"}</button>
              ) : null}
            </div>
          ) : null}
        </header>
      )}
      <div ref={bodyRef}>{body}</div>
      {clickable && widget.type !== "kpi" && !showTable ? <div className="pa-w-hint">{hint(widget.click)}</div> : null}
    </section>
  );
}

function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 500);
}

function svgToPng(svg) {
  const r = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(clone))}`;
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = r.width * 2;
      c.height = r.height * 2;
      const g = c.getContext("2d");
      g.fillStyle = "#161618";
      g.fillRect(0, 0, c.width, c.height);
      g.scale(2, 2);
      g.drawImage(img, 0, 0, r.width, r.height);
      c.toBlob((b) => (b ? resolve(b) : reject(new Error("png failed"))), "image/png");
    };
    img.onerror = reject;
    img.src = src;
  });
}

function hint(c) {
  if (c.action === "filter") return `Click a mark to filter the view by ${humanize(c.field).toLowerCase()}`;
  if (c.action === "ask") return "Click a mark to ask a follow-up about it";
  if (c.action === "navigate") return "Click to open it in the platform";
  return "";
}

function Kpis({ widget, data, filters, cross }) {
  return (
    <div className="pa-kpis">
      {(widget.kpis || []).map((k, i) => {
        const result = data[k.result_id];
        let rows = result ? applyFilters(records(result), result, filters, cross) : [];
        if (k.filter_field) rows = rows.filter((r) => String(r[k.filter_field]) === String(k.filter_value));
        const v = aggregateField(rows, k.field, k.aggregate || "sum");
        return (
          <div className="pa-kpi" key={i}>
            <div className="pa-kpi-label">{k.label}</div>
            <div className="pa-kpi-value">{fmt(v, k.format, true)}</div>
            {k.note ? <div className="pa-kpi-note">{k.note}</div> : null}
          </div>
        );
      })}
    </div>
  );
}

function Table({ widget, result, rows, onRow }) {
  const cols = (widget.columns && widget.columns.length && widget.type === "table" ? widget.columns : result.columns.map((c) => c.name)).filter(
    (c) => colType(result, c),
  );
  const [sort, setSort] = useState(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const out = [...rows];
    out.sort((a, b) => {
      const x = a[sort.col];
      const y = b[sort.col];
      if (x == null) return 1;
      if (y == null) return -1;
      const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return sort.dir * r;
    });
    return out;
  }, [rows, sort]);
  const shown = sorted.slice(0, 200);
  return (
    <div className="pa-table-wrap">
      <table className="pa-table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                className={colType(result, c) === "number" ? "num" : ""}
                key={c}
                onClick={() => setSort((s) => ({ col: c, dir: s && s.col === c ? -s.dir : colType(result, c) === "number" ? -1 : 1 }))}
              >
                {humanize(c)}
                {sort && sort.col === c ? (sort.dir > 0 ? " ↑" : " ↓") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr className={onRow ? "pa-row-click" : ""} key={i} onClick={onRow ? () => onRow(r) : undefined}>
              {cols.map((c) => {
                const t = colType(result, c);
                return (
                  <td className={t === "number" ? "num" : ""} key={c} title={t === "text" ? String(r[c] ?? "") : undefined}>
                    {t === "number" && widget.format && widget.y && widget.y.includes(c) ? fmt(r[c], widget.format, false) : formatCell(r[c], t)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > shown.length ? <div className="pa-w-note">Showing 200 of {rows.length} rows</div> : null}
    </div>
  );
}

/* Two values per row side by side (e.g. Cummins vs a rival spec sheet). The larger
   value's bar is drawn full; "higher is better" is not assumed, so no winner colouring. */
function Comparison({ widget, result, rows }) {
  const [a, b] = widget.y;
  return (
    <div className="pa-cmp">
      <div className="pa-cmp-head">
        <span />
        <span>{humanize(a)}</span>
        <span>{humanize(b)}</span>
      </div>
      {rows.slice(0, 60).map((r, i) => {
        const va = Number(r[a]);
        const vb = Number(r[b]);
        const m = Math.max(Math.abs(va) || 0, Math.abs(vb) || 0) || 1;
        return (
          <div className="pa-cmp-row" key={i}>
            <span className="pa-cmp-label" title={String(r[widget.x])}>{formatCell(r[widget.x], colType(result, widget.x))}</span>
            <span className="pa-cmp-cell">
              <i style={{ width: `${(100 * (Math.abs(va) || 0)) / m}%` }} className="a" />
              <b>{Number.isNaN(va) ? "–" : fmt(va, widget.format, false)}</b>
            </span>
            <span className="pa-cmp-cell">
              <i style={{ width: `${(100 * (Math.abs(vb) || 0)) / m}%` }} className="b" />
              <b>{Number.isNaN(vb) ? "–" : fmt(vb, widget.format, false)}</b>
            </span>
          </div>
        );
      })}
    </div>
  );
}
