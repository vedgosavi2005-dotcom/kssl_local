import { useEffect, useState } from "react";
import "../../styles/pipeline.css";

/* Pipeline log (review site only): runs -> a run's steps -> what a step touched, and one record's journey from harvest to the
   live site. Reads /api/review/pipeline/* (backend/pipeline_log.py). Steps before the live log are RECONSTRUCTED from table
   timestamps, one per stage per day, and are marked so. Mounted from the review banner (components/review/Review.jsx). */

const get = async (path, params) => {
  const r = await fetch(`/api/review/pipeline/${path}?${new URLSearchParams(params || {})}`);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status}`);
  return body;
};
const when = (t) => (t ? String(t).replace("T", " ").slice(0, 16) : "—");
const money = (v) => (v == null ? "" : `$${Number(v).toFixed(2)}`);
const n = (v) => (v == null ? "" : Number(v).toLocaleString("en-IN"));
const STAGE = { harvest: "Harvest", triage: "Triage", prompt: "Prompt", source: "Source", translate: "Translate", log: "Logged", note: "Note", review: "Review" };

/* the record links a step row carries: a card a prompt wrote, a translated / reviewed / logged row */
function linksOf(r) {
  if (Array.isArray(r.cards)) return r.cards.map((c) => ({ tbl: c.table, id: String(c.id) }));
  if (r.tbl && r.rec_id) return [{ tbl: String(r.tbl).replace(/^staging\./, ""), id: String(r.rec_id) }];
  return [];
}

export default function PipelineLog({ onClose }) {
  const [runs, setRuns] = useState(null);
  const [run, setRun] = useState(null);
  const [steps, setSteps] = useState(null);
  const [step, setStep] = useState(null);
  const [records, setRecords] = useState(null);
  const [journey, setJourney] = useState(null);
  const [found, setFound] = useState(null);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const fail = (e) => setErr(e.message || String(e));

  useEffect(() => { get("runs").then((d) => setRuns(d.runs), fail); }, []);
  const openRun = (r) => { setRun(r); setStep(null); setRecords(null); setJourney(null); setFound(null); setSteps(null);
    get("steps", { run: r.id }).then((d) => setSteps(d.steps), fail); };
  const openStep = (s) => { setStep(s); setJourney(null); setFound(null); setRecords(null);
    get("records", { step: s.step_id }).then(setRecords, fail); };
  const openJourney = (tbl, id) => { setJourney(null); setErr("");
    get("journey", { table: tbl, id }).then(setJourney, fail); };
  const search = (text) => { const t = (text ?? q).trim(); if (!t) return; setJourney(null); setFound(null); setErr("");
    get("search", { q: t }).then((d) => setFound(d.results), fail); };

  return (
    <div className="pl-panel" role="dialog" aria-label="Pipeline log">
      <div className="pl-h">
        <b>Pipeline log</b>
        <span className="pl-dim">harvest → triage → prompts → rows → review → live</span>
        <form className="pl-search" onSubmit={(e) => { e.preventDefault(); search(); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a record: title, source url, or table:id" aria-label="Find a record" />
          <button type="submit">Find</button>
        </form>
        <button type="button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {err && <p className="pl-err">{err}</p>}
      <div className="pl-cols">
        <section className="pl-col pl-runs">
          <div className="pl-sec">Runs</div>
          {!runs && <p className="pl-dim">Loading…</p>}
          {(runs || []).map((r) => (
            <button type="button" key={r.id} className={`pl-item${run && run.id === r.id ? " on" : ""}`} onClick={() => openRun(r)}>
              <span className="pl-t">{r.id.startsWith("day:") ? r.id.slice(4) : when(r.started_at)}</span>
              <span className={`pl-st ${r.status}`}>{r.status}</span>
              <span className="pl-dim">{r.steps} steps {money(r.cost_usd)}</span>
              {r.reconstructed && <span className="pl-tag" title="Rebuilt from the timestamps the tables keep: one step per stage per day">reconstructed</span>}
            </button>
          ))}
        </section>

        <section className="pl-col pl-steps">
          <div className="pl-sec">{run ? `Steps · ${run.id.startsWith("day:") ? run.id.slice(4) : when(run.started_at)}` : "Steps"}</div>
          {!run && <p className="pl-dim">Pick a run.</p>}
          {run && !steps && <p className="pl-dim">Loading…</p>}
          {(steps || []).map((s) => (
            <button type="button" key={s.step_id} className={`pl-item${step && step.step_id === s.step_id ? " on" : ""}`} onClick={() => openStep(s)}>
              <span className="pl-t">{s.name}</span>
              <span className={`pl-st ${s.status}`}>{s.status}</span>
              <span className="pl-dim">{when(s.started_at).slice(11)}–{when(s.ended_at).slice(11)}{s.rows_out != null ? ` · ${n(s.rows_out)} rows` : ""} {money(s.cost_usd)}</span>
              {s.script && <span className="pl-dim pl-script">{s.script}</span>}
            </button>
          ))}
        </section>

        <section className="pl-col pl-detail">
          {journey ? (
            <Journey j={journey} onOpen={openJourney} onBack={() => setJourney(null)} />
          ) : found ? (
            <>
              <div className="pl-sec">Found {found.length} record{found.length === 1 ? "" : "s"}</div>
              {found.map((f) => (
                <button type="button" key={`${f.tbl}:${f.id}`} className="pl-item" onClick={() => openJourney(f.tbl, f.id)}>
                  <span className="pl-t">{f.title || f.id}</span>
                  <span className="pl-dim">{f.tbl} · via {f.via}</span>
                </button>
              ))}
              {!found.length && <p className="pl-dim">Nothing matches.</p>}
            </>
          ) : step ? (
            <StepRecords step={step} data={records} onOpen={openJourney} onFindUrl={(u) => { setQ(u); search(u); }} />
          ) : (
            <p className="pl-dim">Pick a step to see what it touched, or find a record to see its journey.</p>
          )}
        </section>
      </div>
    </div>
  );
}

function StepRecords({ step, data, onOpen, onFindUrl }) {
  const rows = data ? data.records : null;
  return (
    <>
      <div className="pl-sec">{step.name} · {rows ? `${rows.length}${rows.length >= 300 ? "+ (first 300)" : ""} records` : "loading…"}</div>
      {step.reconstructed && <p className="pl-dim">Reconstructed from stored timestamps; the live log adds per-row changes from the next run on.</p>}
      {(rows || []).map((r, i) => {
        const links = linksOf(r);
        const url = r.url || null;
        return (
          <div className="pl-rec" key={i}>
            <span className="pl-dim">{when(r.at).slice(11)}</span>
            <span className="pl-t">{r.title || r.subject_key || r.action || r.rec_id || url || "—"}</span>
            {r.status && <span className={`pl-st ${r.status}`}>{r.status}</span>}
            {r.note && <span className="pl-dim">{String(r.note).slice(0, 140)}</span>}
            <span className="pl-acts">
              {links.map((l) => <button type="button" key={`${l.tbl}:${l.id}`} onClick={() => onOpen(l.tbl, l.id)}>journey: {l.tbl}</button>)}
              {url && <button type="button" onClick={() => onFindUrl(url)}>records from this page</button>}
              {url && <a href={url} target="_blank" rel="noreferrer">source ↗</a>}
            </span>
          </div>
        );
      })}
      {(data?.notes || []).length > 0 && <div className="pl-sec">Notes</div>}
      {(data?.notes || []).map((x, i) => <div className="pl-rec" key={`n${i}`}><span className="pl-dim">{when(x.at).slice(11)}</span><span className="pl-t">{x.message || x.outcome}</span></div>)}
    </>
  );
}

function Journey({ j, onOpen, onBack }) {
  return (
    <>
      <div className="pl-sec">
        <button type="button" className="pl-back" onClick={onBack}>‹ back</button> Journey · {j.tbl}
      </div>
      <div className="pl-jh">
        <b>{j.title || j.id}</b>
        <span className={`pl-st ${j.in_serving ? "ok" : "running"}`}>{j.in_serving ? "live on the site" : j.in_staging ? "in staging, not live" : "not in staging"}</span>
      </div>
      {j.parents.map((p) => <button type="button" key={`${p.tbl}:${p.id}`} className="pl-link" onClick={() => onOpen(p.tbl, p.id)}>parent: {p.tbl}</button>)}
      <ol className="pl-tl">
        {j.events.map((e, i) => (
          <li key={i} className={`st-${e.stage}`}>
            <span className="pl-dim">{when(e.at)}</span>
            <span className="pl-stage">{STAGE[e.stage] || e.stage}</span>
            <span className="pl-t">{e.what}</span>
            {e.detail && (e.detail.url || e.detail.title) && (
              <span className="pl-dim">
                {e.detail.title ? `${String(e.detail.title).slice(0, 90)} ` : ""}
                {e.detail.url && <a href={e.detail.url} target="_blank" rel="noreferrer">source ↗</a>}
              </span>
            )}
            {e.detail && e.detail.cost_usd != null && <span className="pl-dim">{money(e.detail.cost_usd)} · {e.detail.model}</span>}
          </li>
        ))}
        <li className={j.in_serving ? "st-live" : "st-wait"}>
          <span className="pl-dim">now</span>
          <span className="pl-stage">{j.in_serving ? "Live" : "Waiting"}</span>
          <span className="pl-t">{j.in_serving ? "approved and served on the live site" : "not approved yet: the review site shows it, the live site does not"}</span>
        </li>
      </ol>
      {!j.events.length && <p className="pl-dim">No stored timestamps for this record yet.</p>}
    </>
  );
}
