/* ===================================================================
   GEO MARKET OVERLAP
   Whether a rival overlaps the client in a country is a STORED judgement of that company's presence there
   (serving.competitive_geo_company_presence.overlap_status, with matched_ranges): the browser reads it and
   does not re-derive it. It used to classify footprint text into product categories by keyword, pair rival models
   to client models and decide who "leads"; none of that is database content, so it is gone.

   Built as a factory over the dataset: nothing is cached on `window`, so a re-fetch gets a fresh set.
   =================================================================== */
import { clientShort } from "./client.js";
import { escAll } from "./html.js";

/* the stored overlap words, mapped to the two badge styles the stylesheet has; any other word is no overlap */
const OV_TIER = { confirmed: "spec", category: "cat" };

export function createGeo(d) {
  const { geoData, geoComps, actLabel } = d;
  const geoPresence = d.geoPresence || [];
  // A KEY, not a label: geoData is keyed by the client's id.
  const CLIENT_KEY = (d.client && (d.client.id || d.client.short));

  /* IS THERE A CLIENT FOOTPRINT AT ALL? With no client footprint row on file an overlap cannot be assessed, and
     "no overlap" must not be read from that absence. Consumers branch on it. */
  const clientFootprintKnown = Object.keys((geoData && geoData[CLIENT_KEY]) || {}).length > 0;

  const countriesForComp = (cid) => Object.keys(geoData[cid] || {});
  const compsInCountry = (country) =>
    geoComps.filter((c) => geoData[c.id] && geoData[c.id][country]);
  const productsFor = (cid, country) => (geoData[cid] && geoData[cid][country]) || [];

  /* the stored presence row of one company in one country */
  const presenceOf = (cid, country) =>
    geoPresence.find((p) => String(p.cid) === String(cid) && p.country === country) || null;

  const rangesOf = (txt) => String(txt == null ? "" : txt).split(",").map((x) => x.trim()).filter(Boolean);

  /* the stored overlap of one rival in one country, or null when none is stored or the stored word says none */
  function geoOverlap(cid, country) {
    if (!clientFootprintKnown) return null;
    const c = geoComps.find((x) => x.id === cid);
    if (!c || c.isBf) return null;
    const p = presenceOf(cid, country);
    const tier = p && p.overlap != null ? OV_TIER[String(p.overlap).trim().toLowerCase()] : null;
    if (!tier) return null;
    return {
      comp: c, country, status: String(p.overlap).trim(), tier,
      ranges: rangesOf(p.ranges), productCount: p.productCount, summary: p.summary, relationship: p.relationship,
    };
  }

  // every rival with a stored overlap in one country
  function geoRivalsIn(country) {
    const ownData = geoData[CLIENT_KEY] || {};
    if (!ownData[country]) return [];
    return compsInCountry(country).map((c) => geoOverlap(c.id, country)).filter(Boolean);
  }

  const rangeText = (ov) => (ov.ranges.length ? ov.ranges.join(" · ") : "");

  // the marker that sits in front of the name
  function geoOvBadge(ov) {
    if (!ov) return "";
    const what = rangeText(ov);
    const tip = `Overlap ${escAll(ov.status)}${what ? `: ${escAll(what)}` : ""}`;
    return ov.tier === "spec"
      ? `<span class="geo-ovb spec" title="${tip}">◉ overlap</span>`
      : `<span class="geo-ovb cat" title="${tip}">◎ category only</span>`;
  }
  function geoOvBadgeCountry(country) {
    const rs = geoRivalsIn(country);
    if (!rs.length) return "";
    const spec = rs.filter((r) => r.tier === "spec").length;
    return spec
      ? `<span class="geo-ovb spec" title="${spec} rival${spec === 1 ? "" : "s"} with a confirmed overlap with ${escAll(clientShort())} here">◉ ${spec} contested</span>`
      : `<span class="geo-ovb cat" title="${rs.length} rival${rs.length === 1 ? "" : "s"} with a category overlap with ${escAll(clientShort())} here">◎ ${rs.length} category only</span>`;
  }

  /* ---- stored product comparisons (data.matchups, the Product Evaluation pairs) ----
     A rival product's client counterpart is the stored matchup on that product (compProductId). Its verdict is the
     stored decision level (competitive_matchup.decision_level); each spec row's winner and
     gap are stored (win, gap). Nothing is paired, graded or classified here. */
  const matchups = Object.values(d.matchups || {});
  const competitors = d.competitors || {};
  const pairOfProduct = (pid) => matchups.find((x) => String(x.compProductId) === String(pid)) || null;
  const pairsOfRival = (cid) => matchups.filter((x) => String(x.compId) === String(cid));
  const CMP_CLS = { rival: "gc-rival", koel: "gc-koel", level: "gc-level", none: "gc-none" };
  const cmpWord = (who) => ({
    rival: "Competitor’s product is better",
    koel: `${clientShort()} has the superior product`,
    level: "Level: neither leads",
    none: "Not decided: no stored verdict",
  })[who];
  // the stored rival product name carries "Company · " in front; the company is already named beside it
  const stripCo = (v) => String(v || "").replace(/^[^·]*·\s*/, "");
  const verdictOf = (x) => (x && x.decision != null ? ({ 1: "rival", 2: "level", 3: "koel" })[Number(x.decision)] || "none" : "none");

  function geoPairCard(x, rivalName) {
    const who = verdictOf(x);
    const specs = x.specs || [];
    const n = (w) => specs.filter((sp) => sp.win === w).length;
    const rv = n("competitor");
    const kv = n("client");
    const lv = n("equal");
    const ks = clientShort();
    const fmt = (v, u) => (v == null || v === "" ? "—" : escAll(`${v}${u && !String(v).includes(u) ? " " + u : ""}`));
    const pct = (g) => {
      const v = Number(g);
      return g == null || g === "" || !Number.isFinite(v) ? "" : `${v < 1 ? "<1" : v.toFixed(v < 10 ? 1 : 0)}%`;
    };
    const lead = (w, who2, cls) => {
      const t = specs.filter((sp) => sp.win === w).sort((a, b) => (Number(b.gap) || 0) - (Number(a.gap) || 0)).slice(0, 3);
      return t.length
        ? `<div class="gc-lead ${cls}"><b>${escAll(who2)} is ahead on</b> ${t
            .map((sp) => `${escAll(String(sp.l).replace(/ \(.*\)$/, ""))}${pct(sp.gap) ? ` (${pct(sp.gap)})` : ""}`)
            .join(", ")}</div>`
        : "";
    };
    let h =
      `<details class="gc-pair" open><summary><span class="gc-names"><b>${escAll(x.bf)}</b> <i>vs</i> <b>${escAll(stripCo(x.comp))}</b></span>` +
      `<span class="gc-chip ${CMP_CLS[who]}">${escAll(cmpWord(who))}</span>` +
      `<span class="gc-score">${rv + kv + lv ? `${escAll(rivalName)} ${rv} · ${escAll(ks)} ${kv} · level ${lv} (of ${rv + kv + lv} decided rows)` : "no decided rows"}</span></summary>`;
    if (x.verdictH) h += `<div class="gc-reason"><b>${escAll(x.verdictH)}</b></div>`;
    if (x.reason) h += `<div class="gc-reason">${escAll(x.reason)}</div>`;
    h += lead("competitor", rivalName, "rv") + lead("client", ks, "kv");
    h += `<table class="gc-tbl"><tr><th>Spec</th><th>${escAll(ks)}<br>${escAll(x.bf)}</th><th>${escAll(rivalName)}<br>${escAll(stripCo(x.comp))}</th><th>Gap</th></tr>`;
    const groups = [];
    specs.forEach((sp) => {
      const g = sp.group || "Other";
      if (!groups.includes(g)) groups.push(g);
    });
    groups.forEach((g) => {
      h += `<tr class="gc-grp"><td colspan="4">${escAll(g)}</td></tr>`;
      specs
        .filter((sp) => (sp.group || "Other") === g)
        .forEach((sp) => {
          const kw = sp.win === "client";
          const rw = sp.win === "competitor";
          h +=
            `<tr><td>${escAll(sp.l)}</td><td class="${kw ? "gc-win" : ""}">${fmt(sp.kv, sp.u)}${kw ? " ▲" : ""}</td>` +
            `<td class="${rw ? "gc-win rv" : ""}">${fmt(sp.cv, sp.u)}${rw ? " ▲" : ""}</td><td class="gc-gap">${kw || rw ? pct(sp.gap) : ""}</td></tr>`;
        });
    });
    h += "</table>";
    const q = [
      ...(x.advComp || []).map((t) => `<li class="rv">${escAll(t)}</li>`),
      ...(x.advBf || []).map((t) => `<li class="kv">${escAll(t)}</li>`),
    ];
    if (q.length) h += `<div class="gc-ql">Qualitative differences</div><ul class="gc-q">${q.join("")}</ul>`;
    if (x.verdict) h += `<div class="gc-reason">${escAll(x.verdict)}</div>`;
    return h + "</details>";
  }

  /* The rival's products in the categories the client also sells (the client's stored product categories), plus any
     with a stored comparison; matched first, then by category and name. One with no comparison says so. */
  function geoRivalProducts(cid) {
    const clientCats = new Set((((competitors[CLIENT_KEY] || {}).products) || []).map((p) => p.category).filter(Boolean));
    return (((competitors[cid] || {}).products) || [])
      .map((p) => ({ p, x: pairOfProduct(p.id) }))
      .filter(({ p, x }) => x || clientCats.has(p.category))
      .sort(
        (a, b) =>
          (b.x ? 1 : 0) - (a.x ? 1 : 0) ||
          String(a.p.category || "").localeCompare(String(b.p.category || "")) ||
          String(a.p.name).localeCompare(String(b.p.name)),
      );
  }
  function geoProductListHtml(cid, activeId) {
    const c = geoComps.find((x) => x.id === cid);
    if (!c || c.isBf) return "";
    const rows = geoRivalProducts(cid);
    if (!rows.length) return "";
    const nm = escAll(c.name);
    const ks = escAll(clientShort());
    const paired = rows.filter((r) => r.x).length;
    let h = `<div class="geo-pl-h"><span class="geo-pl-t">Products ${nm} sells</span><span class="geo-pl-n">${rows.length} model${rows.length === 1 ? "" : "s"} · ${paired} matched to a ${ks} model</span></div>`;
    h += `<div class="geo-pl-hint">Pick a model to compare it with its ${ks} counterpart on the right.</div>`;
    rows.forEach(({ p, x }) => {
      const who = x ? verdictOf(x) : null;
      const chip = x
        ? `<span class="gc-chip ${CMP_CLS[who]}">${escAll(cmpWord(who))}</span>`
        : `<span class="gc-chip gc-none">No matched ${ks} model</span>`;
      h +=
        `<div class="geo-rel-item prod${String(p.id) === String(activeId) ? " active" : ""}" data-cmp-prod="${escAll(p.id)}"><span class="ri-act ex"></span><div class="ri-main">` +
        `<div class="ri-nm">${escAll(p.name)}</div><div class="ri-desc">${escAll(p.category || "")}</div>` +
        `<div class="ri-counter${x ? "" : " none"}"><span class="rc-lab">${ks} counter</span> ` +
        (x ? `<span class="rc-prod">${escAll(x.bf)}</span>` : '<span class="rc-prod muted">no like-for-like product</span>') +
        ` ${chip}</div></div><span class="ri-chev">›</span></div>`;
    });
    return h;
  }
  // { title, html } for the right-hand pane: one rival model against its stored client counterpart
  function geoProductCompare(cid, pid) {
    const row = geoRivalProducts(cid).find((r) => String(r.p.id) === String(pid));
    if (!row) return null;
    const { p, x } = row;
    const c = geoComps.find((z) => z.id === cid) || { name: "" };
    if (x) return { title: `${p.name} vs ${x.bf}`, html: `<div class="gc">${geoPairCard(x, c.name)}</div>` };
    let h = `<div class="gc"><div class="gc-blk"><b>${escAll(p.name)}</b>: no like-for-like comparison. No stored comparison pairs it with a ${escAll(clientShort())} model.</div>`;
    const specs = Object.entries(p.specs || {});
    if (specs.length) {
      h += `<table class="gc-tbl"><tr><th>Spec</th><th>${escAll(p.name)}</th></tr>`;
      specs.forEach(([k, v]) => {
        h += `<tr><td>${escAll(k)}</td><td>${escAll(v)}</td></tr>`;
      });
      h += "</table>";
    }
    return { title: `${p.name}: no ${clientShort()} counterpart`, html: h + "</div>" };
  }

  /* The client's row in a country: every rival with a stored overlap, its stored ranges (or the categories of its
     stored comparisons), its stored comparisons and their stored verdicts, its stored activity here; then the
     stored footprint analysis for the country. */
  const KIND_WORD = { anomaly: "Anomaly", overlap: "Overlap", whitespace: "White space" };
  function analysisItems(country) {
    return ((d.geoAnalysis || {})[country] || []).map((a) => {
      const reasons = (a.reasons || []).map((x) => escAll(String(x).replace(/_/g, " "))).join(", ");
      const url = typeof a.url === "string" && /^https?:\/\//i.test(a.url) ? a.url : null;
      return (
        `<li><b>${escAll(KIND_WORD[a.kind] || a.kind)}${a.comp ? ` · ${escAll(a.comp)}` : ""}${a.ksslProduct ? ` vs ${escAll(a.ksslProduct)}` : ""}.</b> ${escAll(a.finding)}` +
        (a.reasonState === "stated" && reasons
          ? ` <span class="gv-ctr">Stated reason:</span> ${reasons}${url ? ` <a href="${escAll(url)}" target="_blank" rel="noopener noreferrer">source ↗</a>` : ""}`
          : "") +
        (a.reasonState === "not_stated"
          ? ` <span class="gv-non">Reason not stated in any source.${a.toFindOut ? ` Ask: ${escAll(a.toFindOut)}` : ""}</span>`
          : "") +
        (a.hypothesis ? ` <span class="gv-non"><i>${escAll(a.hypothesis)} (analyst hypothesis, no source)</i></span>` : "") +
        "</li>"
      );
    });
  }
  function geoOwnPanel(country) {
    const rs = geoRivalsIn(country);
    const ct = escAll(country);
    const ks = escAll(clientShort());
    const why = analysisItems(country);
    const whyHtml = why.length ? `<div class="geo-ov-why"><span class="gw-l">What this means for ${ks}</span><ul>${why.join("")}</ul></div>` : "";
    if (!clientFootprintKnown) {
      return `<div class="geo-ov none"><div class="geo-ov-h"><span class="geo-ov-t">◌ Overlap not assessed in ${ct}</span></div>${whyHtml}</div>`;
    }
    if (!rs.length) {
      return `<div class="geo-ov none"><div class="geo-ov-h"><span class="geo-ov-t">○ No overlapping rival on file in ${ct}</span></div>${whyHtml}</div>`;
    }
    const spec = rs.filter((r) => r.tier === "spec");
    const rows = rs
      .map((r) => {
        const pairs = pairsOfRival(r.comp.id);
        const graded = pairs.filter((x) => verdictOf(x) !== "none");
        return {
          r,
          pairs,
          graded: graded.length,
          rival: graded.filter((x) => verdictOf(x) === "rival").length,
          koel: graded.filter((x) => verdictOf(x) === "koel").length,
        };
      })
      .sort((a, b) => b.graded - a.graded || b.pairs.length - a.pairs.length);
    let h =
      `<div class="geo-ov ${spec.length ? "spec" : "cat"}"><div class="geo-ov-h"><span class="geo-ov-t">` +
      `${spec.length ? "◉ " : "◎ "}${rs.length} rival${rs.length === 1 ? "" : "s"} overlap ${ks} in ${ct}` +
      `${spec.length ? "" : " - none confirmed"}</span></div>`;
    h +=
      '<table class="geo-ov-tbl"><tr><th>Rival</th><th>Overlapping categories</th><th class="n">Matched pairs</th>' +
      "<th>Datasheet outcome</th><th>Presence</th></tr>";
    rows.forEach(({ r, pairs, graded, rival, koel }) => {
      const p = presenceOf(r.comp.id, country) || {};
      const cats = r.ranges.length ? r.ranges : [...new Set(pairs.map((x) => x.cat).filter(Boolean))];
      let out = '<span class="gv-non">no matched pair</span>';
      if (graded) {
        if (rival > koel) out = `<span class="gv-bad">rival leads ${rival} of ${graded}</span>`;
        else if (koel > rival) out = `<span class="gv-good">${ks} leads ${koel} of ${graded}</span>`;
        else out = '<span class="gv-mid">level</span>';
      } else if (pairs.length) out = '<span class="gv-non">pair found, no stored verdict</span>';
      h +=
        `<tr><td>${escAll(r.comp.name)}</td><td>${cats.length ? escAll(cats.join(" · ")) : '<span class="gv-non">—</span>'}</td>` +
        `<td class="n">${pairs.length || "—"}</td><td>${out}</td><td>${escAll(p.activity || "—")}</td></tr>`;
    });
    h += "</table>" + whyHtml;
    h +=
      '<div class="geo-ov-src">Overlap and categories from the stored footprint rows · datasheet outcome from the stored ' +
      "Product Evaluation comparisons with each rival · what it means from the stored footprint analysis.</div>";
    return `${h}</div>`;
  }

  /* Dot state for one row of the competitor dropdown. Scoped to the selected
     country when there is one, otherwise across every market the rival is in. */
  function geoPickOverlap(c, selCountry) {
    const n = countriesForComp(c.id).length;
    const mk = `${n} mkt${n === 1 ? "" : "s"}`;
    if (c.isBf)
      return { cls: "bf", meta: mk, tip: `${clientShort()} - present in ${n} market${n === 1 ? "" : "s"}` };
    const scope = selCountry ? [selCountry] : countriesForComp(c.id);
    /* "No overlap" is a finding; "not assessed" is not. With no client footprint on file the comparison
       cannot run, so this dot must not be the dot a rival earns by being assessed and cleared. */
    if (!clientFootprintKnown)
      return {
        cls: "ovl-unk",
        meta: mk,
        tip: `Overlap with ${clientShort()} not assessed${selCountry ? ` in ${selCountry}` : ""} - no ${clientShort()} footprint is on file to compare against`,
      };
    const ovs = scope.map((ct) => geoOverlap(c.id, ct)).filter(Boolean);
    if (!ovs.length)
      return { cls: "noovl", meta: mk, tip: `No overlap with ${clientShort()}${selCountry ? ` in ${selCountry}` : ""} on file` };
    const spec = ovs.filter((o) => o.tier === "spec");
    const where = selCountry ? ` in ${selCountry}` : ` in ${ovs.length} market${ovs.length === 1 ? "" : "s"}`;
    return spec.length
      ? { cls: "ovl", meta: mk, tip: `Overlaps ${clientShort()}${where} - ${spec.map((o) => o.status).join(" / ")}` }
      : { cls: "ovl-cat", meta: mk, tip: `Overlaps ${clientShort()}${where} - ${ovs.map((o) => o.status).join(" / ")}` };
  }

  /* Guards the join between the stored presence rows and the footprint: an overlap needs a stored presence row,
     and the dropdown dot must agree with the stored overlaps behind it. */
  function selfCheck() {
    const fail = [];
    const ok = (c, m) => {
      if (!c) fail.push(m);
    };
    Object.keys(geoData).forEach((cid) =>
      Object.keys(geoData[cid]).forEach((ct) => {
        const ov = geoOverlap(cid, ct);
        if (!ov) return;
        ok(!!presenceOf(cid, ct), `${ov.comp.name}/${ct}: an overlap with no stored presence row`);
      }),
    );
    geoComps.forEach((c) => {
      const got = geoPickOverlap(c, null).cls;
      const ovs = countriesForComp(c.id).map((ct) => geoOverlap(c.id, ct)).filter(Boolean);
      const want = c.isBf
        ? "bf"
        : !clientFootprintKnown
          ? "ovl-unk"
          : ovs.some((o) => o.tier === "spec")
            ? "ovl"
            : ovs.length
              ? "ovl-cat"
              : "noovl";
      ok(got === want, `dropdown dot for ${c.name} is "${got}" but the stored overlaps say "${want}"`);
    });
    ok(geoOverlap(CLIENT_KEY, "x") === null, "the client cannot overlap itself");
    if (fail.length) console.error("geo-overlap self-check FAILED:", fail);
    return fail;
  }

  return {
    clientFootprintKnown,
    countriesForComp,
    compsInCountry,
    productsFor,
    presenceOf,
    geoOverlap,
    geoRivalsIn,
    geoOvBadge,
    geoOvBadgeCountry,
    geoOwnPanel,
    geoProductListHtml,
    geoProductCompare,
    geoPickOverlap,
    actLabel,
    selfCheck,
  };
}

/* The Footprint Lookup's competitor menu, and the count line above it, must count the
   same companies. The menu offered the whole roster -- 174 rows on the live dataset,
   97 of them badged "0 mkts", each opening an empty panel -- while the count line
   said 77. A competitor with no served market is not a footprint to look up. */
export function geoCoveredCompetitors(d) {
  const geoData = (d && d.geoData) || {};
  return ((d && d.geoComps) || []).filter((c) => c && geoData[c.id] && Object.keys(geoData[c.id]).length > 0);
}

export function geoLookupCompetitors(d, country, query) {
  const geoData = (d && d.geoData) || {};
  const q = String(query || "").trim().toLowerCase();
  return geoCoveredCompetitors(d).filter(
    (c) =>
      (!q || String(c.name || "").toLowerCase().includes(q)) &&
      (!country || !!geoData[c.id][country]),
  );
}
