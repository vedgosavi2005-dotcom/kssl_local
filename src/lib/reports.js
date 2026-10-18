/* The two CEO briefings: one for a Positioning matchup, one for an Innovation theme.
   Both are descriptive — they restate what the platform already holds and add the
   cross-pillar exposure, and neither prescribes a move. */
import { clientShort } from "./client.js";
import { computeSpecEdge, edgeVerdict } from "./edge.js";
import { escAll, srcChips, attr, stripTags } from "./html.js";
import { formatDate } from "../utils/formatDate.js";

export function positioningReportHtml(m, tenders, today = formatDate(new Date())) {
  const edge = m.edge == null ? null : m.edge;
  if (edge == null) {
    return (
      '<div class="tech-report"><div class="tr-head"><div class="tr-title">Positioning Briefing · CEO</div>' +
      `<div class="tr-sub">${escAll(m.comp || "")} vs ${escAll(m.bf)}</div>` +
      `<div class="tr-meta">CONFIDENTIAL · ${clientShort() ? `${clientShort()} · ` : ""}Prepared ${today} · Category: ${escAll(m.cat || "")}</div></div>` +
      (m.advBf && m.advBf.length
        ? `<div class="tr-sec"><div class="tr-sec-h">${clientShort()} Advantages To Press</div><div class="tr-body">${m.advBf.map((a) => `• ${stripTags(a)}`).join("<br>")}</div></div>`
        : "") +
      (m.advComp && m.advComp.length
        ? `<div class="tr-sec"><div class="tr-sec-h">Competitor Strengths To Counter</div><div class="tr-body">${m.advComp.map((a) => `• ${stripTags(a)}`).join("<br>")}</div></div>`
        : "") +
      '</div>'
    );
  }
  const v = edgeVerdict(m.decision);
  const edgeWord = v.phrase.toUpperCase();
  /* Spec leads are the rows whose gap is beyond the dead-band; the edge score itself is the stored one.
     computeSpecEdge skips null-direction rows and sub-deadband deltas. */
  const ce = computeSpecEdge(m);
  const specByLabel = {};
  (m.specs || []).forEach((s) => {
    specByLabel[s.l] = s;
  });
  const leads = { comp: [], bf: [], even: [] };
  ce.dims.forEach((d) => {
    const s = specByLabel[d.l] || {};
    if (d.a > 0) leads.bf.push(`${d.l} (${s.kv != null ? s.kv : "—"})`);
    else if (d.a < 0) leads.comp.push(`${d.l} (${s.cv != null ? s.cv : "—"})`);
    else leads.even.push(d.l);
  });
  // cross-pillar tenders in this category
  let relT = [];
  try {
    relT = tenders.filter((t) => t.cat === m.cat).slice(0, 4);
  } catch (e) {
    /* no tender pipeline -> no market exposure section */
  }
  // the det rows label this "Provenance"; "Source" matched 0 of 507 matchups
  const srcRow = (m.det || []).find((d) => d[0] === "Provenance" || d[0] === "Source");
  return (
    '<div class="tech-report">' +
    `<div class="trep-head"><div><div class="trep-eyebrow">Positioning Briefing · CEO</div><div class="trep-title">${escAll(m.comp)} vs ${escAll(m.bf)}</div></div><div class="trep-class">CONFIDENTIAL${clientShort() ? ` · ${clientShort()}` : ""}</div></div>` +
    `<div class="trep-meta">Prepared ${today} · Category: ${escAll(m.cat)} · Competitor: ${escAll(m.compBy)}</div>` +
    `<div class="trep-verdict ${v.cls}">${edgeWord}</div>` +
    `<div class="trep-sec"><div class="trep-h">1 · Bottom line</div><p>${m.verdict.replace(/<b>\[Analysis\]<\/b>\s*/, "")}</p></div>` +
    '<div class="trep-sec"><div class="trep-h">2 · Where each side leads (spec gap)</div>' +
    `<p><b>${escAll((m.compBy || m.comp || "—").split(" ")[0])} leads:</b> ${leads.comp.length ? escAll(leads.comp.join("; ")) : "—"}</p>` +
    `<p style="margin-top:6px"><b>${clientShort()} leads:</b> ${leads.bf.length ? escAll(leads.bf.join("; ")) : "—"}</p>` +
    (leads.even.length
      ? `<p style="margin-top:6px"><b>Comparable:</b> ${escAll(leads.even.join("; "))}</p>`
      : "") +
    "</div>" +
    `<div class="trep-sec"><div class="trep-h">3 · ${clientShort()} advantages to press</div><p>${(m.advBf || []).map((a) => `• ${stripTags(a)}`).join("<br>")}</p></div>` +
    `<div class="trep-sec"><div class="trep-h">4 · Competitor strengths to counter</div><p>${(m.advComp || []).map((a) => `• ${stripTags(a)}`).join("<br>")}</p></div>` +
    (relT.length
      ? `<div class="trep-sec"><div class="trep-h">5 · Where this matchup is live (market exposure)</div><p>Open tenders in ${escAll(m.cat)} where this competition plays out:</p>` +
        relT
          .map(
            (t) =>
              `<div class="trep-tender"><b>${escAll(t.title)}</b> - ${escAll(t.country)}, ${escAll(t.value)} · ${clientShort()} match: ${
                t.matches && t.matches[0]
                  ? `${escAll(t.matches[0].n)} (${escAll(t.matches[0].pct)})`
                  : "—"
              } · lean: <span class="trep-lean ${t.lean}">${t.lean}</span></div>`,
          )
          .join("") +
        "</div>"
      : "") +
    (srcRow ? `<div class="trep-sources">Competitor specs: ${escAll(srcRow[1])}</div>` : "") +
    '<div class="trep-foot"><button class="trep-print" data-print="1">⎙ Print / save as PDF</button></div>' +
    "</div>"
  );
}

