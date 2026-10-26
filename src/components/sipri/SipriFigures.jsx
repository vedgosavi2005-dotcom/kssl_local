/* SIPRI figures (owner 2026-10-26), cited on both sites:
     <SipriArms data cid name />   Company profile: arms revenue, Top-100 rank, arms share, a small trend (data.sipriArms)
     <SipriBudget data country />  Geo country panel: the country's defence spending, share of GDP, a small trend (data.sipriMilex)
   Formatting and the parent / predecessor wording: src/lib/sipri.js. Nothing renders when SIPRI has no figure. */
import { armsView, milexView } from "../../lib/sipri";

function Spark({ bars, w, h, color, title }) {
  if (!bars || bars.length < 2) return null;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={title} style={{ display: "block", flexShrink: 0 }}>
      <title>{title}</title>
      {bars.map((b, i) => (
        <rect key={b.year} x={b.x} y={b.y} width={b.w} height={b.h} rx="1.5" fill={color} opacity={i === bars.length - 1 ? 1 : 0.45} />
      ))}
    </svg>
  );
}

const sparkTitle = (bars, fmt) => bars.map((b) => `${b.year}: ${fmt(b.value)}`).join(", ");

export function SipriArms({ data, cid, name }) {
  const a = data && data.sipriArms ? data.sipriArms[cid] : null;
  const v = armsView(a, name);
  if (!v) return null;
  const mono = { fontFamily: "var(--mono)", fontSize: "11px", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase" };
  return (
    <div
      className="cp-sipri"
      style={{ marginBottom: "20px", background: "var(--d-bg-1)", border: "1px solid var(--d-line)", borderRadius: "6px", padding: "14px 18px" }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
        <span style={{ ...mono, color: "var(--d-txt-3)" }}>Arms revenue · SIPRI Top 100</span>
        <span style={{ fontSize: "12px", color: "var(--d-txt-2)" }}>
          {v.entity}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "16px", marginTop: "8px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "17px", fontWeight: 700, color: "var(--d-txt)" }}>{v.headline}</span>
        <Spark bars={v.bars} w={120} h={28} color="var(--d-txt-2)"
          title={`Arms revenue by year (current US$): ${sparkTitle(v.bars, (x) => `$${Math.round(x)}m`)}`} />
      </div>
      {v.facts.length ? (
        <div style={{ display: "flex", gap: "22px", flexWrap: "wrap", marginTop: "10px", fontSize: "12.5px" }}>
          {v.facts.map(([k, val]) => (
            <span key={k}>
              <span style={{ color: "var(--d-txt-3)" }}>{k} </span>
              <span style={{ color: "var(--d-txt)", fontWeight: 600 }}>{val}</span>
            </span>
          ))}
        </div>
      ) : null}
      {v.note ? <div style={{ marginTop: "8px", fontSize: "12px", fontStyle: "italic", color: "var(--d-txt-3)" }}>{v.note}</div> : null}
      <div style={{ marginTop: "10px", fontSize: "11.5px", color: "var(--d-txt-3)" }}>
        Source:{" "}
        <a href={v.source.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--d-txt-2)" }}>
          {v.source.label} ↗
        </a>
        {" "}· current US$
      </div>
    </div>
  );
}

export function SipriBudget({ data, country }) {
  const m = country && data && data.sipriMilex ? data.sipriMilex[country] : null;
  const v = milexView(m);
  if (!v) return null;
  return (
    <div
      className="geo-sipri"
      style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginTop: "6px", fontSize: "11.5px", color: "#cbd5e1", lineHeight: 1.4 }}
    >
      <span style={{ color: "#ffffff", fontWeight: 600 }}>{v.headline}</span>
      {v.facts.map(([k, val]) => (
        <span key={k}>
          <span style={{ color: "#94a3b8" }}>{k} </span>
          {val}
        </span>
      ))}
      <Spark bars={v.bars} w={90} h={16} color="#94a3b8"
        title={`Defence spending by year (constant 2024 US$): ${sparkTitle(v.bars, (x) => `$${Math.round(x)}m`)}`} />
      <a href={v.source.url} target="_blank" rel="noopener noreferrer" style={{ color: "#94a3b8" }} title={`${v.source.label}: current US$; trend in constant 2024 US$`}>
        {v.source.label} ↗
      </a>
    </div>
  );
}
