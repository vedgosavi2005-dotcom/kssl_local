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
      : `<span class="geo-ovb cat" title="${tip}">◎ ${escAll(ov.status)}</span>`;
  }
  function geoOvBadgeCountry(country) {
    const rs = geoRivalsIn(country);
    if (!rs.length) return "";
    const spec = rs.filter((r) => r.tier === "spec").length;
    return spec
      ? `<span class="geo-ovb spec" title="${spec} rival${spec === 1 ? "" : "s"} with a confirmed overlap with ${escAll(clientShort())} here">◉ ${spec} confirmed</span>`
      : `<span class="geo-ovb cat" title="${rs.length} rival${rs.length === 1 ? "" : "s"} with a category overlap with ${escAll(clientShort())} here">◎ ${rs.length} ${escAll(rs[0].status)}</span>`;
  }

  /* The client's row in a country: the rivals with a stored overlap, as stored. */
  function geoOwnPanel(country) {
    const rs = geoRivalsIn(country);
    const ct = escAll(country);
    if (!clientFootprintKnown) {
      return (
        '<div class="geo-ov none"><div class="geo-ov-h"><span class="geo-ov-t">◌ Overlap not assessed in ' +
        `${ct}</span></div></div>`
      );
    }
    if (!rs.length) {
      return `<div class="geo-ov none"><div class="geo-ov-h"><span class="geo-ov-t">○ No overlapping rival on file in ${ct}</span></div></div>`;
    }
    const spec = rs.filter((r) => r.tier === "spec");
    let h =
      `<div class="geo-ov ${spec.length ? "spec" : "cat"}"><div class="geo-ov-h"><span class="geo-ov-t">` +
      `${spec.length ? "◉ " : "◎ "}${rs.length} rival${rs.length === 1 ? "" : "s"} overlap ${escAll(clientShort())} in ${ct}` +
      "</span></div>";
    h += '<table class="geo-ov-tbl"><tr><th>Rival</th><th>Matched ranges</th><th>Overlap</th><th>Presence</th></tr>';
    rs.forEach((r) => {
      const p = presenceOf(r.comp.id, country) || {};
      h += `<tr><td>${escAll(r.comp.name)}</td><td>${escAll(rangeText(r) || "—")}</td><td>${escAll(r.status)}</td><td>${escAll(p.activity || "—")}</td></tr>`;
    });
    h += "</table>";
    h += "<div class=\"geo-ov-src\">Overlap and matched ranges are stored for each rival's presence in this country.</div>";
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
