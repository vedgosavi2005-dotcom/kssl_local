import { useEffect, useRef, useState } from "react";
import { buildOption } from "./options.js";
import { rowFor } from "./transform.js";

let echartsPromise = null;
const loadEcharts = () => (echartsPromise ||= import("./echarts-setup.js").then((m) => m.default));

/* One ECharts instance per widget. A click resolves to {value, row}: the clicked
   category / series value and, where it can be found, the row behind the mark (so a
   navigate action can read an id column such as comp_id). */
export default function Chart({ widget, rows, height, onMark, onReady }) {
  const el = useRef(null);
  const chart = useRef(null);
  const [failed, setFailed] = useState("");
  const latest = useRef({ widget, rows, onMark, onReady });
  latest.current = { widget, rows, onMark, onReady };

  useEffect(() => {
    let disposed = false;
    let ro;
    loadEcharts()
      .then((echarts) => {
        if (disposed || !el.current) return;
        chart.current = echarts.init(el.current, null, { renderer: "canvas" });
        if (latest.current.onReady) latest.current.onReady(chart.current); // PNG export
        chart.current.on("click", (p) => {
          const { widget: w, rows: rs, onMark: cb } = latest.current;
          if (!cb) return;
          if (w.type === "scatter") return cb({ row: p.data && p.data.row, category: p.data && p.data.row && p.data.row[w.x], seriesName: p.seriesName });
          if (w.type === "heatmap") {
            const opt = chart.current.getOption();
            const xv = opt.xAxis[0].data[p.value[0]];
            const yv = opt.yAxis[0].data[p.value[1]];
            return cb({ category: xv, seriesName: yv, row: rowFor(rs, { ...w, series: w.series }, xv, yv) });
          }
          if (w.type === "sankey") {
            const isEdge = p.dataType === "edge";
            const src = isEdge ? String(p.data.source).trim() : String(p.name).endsWith(" ") ? String(p.name).trim() : null;
            const dst = isEdge ? p.data.target : src ? null : p.name;
            return cb({ category: src, seriesName: dst, row: rs.find((r) => (src == null || String(r[w.x]) === src) && (dst == null || String(r[w.series]) === dst)) || null });
          }
          const category = p.name;
          const seriesName = w.series ? p.seriesName : null;
          cb({ category, seriesName, row: rowFor(rs, w, category, seriesName) });
        });
        ro = new ResizeObserver(() => chart.current && chart.current.resize());
        ro.observe(el.current);
        draw();
      })
      .catch((e) => setFailed(String(e && e.message ? e.message : e)));
    return () => {
      disposed = true;
      if (ro) ro.disconnect();
      if (chart.current) chart.current.dispose();
      chart.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function draw() {
    if (!chart.current) return;
    try {
      const opt = buildOption(latest.current.widget, latest.current.rows);
      if (opt) chart.current.setOption(opt, true);
      setFailed("");
    } catch (e) {
      setFailed(String(e && e.message ? e.message : e));
    }
  }

  useEffect(draw, [widget, rows]);
  useEffect(() => {
    if (chart.current) chart.current.resize();
  }, [height]);

  if (failed) return <div className="pa-w-empty">Chart could not render: {failed}</div>;
  return (
    <div
      className={`pa-chart${widget.click && widget.click.action !== "none" ? " pa-clickable" : ""}`}
      ref={el}
      style={{ height }}
    />
  );
}
