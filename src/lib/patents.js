/* ===================================================================
   PATENTS -- display rules over the three served patent tables.

   PATENTS.byCompetitor[cid]   one portfolio (competitive_patent_portfolio): stored counts, notes,
                               its categories (competitive_patent_classification) and its
                               filings (competitive_patent_filing). A filing belongs to a rival
                               by its portfolio's competitor_id -- never by matching names.
   PATENTS.byTechnology[label] one category label across portfolios: summed stored counts, the
                               rivals holding it, and the filings whose classification code or
                               text equals the label (case-insensitive).

   Status vocabulary (shown as stored; granted / pending / filed only pick a badge colour):
   competitive_patent_filing.status. grant_status_state: free text shown beside status_note.
   =================================================================== */
import { attr, escAll } from "./html.js";
import { formatDate } from "../utils/formatDate.js";

const lc = (v) => String(v == null ? "" : v).toLowerCase();
const esc = escAll;

/* A filing is in a category when its stored classification code or text IS the label. */
export const inCategory = (r, label) => !label || lc(r.code) === lc(label) || lc(r.codeText) === lc(label);

/* One filing. `holder` is the rival's name on the by-field lens (attribution is the
   portfolio's competitor_id). Fields with no column (assignee, abstract, grant and publication
   dates, kind code, relevance) are not drawn. */
export function patRecCard(r, holder) {
  const st = lc(r.status);
  const badge = r.status
    ? `<span class="pat-badge ${["granted", "filed", "pending"].includes(st) ? st : "unknown"}">${esc(r.status)}</span>`
    : '<span class="pat-badge unknown">status not captured</span>';
  const meta =
    `<span>${holder ? `<b>${esc(holder)}</b> · ` : ""}${esc(r.id)}</span>` +
    `<span>${esc(r.jurisdiction)}</span>` +
    `<span>${r.filed ? `Filed ${esc(formatDate(r.filed))}` : ""}</span>`;
  const code = r.code ? `<div class="pat-ipc"><span>${esc(r.code)}</span></div>` : "";
  const text = r.codeText
    ? `<div class="pat-abs pat-abs-ipc">${r.code ? `<span class="pat-abs-k">Classified under ${esc(r.code)}</span> ` : ""}${esc(r.codeText)}</div>`
    : "";
  return (
    `<div class="pat-rec" data-cat="${attr(r.codeText || r.code || "")}">` +
    `<div class="pat-rec-h"><div class="pat-rec-t">${esc(r.title)}</div>${badge}</div>` +
    `<div class="pat-rec-meta">${meta}</div>` +
    code +
    text +
    (r.url
      ? `<a class="pat-view-link" href="${attr(r.url)}" target="_blank" rel="noopener noreferrer">View patent ↗</a>`
      : "") +
    "</div>"
  );
}

const stateHtml = (title, body) =>
  `<div class="pat-state"><div class="ps-ic">⊡</div><div class="ps-t">${esc(title)}</div>${body ? `<div class="ps-s">${esc(body)}</div>` : ""}</div>`;

const sourceNote = (notes) => {
  const list = [...new Set((notes || []).filter(Boolean))];
  return list.length ? `<div class="pat-api-note">${list.map(esc).join(" ")}</div>` : "";
};

const tile = (cls, value, label) =>
  `<div class="pat-stat ${cls}"><div class="pv">${value == null ? "—" : esc(value)}</div><div class="pl">${esc(label)}</div></div>`;

/* The by-rival canvas: the portfolio's stored counts, then its filings (under the category filter). */
export function patCompBody(d, cid, catFilter) {
  const pd = ((d.PATENTS && d.PATENTS.byCompetitor) || {})[cid];
  const name = (d.competitors[cid] || {}).name || cid;
  if (!pd) return stateHtml("No patent portfolio on record", name);
  const recs = (pd.records || []).filter((r) => inCategory(r, catFilter));
  let h =
    '<div class="pat-stats">' +
    tile("filed", pd.filingCount != null ? pd.filingCount : pd.records.length, "Filings on record") +
    tile("granted", pd.grantedCount, "Granted") +
    tile("pending", pd.pendingCount, "Pending") +
    "</div>";
  const note = [pd.grantStatusState ? `Grant status: ${pd.grantStatusState}.` : "", pd.statusNote].filter(Boolean).join(" ");
  if (note) h += `<div class="pat-nograde">${esc(note)}</div>`;
  if (!recs.length) {
    h += stateHtml(pd.emptyMessage || "No filings on record", pd.emptyMessage ? "" : name);
  } else {
    h += `<div class="ws-sec-l" style="margin-top:6px">▸ ${recs.length} filing${recs.length !== 1 ? "s" : ""}${catFilter ? ` · ${esc(catFilter)}` : ""}</div>`;
    h += recs.map((r) => patRecCard(r)).join("");
  }
  return h + sourceNote([pd.dataSourceNote]);
}

/* The by-field canvas: one category label across portfolios. */
export function patTechBody(d, area) {
  const td = ((d.PATENTS && d.PATENTS.byTechnology) || {})[area];
  if (!td) return stateHtml("No filings recorded in this field", area);
  const nameOf = (cid) => (d.competitors[cid] || {}).name || cid;
  let h =
    '<div class="ws-crowd"><div></div><div class="pat-stats" style="margin:0">' +
    tile("filed", td.count, "Filings") +
    tile("", td.holders.length, td.holders.length === 1 ? "Rival" : "Rivals") +
    "</div></div>";
  if (td.holders.length) {
    h += '<div class="ws-sec-l">▸ Who holds filings here</div><div class="ws-holders">';
    [...td.holders]
      .sort((a, b) => (b.filings || 0) - (a.filings || 0) || nameOf(a.cid).localeCompare(nameOf(b.cid)))
      .forEach((l) => {
        h +=
          '<div class="ws-holder">' +
          `<div class="wh-l"><span class="wh-name">${esc(nameOf(l.cid))}</span>` +
          `<span class="wh-meta">${l.filings != null ? `${l.filings} filing${l.filings !== 1 ? "s" : ""}` : ""}</span></div>` +
          "</div>";
      });
    h += "</div>";
  }
  h += '<div class="ws-sec-l" style="margin-top:18px">▸ Filings in this field</div>';
  h += td.records.length ? td.records.map((r) => patRecCard(r, nameOf(r.cid))).join("") : stateHtml("No filing rows carry this classification", "");
  return h + sourceNote(td.notes);
}

/* The fields the "By technology field" lens lists: every category label on file, most-filed first. */
export function patentAreas(P) {
  const byTech = (P && P.byTechnology) || {};
  return Object.keys(byTech).sort((a, b) => byTech[b].count - byTech[a].count || a.localeCompare(b));
}
