/* Paired-bar spec renderer for the Positioning dossier, plus the verdict band that sits under
   the verdict. Kept as string builders because they are dense read-only markup.

   PRESENTATION ONLY. The edge index, the ahead / parity / behind decision, each spec's winner
   (better_side) and gap (gap_value) and its comparability_state are stored columns served as
   m.edge, m.decision, s.win, s.gap, s.state (see edge.js); nothing here recomputes them.
   Every stored text is escaped before it goes into the markup. */
import { decisionVerdict, edgeBasis, specSide, specIsCompared } from "./edge.js";
import { escAll as esc } from "./html.js";

/* A spec value with the unit the RECORD holds for it -- and never any other.
   The stored unit, once, and only onto a value that is a plain figure -- a number, a range, a
   bound, a plus. A value that already names a unit is left as it is, a placeholder is left as
   it is, and no unit on the record means no unit on screen. */
export function specValueWithUnit(v, u) {
  if (v == null) return "";
  const s = String(v).trim();
  if (!s) return "";
  const unit = u == null ? "" : String(u).trim();
  if (!unit) return s;
  const re = unit.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const once = s.replace(new RegExp(`(${re})(?:\\s+${re})+$`, "i"), "$1");
  if (new RegExp(`(^|[^A-Za-z])${re}([^A-Za-z]|$)`, "i").test(once)) return once;
  if (/^[<>~]?\s*\d[\d.,]*(?:\s*[-–]\s*\d[\d.,]*)?\s*\+?$/.test(once)) return `${once} ${unit}`;
  return once;
}

/* Matchup sources are served (m.sources) but not shown on the comparison, by an earlier user
   request ("remove sources from specs comparison page"). The dossier reads this switch. */
export const SHOW_POSITIONING_SOURCES = false;

const hasVal = (x) => x != null && x !== "";

/* one comparable row with a stored number on both sides: bars sized from the stored numbers
   (the larger fills the track), the winner and the parity tag from the stored better_side,
   the gap as the stored gap_value. */
function specRow(s, compName) {
  const cn = s.cn;
  const kn = s.kn;
  const axisMax = Math.max(Math.abs(cn), Math.abs(kn), 0.0001);
  const cw = Math.max(4, Math.round((Math.abs(cn) / axisMax) * 100));
  const kw = Math.max(4, Math.round((Math.abs(kn) / axisMax) * 100));
  const side = specSide(s);
  const compWin = side === "competitor";
  const bfWin = side === "client";
  const gapTxt = typeof s.gap === "number" ? ` ${+s.gap.toFixed(1)}%` : "";
  const badge = (w) => (w ? `<span class="sb-lead">leads${gapTxt}</span>` : "");
  const parityTag = side === "equal" ? '<span class="sb-parity">parity</span>' : "";
  const unit = s.u ? ` <span class="sb-unit">(${esc(s.u)})</span>` : "";
  return (
    '<div class="specbar">' +
    `<div class="sb-label">${esc(s.l)}${unit}${parityTag}</div>` +
    `<div class="sb-cmprow${bfWin ? " win" : ""}">` +
    '<span class="sb-who bf">KSSL</span>' +
    `<div class="sb-track"><div class="sb-fill bf${bfWin ? " win" : ""}" style="width:${kw}%"></div></div>` +
    `<span class="sb-val${bfWin ? " win" : ""}">${esc(s.kv)}${badge(bfWin)}</span>` +
    "</div>" +
    `<div class="sb-cmprow${compWin ? " win" : ""}">` +
    `<span class="sb-who comp">${esc(compName || "Competitor")}</span>` +
    `<div class="sb-track"><div class="sb-fill comp${compWin ? " win" : ""}" style="width:${cw}%"></div></div>` +
    `<span class="sb-val${compWin ? " win" : ""}">${esc(s.cv)}${badge(compWin)}</span>` +
    "</div>" +
    "</div>"
  );
}

/* qualitative rows: labelled chips (no bars) */
function specRowQual(s) {
  const cv = hasVal(s.cv) ? esc(specValueWithUnit(s.cv, s.u)) : '<span class="sb-nosrc">not published</span>';
  const kv = hasVal(s.kv) ? esc(specValueWithUnit(s.kv, s.u)) : '<span class="sb-nosrc">not published</span>';
  return (
    `<div class="specbar"><div class="sb-label">${esc(s.l)}</div>` +
    `<div class="sb-text">` +
    `<div class="sb-cell"><div class="sb-chip comp">${cv}</div></div>` +
    `<div class="sb-cell"><div class="sb-chip bf">${kv}</div></div>` +
    `</div></div>`
  );
}

