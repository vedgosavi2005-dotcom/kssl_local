/* ============================ COMPETITIVE EDGE ============================
   The edge index (0-100, 50 = parity) is a STORED score: serving.competitive_matchup.edge_score,
   shipped as `matchup.edge`. The browser does not compute it (ruling R6).

   What stays here is arithmetic over the stored spec rows, nothing more: for every spec row that
   holds a number on both sides and says which direction is better (`hi`), the signed advantage
   a = (client - rival) / mean of the two, sign-flipped when lower is better. A gap below the
   dead-band (3%) is rounding noise and counts as level. The rows are used to list which fields
   lead and by how much, beside the stored score. No spec label is special: there are no pairing
   axes, plausibility ranges or groups of related specs, because those would be assumptions
   about one product family.
   ============================================================================== */
import { clientShort } from "./client.js";

export const EDGE_DEADBAND = 0.03;
export const EDGE_CAP = 0.4;

/* The signed advantage of every comparable spec row of a matchup, and the stored score.
   `edge` is the stored score (null when the matchup has none). */
export function computeSpecEdge(m) {
  const specs = (m && m.specs) || [];
  const dims = [];
  specs.forEach((s) => {
    if (s.cn == null || s.kn == null || s.hi == null) return;
    const c = s.cn;
    const k = s.kn;
    const mean = (c + k) / 2;
    if (!mean) return;
    let a = ((k - c) / mean) * (s.hi ? 1 : -1);
    if (Math.abs(a) < EDGE_DEADBAND) a = 0;
    // `a` is clamped so one lopsided row cannot dominate a list; `raw` keeps the true signed gap
    dims.push({
      l: s.l,
      a: Math.max(-EDGE_CAP, Math.min(EDGE_CAP, a)),
      raw: a,
      cn: c,
      kn: k,
      cv: s.cv,
      kv: s.kv,
    });
  });
  const stored = m && m.edge != null && m.edge !== "" && Number.isFinite(Number(m.edge)) ? Number(m.edge) : null;
  return { edge: stored, n: dims.length, decided: dims.filter((d) => d.a !== 0).length, dims };
}

/* One verdict per stored score. Symmetric band of +/-8 around parity (a presentation threshold). */
export function edgeVerdict(e, clientLabel = clientShort()) {
  const short = clientLabel.toUpperCase();
  const name = clientLabel;
  if (e == null)
    return {
      cls: "parity",
      word: "INSUFFICIENT MEASURED DATA",
      phrase: "no measured basis",
    };
  if (e >= 58) return { cls: "ahead", word: `${short} AHEAD`, phrase: `${name} holds the edge` };
  if (e >= 42) return { cls: "parity", word: "NEAR PARITY", phrase: "near parity" };
  return { cls: "behind", word: `${short} BEHIND`, phrase: "competitor holds the edge" };
}

/* The fields that lead and by how much, beside the stored score. */
export function edgeBasis(ce) {
  const esc = (s) =>
    `${s == null ? "" : s}`.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  if (ce.edge == null) return "";
  const dec = ce.dims.filter((d) => d.a !== 0).sort((a, b) => Math.abs(b.a) - Math.abs(a.a));
  if (!dec.length) return "";
  return `<div class="eg-dims">${dec
    .map((d) => {
      const pct = Math.round(Math.abs(d.a) * 100);
      return (
        `<span class="eg-dim ${d.a > 0 ? "up" : "down"}">${d.a > 0 ? "▲" : "▼"} ` +
        `${esc(d.l.replace(/\s*\(.*\)$/, ""))}` +
        ` <i>${pct}%${Math.abs(d.a) >= EDGE_CAP ? "+" : ""}</i></span>`
      );
    })
    .join("")}</div>`;
}

/* shared: a value is a real statistic only if its displayed value leads with a number */
export function isNumericVal(v) {
  if (v == null) return false;
  const t = String(v).trim();
  if (!/\d/.test(t)) return false;
  return /^[~$<>]?\s*\d/.test(t);
}
