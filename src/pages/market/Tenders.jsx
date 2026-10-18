import { clientShort } from "../../lib/client.js";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import HtmlBlock from "../../components/htmlBlock/HtmlBlock";
import ScopeChat from "../../components/scopeChat/ScopeChat";
import { isVisible } from "../../lib/visibility";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { gapCorrelateStrip } from "../../lib/gapModel";
import { productOwner } from "../../lib/productLink";
import { srcChips, cssWord } from "../../lib/html";
import { formatLabel, smartTitleCase } from "../../lib/profile";
import { facetOptions } from "../../lib/countryFacet";
import { NOT_ON_RECORD, reqLabel, resolveTenderRow, tenderCardCells, tenderFactRows, tenderFitBar, compareTenders } from "../../lib/tenderRow";
import { Review } from "../../components/review/Review";

const fitClass = (p) => {
  const n = parseInt(p, 10);
  return n >= 75 ? "high" : n >= 50 ? "mid" : "low";
};

const has = (v) => v != null && String(v).trim() !== "";

/* The source record's own reference (the part after the 'ted_/ca_/gem_/uk_/sam_'
   prefix on the id) — the number a buyer's portal actually indexes the notice by. */
const noticeRef = (t) => {
  if (!t || !t.id) return null;
  const s = String(t.id);
  const u = s.indexOf("_");
  return u > -1 ? s.slice(u + 1) : s;
};

/* The facts of a notice: the FIXED eight (src/lib/tenderRow.js) -- each a stored value
   or the explicit unresolved state -- then the notice reference the portal indexes it
   by. Rows are [label, text, resolved]. Nothing is dropped for being empty: a field the
   notice does not publish is a fact about the notice, and it used to vanish here (and
   an empty status used to be printed as "Open", which nobody recorded). */
const factRows = (t) => {
  if (!t) return [];
  const rows = tenderFactRows(t);
  const ref = noticeRef(t);
  rows.push(["Notice ref.", has(ref) ? ref : NOT_ON_RECORD, has(ref)]);
  return rows;
};

/* A meta line is only the parts the record carries — a null `value` used to leave
   its separator behind, so every card read "… ·  · …". A part is a string, or
   [text, className] where the original markup styled that span. */
const metaLine = (parts) =>
  parts
    .map((p) => (Array.isArray(p) ? p : [p, null]))
    .filter(([txt]) => has(txt))
    .map(([txt, cls], n) => (
      <Fragment key={`${n}-${txt}`}>
        {n ? <span className="sep">·</span> : null}
        <span className={cls || undefined}>{txt}</span>
      </Fragment>
    ));

const dlClass = (d, statusClass) => {
  if (statusClass) return statusClass;
  const n = Number(d);
  if (isNaN(n) || n <= 0) return "settled";
  return n <= 7 ? "urgent" : n <= 14 ? "soon" : "normal";
};

/* The button used to promise a portal and open nothing. Every tender carries its
   source URL, so open that. urlKind says what it lands on: 'notice' = this tender's
   own page, 'portal' = the listing it was found in, 'award' = an already-decided
   contract. Label it honestly rather than promising a notice we do not have. */
const tpUrl = (t) => (t && t.url) || (t && t.srcs && t.srcs.length ? t.srcs[0].url : null);
const ctaLabel = (t) =>
  t.urlKind === "award"
    ? "Read the award announcement"
    : t.urlKind === "portal"
      ? "Open the tender portal"
      : tpUrl(t)
        ? "Open the tender notice"
        : "Pursue this tender";
const ctaNote = (t) => {
  const u = tpUrl(t);
  if (!u) return "no source URL on this record";
  return (
    ({
      notice: "opens this tender on ",
      portal: "no per-tender page on record - opens the listing on ",
      award: "this contract is settled - opens the announcement on ",
    }[t.urlKind] || "opens ") + u.replace(/^https?:\/\/(www\.)?/, "").split("/")[0]
  );
};

