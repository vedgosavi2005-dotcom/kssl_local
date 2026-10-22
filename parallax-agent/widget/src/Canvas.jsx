import { useEffect, useMemo, useRef, useState } from "react";
import Widget from "./widgets/Widget.jsx";
import { domain, records } from "./widgets/transform.js";
import { humanize } from "./format.js";
import { checkCanvas } from "./layoutGuard.js";

/* THE INSIGHT CANVAS: the generated view, over the product's main area (right of its
   rail, below its top bar). The product page stays mounted underneath; "Back to page"
   just hides the canvas. */
export default function Canvas({ view, pending, index, total, onPrev, onNext, onClose, onAsk, onNavigate, frame, debug, saved, onSave, onShare }) {
  const [filters, setFilters] = useState({});
  const [cross, setCross] = useState([]);
  const [showSources, setShowSources] = useState(false);
  const [layout, setLayout] = useState({ fixes: [], issues: [], checked: false });
  const [zoomed, setZoomed] = useState(null);
  const [toast, setToast] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    // filters open on the designer's default (e.g. Segment = Healthcare), not always on All
    setFilters(Object.fromEntries((view && view.filters ? view.filters : []).filter((f) => f.default).map((f) => [f.field, f.default])));
    setCross([]);
    setShowSources(false);
    setLayout({ fixes: [], issues: [], checked: false });
    setZoomed(null);
  }, [view && view.id]);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(""), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  // layout guardian pass once the widgets (and their lazy chart libraries) have drawn
  useEffect(() => {
    if (!view) return undefined;
    const t = setTimeout(() => {
      const r = checkCanvas(ref.current, frame);
      setLayout((prev) => ({ fixes: [...prev.fixes, ...r.fixes], issues: r.issues, checked: true }));
    }, 1200);
    return () => clearTimeout(t);
  }, [view, frame, filters, cross]);

  // options for each filter: distinct values across every result that has the column
  const filterOptions = useMemo(() => {
    if (!view) return {};
    const out = {};
    for (const f of view.filters || []) {
      const vals = new Set();
      for (const res of Object.values(view.data || {})) {
        if (!res.columns.some((c) => c.name === f.field)) continue;
        domain(records(res), f.field, "x_asc").forEach((v) => vals.add(v));
      }
      out[f.field] = [...vals].filter((v) => v !== "(none)");
    }
    return out;
  }, [view]);

  // the frame opens as soon as a view is on its way, and fills in when it arrives
  if (pending && (!view || pending.after === view.id)) return <Skeleton frame={frame} pending={pending} onClose={onClose} />;
  if (!view) return null;

  const onAction = (click, value) => {
    if (click.action === "filter") {
      setCross((c) => {
        const exists = c.find((x) => x.field === click.field && String(x.value) === String(value));
        return exists ? c.filter((x) => x !== exists) : [...c.filter((x) => x.field !== click.field), { field: click.field, value }];
      });
    } else if (click.action === "ask") {
      onAsk(click.question.split("{value}").join(String(value)));
    } else if (click.action === "navigate") {
      onNavigate(click.pillar, click.view, { [click.payload_key]: String(value) }, String(value));
    }
  };

  return (
    <div className="pa-canvas" ref={ref} style={{ top: frame.top, left: frame.left }} role="region" aria-label="Generated insight">
      <div className="pa-cv-bar">
        <span className="pa-cv-tag"><i />Generated view</span>
        <span className="pa-cv-bar-title">{view.title}</span>
        <div className="pa-cv-nav">
          <button className="pa-fbtn" disabled={index <= 0} onClick={onPrev} type="button" aria-label="Previous view">‹</button>
          <span>{index + 1} / {total}</span>
          <button className="pa-fbtn" disabled={index >= total - 1} onClick={onNext} type="button" aria-label="Next view">›</button>
        </div>
        <button className={`pa-btn${saved ? " is-saved" : ""}`} disabled={saved} onClick={() => onSave(view).then(() => setToast("Saved to History")).catch(() => setToast("Could not save"))}
          title={saved ? "Saved: find it under History" : "Save this view to History"} type="button">
          {saved ? "★ Saved" : "☆ Save"}
        </button>
        <button className="pa-btn" onClick={() => onShare(view).then(() => setToast("Link copied")).catch(() => setToast("Could not create a link"))}
          title="Copy a link that opens this view" type="button">
          Share
        </button>
        <button className="pa-btn primary" onClick={onClose} type="button" title="Close the generated view and return to the page (Esc)">
          ✕ Close
        </button>
        {toast ? <span className="pa-toast">{toast}</span> : null}
      </div>

      <div className="pa-cv-scroll">
        <header className="pa-cv-head">
          <h2>{view.title}</h2>
          {view.subtitle ? <div className="pa-cv-sub">{view.subtitle}</div> : null}
          {view.summary ? <p className="pa-cv-summary">{view.summary}</p> : null}
        </header>

        {(view.filters || []).length || cross.length ? (
          <div className="pa-cv-filters">
            {(view.filters || []).map((f) => (
              <label className="pa-filter" key={f.field}>
                <span>{f.label || humanize(f.field)}</span>
                <select value={filters[f.field] ?? ""} onChange={(e) => setFilters((s) => ({ ...s, [f.field]: e.target.value }))}>
                  <option value="">All</option>
                  {(filterOptions[f.field] || []).map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </label>
            ))}
            {cross.map((c) => (
              <button className="pa-chip-filter" key={`${c.field}=${c.value}`} onClick={() => setCross((x) => x.filter((y) => y !== c))} type="button">
                {humanize(c.field)}: {String(c.value)} ✕
              </button>
            ))}
            {Object.values(filters).some(Boolean) || cross.length ? (
              <button className="pa-link" onClick={() => { setFilters({}); setCross([]); }} type="button">Reset</button>
            ) : null}
          </div>
        ) : null}

        <div className="pa-grid">
          {(view.widgets || []).map((w) => (
            <Widget cross={cross} data={view.data || {}} filters={filters} key={w.id} onAction={onAction} onZoom={setZoomed} widget={w} />
          ))}
        </div>

        {(view.assumptions || []).length || (view.caveats || []).length ? (
          <div className="pa-cv-notes">
            {(view.assumptions || []).length ? (
              <div>
                <div className="pa-eyebrow">How this was worked out</div>
                <ul>{view.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
              </div>
            ) : null}
            {(view.caveats || []).length ? (
              <div>
                <div className="pa-eyebrow">Data caveats</div>
                <ul>{view.caveats.map((a, i) => <li key={i}>{a}</li>)}</ul>
              </div>
            ) : null}
          </div>
        ) : null}

        {(view.followups || []).length ? (
          <div className="pa-cv-follow">
            <div className="pa-eyebrow">Ask next</div>
            <div className="pa-chips">
              {view.followups.map((q) => (
                <button className="pa-chip" key={q} onClick={() => onAsk(q)} type="button">{q}</button>
              ))}
            </div>
          </div>
        ) : null}

        {debug ? <div className="pa-cv-qa">
          {view.qa && view.qa.reviewed ? (
            <span title={(view.qa.fixes || []).join("\n")}>
              Design review: {view.qa.fixes && view.qa.fixes.length ? `${view.qa.fixes.length} fix${view.qa.fixes.length === 1 ? "" : "es"} applied` : "approved"}
            </span>
          ) : null}
          {layout.checked ? (
            <span title={[...layout.fixes, ...layout.issues].join("\n")}>
              Layout check: {layout.issues.length ? `${layout.issues.length} issue${layout.issues.length === 1 ? "" : "s"}` : layout.fixes.length ? `${layout.fixes.length} adjusted` : "passed"}
            </span>
          ) : null}
        </div> : null}

        {debug ? <div className="pa-cv-sources">
          <button className="pa-link" onClick={() => setShowSources((s) => !s)} type="button">
            {showSources ? "Hide" : "Show"} data and SQL ({Object.keys(view.data || {}).length} result{Object.keys(view.data || {}).length === 1 ? "" : "s"})
          </button>
          {showSources
            ? Object.values(view.data || {}).map((r) => (
                <div className="pa-src" key={r.id}>
                  <div className="pa-src-title">{r.title} <span>· {r.rows.length} rows{r.truncated ? " (capped)" : ""}</span></div>
                  <pre>{r.sql}</pre>
                </div>
              ))
            : null}
        </div> : null}
      </div>
      {zoomed ? (
        <div className="pa-zoom" role="dialog" aria-label="Full-screen chart">
          {(view.widgets || []).filter((w) => w.id === zoomed).map((w) => (
            <Widget cross={cross} data={view.data || {}} filters={filters} key={w.id} onAction={onAction} onZoom={setZoomed} widget={w} zoomed />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Skeleton({ frame, pending, onClose }) {
  return (
    <div className="pa-canvas" style={{ top: frame.top, left: frame.left }} role="region" aria-label="Building a view" aria-busy="true">
      <div className="pa-cv-bar">
        <span className="pa-cv-tag"><i />Generated view</span>
        <span className="pa-cv-bar-title">{pending.title}</span>
        <button className="pa-btn primary" onClick={onClose} type="button">✕ Close</button>
      </div>
      <div className="pa-cv-scroll">
        <header className="pa-cv-head">
          <h2>{pending.title}</h2>
          <div className="pa-cv-sub pa-pending-stage"><span className="pa-dots"><i /><i /><i /></span>{pending.stage || "Designing the view"}</div>
        </header>
        <div className="pa-skel-kpis"><i /><i /><i /></div>
        <div className="pa-grid">
          <section className="pa-w pa-skel" style={{ gridColumn: "span 6" }}><b /><span /></section>
          <section className="pa-w pa-skel" style={{ gridColumn: "span 6" }}><b /><span /></section>
          <section className="pa-w pa-skel" style={{ gridColumn: "span 12" }}><b /><span className="short" /></section>
        </div>
      </div>
    </div>
  );
}
