import { useEffect, useMemo, useState } from "react";
import "../../styles/flow.css";

/* THE FLOW DASHBOARD (owner 24 Oct: "a proper dashboard of our Flow, which we run every day ... each and every log").
   Review site only, its own page at /flow (src/main.jsx). Reads /api/review/flow/* (backend/flow_dashboard.py):
   runs -> steps -> a step's whole output, every error and warning, every model call, data added per pillar, coverage. */

const api = async (path, params) => {
  const r = await fetch(`/api/review/flow/${path}?${new URLSearchParams(params || {})}`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${path}: HTTP ${r.status}`);
  return body;
};
const when = (t) => (t ? String(t).replace("T", " ").slice(0, 16) : "—");
const money = (v) => (v == null ? "—" : `$${Number(v).toFixed(2)}`);
const num = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const dur = (s) => (s == null ? "—" : s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
const TABS = [["runs", "Runs"], ["errors", "Errors & warnings"], ["models", "Model calls"], ["data", "Data & coverage"]];

/* one single-series daily bar chart: magnitude per day, value on hover (title), baseline-anchored rounded ends */
function DayBars({ rows, field, label, tone, fmt = num }) {
  const max = Math.max(1, ...rows.map((r) => Number(r[field]) || 0));
  const w = 640, h = 90, gap = 2, bw = Math.max(2, (w - gap * (rows.length - 1)) / Math.max(1, rows.length));
  const total = rows.reduce((a, r) => a + (Number(r[field]) || 0), 0);
  return (
    <figure className="fl-chart">
      <figcaption>{label} <b>{fmt(total)}</b></figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${label} per day`}>
        <line x1="0" x2={w} y1={h - 0.5} y2={h - 0.5} className="fl-base" />
        {rows.map((r, i) => {
          const v = Number(r[field]) || 0;
          const bh = v ? Math.max(3, (v / max) * (h - 6)) : 0;
          return (
            <g key={String(r.day)}>
              <rect x={i * (bw + gap)} y={0} width={bw} height={h} className="fl-hit"><title>{`${String(r.day).slice(0, 10)}: ${fmt(v)}`}</title></rect>
              {bh ? <rect x={i * (bw + gap)} y={h - bh} width={bw} height={bh} rx={Math.min(4, bw / 2)} className={`fl-bar ${tone}`} pointerEvents="none" /> : null}
            </g>
          );
        })}
      </svg>
      <div className="fl-axis"><span>{String(rows[0]?.day || "").slice(0, 10)}</span><span>{String(rows[rows.length - 1]?.day || "").slice(0, 10)}</span></div>
    </figure>
  );
}

function Status({ s }) {
  return <span className={`fl-st ${s || ""}`}>{s || "—"}</span>;
}

function rowsText(rows) {
  const t = { insert: 0, update: 0, delete: 0 };
  Object.values(rows || {}).forEach((c) => { Object.keys(t).forEach((k) => { t[k] += Number((c || {})[k]) || 0; }); });
  return t.insert || t.update || t.delete ? `+${num(t.insert)} ~${num(t.update)} -${num(t.delete)}` : "—";
}

function OutputView({ stepId, onClose }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [only, setOnly] = useState(false);
  useEffect(() => { setD(null); api("output", { step: stepId }).then(setD, (e) => setErr(e.message)); }, [stepId]);
  const lines = useMemo(() => String((d && d.step && (d.step.output || d.step.error)) || "").split("\n"), [d]);
  const bad = (l) => /(Traceback|Error\b|Exception\b|Violation\b|\bFAILED\b|\bERROR\b|error:)/.test(l);
  const warn = (l) => /\bWARN(ING)?\b|warning:/i.test(l);
  const save = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/plain" }));
    a.download = `${(d && d.step && d.step.name) || "step"}_${stepId.slice(0, 8)}.log`;
    a.click();
  };
  return (
    <div className="fl-out">
      <div className="fl-out-h">
        <b>{d && d.step ? d.step.name : "Step output"}</b>
        {d && d.step ? <Status s={d.step.status} /> : null}
        <span className="fl-dim">{d && d.step ? d.step.script : ""}</span>
        <label className="fl-chk"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} /> problems only</label>
        <button type="button" onClick={save} disabled={!d}>Download log</button>
        <button type="button" onClick={onClose}>Close</button>
      </div>
      {err ? <p className="fl-err">{err}</p> : null}
      {!d ? <p className="fl-dim">Loading…</p> : (
        <>
          {d.step && !d.step.output ? <p className="fl-dim">No full output stored for this step (it ran before the Flow log, or printed nothing). {d.step.log_path ? `Laptop log: ${d.step.log_path}` : ""}</p> : null}
          <pre className="fl-pre">{lines.map((l, i) => (only && !bad(l) && !warn(l) ? null : (
            <div key={i} className={bad(l) ? "e" : warn(l) ? "w" : ""}><i>{i + 1}</i>{l}</div>
          )))}</pre>
          {d.notes && d.notes.length ? (
            <>
              <div className="fl-sec">Notes the step wrote ({d.notes.length})</div>
              <table className="fl-tab"><tbody>{d.notes.map((n, i) => (
                <tr key={i} className={n.level}><td>{when(n.at)}</td><td>{n.level}</td><td>{n.kind} / {n.outcome}</td><td>{n.message}</td><td className="fl-dim">{n.subject}</td></tr>
              ))}</tbody></table>
            </>
          ) : null}
        </>
      )}
    </div>
  );
}