export function techReportHtml(iv, d, techCatId, today = formatDate(new Date())) {
  const matLab = iv.matLabel || "—";
  const gapLab = iv.gapLabel || "";
  const catName = (() => {
    const c = d.techCats.filter((x) => x.id === techCatId)[0];
    return c ? c.name : "";
  })();
  let relTenders = [];
  let relComps = [];
  try {
    relTenders = d.tenders.filter((t) => t.cat === catName).slice(0, 4);
  } catch (e) {
    /* no matching tenders -> section omitted */
  }
  try {
    relComps = [
      ...new Set(
        Object.values(d.matchups)
          .filter((m) =>
            m.cat.toLowerCase().includes((catName.split(" ")[0] || "").toLowerCase()),
          )
          .map((m) => m.comp),
      ),
    ].slice(0, 6);
  } catch (e) {
    /* no matching matchups -> landscape list omitted */
  }
  return (
    '<div class="tech-report">' +
    `<div class="trep-head"><div><div class="trep-eyebrow">Intelligence Briefing · CEO</div><div class="trep-title">${escAll(iv.t)}</div></div><div class="trep-class">CONFIDENTIAL${clientShort() ? ` · ${clientShort()}` : ""}</div></div>` +
    `<div class="trep-meta">Prepared ${today} · Domain: ${escAll(catName)} · Maturity: ${escAll(matLab)} · Horizon: ${escAll(iv.horizon)}</div>` +
    `${gapLab ? `<div class="trep-verdict ${iv.gap}">${escAll(gapLab)}</div>` : ""}` +
    `<div class="trep-sec"><div class="trep-h">1 · Executive summary</div><p>${iv.body}</p></div>` +
    `<div class="trep-sec"><div class="trep-h">2 · What's new</div><p>${iv.whatsNew}</p></div>` +
    `<div class="trep-sec"><div class="trep-h">3 · Strategic implication for ${clientShort()}</div><p>${iv.impact.replace(/<b>\[Analysis\][^<]*<\/b>\s*/, "")}</p></div>` +
    `<div class="trep-sec"><div class="trep-h">4 · Competitive landscape</div><p>${iv.compNote}</p>` +
    (relComps.length
      ? `<p style="margin-top:8px"><b>Competitor products tracked in ${escAll(catName)}:</b><br>${relComps.map((c) => `• ${escAll(c)}`).join("<br>")}</p>`
      : "") +
    "</div>" +
    (relTenders.length
      ? `<div class=\"trep-sec\"><div class=\"trep-h\">5 · Live market exposure</div><p>Open tenders in this domain where the technology bears on ${clientShort()}'s bid:</p>` +
        relTenders
          .map(
            (t) =>
              `<div class="trep-tender"><b>${escAll(t.title)}</b> - ${escAll(t.country)}, ${escAll(t.value)} · matched: ${
                t.matches && t.matches[0]
                  ? `${escAll(t.matches[0].n)} (${escAll(t.matches[0].pct)})`
                  : "—"
              } · lean: <span class="trep-lean ${t.lean}">${t.lean}</span></div>`,
          )
          .join("") +
        "</div>"
      : "") +
    `<div class="trep-sources">Sources: ${attr(iv.sources || "—")} ` +
    srcChips(
      iv.srcs && iv.srcs.length
        ? iv.srcs
        : iv.url
          ? [{ label: "Source", url: iv.url }]
          : null,
    ) +
    "</div>" +
    '<div class="trep-foot"><button class="trep-print" data-print="1">⎙ Print / save as PDF</button></div>' +
    "</div>"
  );
}
