import { clientShort } from "../../lib/client.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { marketNews } from "../../lib/news";
import HtmlBlock from "../../components/htmlBlock/HtmlBlock";
import ScopeChat from "../../components/scopeChat/ScopeChat";
import { isVisible } from "../../lib/visibility";
import GeoMap, { servedGeoCountries } from "../../components/geoMap/GeoMap";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { geoLookupCompetitors } from "../../lib/geo";
import { useData } from "../../state/DataProvider";
import { srcChips, attr, escAll, cssWord } from "../../lib/html";
import Thumb from "../../components/thumb/Thumb.jsx";
/* A SELECTION IS REMEMBERED WHILE YOU STAY IN THIS PILLAR, not for ever. This page
   persisted to localStorage, which survives the tab, the browser and the machine's
   next reboot -- so a company opened once was still the landing selection weeks
   later, on a dashboard whose job is "what is new". Same key/value shape, held in
   memory, cleared on a pillar change. See lib/viewState. */
import * as viewState from "../../lib/viewState";
import { REVIEW, ReviewList } from "../../components/review/Review";

/* Two dropdowns resolve to one of three lists — countries for a rival, rivals in a
   country, or the products for a pair — and every product opens a detail column.
   The dropdown dots mark OVERLAP WITH KSSL, not threat level, so the contested
   rivals are findable without opening each one. */
/* Only http(s) becomes a link. The urls come from the pipeline rather than from a
   person, but this markup is injected as a string, so a `javascript:` value would
   otherwise become a working link. */
function safeHref(u) {
  return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null;
}
/* The same fallback the React <Thumb> gives, for the one thumbnail that lives inside a
   markup string. An <img> whose fetch fails is drawn as the browser's broken glyph, so
   a publisher blocking hotlinking looks exactly like a broken page. */
const THUMB_ONERROR =
  "this.outerHTML='&lt;div class=&quot;thumb-none&quot; style=&quot;width:72px;height:60px;"
  + "flex-shrink:0&quot;&gt;&lt;span class=&quot;thumb-none-label&quot;&gt;No image"
  + "&lt;/span&gt;&lt;/div&gt;'";

