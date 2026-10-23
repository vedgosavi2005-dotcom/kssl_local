import "../../styles/risk.css";
import { reasonFor, dimensionReason, analyticalReading } from "../../lib/riskReading";

/* Why a signal is watch or threat, from details[id].labelBasis, and what its prompts cost, from details[id].promptStats
   (labelBasis on both sites since 24 Oct; promptStats from the review API only). A threat is exactly every test
   passing (prompts/derive.signal_label_tests, rule s3: question / answer / need are plain English, basis says where the
   answer came from). */
const SCORES = [1, 2, 3, 4, 5];
const shown = (v) => (v === null || v === undefined || v === "" ? "not scored" : String(v));
const BASIS = { stated: "From the article", derived: "Worked out from the facts", unknown: "Not known" };
const usd = (x) => (x == null ? "—" : `$${Number(x).toFixed(x < 1 ? 3 : 2)}`);
const num = (x) => (x == null ? "—" : Number(x).toLocaleString("en-IN"));

export default function RiskBasis({ basis, stats, title }) {
  if (!basis && !stats) return null;
  const { probability: p, impact: i, dimensions = [], tests = [], mainDimension, label, labelText, summary, score, confidence } = basis || {};
  const failed = tests.filter((t) => !t.pass).length;
  const dot = p && i;
  // signal rule only: tech / tender / partnership bases carry no probability x impact, so no grid and the summary moves down
  const grid = !!basis && ("probability" in basis || "impact" in basis);
  const allPass = label === "threat" || label === "watch";   // the threat/watch rules: threat = every check passes
  return (
    <>
      {grid ? (
        <div className="ctx-sec">
          <span className="eyebrow">Risk assessment</span>
          {summary ? <p className="rk-summary">{summary}</p> : null}
          {score != null || confidence ? (
            <div className="rk-kpis">
              {score != null ? <span><b>{score}</b>/100 risk score</span> : null}
              {confidence ? <span className={`rk-conf ${confidence}`}>{confidence} confidence</span> : null}
            </div>
          ) : null}
          <div className="rk-wrap">
            <div className="rk-grid" role="img" aria-label={dot ? `Likelihood ${p} of 5, impact ${i} of 5` : "Likelihood or impact not scored"}>
              {SCORES.slice().reverse().map((py) => SCORES.map((ix) => (
                <span key={`${py}-${ix}`} className={`rk-cell${py >= 4 && ix >= 4 ? " zone" : ""}`}>
                  {dot && py === p && ix === i ? <span className={`rk-dot ${label || ""}`} /> : null}
                </span>
              )))}
            </div>
            <div className="rk-axes">
              <span>How likely ↑ {shown(p)} of 5</span>
              <span>How hard it hits KSSL → {shown(i)} of 5</span>
              {!dot ? <span className="rk-note">Not plotted: {!p && !i ? "likelihood and impact" : !p ? "likelihood" : "impact"} not scored</span> : null}
              <span className="rk-note">Shaded corner: threat zone (both 4 or 5)</span>
            </div>
          </div>
        </div>
      ) : null}

      {dimensions.length ? (
        <div className="ctx-sec">
          <span className="eyebrow">Where it hits KSSL</span>
          {dimensions.map((d) => (
            <div className={`rk-dim${d.key === mainDimension ? " main" : ""}`} key={d.key}>
              <span className="rk-dk">{d.label}</span>
              <span className="rk-bar"><span style={{ width: `${((d.score || 0) / 5) * 100}%` }} /></span>
              <span className="rk-dv">{shown(d.score)}</span>
              {dimensionReason(d.key, basis) && (d.score || 0) > 1 ? <span className="rk-why">{dimensionReason(d.key, basis)}</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      {tests.length ? (
        <div className="ctx-sec">
          <span className="eyebrow">{labelText || `Why ${label ? label.replace(/_/g, " ") : "this label"}`}</span>
          {!grid && summary ? <p className="rk-summary">{summary}</p> : null}
          {allPass ? <span className="rk-sum">{failed ? `A threat must pass all ${tests.length} checks. This one misses ${failed}.` : `Passes all ${tests.length} threat checks.`}</span> : null}
          {tests.map((t) => (
            <div className={`rk-test${t.pass ? "" : " fail"}`} key={t.key || t.test}>
              <span className="rk-ic" aria-label={t.pass ? "pass" : "fail"}>{t.pass ? "✓" : "✗"}</span>
              <span className="rk-tn">{t.question || t.test}</span>
              <span className="rk-tg">{shown(t.answer ?? t.got)}</span>
              <span className="rk-tneed">
                {t.need ? `${allPass ? "Threat needs" : "Needs"}: ${t.need}` : null}
                {t.basis && BASIS[t.basis] ? <span className={`rk-basis ${t.basis}`}>{BASIS[t.basis]}</span> : null}
              </span>
              {reasonFor(t, basis) ? <span className="rk-why">Why: {reasonFor(t, basis)}</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      {/* the analytical reading: the checks above as one chain of plain sentences, ending in why it is a threat or a watch */}
      {analyticalReading(basis, title).length ? (
        <div className="ctx-sec">
          <span className="eyebrow">Analytical reading</span>
          <div className="rk-reading">
            {analyticalReading(basis, title).map((line, n) => <p key={n}>{line}</p>)}
          </div>
        </div>
      ) : null}

      {stats && stats.total ? (
        <div className="ctx-sec">
          <span className="eyebrow">Prompt analytics</span>
          <div className="rk-kpis">
            <span><b>{usd(stats.total.costUsd)}</b> cost</span>
            <span><b>{num(stats.total.runs)}</b> runs</span>
            <span><b>{num(stats.total.tokensIn)}</b> in / <b>{num(stats.total.tokensOut)}</b> out tokens</span>
            <span><b>{num(stats.total.seconds)}</b> s</span>
            {stats.total.failures ? <span className="rk-bad">{stats.total.failures} failed</span> : null}
            {stats.total.reruns ? <span className="rk-bad">{stats.total.reruns} re-runs</span> : null}
          </div>
          <table className="rk-ps">
            <thead><tr><th>Prompt</th><th>Runs</th><th>Tokens in / out</th><th>Cost</th><th>Seconds</th></tr></thead>
            <tbody>
              {(stats.byPrompt || []).map((r) => (
                <tr key={r.prompt} title={[r.models, r.lastRunAt ? `last run ${r.lastRunAt.slice(0, 16).replace("T", " ")}` : ""].filter(Boolean).join(" · ")}>
                  <td>{r.prompt}</td>
                  <td>{r.runs}{r.failures ? ` (${r.failures} failed)` : ""}{r.reruns ? ` (${r.reruns} re-run)` : ""}</td>
                  <td>{num(r.tokensIn)} / {num(r.tokensOut)}</td>
                  <td>{usd(r.costUsd)}</td>
                  <td>{num(r.seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
