import { useEffect, useRef } from "react";
import { useAppState } from "../../state/AppState";
/* The analytics panel of the Market outlook: opens beside the tables when a row is clicked, in the same panel style as
   the tender assessment. It only draws what lib/outlookDetail computed: tiles, a monthly chart, ranked lists, and plain
   lines. A tender row opens that tender on the Tenders page; any other row with a source opens the source. */
const COLORS = ["#e0a020", "#4aa3df", "#3fa86a", "#d8603c"];
const KIND = { segment: "Segment", winner: "Winner", calibre: "Calibre", buyer: "Buyer", driver: "Driver" };

function Chart({ c }) {
  const max = Math.max(1, ...c.rows.flatMap((r) => r.v));
  const W = 420, H = 130, T = 22, pad = 18, bw = (W - pad) / c.rows.length;
  const g = c.names.length;
  const w1 = Math.max(3, Math.min(14, (bw - 4) / g));
  const sum = (rows) => rows.reduce((n, r) => n + r.v.reduce((a, b) => a + b, 0), 0);
  const half = c.rows.length / 2, prior = sum(c.rows.slice(0, half)), now = sum(c.rows.slice(half));
  const midX = pad + half * bw;
  return (
    <div className="ol-chart">
      <svg viewBox={`0 0 ${W} ${H + 22}`} role="img" aria-label={`${c.title}: ${c.dated} dated records`}>
        {[0, 0.5, 1].map((f) => <line key={f} x1={pad} x2={W} y1={H - f * (H - T)} y2={H - f * (H - T)} stroke="currentColor" opacity=".12" />)}
        <text x="0" y={T + 3} fontSize="9" fill="currentColor" opacity=".55">{max}</text>
        {c.halves ? <>
          <line x1={midX} x2={midX} y1="2" y2={H} stroke="currentColor" opacity=".3" strokeDasharray="3 3" />
          <text x={midX - 4} y="11" fontSize="9" textAnchor="end" fill="currentColor" opacity=".7">prior 6 months: {prior}</text>
          <text x={midX + 4} y="11" fontSize="9" fill="currentColor" opacity=".7">last 6 months: {now}</text>
        </> : null}
        {c.rows.map((r, i) => (
          <g key={i} transform={`translate(${pad + i * bw + (bw - w1 * g) / 2},0)`}>
            {r.v.map((v, gi) => <rect key={gi} x={gi * w1} y={H - (v / max) * (H - T)} width={w1 - 1} height={(v / max) * (H - T)} fill={COLORS[gi]} rx="1"><title>{`${r.label}: ${v} ${c.names[gi]}`}</title></rect>)}
            <text x={(w1 * g) / 2} y={H + 13} fontSize="8.5" textAnchor="middle" fill="currentColor" opacity=".6">{r.label.split(" ")[0]}</text>
          </g>
        ))}
      </svg>
      <div className="ol-legend">{c.names.map((n, i) => <span key={n}><i style={{ background: COLORS[i] }} />{n}</span>)}</div>
      {c.note ? <div className="ol-note">{c.note}</div> : null}
    </div>
  );
}

function Row({ r, onTender }) {
  return (
    <div className="olr">
      <div className="olr-h">
        <span className="olr-t">{r.id ? <button type="button" className="olr-tender-link" onClick={() => onTender(r.id)}>{r.title}</button> : r.url ? <a href={r.url} target="_blank" rel="noreferrer">{r.title}</a> : r.title}</span>
        {r.right ? <span className={`olr-r ${r.tone || ""}`}>{r.right}</span> : null}
      </div>
      {r.sub || r.tag || r.date ? <div className="olr-s">{[r.tag, r.sub, r.date].filter(Boolean).join(" · ")}</div> : null}
      {r.fields ? (
        <dl className="olr-f">{r.fields.filter(([, v]) => !/^not stated$/i.test(String(v))).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      ) : null}
      {r.bar != null ? <div className="olr-bar"><i style={{ width: `${Math.max(2, Math.round(r.bar * 100))}%` }} /></div> : null}
    </div>
  );
}

export default function OutlookPanel({ detail, onClose }) {
  const { jumpTo } = useAppState();
  const openTender = (tenderId) => { onClose(); jumpTo("market", "tender", { tenderId }); };
  const scroller = useRef(null);
  /* a new row opens at the top: the box keeps one scroll position, so without this it stays wherever the last row left it */
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 0;
  }, [detail && detail.kind, detail && detail.title]);
  if (!detail) return null;
  return (
    <aside className="ctx ol-panel revealed" aria-label={detail.title}>
      <div className="ctx-scroll" ref={scroller}>
        <div className="ctx-h">
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">✕</button>
            <span className="dirpill dir-watch">{KIND[detail.kind]}</span>
          </div>
          <div className="ct">{detail.title}</div>
          {detail.subtitle ? <div className="ol-sub">{detail.subtitle}</div> : null}
        </div>
        <div className="ctx-sec"><div className="ol-tiles">{detail.tiles.map((t) => <div className="olt" key={t.k}><span>{t.k}</span><b>{t.v}</b>{t.sub ? <em>{t.sub}</em> : null}</div>)}</div></div>
        {detail.charts.map((c) => <div className="ctx-sec" key={c.title}><span className="eyebrow">{c.title}</span><div className="ol-note">{c.sub}</div><Chart c={c} /></div>)}
        {detail.sections.map((s) => {
          const has = (s.rows && s.rows.length) || (s.lines && s.lines.length);
          if (!has && !s.empty) return null;
          return (
            <div className="ctx-sec" key={s.h}>
              <span className="eyebrow">{s.h}</span>
              {s.note ? <div className="ol-note">{s.note}</div> : null}
              {s.lines && s.lines.length ? <ul className="cd-bullets">{s.lines.slice(0, 6).map((l, i) => <li key={i}>{l}</li>)}</ul> : null}
              {s.rows && s.rows.length ? s.rows.map((r, i) => <Row key={i} r={r} onTender={openTender} />) : null}
              {!has ? <div className="ol-note">{s.empty}</div> : null}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