export function specBars(specs, compName) {
  /* quantitative = the stored numbers exist on both sides */
  const quant = specs.filter((s) => typeof s.cn === "number" && typeof s.kn === "number");
  let html = "";
  html +=
    '<div class="sb-sect">Quantitative specifications <span class="sb-sect-note">stored numbers on both sides</span></div>';
  html += quant.length
    ? quant.map((s) => specRow(s, compName)).join("")
    : '<div class="sb-empty">No specification has a number on both sides for this matchup.</div>';
  html +=
    '<div class="sb-sect">Compared specifications <span class="sb-sect-note">published on both sides</span></div>';
  html += specs.length
    ? specs.map(specRowQual).join("")
    : '<div class="sb-empty">No specifications recorded for this matchup.</div>';
  return html;
}

/* The whole Spec Comparison panel body for one matchup. */
export function specPanelHtml(m, clientName = "KSSL") {
  const compName = m.compBy || m.comp || "Competitor";
  /* A comparison needs a value on BOTH sides and a comparability_state that does not say
     one_sided / not_comparable. Other rows are not shown here. */
  const compared = (m.specs || []).filter((s) => hasVal(s.cv) && hasVal(s.kv) && specIsCompared(s));
  const legend = `<div class="sb-legend"><span class="sb-key"><i class="k-comp"></i> ${esc(compName)}</span><span class="sb-key"><i class="k-bf"></i> ${esc(clientName)}</span><span class="sb-key"><i class="k-win"></i> leads (stored)</span></div>`;

  if (!compared.length) {
    return (
      '<div class="edge-gauge undisclosed"><span class="eg-word" style="background:#555;color:#fff;padding:3px 9px;border-radius:3px">NOTHING COMPARED ON BOTH SIDES</span>' +
      '<div style="font-size:11px;color:var(--l-txt-3);margin-top:8px;line-height:1.5">No specification is stored for both products, so there is nothing to compare here.</div></div>'
    );
  }

  const v = decisionVerdict(m.decision, clientName);
  const hasEdge = typeof m.edge === "number";
  if (!v && !hasEdge) {
    return (
      '<div class="edge-gauge undisclosed"><span class="eg-word" style="background:#555;color:#fff;padding:3px 9px;border-radius:3px">NO EDGE INDEX STORED</span></div>' +
      legend +
      specBars(compared, compName)
    );
  }
  const gPos = hasEdge ? Math.max(0, Math.min(100, m.edge)) : null;
  const word = [v ? v.word : "", hasEdge ? String(+m.edge.toFixed(1)) : ""].filter(Boolean).join(" · ");
  return (
    `<div class="edge-gauge ${v ? v.cls : "parity"}">` +
    `<div class="eg-top"><span class="eg-lab">Competitive edge index <span class="eg-sub">stored for this matchup</span></span><span class="eg-word">${esc(word)}</span></div>` +
    (gPos == null
      ? ""
      : `<div class="eg-track"><div class="eg-mid"></div><div class="eg-marker" style="left:${gPos}%"></div></div>`) +
    '<div class="eg-scale"><span>Competitor stronger</span><span>Parity</span><span>KSSL stronger</span></div>' +
    edgeBasis(m) +
    "</div>" +
    legend +
    specBars(compared, compName)
  );
}

/* VERDICT BAND under the verdict: the stored decision_level as a word, the stored edge_score,
   and the stored spec counts. Nothing is derived; with no decision_level nothing is drawn. */
export function matchupGapHtml(m, clientName = "KSSL") {
  const v = decisionVerdict(m.decision, clientName);
  if (!v) return "";
  const band = v.cls === "ahead" ? "lead" : v.cls === "behind" ? "high" : "par";
  const word = v.cls === "ahead" ? `${clientName} leads` : v.cls === "behind" ? `${clientName} behind` : v.cls === "parity" ? "Near parity" : v.word;
  const counts = [
    m.comparable != null ? `${m.comparable} comparable specification${Number(m.comparable) === 1 ? "" : "s"}` : "",
    m.sourced != null ? `${m.sourced} sourced` : "",
  ].filter(Boolean).join(" · ");
  let h = `<div class="mug ${band}">`;
  h += `<div class="mug-head"><span class="mug-verdict ${band}">${esc(word)}${typeof m.edge === "number" ? ` · ${+m.edge.toFixed(1)}` : ""}</span></div>`;
  h += `<div class="mug-line"><b>${esc(m.bf)}</b> vs <b>${esc(m.comp)}</b></div>`;
  if (counts) h += `<div class="mug-desc">${esc(counts)}.</div>`;
  h += "</div>";
  return h;
}