export default function Geo() {
  const { data, geo } = useData();
  const { setScope } = useAppState();
  const clientName =
    clientShort();
  const getSavedGeo = () => {
    try {
      const s = viewState.getItem("kssl_geo_state");
      return s ? JSON.parse(s) : {};
    } catch (e) {
      return {};
    }
  };
  const savedGeo = getSavedGeo();

  const [comp, setComp] = useState(savedGeo.comp || null);
  const [country, setCountry] = useState(savedGeo.country || null);
  const [showDetail, setShowDetail] = useState(!!savedGeo.showDetail);
  const [menu, setMenu] = useState(null); // 'comp' | 'country' | null
  const [menuQuery, setMenuQuery] = useState("");
  const [back, setBack] = useState(savedGeo.back || null); // {mode, arg}
  const [pair, setPair] = useState(savedGeo.pair || null); // {cid, country}
  const [cmp, setCmp] = useState(null); // {prod} while the product comparison pane is open
  const [prodIndex, setProdIndex] = useState(
    savedGeo.prodIndex !== undefined ? savedGeo.prodIndex : null,
  );
  const rootRef = useRef(null);

  /* Three invented market stories used to be returned here for every
     company-country pair -- "$120M Export Contract for 18 Platform Units", a
     "CAIRO / NEW DELHI" dateline, attributed to a "Ministry of Defence / Official
     Export Filings", a "Defence Procurement Directorate" and a "Bilateral Trade &
     Export Credit Bureau", none of which issued anything. They are replaced by the
     company's real pipeline news filtered to the articles that name this country;
     when none do, the panel shows nothing rather than something untrue. */
  const geoNewsArticles = useMemo(() => {
    const cid = comp || (pair ? pair.cid : null);
    const ctName = country || (pair ? pair.country : null);
    if (!cid || !ctName) return [];
    return marketNews(data, cid, ctName);
  }, [comp, country, pair, data]);
  useEffect(() => {
    try {
      viewState.setItem(
        "kssl_geo_state",
        JSON.stringify({ comp, country, showDetail, pair, prodIndex, back }),
      );
    } catch (e) {}
  }, [comp, country, showDetail, pair, prodIndex, back]);

  const closeDetail = () => {
    setShowDetail(false);
    setPair(null);
    setComp(null);
    setCountry(null);
    setBack(null);
    setProdIndex(null);
    try {
      viewState.removeItem("kssl_geo_state");
    } catch (e) {}
  };

  // clicking outside closes whichever menu is open
  useEffect(() => {
    const onDocClick = (e) => {
      if (!e.target.closest(".geo-dd")) setMenu(null);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  /* resolve(): what the middle list shows, given the two selections */
  const resolved = useMemo(() => {
    if (!comp && !country) return { kind: "empty" };
    if (comp && country) return { kind: "products", cid: comp, country };
    if (comp) return { kind: "countries", cid: comp };
    return { kind: "competitors", country };
  }, [comp, country]);

  /* A fresh resolve drops the product detail, as the original's resetProdDetail did --
     with two exceptions this effect used to trample:
       - its MOUNT run. An effect with these deps fires once after the first render,
         and that run cleared the pair, the Back door and the open product just
         restored from localStorage: a drill into "Adani Defence in India" came back
         from a reload, or from a detour to Patents, as the competitor's country list.
       - a click that sets a selection AND a pair in one go (a map marker: country +
         top competitor's products). The pair landed, the effect saw the country
         change and wiped it. `holdPair` is set by openProducts for exactly that tick. */
  const mounted = useRef(false);
  const holdPair = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    if (holdPair.current) {
      holdPair.current = false;
      return;
    }
    setBack(null);
    setProdIndex(null);
    if (resolved.kind === "products")
      setPair({ cid: resolved.cid, country: resolved.country });
    else setPair(null);
  }, [resolved.kind, resolved.cid, resolved.country]);

  const openProducts = (cid, ct, backMode, backArg) => {
    holdPair.current = true;
    setPair({ cid, country: ct });
    setProdIndex(null);
    if (backMode) setBack({ mode: backMode, arg: backArg });
  };

  useEffect(() => { setCmp(null); }, [pair && pair.cid, pair && pair.country]);
  const cmpProd = pair && cmp && cmp.prod ? geo.geoProductCompare(pair.cid, cmp.prod) : null;
  const prods = pair ? geo.productsFor(pair.cid, pair.country) : [];
  const prod = prodIndex !== null && prods ? prods[prodIndex] : null;

  /* What the header's Copy / Export / Print act on: whichever of the four resolutions
     is on screen -- a company in a country (with the open product), a company's
     countries, a country's companies -- read straight from geoData. */
  const report = useMemo(() => {
    const compName = (id) => {
      const co = (data.geoComps || []).find((x) => x.id === id);
      return co ? co.name : id;
    };
    const nd = (v) => (v && v !== "n/d" ? String(v) : "—");
    const prodRow = (p) => [p.name, [p.stage, p.qty, p.val, p.since].filter((v) => v && v !== "n/d").join(" · ")];
    const plural = (k, w) => `${k} ${w}${k === 1 ? "" : "s"}`;
    if (pair) {
      const rows = geo.productsFor(pair.cid, pair.country);
      return {
        title: `${compName(pair.cid)} in ${pair.country}`,
        subtitle: `${plural(rows.length, "product")} on record`,
        sections: [
          prod
            ? {
                h: prod.name,
                rows: [
                  ["Stage", nd(prod.stage)],
                  ["Quantity", nd(prod.qty)],
                  ["Value", nd(prod.val)],
                  ["Since", nd(prod.since)],
                  prod.note ? ["Note", prod.note] : null,
                  prod.srcnote ? ["Source", prod.srcnote] : null,
                ].filter(Boolean),
              }
            : null,
          { h: "Products in this market", rows: rows.map(prodRow) },
        ].filter(Boolean),
        payload: { cid: pair.cid, company: compName(pair.cid), country: pair.country, selected: prod || null, products: rows },
      };
    }
    if (resolved.kind === "countries") {
      const byCountry = (data.geoData || {})[resolved.cid] || {};
      const rows = Object.entries(byCountry).map(([ct, ps]) => [ct, plural((ps || []).length, "product")]);
      return {
        title: `${compName(resolved.cid)} · markets`,
        subtitle: plural(rows.length, "country").replace("countrys", "countries"),
        sections: [{ h: "Countries", rows }],
        payload: { cid: resolved.cid, company: compName(resolved.cid), countries: byCountry },
      };
    }
    if (resolved.kind === "competitors") {
      const present = Object.entries(data.geoData || {}).filter(([, by]) => by && by[resolved.country]);
      return {
        title: `${resolved.country} · competitors present`,
        subtitle: plural(present.length, "company").replace("companys", "companies"),
        sections: [{ h: "Competitors", rows: present.map(([id, by]) => [compName(id), plural(by[resolved.country].length, "product")]) }],
        payload: {
          country: resolved.country,
          competitors: present.map(([id, by]) => ({ cid: id, company: compName(id), products: by[resolved.country] })),
        },
      };
    }
    /* nothing selected: every company with a footprint, and how many countries it is in */
    const all = Object.entries(data.geoData || {}).map(([id, by]) => [id, Object.keys(by || {})]);
    return {
      title: "Geo Footprint",
      subtitle: `${plural(all.length, "company").replace("companys", "companies")} · no competitor or country selected`,
      sections: [
        {
          h: "Companies by footprint",
          rows: all.map(([id, countries]) => [compName(id), plural(countries.length, "country").replace("countrys", "countries")]),
        },
      ],
      payload: { companies: all.map(([id, countries]) => ({ cid: id, company: compName(id), countries })) },
    };
  }, [pair, prod, resolved, geo, data]);
  useHeaderReport(report);

  // selecting a product scopes the panel chat to it
  useEffect(() => {
    if (!pair || !prod) return;
    const co = data.geoComps.find((x) => x.id === pair.cid);
    setScope(
      "geo",
      {
        type: "geo",
        data: prod,
        comp: co ? co.name : pair.cid,
        country: pair.country,
      },
      {
        pillar: "Competitive",
        view: "Geo Footprint",
        selection: `${co ? co.name : pair.cid} → ${pair.country}`,
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pair, prodIndex]);

  /* ---- dropdown menus ---- */
  /* Only competitors with a served footprint (lib/geo.js geoLookupCompetitors). This
     offered the whole roster -- 174 rows on the live dataset, 97 badged "0 mkts",
     each opening an empty panel -- under a count line that said 77. */
  const compMenuItems = useMemo(
    () => geoLookupCompetitors(data, country, menuQuery),
    [data, menuQuery, country],
  );

  const countryMenuItems = useMemo(() => {
    const q = menuQuery.toLowerCase();
    // only countries the served footprint data actually covers — geoCountries orders them
    let list = servedGeoCountries(data).filter((c) => c.toLowerCase().includes(q));
    if (comp) {
      const cc = geo.countriesForComp(comp);
      list = list.filter((ct) => cc.includes(ct));
    }
    return list;
  }, [data, menuQuery, comp, geo]);

  const compName = comp
    ? (data.geoComps.find((x) => x.id === comp) || {}).name
    : "All";

  /* The footprint cards are the presence rows (company x country); the lists below are drawn as
     markup strings, so the review copy lists the same records with their controls. The overlay
     lists the rows behind what it shows, the map lists all of them. */
  const presenceItems = (rows) =>
    (rows || []).map((p) => ({ src: p._src, label: [p.comp, p.country, p.activity, p.status].filter(Boolean).join(" · ") }));
  const allPresences = data.geoPresence || [];
  const shownPresences = pair
    ? allPresences.filter((p) => p.cid === pair.cid && p.country === pair.country)
    : resolved.kind === "countries"
      ? allPresences.filter((p) => p.cid === resolved.cid)
      : resolved.kind === "competitors"
        ? allPresences.filter((p) => p.country === resolved.country)
        : [];

  /* ---- the middle list, as markup (rows are dense and data-carrying) ----
     `pair` wins over `resolved`: drilling from a country row into its products sets
     the pair without changing the two dropdowns, and the list has to follow the drill
     rather than the dropdowns. The Back button clears the pair to come back out. */
  /* the activity word of a footprint row, as stored */
  const actOf = (p) => escAll(geo.actLabel[p.c]);
  /* the client's own row is drawn in the client colour and reads "<client> present", as in the reference */
  const actCls = (c, p) => (c && c.isBf ? "bf" : cssWord(p.c));
  const actWord = (c, p) => (c && c.isBf ? `${escAll(clientName)} present` : actOf(p));

  const relList = () => {
    if (pair) {
      // `pair` is rehydrated from localStorage: a company dropped from a later
      // dataset would otherwise take the whole panel down on mount
      const c = data.geoComps.find((x) => x.id === pair.cid);
      const ovPanel = c && c.isBf ? geo.geoOwnPanel(pair.country) : "";
      return (
        (c && !c.isBf ? geo.geoProductListHtml(pair.cid, cmp && cmp.prod) : "") +
        ovPanel +
        prods
          .map((p, i) => {
            return `<div class="geo-rel-item prod${i === prodIndex ? " active" : ""}" data-pi="${i}"><span class="ri-act ${cssWord(p.c)}"></span><div class="ri-main"><div class="ri-nm">${escAll(p.name)} ${
              p.src === "syn"
                ? '<span class="syn" title="Illustrative" style="margin-left:4px"></span>'
                : '<span class="srcbadge" style="margin-left:4px;font-size:7.5px;padding:1px 4px">Sourced</span>'
            }</div><div class="ri-desc"><span class="ri-actlab ${cssWord(p.c)}">${actOf(p)}</span>${p.qty ? ` · ${escAll(p.qty)}` : ""}</div><span class="ri-tag">${escAll(p.stage)}${
              p.val && p.val !== "n/d" ? ` · ${escAll(p.val)}` : ""
            }</span></div><span class="ri-chev">›</span></div>`;
          })
          .join("")
      );
    }
    if (resolved.kind === "countries") {
      const c = data.geoComps.find((x) => x.id === resolved.cid);
      const cs = geo.countriesForComp(resolved.cid);
      return cs
        .map((ct) => {
          const rows = geo.productsFor(resolved.cid, ct);
          const ov = c.isBf ? null : geo.geoOverlap(resolved.cid, ct);
          const badge = c.isBf ? geo.geoOvBadgeCountry(ct) : geo.geoOvBadge(ov);
          const cls = c.isBf
            ? geo.geoRivalsIn(ct).some((o) => o.tier === "spec")
              ? " ov-spec"
              : geo.geoRivalsIn(ct).length
                ? " ov-cat"
                : ""
            : ov
              ? ` ov-${ov.tier}`
              : "";
          const meets = ov && ov.ranges.length ? ` · meets ${clientName} in ${escAll(ov.ranges.join(", "))}` : "";
          return `<div class="geo-rel-item${cls}" data-country="${attr(ct)}"><span class="ri-act ${actCls(c, rows[0])}"></span><div class="ri-main"><div class="ri-nm">${badge}${escAll(ct)}</div><div class="ri-desc">${rows.length} product${rows.length !== 1 ? "s" : ""} · ${actWord(c, rows[0])}${rows.length > 1 ? " +" : ""}${meets}</div><span class="ri-tag">since ${escAll(rows[0].since)}</span></div></div>`;
        })
        .join("");
    }
    if (resolved.kind === "competitors") {
      const cs = geo.compsInCountry(resolved.country);
      return cs
        .map((c) => {
          const rows = geo.productsFor(c.id, resolved.country);
          const ov = geo.geoOverlap(c.id, resolved.country);
          const meets = ov && ov.ranges.length ? ` · meets ${clientName} in ${escAll(ov.ranges.join(", "))}` : "";
          return `<div class="geo-rel-item${ov ? ` ov-${ov.tier}` : ""}" data-comp="${attr(c.id)}"><span class="ri-act ${actCls(c, rows[0])}"></span><div class="ri-main"><div class="ri-nm">${geo.geoOvBadge(ov)}${escAll(c.name)}</div><div class="ri-desc">${rows.length} product${rows.length !== 1 ? "s" : ""} · ${actWord(c, rows[0])}${rows.length > 1 ? " +" : ""}${meets}</div><span class="ri-tag">${escAll(rows[0].name)}</span></div></div>`;
        })
        .join("");
    }
    return "";
  };

  /* ---- the product detail column ---- */
  const detailBody = () => {
    if (!pair || !prod) return "";
    const p = prod;
    const kv = [
      ["Activity", geo.actLabel[p.c]],
      ["Quantity", p.qty],
      ...(p.val && p.val !== p.qty ? [["Value", p.val]] : []),
      ...(p.customer ? [["Customer", p.customer]] : []),
      ...(p.localPartner ? [["Local partner", p.localPartner]] : []),
      ["Stage", p.stage],
      ["Since", p.since],
    ];
    /* The "What this means for KSSL" caption was removed: it was a hand-written
       interpretation the code authored per activity type ("a local foothold that can
       deepen over time", "often precedes platform competition"), not a served fact. The
       activity itself is the structured "Activity" row below and stays. */
    const coName = comp ? (data.geoComps.find((x) => x.id === comp)?.name || comp) : (pair ? pair.cid : "OEM");
    const newsCardsHtml = !geoNewsArticles.length ? "" : `
      <div style="padding: 16px 18px 24px 18px; border-top: 1px solid #e2e8f0; margin-top: 16px; background: #f8fafc;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
          <span style="width: 7px; height: 7px; border-radius: 50%; background: #992424; display: inline-block;"></span>
          <span style="font-family: var(--mono); font-size: 11px; color: #334155; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;">
            PRODUCT & MARKET NEWS INTEL (${escAll(coName)} · ${escAll(p.name)})
          </span>
        </div>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          ${geoNewsArticles.map((article) => `
            <!-- THE WHOLE CARD IS THE LINK, as on Profile and Products. It used to open
                 an in-app drawer that re-hosted the story, with the publisher's own link
                 buried inside it; a news item now goes to the news source. An <a> gives
                 the reader the affordances a div with a delegated handler never had --
                 the status-bar preview, middle-click, open-in-new-tab, copy link. A row
                 with no usable url stays a plain div rather than a link that goes
                 nowhere. -->
            ${safeHref(article.url) ? `<a
              class="geo-news-card-item"
              href="${attr(article.url)}"
              target="_blank"
              rel="noopener noreferrer"
              title="Open this article at ${escAll(article.source || "the source")}"
              style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,0.05); display: flex; gap: 10px; align-items: center; text-decoration: none; color: inherit;"
            >` : `<div
              class="geo-news-card-item"
              style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); display: flex; gap: 10px; align-items: center;"
            >`}
              ${article.image
                ? `<img src="${attr(article.image)}" alt="${escAll(article.title)}" loading="lazy" decoding="async" onerror="${THUMB_ONERROR}" style="width: 72px; height: 60px; border-radius: 4px; object-fit: contain; flex-shrink: 0; background: #f1f5f9;" />`
                : `<div class="thumb-none" style="width: 72px; height: 60px; flex-shrink: 0;"><span class="thumb-none-label">No image</span></div>`}
              <div style="display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0;">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span style="background: #f1f5f9; color: #b5341f; font-family: var(--mono); font-size: 9.5px; font-weight: 700; padding: 1px 5px; border-radius: 3px; border: 1px solid #cbd5e1;">${escAll(article.category)}</span>
                  <span style="font-size: 10.5px; color: #64748b;">${escAll(article.ago)}</span>
                </div>
                <div style="font-size: 12px; font-weight: 700; color: #0f172a; line-height: 1.3;">${escAll(article.title)}</div>
                <!-- the publisher's NAME, not a nested <a>: an anchor inside an anchor is
                     invalid, and browsers close the outer one at the inner tag, which
                     would leave the lower half of the card unclickable -->
                <div style="font-size: 10.5px; color: #64748b;">Source: <span style="color:#b5341f;font-weight:600">${escAll(article.source)}${safeHref(article.url) ? " &#8599;" : ""}</span></div>
              </div>
            ${safeHref(article.url) ? "</a>" : "</div>"}
          `).join("")}
        </div>
      </div>
    `;

    return (
      `<div class="geo-d-sec"><span class="eyebrow">Product</span><div style="font-size:12.5px;color:var(--l-txt-2);line-height:1.5;margin-bottom:12px">${p.note}</div>` +
      kv
        .map(
          (x) =>
            `<div class="geo-d-row" style="border-bottom:1px solid var(--l-bg-2)"><span class="gt" style="color:var(--l-txt-3);min-width:90px">${x[0]}</span><span class="gt" style="flex:1;text-align:right;font-family:var(--mono);font-size:11px">${escAll(x[1])}</span></div>`,
        )
        .join("") +
      `<div class="geo-d-row" style="border-bottom:none"><span class="gt" style="color:var(--l-txt-3);min-width:90px">Source</span><span class="gt" style="flex:1;text-align:right;font-family:var(--mono);font-size:11px;color:${
        p.src === "syn" ? "var(--synthetic)" : "var(--ok)"
      }">${p.src === "syn" ? '<span class="syn" title="Analytical estimate"></span> ' : ""}${attr(
        p.srcnote && !/^https?:/i.test(p.srcnote)
          ? p.srcnote
          : p.src === "syn"
            ? "analytical estimate"
            : "—",
      )} ${srcChips(p.srcs)}</span></div></div>` +
      newsCardsHtml
    );
  };

  const relHeader = () => {
    if (pair) {
      const c = data.geoComps.find((x) => x.id === pair.cid);
      if (!c) {
        return { kind: "Products supplied", name: pair.country, subHtml: "" };
      }
      const counts = {};
      prods.forEach((p) => {
        const k = p.c;
        counts[k] = (counts[k] || 0) + 1;
      });
      const chips = Object.keys(counts)
        .map(
          (k) =>
            `<span class="geo-mix-chip ${cssWord(k)}"><span class="mc-dot"></span>${counts[k]} ${geo.actLabel[k]}</span>`,
        )
        .join("");
      return {
        kind: "Products supplied",
        name: `${c.name} → ${pair.country}`,
        subHtml: `${prods.length} product${prods.length !== 1 ? "s" : ""} in this market <div class="geo-mix">${chips}</div>`,
      };
    }
    if (resolved.kind === "countries") {
      const c = data.geoComps.find((x) => x.id === resolved.cid);
      const cs = geo.countriesForComp(resolved.cid);
      const nOv = c.isBf
        ? cs.filter((ct) => geo.geoRivalsIn(ct).length).length
        : cs.filter((ct) => geo.geoOverlap(resolved.cid, ct)).length;
      /* "meets KSSL in 0 of them" used to print for EVERY rival, because the overlap
         test has no left-hand side when no client footprint is served (see
         clientFootprintKnown in lib/geo.js). Zero there measures nothing — it is the
         absence of a comparison, not a finding of separation, so the line says so. */
      const meetsLine = geo.clientFootprintKnown
        ? ` · meets ${clientName} in ${nOv} of them`
        : ` · overlap with ${clientName} not assessed - no ${clientName} footprint on file`;
      return {
        kind: c.isBf ? "Own markets" : "Competitor markets",
        name: c.name,
        sub: `Supplies ${cs.length} market${cs.length !== 1 ? "s" : ""}${
          c.isBf
            ? ` · ${nOv} contested by a rival offering, ${cs.length - nOv} with none on file`
            : meetsLine
        } - select one for products`,
      };
    }
    if (resolved.kind === "competitors") {
      const cs = geo.compsInCountry(resolved.country);
      const rivals = cs.filter((c) => !c.isBf).length;
      const ownData = data.geoData
        ? data.geoData[data.client?.id || clientShort()] ||
          data.geoData[data.client?.short] ||
          {}
        : {};
      const bf = !!ownData[resolved.country];
      const ovs = geo.geoRivalsIn(resolved.country);
      const nSpec = ovs.filter((o) => o.tier === "spec").length;
      const nCat = ovs.length - nSpec;
      /* "KSSL absent" with a warning triangle fired on 100% of countries: the served
         footprint tables carry no client rows at all, so `bf` is false everywhere and
         the header was reporting a data gap as a market retreat. A missing footprint
         table cannot say KSSL is absent from any one country — only that nothing is
         on file about where it is. */
      const presence = geo.clientFootprintKnown
        ? bf
          ? ` · ${clientName} present`
          : ` · ${clientName} not on record here`   // no row for this country is not proof of absence
        : ` · ${clientName} presence not established - no footprint on file`;
      let sub = `${rivals} competitor${rivals !== 1 ? "s" : ""} active${presence}`;
      if (bf)
        sub += ovs.length
          ? ` · ${nSpec} with a confirmed overlap${nCat ? `, ${nCat} on category only` : ""}`
          : ` · no rival with a stored overlap here`;
      return {
        kind: "Market",
        name: resolved.country,
        sub: `${sub} - select one for products`,
      };
    }
    return { kind: "Results", name: "—", sub: "" };
  };

  const head = relHeader();
  const co = pair ? data.geoComps.find((x) => x.id === pair.cid) : null;
  /* the header carries a stance class only for the client's own row, which is the one the data marks */
  const dir = prod && co && co.isBf ? "client" : null;

  return (
    <div className="geo-view v-geo" ref={rootRef} style={{ position: "relative" }}>
      {/* top control bar: two dropdowns */}
      <div className="geo-bar">
        <span className="eyebrow">
          Footprint Lookup{" "}
          <span className="srcbadge" style={{ marginLeft: "6px" }}>
            Sourced
          </span>
        </span>

        <div className="geo-dd" data-dd="comp">
          <div
            className={`geo-dd-input${comp ? " has-val" : ""}`}
            onClick={() => {
              setMenuQuery("");
              setMenu(menu === "comp" ? null : "comp");
            }}
            role="button"
            tabIndex={0}
          >
            <span className="ddlbl">Competitor</span>
            <span className={`ddval${comp ? "" : " placeholder"}`}>
              {compName}
            </span>
            <span className="caret">▾</span>
            <span
              className="ddclear"
              onClick={(e) => {
                e.stopPropagation();
                setComp(null);
              }}
              title="clear"
            >
              ×
            </span>
          </div>
          <div className={`geo-dd-menu${menu === "comp" ? " open" : ""}`}>
            <div className="geo-dd-search">
              <input
                onChange={(e) => setMenuQuery(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="Search competitor…"
                type="text"
                value={menu === "comp" ? menuQuery : ""}
              />
            </div>
            {compMenuItems.length ? (
              compMenuItems.map((c) => {
                const ov = geo.geoPickOverlap(c, country);
                return (
                  <div
                    className={`geo-pick${comp === c.id ? " sel" : ""}`}
                    key={c.id}
                    onClick={() => {
                      setComp(c.id);
                      setMenu(null);
                      setShowDetail(true);
                    }}
                    title={ov.tip}
                  >
                    <span className={`pk-dot ${ov.cls}`} />
                    <span className="pk-nm">{c.name}</span>
                    <span className="pk-meta">{ov.meta}</span>
                  </div>
                );
              })
            ) : (
              <div
                className="geo-pick"
                style={{ cursor: "default", color: "var(--d-txt-4)" }}
              >
                No competitors match
              </div>
            )}
          </div>
        </div>

        <div className="geo-dd" data-dd="country">
          <div
            className={`geo-dd-input${country ? " has-val" : ""}`}
            onClick={() => {
              setMenuQuery("");
              setMenu(menu === "country" ? null : "country");
            }}
            role="button"
            tabIndex={0}
          >
            <span className="ddlbl">Country</span>
            <span className={`ddval${country ? "" : " placeholder"}`}>
              {country || "All"}
            </span>
            <span className="caret">▾</span>
            <span
              className="ddclear"
              onClick={(e) => {
                e.stopPropagation();
                setCountry(null);
              }}
              title="clear"
            >
              ×
            </span>
          </div>
          <div className={`geo-dd-menu${menu === "country" ? " open" : ""}`}>
            <div className="geo-dd-search">
              <input
                onChange={(e) => setMenuQuery(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="Search country…"
                type="text"
                value={menu === "country" ? menuQuery : ""}
              />
            </div>
            {countryMenuItems.length ? (
              countryMenuItems.map((ct) => {
                const n = geo.compsInCountry(ct).filter((c) => !c.isBf).length;
                const ownData = data.geoData
                  ? data.geoData[data.client?.id || clientShort()] ||
                    data.geoData[data.client?.short] ||
                    {}
                  : {};
                const bf = !!ownData[ct];
                const dot = !bf && n > 0 ? "threat" : bf ? "client" : "none";
                return (
                  <div
                    className={`geo-pick${country === ct ? " sel" : ""}`}
                    key={ct}
                    onClick={() => {
                      setCountry(ct);
                      setMenu(null);
                      setShowDetail(true);
                    }}
                  >
                    <span className={`pk-dot ${dot}`} />
                    <span className="pk-nm">{ct}</span>
                    <span className="pk-meta">
                      {n}
                      {!bf && n > 0 ? " ⚠" : ""}
                    </span>
                  </div>
                );
              })
            ) : (
              <div
                className="geo-pick"
                style={{ cursor: "default", color: "var(--d-txt-4)" }}
              >
                No countries match
              </div>
            )}
          </div>
        </div>
      </div>

      {/* content */}
      <div className="geo-content-map">
        <div className="geo-map-full">
          <GeoMap
            data={data}
            geo={geo}
            onSelectCountry={(ct) => {
              /* A dot click opens the COUNTRY MARKET list (the competitors active in
                 that country), NOT a single company's products. It used to call
                 openProducts() with the top competitor, which sets a `pair`; a pair
                 wins over `resolved` in the panel, so the click landed straight on
                 Products-supplied. Selecting the country with no competitor resolves to
                 { kind: "competitors" } — the market list — and the user drills into a
                 company from there (which sets the Back button via the data-comp
                 handler). Clear any prior comp/pair/drill so the market list always
                 shows, even on a re-click of the same country. */
              setComp(null);
              setCountry(ct);
              setPair(null);
              setProdIndex(null);
              setBack(null);
              setShowDetail(true);
            }}
            selectedCountry={country || (pair ? pair.country : null)}
          />
        </div>
        {REVIEW ? (
          <div style={{ position: "absolute", left: 12, bottom: 56, width: 380, maxHeight: "42%", overflowY: "auto", zIndex: 5 }}>
            <ReviewList items={presenceItems(allPresences)} title="Footprint records" />
          </div>
        ) : null}
      </div>

      {showDetail && (country || pair || comp) ? (
        <div className="geo-det-overlay" id="geo-det">
            <div
              className={dir ? `geo-d-h dir-${dir}` : "geo-d-h"}
              style={{
                position: "relative",
                background: "#1c1c1f",
                color: "#ffffff",
                padding: "14px 18px",
                borderBottom: "1px solid #2a2a2f",
              }}
            >
              <div
                className="geo-hdr-controls"
                style={{
                  position: "absolute",
                  right: "18px",
                  top: "12px",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  zIndex: 30,
                }}
              >

                {back ? (
                  <button
                    className="geo-back"
                    onClick={() => {
                      setPair(null);
                      setBack(null);
                    }}
                    type="button"
                    style={{
                      position: "static",
                      margin: 0,
                      color: "#cbd5e1",
                      borderColor: "#475569",
                      background: "rgba(255,255,255,0.08)",
                      padding: "4px 10px",
                      fontSize: "11px",
                      borderRadius: "4px",
                      cursor: "pointer",
                    }}
                  >
                    ‹ Back
                  </button>
                ) : null}
                <button
                  aria-label="Close"
                  className="geo-close-btn"
                  onClick={closeDetail}
                  title="Close and view full map"
                  type="button"
                  style={{
                    position: "static",
                    cursor: "pointer",
                    background: "rgba(255,255,255,0.08)",
                    border: "1px solid #475569",
                    borderRadius: "4px",
                    fontSize: "14px",
                    color: "#cbd5e1",
                    padding: "3px 8px",
                    lineHeight: 1,
                  }}
                >
                  ✕
                </button>
              </div>

              <span
                className="eyebrow"
                style={{
                  color: "#94a3b8",
                  display: "block",
                  fontSize: "10px",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                {head.kind}
              </span>
              <div
                className="geo-hdr-main"
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "14px",
                  flexWrap: "wrap",
                  marginTop: "4px",
                  paddingRight: "440px",
                }}
              >
                <div
                  className="ct"
                  style={{
                    fontSize: "16px",
                    color: "#ffffff",
                    fontWeight: "700",
                    margin: 0,
                    lineHeight: "1.3",
                  }}
                >
                  {head.name}
                </div>
                {head.subHtml ? (
                  <div
                    className="geo-rel-sub"
                    style={{
                      margin: 0,
                      color: "#cbd5e1",
                      fontSize: "12px",
                      lineHeight: "1.4",
                    }}
                    dangerouslySetInnerHTML={{ __html: head.subHtml }}
                  />
                ) : (
                  <div
                    className="geo-rel-sub"
                    style={{
                      fontSize: "12px",
                      color: "#cbd5e1",
                      margin: 0,
                      lineHeight: "1.4",
                    }}
                  >
                    {head.sub}
                  </div>
                )}
              </div>
            </div>

            <div
              className={`geo-det-overlay-body${prod || cmpProd ? " has-prod" : " no-prod"}`}
            >
              <div className="geo-rel-overlay-list">
                <HtmlBlock
                  handlers={{
                    ".geo-rel-item[data-country]": (el) =>
                      openProducts(
                        resolved.cid,
                        el.getAttribute("data-country"),
                        "countries",
                        resolved.cid,
                      ),
                    ".geo-rel-item[data-comp]": (el) =>
                      openProducts(
                        el.getAttribute("data-comp"),
                        resolved.country,
                        "competitors",
                        resolved.country,
                      ),
                    ".geo-rel-item[data-pi]": (el) => {
                      setCmp(null);
                      setProdIndex(Number(el.getAttribute("data-pi")));
                    },
                    ".geo-rel-item[data-cmp-prod]": (el) => {
                      setProdIndex(null);
                      setCmp({ prod: el.getAttribute("data-cmp-prod") });
                    },
                  }}
                  html={relList()}
                  id="geo-rel-list"
                />
                <ReviewList items={presenceItems(shownPresences)} title="Footprint records" />
              </div>

              {cmpProd && !prod && (
                <div className="geo-det-product-sec" style={{ background: "transparent", display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
                  <div className="geo-det-product-scroll" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: "24px" }}>
                    <div className="geo-d-h" style={{ position: "relative", background: "#ffffff", color: "#0f172a", padding: "14px 18px", borderBottom: "1px solid #e2e8f0" }}>
                      <button
                        aria-label="Close comparison"
                        className="geo-close-btn"
                        onClick={() => setCmp(null)}
                        title="Close"
                        type="button"
                        style={{ position: "absolute", right: "14px", top: "12px", cursor: "pointer", background: "#f1f5f9", border: "1px solid #cbd5e1", borderRadius: "4px", fontSize: "14px", color: "#334155", padding: "3px 8px", lineHeight: 1 }}
                      >
                        ✕
                      </button>
                      <span className="eyebrow" style={{ color: "#64748b", display: "block", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Product comparison · {(data.geoComps.find((x) => x.id === pair.cid) || {}).name} in {pair.country}
                      </span>
                      <div className="ct" style={{ fontSize: "15px", color: "#0f172a", fontWeight: 700, marginTop: "2px", lineHeight: 1.3, paddingRight: "40px" }}>
                        {cmpProd.title}
                      </div>
                    </div>
                    <HtmlBlock html={cmpProd.html} id="geo-cmp-body" />
                  </div>
                </div>
              )}

              {prod && (
                <div
                  className="geo-det-product-sec"
                  style={{ background: "transparent", display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}
                >
                  <div className="geo-det-product-scroll" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: "24px" }}>
                    <div
                      className={dir ? `geo-d-h dir-${dir}` : "geo-d-h"}
                      style={{
                        position: "relative",
                        background: "#ffffff",
                        color: "#0f172a",
                        padding: "14px 18px",
                        borderBottom: "1px solid #e2e8f0",
                      }}
                    >
                      <button
                        aria-label="Close product details"
                        className="geo-close-btn"
                        onClick={() => setProdIndex(null)}
                        title="Close product details"
                        type="button"
                        style={{
                          position: "absolute",
                          right: "14px",
                          top: "12px",
                          cursor: "pointer",
                          background: "#f1f5f9",
                          border: "1px solid #cbd5e1",
                          borderRadius: "4px",
                          fontSize: "14px",
                          color: "#334155",
                          padding: "3px 8px",
                          lineHeight: 1,
                        }}
                      >
                        ✕
                      </button>
                      <span
                        className="eyebrow"
                        style={{
                          color: "#64748b",
                          display: "block",
                          fontSize: "10px",
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                        }}
                      >
                        {co
                          ? `${co.name} · ${pair.country}`
                          : `Product Detail & ${clientName} Counters`}
                      </span>
                      <div
                        className="ct"
                        style={{
                          fontSize: "15px",
                          color: "#0f172a",
                          fontWeight: "700",
                          marginTop: "2px",
                          lineHeight: "1.3",
                          paddingRight: "40px",
                        }}
                      >
                        {prod.name}
                      </div>
                      <div
                        className="gd-sub"
                        style={{
                          fontSize: "11.5px",
                          color: "#475569",
                          marginTop: "4px",
                          lineHeight: "1.4",
                        }}
                      >
                        {geo.actLabel[prod.c]}
                      </div>
                    </div>
                    {/* No delegated news handler any more: the card IS an anchor, so the
                        browser navigates and nothing here has to. That also retires the
                        guard that used to sit in this handler -- it existed only because
                        one click was doing two things, opening the drawer behind the
                        publisher's own link. */}
                    <HtmlBlock html={detailBody()} id="geo-d-body" />
                  </div>
                  {isVisible("chat") ? (
                    <ScopeChat
                      placeholder="Ask about this market or product…"
                      scopeKey="geo"
                    />
                  ) : null}
                </div>
              )}
            </div>
          </div>
        ) : null}

        {/* THE FULL-SCREEN ARTICLE OVERLAY IS GONE. A geo news card is now an anchor to
            the publisher (see newsCardsHtml above), at the operator's request, so nothing
            opens this any more -- and what it showed was the pipeline's own read of the
            article laid out as the article. */}
    </div>
  );
}
