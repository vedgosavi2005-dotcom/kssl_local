/* ============================ COMPETITIVE EDGE: PRESENTATION ============================
   Nothing in this file decides who is ahead. The edge index (0-100, 50 = parity, higher =
   KSSL stronger), the ahead / parity / behind decision and every per-spec winner and gap are
   STORED columns, computed once by the loader from the prompt's per-spec better_side:

     competitive_matchup.edge_score, decision_level, comparable_spec_count, sourced_spec_count
     competitive_matchup_specification.better_side, gap_value, comparability_state

   The backend serves them as m.edge, m.decision, m.comparable, m.sourced and, per spec,
   s.win, s.gap, s.state (backend/areas/b_products.py documents the vocabularies). The browser
   only labels and draws them; it never recomputes (the old formulas gave the database, the API
   and the screen three different numbers).

   decision_level: 1 = KSSL behind (rival ahead), 2 = near parity, 3 = KSSL ahead, null = no
   judgement -> nothing is labelled.
   better_side:    client | competitor | equal.
   ======================================================================================== */

const lc = (v) => String(v == null ? "" : v).trim().toLowerCase();

/* The label for a STORED decision_level. null for "no judgement"; an unknown code is shown
   as stored (never coerced into one of the three). */
export function decisionVerdict(level, clientName = "KSSL") {
  if (level == null || level === "") return null;
  const short = (clientName || "KSSL").toUpperCase();
  const name = clientName || "KSSL";
  const n = Number(level);
  if (n === 3) return { cls: "ahead", word: `${short} AHEAD`, phrase: `${name} holds the edge` };
  if (n === 2) return { cls: "parity", word: "NEAR PARITY", phrase: "near parity" };
  if (n === 1) return { cls: "behind", word: `${short} BEHIND`, phrase: "competitor holds the edge" };
  return { cls: "parity", word: `DECISION ${level}`, phrase: `decision level ${level}` };
}

/* A spec row's stored winner: "client" | "competitor" | "equal" | null (not judged). */
export function specSide(s) {
  const w = lc(s && s.win);
  return w === "client" || w === "competitor" || w === "equal" ? w : null;
}

/* Is this row one the loader marked as a like-for-like comparison? Anything but an explicit
   one_sided / not_comparable counts, so an unknown or empty state is not silently hidden. */
export function specIsCompared(s) {
  const st = lc(s && s.state);
  return st !== "one_sided" && st !== "not_comparable";
}

/* The stored per-spec gaps, as the dimension list the basis chips draw:
   a > 0 KSSL leads, a < 0 the rival leads, a = 0 level; `raw` is the stored gap_value as a
   fraction. Only rows with a stored better_side and gap_value take part. */
export function storedDims(m) {
  const dims = [];
  ((m && m.specs) || []).forEach((s) => {
    const side = specSide(s);
    if (!side || !specIsCompared(s) || typeof s.gap !== "number") return;
    const g = s.gap / 100;
    dims.push({ l: s.l, a: side === "client" ? g : side === "competitor" ? -g : 0, raw: side === "client" ? g : side === "competitor" ? -g : 0, gap: s.gap, cv: s.cv, kv: s.kv, cn: s.cn, kn: s.kn });
  });
  return dims;
}

/* The chips under the gauge: the specs the loader judged, widest stored gap first. */
export function edgeBasis(m) {
  const esc = (s) =>
    `${s == null ? "" : s}`.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const dec = storedDims(m).filter((d) => d.a !== 0).sort((a, b) => b.gap - a.gap);
  if (!dec.length) return "";
  return `<div class="eg-dims">${dec
    .map((d) => `<span class="eg-dim ${d.a > 0 ? "up" : "down"}">${d.a > 0 ? "▲" : "▼"} ${esc(d.l)} <i>${+d.gap.toFixed(1)}%</i></span>`)
    .join("")}</div>`;
}