export default function Tenders({ mode = "tender" }) {
  const { data, gapModel } = useData();
  const { setScope, takePending, searchQuery, jumpTo } = useAppState();
  const clientName = clientShort();
  /* a model named on a tender opens that product in Products; a label that is not a model stays text */
  const prodName = (name) => {
    const own = productOwner(data, name);
    return own ? (
      <button className="prod-link" onClick={() => jumpTo("competitive", "products", own)} title="Open this product in Products" type="button">{name}</button>
    ) : name;
  };
  const getSavedTender = () => {
    try {
      const s = localStorage.getItem("kssl_tender_state");
      return s ? JSON.parse(s) : {};
    } catch (e) { return {}; }
  };
  const savedTender = getSavedTender();

  const [productType, setProductType] = useState(null); // Product Type dropdown removed; ignore any saved value
  const [country, setCountry] = useState(savedTender.country || null);
  const [cat, setCat] = useState(savedTender.cat || null);
  const [menu, setMenu] = useState(null);
  const [menuQuery, setMenuQuery] = useState("");
  // Selection is NOT persisted: leaving the pillar and coming back collapses the
  // detail (operator request). Filters below DO persist, so the list stays as it was.
  const [sel, setSel] = useState(null);
  const asmtRef = useRef(null);

  useEffect(() => {
    if (asmtRef.current) {
      asmtRef.current.scrollTop = 0;
    }
  }, [sel]);

  useEffect(() => {
    try {
      localStorage.setItem("kssl_tender_state", JSON.stringify({ productType, country, cat }));
    } catch (e) {}
  }, [productType, country, cat]);

  /* A tab CHANGE drops the selection -- a row from the open list is not on the awarded
     list. Guarded against the mount run: an effect with [mode] also fires once after
     the first render, and that run was clearing the `sel` restored from localStorage
     three lines up, so the selection this page saves on every change never survived a
     reload or a detour to the Market Report and back. */
  const lastMode = useRef(mode);
  useEffect(() => {
    if (lastMode.current === mode) return;
    lastMode.current = mode;
    setSel(null);
  }, [mode]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (!e.target.closest(".tp-dd")) setMenu(null);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  /* `scope` is the tab and the search box -- everything that is NOT one of the three
     dropdown facets. Each facet's option counts are then taken from scope with the OTHER
     two facets applied, so a badge can never describe a different set than the rows
     below it. They read "India 7" over a list of 2, because the counts ran over all 106
     tenders while the list showed only the 74 that are open; five of those seven had
     closed. Product Type had the same fault and is included here -- fixing two of three
     facets and leaving the third is how this bug survives a fix. */
  const isAirNaval = (t) =>
    /uav|drone|naval|marine|missile|air defence/i.test(`${t.cat} ${t.title}`);

  const scope = useMemo(
    () =>
      (data.tenders || [])
        .filter((t) => {
          const isAwarded = (t.status || "").toLowerCase() === "awarded" || t.urlKind === "award";
          const isClosed = !isAwarded && (t.isLive === false || (t.status || "").toLowerCase() === "closed" || (t.deadline || "").toLowerCase().includes("closed"));
          const isOpen = !isAwarded && !isClosed;

          if (mode === "awarded-tenders") return isAwarded;
          if (mode === "closed-tenders") return isClosed;
          return isOpen;
        })
        .filter((t) => {
          if (!searchQuery) return true;
          const tokens = searchQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);
          const fullText = `${t.title || ""} ${t.issuer || ""} ${t.cat || ""} ${t.country || ""} ${t.desc || ""}`.toLowerCase();
          return tokens.every((tok) => fullText.includes(tok));
        }),
    [data.tenders, mode, searchQuery],
  );

  /* One place decides what each facet means, so the list and the counts cannot drift. */
  const facetOk = {
    country: (t, v) => !v || t.country === v,
    cat: (t, v) => !v || t.cat === v,
    productType: (t, v) =>
      !v || (v === "Air, Naval & Missiles" ? isAirNaval(t) : !isAirNaval(t)),
  };

  const applyFacets = (rows, except) =>
    rows.filter(
      (t) =>
        (except === "country" || facetOk.country(t, country)) &&
        (except === "cat" || facetOk.cat(t, cat)) &&
        (except === "productType" || facetOk.productType(t, productType)),
    );

  const list = useMemo(
    () =>
      applyFacets(scope, null).sort(compareTenders),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scope, country, cat, productType],
  );

  const select = (id) => {
    const t = (data.tenders || []).find((x) => x.id === id);
    if (!t) return;
    setSel(id);
    setScope("tender", { type: "tender", data: t }, {
      pillar: "Market",
      view: "Tenders",
      selection: `${t.title} (${t.country})`,
    });
  };

  /* A correlate chip elsewhere can open a tender here by title. */
  useEffect(() => {
    const p = takePending("tender");
    /* a category row on Market Intelligence opens the pipeline on that category (and country) */
    if (p && "cat" in p) {
      setCat(p.cat || null);
      setCountry(p.country || null);
      setProductType(null);
    }
    if (p && p.tenderTitle) {
      const t =
        (data.tenders || []).find((x) => x.title === p.tenderTitle) ||
        (data.tenders || []).find(
          (x) => x.title.indexOf(p.tenderTitle) > -1 || p.tenderTitle.indexOf(x.title) > -1,
        );
      if (t) {
        select(t.id);
        setTimeout(() => asmtRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 130);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takePending]);

  const t = sel ? (data.tenders || []).find((x) => x.id === sel) : null;

  /* What the header's Copy / Export / Print act on: the open tender's facts and
     requirement rows as served, then every tender listed under the tab and facets in
     force. */
  const modeTitle =
    mode === "awarded-tenders" ? "Awarded Tenders" : mode === "closed-tenders" ? "Closed Tenders" : "Tenders";
  const report = useMemo(() => {
    /* the same eight parameters the card shows, labelled, unresolved ones included */
    const row = (x) => [
      x.title,
      resolveTenderRow(x).params.map((p) => `${p.label}: ${p.text}`).join(" · "),
    ];
    const sections = [];
    if (t) {
      sections.push({
        h: "Selected tender",
        rows: [["Title", t.title], ...factRows(t).map(([k, v]) => [k, v])],
      });
      if (has(t.reqNote)) sections.push({ h: "Requirement", rows: [t.reqNote] });
      if (Array.isArray(t.req) && t.req.length) sections.push({ h: "Requirements", rows: t.req.map((r) => [reqLabel(r[0]), r[1]]) });
      if (Array.isArray(t.matches) && t.matches.length) {
        sections.push({
          h: `${clientName} match`,
          rows: t.matches.map((m) => [m.n, [m.fit, m.pct].filter(has).join(" · ")]),
        });
      }
    }
    sections.push({ h: `${modeTitle} (${list.length})`, rows: list.map(row) });
    return {
      title: modeTitle,
      subtitle: [country, cat, productType].filter(Boolean).join(" · ") || "all tenders in this tab",
      sections,
      payload: {
        tab: mode,
        filters: { country: country || null, category: cat || null, productType: productType || null },
        selected: t || null,
        tenders: list,
      },
    };
  }, [t, list, mode, modeTitle, country, cat, productType, clientName]);
  useHeaderReport(report);

  const menuItems = (which) => {
    if (which === "productType") {
      const pool = applyFacets(scope, "productType");
      return [
        { v: "Land Systems", n: pool.filter((x) => !isAirNaval(x)).length },
        { v: "Air, Naval & Missiles", n: pool.filter(isAirNaval).length },
      ];
    }
    /* Option values come from the SERVED tenders only. The config vocabulary
       (tpAllCountries / tpAllCats) ORDERS them; it adds nothing. It used to be unioned
       in "for completeness", which put Armenia, Kenya, Morocco and eight more countries
       with no tender at all into the menu as unclickable zero rows -- eleven of the
       twenty-five options were padding -- and the acceptance test read that as the
       filter not matching the data. An option is a promise of rows; a zero is not
       information a menu should carry.
       Counted over `scope` with the OTHER facets applied -- the facet being counted is
       excluded, so picking one of its options gives exactly the number promised. */
    const cfgOrder = which === "country" ? data.tpAllCountries || [] : data.tpAllCats || [];
    const pool = applyFacets(scope, which);
    const q = menuQuery.trim().toLowerCase();
    return facetOptions(pool, (x) => (which === "country" ? x.country : x.cat), cfgOrder)
      .filter((o) => which !== "country" || !q || o.v.toLowerCase().includes(q));
  };

  const dd = (which, label, value, setValue) => {
    /* one array: the "All" row prints its length, the rows under it are its members */
    const items = menuItems(which);
    return (
    <div className="tp-dd" data-tpdd={which}>
      <div
        className={`tp-dd-input${value ? " has-val" : ""}`}
        onClick={() => {
          setMenuQuery("");
          setMenu(menu === which ? null : which);
        }}
        role="button"
        tabIndex={0}
      >
        <span className="ddlbl">{label}</span>
        <span className={`ddval${value ? "" : " placeholder"}`}>{value || "All"}</span>
        <span className="caret">▾</span>
        <span
          className="ddclear"
          onClick={(e) => {
            e.stopPropagation();
            setValue(null);
          }}
        >
          ×
        </span>
      </div>
      <div className={`tp-dd-menu${menu === which ? " open" : ""}`}>
        {which === "country" ? (
          <div className="tp-dd-search">
            <input
              autoComplete="off"
              onChange={(e) => setMenuQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder="Search country…"
              type="text"
              value={menu === "country" ? menuQuery : ""}
            />
          </div>
        ) : null}
        <div
          className="tp-dd-pick tp-dd-all"
          onClick={() => {
            setValue(null);
            setMenu(null);
          }}
        >
          All {which === "country" ? "countries" : which === "productType" ? "product types" : "categories"} ({items.length})
        </div>
        {items.map(({ v, n }) => (
          <div
            className="tp-dd-pick"
            key={v}
            onClick={() => {
              setValue(v);
              setSel(null);
              setMenu(null);
            }}
          >
            {v}
            <span className="m">{n}</span>
          </div>
        ))}
      </div>
    </div>
    );
  };

  return (
    <div className={`tp-view v-tender ${t ? "has-sel" : "no-sel"}`}>
      <div className="tp-list">
        <div className="tp-fbar">
          <span className="eyebrow">Filter</span>
          {dd("country", "Country", country, setCountry)}
          {dd("cat", "Category", cat, setCat)}
          {/* the one deadline hint the operator kept; the verbose count line and the
              "no fit assessment" note below it are cut as redundant noise. Fit is now
              shown per card WHEN a tender carries it, and silent when it does not --
              no list-level placeholder. */}
          <span className="sortnote">{clientName} fit first, then deadline</span>
        </div>
        <div id="tp-cards">
          {list.length ? (
            list.map((row) => {
              const fit = tenderFitBar(row);
              return (
                <div
                  className={`tcard${sel === row.id ? " sel" : ""}`}
                  key={row.id}
                  onClick={() => select(row.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      select(row.id);
                    }
                  }}
                >
                  <div className="trow1">
                    <div className="ttl">{smartTitleCase(row.title)}</div>
                    <span className={`ddl ${dlClass(row.dl, row.statusClass)}`}>{row.deadline}</span>
                  </div>
                  <div className="tpgrid">
                    {/* The same five cells on every card, in this order: Buyer, Country, Category, Value, Status.
                        A cell the record leaves empty prints the screen's empty word, it is not dropped. */}
                    {tenderCardCells(row).map((c) => (
                      <div className="tpp" key={c.key}>
                        <span className="tpk">{c.label}</span>
                        <span className="tpv">{c.text}</span>
                      </div>
                    ))}
                  </div>
                  {/* the client's fit row is on every card: the bar and the stored word, or an empty bar and a dash */}
                  <div className="fitbar">
                    <span className="fitlab">{clientName} fit</span>
                    <span className="fittrack">
                      <i className={fit.cls} style={{ width: fit.width }} />
                    </span>
                    <span className={`fitpct${fit.scored ? "" : " grade"}`}>{fit.word}</span>
                  </div>
                  <Review src={row._src} />
                </div>
              );
            })
          ) : (
            <div className="tp-list-empty">
              {productType || country || cat
                ? "No tenders match this filter"
                : "No tenders served yet"}
            </div>
          )}
        </div>
      </div>

      <div className="tp-asmt" id="tp-asmt">
        {t ? (
          <div id="tp-asmt-body" style={{ display: "flex", flex: 1, flexDirection: "column", height: "100%", overflow: "hidden" }}>
            <div className="tp-asmt-scroll" ref={asmtRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: "24px" }}>
              <div className="tp-asmt-h">
                <div className="ctx-h-actions">
                  <button
                    aria-label="Close"
                    className="col-close"
                    onClick={() => setSel(null)}
                    title="Close"
                    type="button"
                  >
                    ✕
                  </button>
                </div>
                <span className="eyebrow">Tender Assessment</span>
                <div className="ct">{smartTitleCase(t.title)}</div>
                <Review src={t._src} />
                <div className="sub" style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "8px" }}>
                  <div>{metaLine([t.issuer, t.country, t.value])}</div>
                  <div>{metaLine([t.timing || t.deadline])}</div>
                </div>
              </div>

              {/* Client fit & rank section */}
              {(() => {
                const m0 = (t.matches || [])[0];
                const pctNum = m0 && /%/.test(m0.pct || "")
                  ? parseFloat(String(m0.pct).replace(/[^\d.]/g, ""))
                  : NaN;
                const scored = !Number.isNaN(pctNum);
                const graded = !!(m0 && has(m0.fit));
                const fc = scored ? fitClass(m0.pct) : graded ? m0.fit : null;
                const fp = scored
                  ? m0.pct
                  : graded
                    ? { high: "strong", mid: "partial", low: "weak" }[fc] || fc
                    : "";
                const verdict = fp || t.fit;
                if (!verdict && !has(t.rank)) return null;
                return (
                  <div className="tp-asmt-sec">
                    <span className="eyebrow">{clientName} Fit{has(t.rank) ? ` · Rank #${t.rank}` : ""}</span>
                    {verdict ? (
                      <div className={`tp-fit-verdict ${{ strong: "high", partial: "mid", weak: "low" }[String(verdict).toLowerCase()] || ""}`}>{verdict.charAt(0).toUpperCase() + verdict.slice(1)}</div>
                    ) : null}
                  </div>
                );
              })()}

              <div className="tp-asmt-sec">
                <span className="eyebrow">Tender details</span>
                <div className="tp-facts">
                  {factRows(t).filter(([, v]) => v !== NOT_ON_RECORD).map(([k, v, resolved]) => (
                    <div className="kv" key={k}>
                      {/* the label wears the house capitalisation, the value never does */}
                      <span className="k">{formatLabel(k)}</span>
                      <span className={`v${resolved ? "" : " na"}`}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>

              {has(t.reqNote) || (t.req || []).length || has(t.desc) ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">What the tender requires</span>
                  {has(t.reqNote) ? (
                    <div className="req" dangerouslySetInnerHTML={{ __html: t.reqNote }} />
                  ) : has(t.desc) ? (
                    <div className="req">{t.desc}</div>
                  ) : null}
                  {(t.req || []).map((r, i) => (
                    <div className="kv" key={`${r[0]}-${i}`}>
                      <span className="k">{reqLabel(r[0])}</span>
                      <span className="v" dangerouslySetInnerHTML={{ __html: r[1] }} />
                    </div>
                  ))}
                </div>
              ) : null}

              {(t.matches || []).length ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Matched {clientName} products</span>
                  {(t.matches || []).map((m, i) => (
                    <div className="tp-match" key={`${m.n}-${i}`}>
                      <div className="mh">
                        <span className="mn">{prodName(m.n)}</span>
                        {/* the stored percentage, else the stored fit word (strong / partial / weak) */}
                        <span className={`fit ${cssWord(m.fit)}`}>{has(m.pct) ? m.pct : has(m.fit) ? m.fit : "—"} fit</span>
                      </div>
                      {/* a stored line is [label, value] (market_tender_product_match_line); a reference-style line is
                          [up|down, text]. Only a stored direction draws an arrow. */}
                      {(m.lines || []).map((l, j) => {
                        const dirn = l[0] === "up" || l[0] === "down";
                        return (
                          <div className="mline" key={j}>
                            <span className={`mk ${dirn ? l[0] : "info"}`}>{l[0] === "up" ? "▲" : l[0] === "down" ? "▼" : "•"}</span>
                            <span>
                              {dirn || !has(l[0]) ? null : <b>{l[0]}: </b>}
                              <span dangerouslySetInnerHTML={{ __html: l[1] }} />
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              ) : null}

              {has(t.revenueEstimate) || has(t.expectedRevenue) ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Expected revenue (estimate)</span>
                  <div className="req">{t.revenueEstimate || t.expectedRevenue}</div>
                </div>
              ) : null}

              {(t.competitorFit || t.competitors || []).length ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Competitor fit</span>
                  {/* served shape: { company, products[], why, incumbent } (db/tender_fit.py) */}
                  {(t.competitorFit || t.competitors).map((c, i) => (
                    <div className="tp-comp-card" key={i}>
                      <div className="tp-comp-header">
                        <span className="tp-comp-name">{c.company || c.name || c.n}</span>
                        {c.incumbent ? <span className="fit high">Incumbent</span> : c.fit ? <span className={`fit ${cssWord(c.fit)}`}>{c.fit} fit</span> : null}
                      </div>
                      {(c.products || c.models || c.lines || []).map((l, j) => (
                        <div className="tp-comp-line" key={j}>
                          <span className="tp-comp-arrow">▲</span>
                          <span>{typeof l === "string" ? prodName(l) : l[1] || l.text}</span>
                        </div>
                      ))}
                      {c.why || c.desc || c.note || c.rationale ? (
                        <div className="tp-comp-desc">{c.why || c.desc || c.note || c.rationale}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="tp-asmt-sec">
                {srcChips(t.srcs && t.srcs.length ? t.srcs : t.url ? [{ label: "Source", url: t.url }] : null) ? (
                  <div style={{ marginTop: "10px" }}>
                    <span className="eyebrow">Source</span>
                    <div
                      dangerouslySetInnerHTML={{
                        __html: srcChips(
                          t.srcs && t.srcs.length ? t.srcs : t.url ? [{ label: "Source", url: t.url }] : null,
                        ),
                      }}
                      style={{ marginTop: "5px" }}
                    />
                  </div>
                ) : null}
              </div>

              <div className="tp-cta-wrap">
                <button
                  className="tp-pursue"
                  onClick={() => {
                    const u = tpUrl(t);
                    if (u) window.open(u, "_blank", "noopener,noreferrer");
                    else
                      window.alert(
                        `No source URL on record for:\n\n${t.title}\n${t.issuer} · ${t.country}`,
                      );
                  }}
                  type="button"
                >
                  {ctaLabel(t)} <span style={{ fontFamily: "var(--mono)" }}>→</span>
                </button>
                <div className="tp-cta-note">{ctaNote(t)}</div>
              </div>
            </div>

            {isVisible("chat") ? <ScopeChat placeholder="Ask about this tender…" scopeKey="tender" /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
