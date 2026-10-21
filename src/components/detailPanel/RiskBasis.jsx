import "../../styles/risk.css";

/* Why a signal is watch or threat, from details[id].labelBasis (review API only; the live API does not ship it, so
   the live drawer keeps "no risk scores"). A threat is exactly every test passing (prompts/derive.signal_label_tests). */
const SCORES = [1, 2, 3, 4, 5];
const shown = (v) => (v === null || v === undefined || v === "" ? "not scored" : String(v));

export default function RiskBasis({ basis }) {
  if (!basis) return null;
  const { probability: p, impact: i, dimensions = [], tests = [], mainDimension, label } = basis;
  const failed = tests.filter((t) => !t.pass).length;
  const dot = p && i;
  return (
    <>
      <div className="ctx-sec">
        <span className="eyebrow">Risk assessment</span>
        <div className="rk-wrap">
          <div className="rk-grid" role="img" aria-label={dot ? `Probability ${p} of 5, impact ${i} of 5` : "Probability or impact not scored"}>
            {SCORES.slice().reverse().map((py) => SCORES.map((ix) => (
              <span key={`${py}-${ix}`} className={`rk-cell${py >= 4 && ix >= 4 ? " zone" : ""}`}>
                {dot && py === p && ix === i ? <span className={`rk-dot ${label || ""}`} /> : null}
              </span>
            )))}
          </div>
          <div className="rk-axes">
            <span>Probability ↑ {shown(p)}</span>
            <span>Impact → {shown(i)}</span>
            <span>Risk (p × i) {shown(basis.risk)}</span>
            {!dot ? <span className="rk-note">Not plotted: {!p && !i ? "probability and impact" : !p ? "probability" : "impact"} not scored</span> : null}
            <span className="rk-note">Shaded: threat zone (both 4 or 5)</span>
          </div>
        </div>
      </div>

      {dimensions.length ? (
        <div className="ctx-sec">
          <span className="eyebrow">Impact by dimension</span>
          {dimensions.map((d) => (
            <div className={`rk-dim${d.key === mainDimension ? " main" : ""}`} key={d.key}>
              <span className="rk-dk">{d.label}</span>
              <span className="rk-bar"><span style={{ width: `${((d.score || 0) / 5) * 100}%` }} /></span>
              <span className="rk-dv">{shown(d.score)}</span>
            </div>
          ))}
        </div>
      ) : null}

      {tests.length ? (
        <div className="ctx-sec">
          <span className="eyebrow">Why {label || "this label"}</span>
          <span className="rk-sum">{failed ? `${failed} of ${tests.length} threat tests fail; a threat needs all ${tests.length} to pass.` : `All ${tests.length} threat tests pass.`}</span>
          {tests.map((t) => (
            <div className={`rk-test${t.pass ? "" : " fail"}`} key={t.test}>
              <span className="rk-ic" aria-label={t.pass ? "pass" : "fail"}>{t.pass ? "✓" : "✗"}</span>
              <span className="rk-tn">{t.test}</span>
              <span className="rk-tg">{shown(t.got)}</span>
              <span className="rk-tneed">needs {t.need}</span>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}