function RunsTab({ days, openStep }) {
  const [d, setD] = useState(null);
  const [run, setRun] = useState(null);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { setD(null); api("runs", { days }).then(setD, (e) => setErr(e.message)); }, [days]);
  const open = (r) => { setRun(r); setDetail(null); api("run", { id: r.run_id }).then(setDetail, (e) => setErr(e.message)); };
  return (
    <>
      {err ? <p className="fl-err">{err}</p> : null}
      {d && d.daily && d.daily.length ? (
        <div className="fl-charts">
          <DayBars rows={d.daily} field="cost" label="Model spend" tone="spend" fmt={money} />
          <DayBars rows={d.daily} field="calls" label="Model calls" tone="calls" />
          <DayBars rows={d.daily} field="failed_calls" label="Failed model calls" tone="bad" />
          <DayBars rows={d.daily} field="failed_steps" label="Failed steps" tone="bad" />
        </div>
      ) : null}
      <div className="fl-split">
        <div className="fl-list">
          <div className="fl-sec">Runs ({d ? d.runs.length : "…"})</div>
          {(d ? d.runs : []).map((r) => (
            <button type="button" key={r.run_id} className={`fl-run${run && run.run_id === r.run_id ? " on" : ""}`} onClick={() => open(r)}>
              <span className="fl-run-t">{when(r.started_at)} · {r.kind}</span>
              <Status s={r.status} />
              <span className="fl-dim">{r.steps} steps · {dur(Number(r.seconds))} · {money(r.cost_usd ?? r.step_cost)}</span>
              <span className="fl-dim">{r.failed_steps ? <b className="fl-bad">{r.failed_steps} failed</b> : null} {r.error_lines + r.error_notes ? <b className="fl-bad">{r.error_lines + r.error_notes} error lines</b> : null} {r.warn_lines + r.warn_notes ? <span className="fl-warn">{r.warn_lines + r.warn_notes} warnings</span> : null}</span>
              <span className="fl-dim">rows {`+${num(r.rows_written.ins)} ~${num(r.rows_written.upd)} -${num(r.rows_written.del)}`}</span>
            </button>
          ))}
        </div>
        <div className="fl-detail">
          {!run ? <p className="fl-dim">Pick a run to see its steps.</p> : !detail ? <p className="fl-dim">Loading…</p> : (
            <>
              <div className="fl-sec">Run {when(run.started_at)} · {run.kind} · git {run.git_sha || "—"} · host {run.host || "—"}</div>
              <p className="fl-dim">Arguments: {JSON.stringify(run.args || {})}</p>
              <table className="fl-tab">
                <thead><tr><th>Step</th><th>Status</th><th>Started</th><th>Took</th><th>Spend</th><th>Rows</th><th>Errors / warnings</th><th /></tr></thead>
                <tbody>{detail.steps.map((s) => (
                  <tr key={s.step_id} className={s.status === "failed" ? "error" : ""}>
                    <td><b>{s.name}</b><div className="fl-dim fl-mono">{s.script}</div>{s.error ? <div className="fl-bad fl-mono">{String(s.error).trim().split("\n").slice(-1)[0]}</div> : null}</td>
                    <td><Status s={s.status} /></td>
                    <td>{when(s.started_at).slice(11)}</td>
                    <td>{dur(Number(s.seconds))}</td>
                    <td>{s.cost_usd != null ? money(s.cost_usd) : "—"}</td>
                    <td className="fl-mono" title={JSON.stringify(s.rows || {}, null, 1)}>{rowsText(s.rows)}</td>
                    <td>{s.error_lines.length + Number(s.error_notes) ? <b className="fl-bad">{s.error_lines.length + Number(s.error_notes)}</b> : "0"} / {s.warn_lines.length + Number(s.warn_notes) ? <span className="fl-warn">{s.warn_lines.length + Number(s.warn_notes)}</span> : "0"}</td>
                    <td><button type="button" onClick={() => openStep(s.step_id)}>Log{s.output_chars ? ` (${num(Math.round(s.output_chars / 1000))}k)` : ""}</button></td>
                  </tr>
                ))}</tbody>
              </table>
              {detail.calls && detail.calls.length ? (
                <>
                  <div className="fl-sec">Model calls during this run</div>
                  <table className="fl-tab"><thead><tr><th>Prompt</th><th>Outcome</th><th>Calls</th><th>Spend</th></tr></thead>
                    <tbody>{detail.calls.map((c, i) => <tr key={i} className={c.status === "failed" ? "error" : ""}><td>{c.prompt_id}</td><td><Status s={c.status} /></td><td>{num(c.n)}</td><td>{money(c.cost)}</td></tr>)}</tbody></table>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function ErrorsTab({ days, openStep }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [level, setLevel] = useState("error");
  const [openOnly, setOpenOnly] = useState(true);
  const [kind, setKind] = useState("");
  useEffect(() => { setD(null); api("errors", { days }).then(setD, (e) => setErr(e.message)); }, [days]);
  const items = (d ? d.items : []).filter((i) => (level === "all" || i.level === level) && (!openOnly || !i.fixed) && (!kind || i.kind === kind));
  return (
    <>
      {err ? <p className="fl-err">{err}</p> : null}
      {d ? (
        <div className="fl-kpis">
          <span><b className={d.open_errors ? "fl-bad" : "fl-good"}>{num(d.open_errors)}</b> open errors</span>
          <span><b>{num(d.total)}</b> problems logged in {days} days (incl. fixed and warnings)</span>
        </div>
      ) : null}
      {d && d.open_by_kind.length ? (
        <div className="fl-chips">
          <button type="button" className={!kind ? "on" : ""} onClick={() => setKind("")}>All kinds</button>
          {d.open_by_kind.map(([k, c]) => <button type="button" key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{k} · {c}</button>)}
        </div>
      ) : null}
      <div className="fl-filters">
        <select value={level} onChange={(e) => setLevel(e.target.value)}><option value="error">Errors</option><option value="warn">Warnings</option><option value="all">Errors and warnings</option></select>
        <label className="fl-chk"><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> not fixed by a later run</label>
        <span className="fl-dim">{num(items.length)} shown</span>
      </div>
      {!d ? <p className="fl-dim">Loading…</p> : !items.length ? <p className="fl-good">Nothing here.</p> : (
        <table className="fl-tab">
          <thead><tr><th>When</th><th>Level</th><th>Where</th><th>What</th><th>About</th><th>Fixed later</th><th /></tr></thead>
          <tbody>{items.slice(0, 1500).map((i, k) => (
            <tr key={k} className={i.level}>
              <td>{when(i.at)}</td><td>{i.level}</td><td>{i.where}<div className="fl-dim">{i.source}</div></td>
              <td className="fl-mono">{i.message}</td><td className="fl-dim fl-mono">{i.subject || ""}</td>
              <td>{i.fixed === true ? "yes" : i.fixed === false ? <b className="fl-bad">no</b> : "—"}</td>
              <td>{i.step_id ? <button type="button" onClick={() => openStep(i.step_id)}>Log</button> : null}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </>
  );
}

function ModelsTab({ days }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { setD(null); api("models", { days }).then(setD, (e) => setErr(e.message)); }, [days]);
  const tot = (k) => (d ? d.prompts.reduce((a, p) => a + Number(p[k] || 0), 0) : 0);
  return (
    <>
      {err ? <p className="fl-err">{err}</p> : null}
      {d ? (
        <div className="fl-kpis">
          <span><b>{money(tot("cost"))}</b> spend</span><span><b>{num(tot("calls"))}</b> calls</span>
          <span><b className={tot("failed") ? "fl-bad" : "fl-good"}>{num(tot("failed"))}</b> failed</span>
          <span><b>{num(tot("retried"))}</b> retried</span><span><b>{num(tot("tokens_in"))}</b> tokens in · <b>{num(tot("tokens_out"))}</b> out</span>
        </div>
      ) : null}
      {!d ? <p className="fl-dim">Loading…</p> : (
        <>
          <table className="fl-tab">
            <thead><tr><th>Prompt</th><th>Calls</th><th>Loaded</th><th>Skipped</th><th>Rejected</th><th>Failed</th><th>Retried</th><th>Tokens in / out</th><th>Spend</th><th>Avg</th><th>Rows loaded</th><th>Models</th><th>Last call</th></tr></thead>
            <tbody>{d.prompts.map((p) => (
              <tr key={p.prompt_id} className={p.failed ? "error" : ""}>
                <td><b>{p.prompt_id}</b></td><td>{num(p.calls)}</td><td>{num(p.loaded)}</td><td>{num(p.skipped)}</td><td>{num(p.rejected)}</td>
                <td>{p.failed ? <b className="fl-bad">{num(p.failed)}</b> : 0}</td><td>{num(p.retried)}</td>
                <td>{num(p.tokens_in)} / {num(p.tokens_out)}</td><td>{money(p.cost)}</td><td>{p.avg_seconds == null ? "—" : `${p.avg_seconds} s`}</td><td>{num(p.rows_loaded)}</td>
                <td className="fl-dim">{(p.models || []).join(", ")}</td><td>{when(p.last_call)}</td>
              </tr>
            ))}</tbody>
          </table>
          <div className="fl-sec">Latest failed calls ({d.failures.length})</div>
          <table className="fl-tab"><tbody>{d.failures.map((f, i) => (
            <tr key={i} className="error"><td>{when(f.started_at)}</td><td>{f.prompt_id}</td><td className="fl-dim fl-mono">{f.subject_key}</td><td>{f.attempts}</td><td className="fl-mono">{f.error}</td></tr>
          ))}</tbody></table>
        </>
      )}
    </>
  );
}

function DataTab({ days }) {
  const [d, setD] = useState(null);
  const [cov, setCov] = useState(null);
  const [err, setErr] = useState("");
  const [emptyOnly, setEmptyOnly] = useState(false);
  useEffect(() => {
    setD(null); setCov(null);
    api("data", { days }).then(setD, (e) => setErr(e.message));
    api("coverage", { days }).then(setCov, (e) => setErr(e.message));
  }, [days]);
  const counts = (d ? d.counts : []).filter((c) => !emptyOnly || !c.staging || c.serving === 0);
  return (
    <>
      {err ? <p className="fl-err">{err}</p> : null}
      <div className="fl-sec">Coverage: did every pillar triage promised get the document?</div>
      {!cov ? <p className="fl-dim">Loading…</p> : (
        <>
          <p className="fl-dim">{num(cov.docs)} routed documents harvested in {days} days; {num(cov.used_anywhere)} used by at least one pillar; {num(cov.partial_total)} used by some pillars but not every pillar triage gave them. "Not fed" = the lane has not read it yet, judged it not relevant, or failed on it.</p>
          <table className="fl-tab">
            <thead><tr><th>Route</th><th>Pillar</th><th>Routed</th><th>Fed</th><th>Fed %</th></tr></thead>
            <tbody>{cov.routes.map((r) => {
              const pct = r.routed ? Math.round((100 * r.fed) / r.routed) : 0;
              return (
                <tr key={r.route}><td>{r.route}</td><td>{r.pillar}</td><td>{num(r.routed)}</td><td>{num(r.fed)}</td>
                  <td><span className="fl-meter"><span style={{ width: `${pct}%` }} /></span> {pct}%</td></tr>
              );
            })}</tbody>
          </table>
          {cov.partial.length ? (
            <details className="fl-det"><summary>Documents with a pillar missing ({num(cov.partial_total)})</summary>
              <table className="fl-tab"><thead><tr><th>Day</th><th>Title</th><th>Routes</th><th>Fed</th><th>Missing</th></tr></thead>
                <tbody>{cov.partial.slice(0, 500).map((p) => (
                  <tr key={p.doc_id}><td>{String(p.day || "").slice(0, 10)}{p.undated ? " (undated)" : ""}</td><td><a href={p.url} target="_blank" rel="noreferrer">{p.title || p.url}</a><div className="fl-dim">{p.source_name}</div></td>
                    <td>{(p.routes || []).join(", ")}</td><td>{(p.pillars || []).join(", ")}</td><td className="fl-bad">{p.missing.join(", ")}</td></tr>
                ))}</tbody></table>
            </details>
          ) : null}
        </>
      )}
      <div className="fl-sec">Rows written per pillar per day</div>
      {!d ? <p className="fl-dim">Loading…</p> : (
        <>
          <table className="fl-tab"><thead><tr><th>Day</th><th>Pillar</th><th>Inserted</th><th>Updated</th><th>Deleted</th></tr></thead>
            <tbody>{d.written.slice(0, 400).map((w, i) => <tr key={i}><td>{w.day}</td><td>{w.pillar}</td><td>{num(w.insert)}</td><td>{num(w.update)}</td><td>{num(w.delete)}</td></tr>)}</tbody></table>
          <div className="fl-sec">Approvals to the live data</div>
          <table className="fl-tab"><thead><tr><th>Day</th><th>Table</th><th>Action</th><th>Rows</th></tr></thead>
            <tbody>{d.approvals.slice(0, 400).map((a, i) => <tr key={i}><td>{String(a.day).slice(0, 10)}</td><td>{a.tbl}</td><td>{a.action}</td><td>{num(a.n)}</td></tr>)}</tbody></table>
          <div className="fl-sec">Review data vs live data, per table</div>
          <label className="fl-chk"><input type="checkbox" checked={emptyOnly} onChange={(e) => setEmptyOnly(e.target.checked)} /> only tables that are empty in review or live</label>
          <table className="fl-tab"><thead><tr><th>Table</th><th>Pillar</th><th>Review (staging)</th><th>Live (serving)</th></tr></thead>
            <tbody>{counts.map((c) => (
              <tr key={c.table} className={!c.staging || c.serving === 0 ? "warn" : ""}><td className="fl-mono">{c.table}</td><td>{c.pillar}</td><td>{num(c.staging)}</td><td>{c.serving == null ? "not on live" : num(c.serving)}</td></tr>
            ))}</tbody></table>
        </>
      )}
    </>
  );
}

export default function FlowDashboard() {
  const [tab, setTab] = useState(() => new URLSearchParams(window.location.search).get("tab") || "runs");
  const [days, setDays] = useState(30);
  const [step, setStep] = useState(null);
  const [head, setHead] = useState(null);
  useEffect(() => { document.title = "Flow · 137Parallax review"; }, []);
  useEffect(() => { api("runs", { days: 7 }).then(setHead, () => setHead({ runs: [] })); }, []);
  const pick = (t) => { setTab(t); const u = new URL(window.location.href); u.searchParams.set("tab", t); window.history.replaceState(null, "", u); };
  const last = head && head.runs[0];
  return (
    <div className="fl-page">
      <header className="fl-top">
        <b>137Parallax · Flow</b>
        <span className="fl-dim">every run of the data flow: steps, logs, errors, model calls, data added</span>
        {last ? <span className="fl-last">last run {when(last.started_at)} <Status s={last.status} /></span> : null}
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Window">
          {[1, 7, 30, 90, 365].map((d) => <option key={d} value={d}>last {d} day{d > 1 ? "s" : ""}</option>)}
        </select>
        <a href="/" className="fl-back">Review site</a>
      </header>
      <nav className="fl-tabs">{TABS.map(([k, l]) => <button type="button" key={k} className={tab === k ? "on" : ""} onClick={() => pick(k)}>{l}</button>)}</nav>
      <main className="fl-main">
        {tab === "runs" && <RunsTab days={days} openStep={setStep} />}
        {tab === "errors" && <ErrorsTab days={days} openStep={setStep} />}
        {tab === "models" && <ModelsTab days={days} />}
        {tab === "data" && <DataTab days={days} />}
      </main>
      {step ? <OutputView stepId={step} onClose={() => setStep(null)} /> : null}
    </div>
  );
}
