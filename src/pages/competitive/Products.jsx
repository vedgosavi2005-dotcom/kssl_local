import { useState, useMemo, useEffect } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { specValueWithUnit } from "../../lib/specs";
import { ArticleLink } from "../../components/sourceLink/SourceLink.jsx";
import { Review } from "../../components/review/Review.jsx";
import * as viewState from "../../lib/viewState";

/* PRODUCTS. Every value comes from the product tables as served (backend/areas/b_products.py):
     rival catalogue   competitive_product + _specification, _program, _news
                       -> data.competitors[cid].products[]
     KSSL catalogue    client_product + _specification, _program, _source -> data.clientProducts[]
     comparison link   competitive_matchup (client_product_id / competitor_product_id)
   Nothing is guessed, defaulted or written here: a product without specs, programmes or news
   shows nothing for them. Product images are hidden by decision.

   Live web-mentions (/api/pulse, Google News RSS) are the one live, non-DB element, by decision.
   They are a slow server-side fetch, so the result is cached per product for the session:
   re-selecting a product is instant. In-memory Map backed by sessionStorage, both wrapped so
   blocked storage degrades to memory-only. They are shown in their own block, never as a
   substitute for the stored product news. */
const PULSE_CACHE = new Map();
const pulseKey = (cid, product) => `${cid}|${product}`;
function readPulse(k) {
  if (PULSE_CACHE.has(k)) return PULSE_CACHE.get(k);
  try {
    const s = sessionStorage.getItem("pulse:" + k);
    if (s) { const v = JSON.parse(s); PULSE_CACHE.set(k, v); return v; }
  } catch (e) { /* private mode / blocked storage: memory only */ }
  return null;
}
function writePulse(k, v) {
  PULSE_CACHE.set(k, v);
  try { sessionStorage.setItem("pulse:" + k, JSON.stringify(v)); } catch (e) { /* ignore */ }
}

const lc = (v) => String(v == null ? "" : v).trim().toLowerCase();
const nameKey = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const UNCATEGORISED = "Uncategorised";

/* a stored date, for display; a value that is not a date is shown as stored */
const fmtDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

/* Filter options for the sidebar selects: [{ v, n }] over the roster rows, every option backed
   by at least one company, sorted by value. */
function facetOptions(rows, valuesOf) {
  const counts = new Map();
  rows.forEach((r) => {
    new Set((valuesOf(r) || []).filter(Boolean)).forEach((v) => counts.set(v, (counts.get(v) || 0) + 1));
  });
  return [...counts.entries()].map(([v, n]) => ({ v, n })).sort((a, b) => a.v.localeCompare(b.v));
}

const SECTION_HEAD = {
  fontFamily: "var(--mono)",
  fontSize: "12px",
  letterSpacing: ".1em",
  textTransform: "uppercase",
  color: "var(--d-txt)",
  fontWeight: "700",
  marginBottom: "14px",
  paddingBottom: "8px",
  borderBottom: "1px solid var(--d-line)",
};

/* the stored status colour when the record carries one, else a neutral chip */
const statusStyle = (color) => ({
  fontFamily: "var(--mono)",
  fontSize: "10.5px",
  padding: "2px 8px",
  borderRadius: "4px",
  color: color || "var(--d-txt-3)",
  border: `1px solid ${color || "var(--d-line)"}`,
  textTransform: "uppercase",
  letterSpacing: ".04em",
});

const PRODUCTS_KEY = "kssl_products_cid";

export default function Products() {
  const { data } = useData();
  const { setScope, jumpTo, takePending, searchQuery } = useAppState();

  const clientCid = (data.client && data.client.id) || "";
  const clientName = (data.client && (data.client.short || data.client.name)) || "";

  const [companyQuery, setCompanyQuery] = useState("");
  const [sidebarCountryFilter, setSidebarCountryFilter] = useState("all");
  const [sidebarCategoryFilter, setSidebarCategoryFilter] = useState("all");
  const [sidebarRevenueFilter, setSidebarRevenueFilter] = useState("all");

  /* Roster: KSSL first (its own catalogue, client_product), then the tracked competitors in the
     served order. Country and revenue tier are the stored columns (origin_country, revenue_tier);
     categories are the categories of the company's own products. */
  const companyRoster = useMemo(() => {
    const rows = [];
    if (clientCid) {
      rows.push({
        cid: clientCid,
        name: clientName,
        isClient: true,
        threat: "",
        sector: "",
        countries: [],
        categories: [...new Set((data.clientProducts || []).map((p) => p.category).filter(Boolean))],
        revenueTier: "",
      });
    }
    const order = (data.compOrder || []).filter((id) => data.competitors[id]);
    const rest = Object.keys(data.competitors || {}).filter((id) => order.indexOf(id) < 0 && id !== clientCid);
    order.concat(rest).forEach((id) => {
      if (id === clientCid) return;
      const co = data.competitors[id];
      if (!co) return;
      const facet = (data.productFacets || {})[id] || {};
      rows.push({
        cid: id,
        name: co.name || "",
        isClient: false,
        threat: co.threat || "",
        sector: co.sector || "",
        countries: facet.country ? [facet.country] : [],
        categories: [...new Set((co.products || []).map((p) => p.category).filter(Boolean))],
        revenueTier: facet.revenueTier || "",
      });
    });
    return rows;
  }, [data, clientCid, clientName]);

  const firstCid = companyRoster[0] ? companyRoster[0].cid : "";
  /* Remembered while you stay in this pillar (lib/viewState). A saved id the served roster no
     longer carries falls back to the first row. */
  const [selectedCid, setSelectedCidState] = useState(() => {
    try {
      const saved = viewState.getItem(PRODUCTS_KEY);
      if (saved && companyRoster.some((r) => r.cid === saved)) return saved;
    } catch (e) {}
    return firstCid;
  });
  const setSelectedCid = (next) => {
    setSelectedCidState(next);
    try {
      if (next) viewState.setItem(PRODUCTS_KEY, next);
      else viewState.removeItem(PRODUCTS_KEY);
    } catch (e) {}
  };
  useEffect(() => {
    if (!selectedCid && firstCid) setSelectedCid(firstCid);
  }, [selectedCid, firstCid]);

  const [selectedProduct, setSelectedProduct] = useState(null);
  const [productSearch, setProductSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  /* Portfolio categories the reader has collapsed. Every category starts OPEN; a different
     company starts OPEN again. */
  const [collapsedCats, setCollapsedCats] = useState(() => new Set());
  useEffect(() => { setCollapsedCats(new Set()); }, [selectedCid]);
  const toggleCat = (catName) =>
    setCollapsedCats((prev) => {
      const next = new Set(prev);
      if (next.has(catName)) next.delete(catName);
      else next.add(catName);
      return next;
    });

  // product news category pill
  const [prodNewsFilter, setProdNewsFilter] = useState("All");
  useEffect(() => { setProdNewsFilter("All"); }, [selectedProduct]);

  /* Opened from the global search with {cid | company, productName}; the product is selected a
     render later, once that company's catalogue exists. */
  const [pendingProduct, setPendingProduct] = useState(null);
  useEffect(() => {
    const p = takePending("products");
    if (!p) return;
    let cid = p.cid || null;
    if (!cid && p.company) {
      const row = companyRoster.find((r) => lc(r.name) === lc(p.company));
      if (row) cid = row.cid;
    }
    if (cid && companyRoster.some((r) => r.cid === cid)) {
      setSelectedCid(cid);
      setSelectedProduct(null);
      setProductSearch("");
      setCategoryFilter("all");
    }
    if (p.productName) setPendingProduct(String(p.productName));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takePending]);

  const sidebarCountries = useMemo(() => facetOptions(companyRoster, (c) => c.countries), [companyRoster]);
  const sidebarCategories = useMemo(() => facetOptions(companyRoster, (c) => c.categories), [companyRoster]);
  const sidebarRevenue = useMemo(() => facetOptions(companyRoster, (c) => [c.revenueTier]), [companyRoster]);

  const filteredCompanyRoster = useMemo(() => {
    const q = (companyQuery || searchQuery || "").trim().toLowerCase();
    const tokens = q.split(/\s+/).filter(Boolean);
    return companyRoster.filter((c) => {
      if (tokens.length > 0) {
        const fullText = `${c.name} ${c.sector}`.toLowerCase();
        if (!tokens.every((tok) => fullText.includes(tok))) return false;
      }
      if (sidebarCountryFilter !== "all" && !c.countries.includes(sidebarCountryFilter)) return false;
      if (sidebarCategoryFilter !== "all" && !c.categories.includes(sidebarCategoryFilter)) return false;
      if (sidebarRevenueFilter !== "all" && c.revenueTier !== sidebarRevenueFilter) return false;
      return true;
    });
  }, [companyRoster, companyQuery, searchQuery, sidebarCountryFilter, sidebarCategoryFilter, sidebarRevenueFilter]);

  const selectedCompany = useMemo(() => {
    const row = companyRoster.find((r) => r.cid === selectedCid);
    return { cid: selectedCid, name: row ? row.name : "", isClient: !!(row && row.isClient) };
  }, [companyRoster, selectedCid]);

  /* The selected company's catalogue, as served. Same shape for both sides. */
  const companyProducts = useMemo(() => {
    const list = selectedCompany.isClient
      ? data.clientProducts || []
      : ((data.competitors || {})[selectedCid] || {}).products || [];
    return list.filter((p) => p && p.name).map((p) => ({ ...p, category: p.category || "", specs: p.specs || [] }));
  }, [data, selectedCid, selectedCompany]);

  useEffect(() => {
    if (pendingProduct === null) return;
    const want = nameKey(pendingProduct);
    const hit = companyProducts.find((p) => nameKey(p.name) === want);
    if (hit) setSelectedProduct(hit);
    setPendingProduct(null);
  }, [pendingProduct, companyProducts]);

  const categories = useMemo(
    () => [...new Set(companyProducts.map((p) => p.category || UNCATEGORISED))],
    [companyProducts],
  );

  const filteredCompanyProducts = useMemo(() => {
    const q = productSearch.trim().toLowerCase();
    return companyProducts.filter((p) => {
      if (categoryFilter !== "all" && (p.category || UNCATEGORISED) !== categoryFilter) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        (p.category || "").toLowerCase().includes(q) ||
        p.specs.some((s) => `${s.label} ${s.value}`.toLowerCase().includes(q))
      );
    });
  }, [companyProducts, productSearch, categoryFilter]);

  const groupedProducts = useMemo(() => {
    const groups = {};
    filteredCompanyProducts.forEach((p) => {
      const cat = p.category || UNCATEGORISED;
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(p);
    });
    return groups;
  }, [filteredCompanyProducts]);

  /* PRODUCT NEWS: the product's own competitive_product_news rows (written by the news job),
     newest first as served. Company news is NOT substituted when there are none. */
  const productNewsArticles = useMemo(() => (selectedProduct && selectedProduct.news) || [], [selectedProduct]);
  const prodNewsCats = useMemo(
    () => [...new Set(productNewsArticles.map((a) => a.category).filter(Boolean))],
    [productNewsArticles],
  );
  const filteredProdArticles = useMemo(
    () => (prodNewsFilter === "All" ? productNewsArticles : productNewsArticles.filter((a) => a.category === prodNewsFilter)),
    [productNewsArticles, prodNewsFilter],
  );

  /* LIVE WEB MENTIONS for the selected product -- Google News RSS, fetched server-side via
     /api/pulse. Separate from the stored news above, labelled as not reviewed; a dead feed just
     yields nothing. */
  const [productPulse, setProductPulse] = useState(null);
  useEffect(() => {
    const cid = selectedCompany && selectedCompany.cid;
    const pname = selectedProduct && selectedProduct.name;
    if (!cid || !pname) { setProductPulse(null); return; }
    const k = pulseKey(cid, pname);
    const cached = readPulse(k);
    if (cached) { setProductPulse(cached); return; }
    setProductPulse(null);
    let cancelled = false;
    fetch(`/api/pulse?cid=${encodeURIComponent(cid)}&name=${encodeURIComponent(selectedCompany.name || "")}&product=${encodeURIComponent(pname)}`)
      .then((r) => r.json())
      .then((j) => { const v = j || {}; if (!cancelled) { setProductPulse(v); writePulse(k, v); } })
      .catch(() => { if (!cancelled) setProductPulse({ trending: [] }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCompany && selectedCompany.cid, selectedProduct && selectedProduct.name]);
  const productMentions = (productPulse && productPulse.trending) || [];

  /* The stored comparisons this product takes part in (matchup ids joined by product id). */
  const productMatchups = useMemo(
    () => ((selectedProduct && selectedProduct.matchupIds) || []).map((id) => (data.matchups || {})[id]).filter(Boolean),
    [selectedProduct, data.matchups],
  );

  /* "label value unit" rows of one product's sheet, in served order */
  const specLine = (s) => specValueWithUnit(s.value, s.unit);

  /* What the header's Copy / Export / Print act on: the open product's sheet and its stored news,
     or the company's catalogue as filtered. */
  const report = useMemo(() => {
    if (selectedProduct) {
      const specRows = [...(selectedProduct.details || []), ...selectedProduct.specs].map((s) => [s.label, specLine(s)]);
      const newsRows = productNewsArticles.map((a) => [a.title, [a.source, a.date, a.category].filter(Boolean).join(" · ")]);
      return {
        title: `${selectedCompany.name} - ${selectedProduct.name}`,
        subtitle: `${selectedProduct.category || UNCATEGORISED} · product technical specification`,
        sections: [
          {
            h: "Technical specifications",
            rows: specRows.length ? specRows : [`No specifications are held for ${selectedProduct.name}.`],
          },
          {
            h: `News naming ${selectedProduct.name} (${productNewsArticles.length})`,
            rows: newsRows.length ? newsRows : ["No news on record for this product."],
          },
        ],
        payload: {
          company: selectedCompany.name,
          cid: selectedCompany.cid,
          product: {
            name: selectedProduct.name,
            category: selectedProduct.category || null,
            specs: selectedProduct.specs.map((s) => ({ label: s.label, value: s.value, unit: s.unit || null })),
          },
          news: productNewsArticles.map((a) => ({
            title: a.title,
            source: a.source || null,
            date: a.date || null,
            category: a.category || null,
            url: a.url || null,
          })),
        },
      };
    }
    return {
      title: `${selectedCompany.name} Product Portfolio`,
      subtitle:
        `${filteredCompanyProducts.length} of ${companyProducts.length} products` +
        (productSearch ? ` matching "${productSearch}"` : "") +
        (categoryFilter !== "all" ? ` · ${categoryFilter}` : ""),
      sections: Object.entries(groupedProducts).map(([cat, list]) => ({
        h: cat,
        rows: list.map((p) => [p.name, p.specs.length ? `${p.specs.length} spec field${p.specs.length === 1 ? "" : "s"}` : "no specs held"]),
      })),
      payload: {
        company: selectedCompany.name,
        cid: selectedCompany.cid,
        products: filteredCompanyProducts.map((p) => ({
          name: p.name,
          category: p.category || null,
          specs: p.specs.map((s) => ({ label: s.label, value: s.value, unit: s.unit || null })),
        })),
      },
    };
  }, [selectedProduct, selectedCompany, productNewsArticles, groupedProducts, filteredCompanyProducts, companyProducts, productSearch, categoryFilter]);
  useHeaderReport(report);

  useEffect(() => {
    setScope("products", { selection: `${selectedCompany.name} Products` }, {
      pillar: "Competitive",
      view: "Products",
      selection: `${selectedCompany.name} Products`,
    });
  }, [setScope, selectedCompany]);

  /* threat dot class for a stored threat_level; no dot when none is stored. Known codes are
     chrome; an unknown code gets the neutral dot. */
  const dotClass = (t) => {
    const v = lc(t);
    if (!v) return null;
    return v === "high" || v === "threat" ? "threat" : v === "fav" ? "fav" : v === "watch" ? "watch" : "";
  };

  return (
    <div className="pos-view v-products" style={{ gridTemplateColumns: "300px 1fr" }}>
      {/* 1. LEFT SIDEBAR: COMPANY SELECTOR */}
      <div className="mu-list">
        <div className="mu-list-h">
          <span className="eyebrow">Companies ({filteredCompanyRoster.length})</span>

          {/* Company Sidebar Filters (Country, Product Category, Revenue tier): stored values only */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "10px", marginBottom: "10px" }}>
            {sidebarCountries.length ? (
              <select
                aria-label="Filter companies by country"
                className="mu-fsel"
                onChange={(e) => setSidebarCountryFilter(e.target.value)}
                style={{ width: "100%" }}
                value={sidebarCountryFilter}
              >
                <option value="all">All countries ({sidebarCountries.length})</option>
                {sidebarCountries.map((o) => (
                  <option key={o.v} value={o.v}>{o.v} ({o.n})</option>
                ))}
              </select>
            ) : null}

            {sidebarCategories.length ? (
              <select
                aria-label="Filter companies by category"
                className="mu-fsel"
                onChange={(e) => setSidebarCategoryFilter(e.target.value)}
                style={{ width: "100%" }}
                value={sidebarCategoryFilter}
              >
                <option value="all">All categories ({sidebarCategories.length})</option>
                {sidebarCategories.map((o) => (
                  <option key={o.v} value={o.v}>{o.v} ({o.n})</option>
                ))}
              </select>
            ) : null}

            {sidebarRevenue.length ? (
              <select
                aria-label="Filter companies by revenue tier"
                className="mu-fsel"
                onChange={(e) => setSidebarRevenueFilter(e.target.value)}
                style={{ width: "100%" }}
                value={sidebarRevenueFilter}
              >
                <option value="all">All revenue tiers ({sidebarRevenue.length})</option>
                {sidebarRevenue.map((o) => (
                  <option key={o.v} value={o.v}>{o.v} ({o.n})</option>
                ))}
              </select>
            ) : null}
          </div>

          <div className="mu-search">
            <span className="si">⌕</span>
            <input
              type="text"
              placeholder="Search company…"
              value={companyQuery}
              onChange={(e) => setCompanyQuery(e.target.value)}
            />
          </div>
        </div>

        <div id="patc-list">
          {filteredCompanyRoster.map((r) => {
            const dot = dotClass(r.threat);
            const open = () => {
              setSelectedCid(r.cid);
              setSelectedProduct(null);
              setProductSearch("");
              setCategoryFilter("all");
            };
            return (
              <div
                key={r.cid}
                className={`pat-li${selectedCid === r.cid ? " active" : ""}`}
                onClick={open}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    open();
                  }
                }}
              >
                <span className="pli-n" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  {dot !== null ? <span className={`wdot ${dot}`} /> : null}
                  {r.name}
                </span>
              </div>
            );
          })}
          {!filteredCompanyRoster.length && (
            <div className="cp-empty">{companyRoster.length ? `no company matches “${companyQuery}”` : "No companies on record"}</div>
          )}
        </div>
      </div>

      {/* 2. RIGHT PANE: PRODUCTS LIST, OR THE SPECS TAB OF ONE PRODUCT */}
      <div className="cp-body" style={{ padding: "20px", background: "var(--d-bg)" }}>
        {selectedProduct ? (
          <div
            className="product-specs-dark-tab"
            style={{
              background: "var(--d-bg-1)",
              color: "var(--d-txt)",
              borderRadius: "8px",
              border: "1px solid var(--d-line)",
              padding: "24px",
              boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
              minHeight: "calc(100vh - 140px)",
              display: "flex",
              flexDirection: "column",
              gap: "28px",
            }}
          >
            {/* Top bar: product title and Back */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: "1px solid var(--d-line)",
                paddingBottom: "16px",
              }}
            >
              <div>
                <h3 style={{ fontSize: "20px", fontWeight: "700", color: "#ffffff", margin: 0 }}>
                  {selectedCompany.name} - {selectedProduct.name}
                </h3>
                {selectedProduct.country ? (
                  <div style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", marginTop: "6px" }}>
                    {selectedProduct.country}
                  </div>
                ) : null}
                <Review src={selectedProduct._src} />
              </div>
              <button
                type="button"
                onClick={() => setSelectedProduct(null)}
                style={{
                  background: "var(--d-bg-2)",
                  border: "1px solid var(--d-line)",
                  color: "var(--d-txt)",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                ← Back
              </button>
            </div>

            {/* PRODUCT DETAILS (KSSL products: the client_product columns) */}
            {(selectedProduct.details || []).length ? (
              <div>
                <div style={SECTION_HEAD}>Product details</div>
                <div style={{ border: "1px solid var(--d-line)", borderRadius: "6px", overflow: "hidden" }}>
                  {selectedProduct.details.map((row, idx, arr) => (
                    <div
                      key={row.label}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "220px 1fr",
                        gap: "16px",
                        padding: "12px 18px",
                        background: idx % 2 === 0 ? "var(--d-bg-2)" : "var(--d-bg-1)",
                        borderBottom: idx < arr.length - 1 ? "1px solid var(--d-line)" : "none",
                        fontSize: "13px",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600" }}>{row.label}</span>
                      <span style={{ color: "#ffffff", fontWeight: "600" }}>{specLine(row)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* 1. TECHNICAL SPECIFICATIONS: the product's specification rows, in served order */}
            <div>
              <div style={SECTION_HEAD}>Technical specifications</div>
              {selectedProduct.specs.length ? (
                <div style={{ border: "1px solid var(--d-line)", borderRadius: "6px", overflow: "hidden" }}>
                  {selectedProduct.specs.map((s, idx, arr) => (
                    <div
                      key={s.id || `${s.label}-${idx}`}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "220px 1fr",
                        gap: "16px",
                        padding: "12px 18px",
                        background: idx % 2 === 0 ? "var(--d-bg-2)" : "var(--d-bg-1)",
                        borderBottom: idx < arr.length - 1 ? "1px solid var(--d-line)" : "none",
                        fontSize: "13px",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600" }}>{s.label}</span>
                      <span style={{ color: "#ffffff", fontWeight: "600" }}>
                        {specLine(s)}
                        {s.sourceUrl ? (
                          <a
                            href={s.sourceUrl}
                            rel="noopener noreferrer"
                            target="_blank"
                            style={{ marginLeft: "10px", fontFamily: "var(--mono)", fontSize: "10.5px", fontWeight: "400", color: "var(--d-txt-3)" }}
                          >
                            source ↗
                          </a>
                        ) : null}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: "13px", color: "var(--d-txt-3)" }}>No specifications on record for this product.</div>
              )}
            </div>

            {/* 2. PROGRAMS: only when the product has programme rows */}
            {(selectedProduct.programs || []).length ? (
              <div>
                <div style={SECTION_HEAD}>Programs</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {selectedProduct.programs.map((prog) => {
                    const when = prog.date ? fmtDate(prog.date) : [fmtDate(prog.start), fmtDate(prog.end)].filter(Boolean).join(" – ");
                    const line = [prog.type, prog.authority, when].filter(Boolean).join(" · ");
                    return (
                      <div
                        key={prog.id}
                        style={{
                          background: "var(--d-bg-2)",
                          border: "1px solid var(--d-line)",
                          borderRadius: "8px",
                          padding: "14px 18px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "6px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                          <span style={{ fontSize: "14px", fontWeight: "700", color: "#ffffff" }}>{prog.title}</span>
                          {prog.status ? <span style={statusStyle(prog.statusColor)}>{prog.status}</span> : null}
                        </div>
                        {line ? <div style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)" }}>{line}</div> : null}
                        {prog.description ? (
                          <div style={{ fontSize: "12.5px", color: "var(--d-txt-2)", lineHeight: "1.5", marginTop: "2px" }}>{prog.description}</div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {/* 3. PRODUCT COMPARISON: only the stored matchups this product is in */}
            {productMatchups.length ? (
              <div>
                <div style={SECTION_HEAD}>Product comparison</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {productMatchups.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        background: "var(--d-bg-1)",
                        border: "1px solid var(--d-line)",
                        borderRadius: "8px",
                        padding: "18px 22px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "16px",
                        flexWrap: "wrap",
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                        <div style={{ fontSize: "14px", fontWeight: "700", color: "#ffffff" }}>
                          <span>{m.comp}</span>
                          <span style={{ color: "var(--d-txt-3)", fontWeight: "400", margin: "0 8px", fontSize: "13px" }}>vs</span>
                          <span>{clientName} · {m.bf}</span>
                        </div>
                        {m.matchBasis ? (
                          <div style={{ fontSize: "12.5px", color: "var(--d-txt-3)", lineHeight: "1.4" }}>{m.matchBasis}</div>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => jumpTo("competitive", "positioning", { matchupId: m.id })}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#34d399",
                          fontFamily: "var(--mono)",
                          fontSize: "13px",
                          fontWeight: "600",
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          whiteSpace: "nowrap",
                          padding: "6px 10px",
                          borderRadius: "4px",
                        }}
                      >
                        <span>Open comparison</span>
                        <span style={{ fontSize: "14px" }}>↗</span>
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* 4. NEWS: the stored product news (competitor products only; KSSL has no product-news table) */}
            {!selectedCompany.isClient ? (
              <div>
                <div style={SECTION_HEAD}>News</div>

                {prodNewsCats.length ? (
                  <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
                    {["All", ...prodNewsCats].map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        className={`ln-pill${prodNewsFilter === cat ? " on" : ""}`}
                        onClick={() => setProdNewsFilter(cat)}
                      >
                        {cat === "All" ? "All Product News" : cat}
                      </button>
                    ))}
                  </div>
                ) : null}

                {filteredProdArticles.length ? (
                  <div className="ln-grid">
                    {filteredProdArticles.map((item) => (
                      <div key={item.id}>
                      <ArticleLink
                        article={item}
                        className="ln-card"
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          background: "var(--d-bg-2)",
                          border: "1px solid var(--d-line)",
                          borderRadius: "8px",
                          overflow: "hidden",
                          textDecoration: "none",
                          color: "inherit",
                        }}
                      >
                        <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: "6px", flex: 1 }}>
                          {item.category || item.date ? (
                            <div style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "11px", color: "var(--d-txt-3)", fontFamily: "var(--mono)" }}>
                              {item.category ? <span style={{ color: "#f0593c", fontWeight: "600" }}>{item.category}</span> : null}
                              {item.category && item.date ? <span>·</span> : null}
                              {item.date ? <span>{fmtDate(item.date)}</span> : null}
                            </div>
                          ) : null}
                          <div style={{ fontSize: "13px", fontWeight: "600", color: "#ffffff", lineHeight: "1.4" }}>{item.title}</div>
                          {item.reason ? <div style={{ fontSize: "12px", color: "var(--d-txt-3)", lineHeight: "1.4" }}>{item.reason}</div> : null}
                          {item.source ? (
                            <div style={{ marginTop: "auto", paddingTop: "6px", fontSize: "11px", color: "var(--d-txt-3)", fontFamily: "var(--mono)" }}>{item.source}</div>
                          ) : null}
                        </div>
                      </ArticleLink>
                      <Review src={item._src} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: "13px", color: "var(--d-txt-3)" }}>No news on record for this product.</div>
                )}
              </div>
            ) : null}

            {/* LIVE HEADLINES: Google News, a live fetch outside the database, never a fallback for the news above */}
            {productMentions.length ? (
              <div>
                <div style={SECTION_HEAD}>Live headlines (Google News, not reviewed)</div>
                <div className="ln-grid">
                  {productMentions.slice(0, 6).map((item, idx) => (
                    <ArticleLink
                      key={item.id || item.url || `pm-${idx}`}
                      article={item}
                      className="ln-card"
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        background: "var(--d-bg-2)",
                        border: "1px solid var(--d-line)",
                        borderRadius: "8px",
                        overflow: "hidden",
                        textDecoration: "none",
                        color: "inherit",
                      }}
                    >
                      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: "6px", flex: 1 }}>
                        {item.date ? (
                          <div style={{ fontSize: "11px", color: "var(--d-txt-3)", fontFamily: "var(--mono)" }}>{fmtDate(item.date)}</div>
                        ) : null}
                        <div style={{ fontSize: "13px", fontWeight: "600", color: "#ffffff", lineHeight: "1.4" }}>{item.title}</div>
                        {item.source ? (
                          <div style={{ marginTop: "auto", paddingTop: "6px", fontSize: "11px", color: "var(--d-txt-3)", fontFamily: "var(--mono)" }}>{item.source}</div>
                        ) : null}
                      </div>
                    </ArticleLink>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          /* PRODUCTS CATALOGUE VIEW */
          <>
            <div
              className="products-header"
              style={{
                marginBottom: "20px",
                display: "flex",
                gap: "14px",
                flexWrap: "wrap",
                alignItems: "center",
                background: "var(--d-bg-1)",
                padding: "16px 20px",
                borderRadius: "8px",
                border: "1px solid var(--d-line)",
              }}
            >
              <div>
                <h2 style={{ fontSize: "16px", fontWeight: "700", color: "var(--d-txt)", margin: 0 }}>
                  {selectedCompany.name} Product Portfolio
                </h2>
                {selectedCompany.isClient ? <Review src={data.client && data.client._src} /> : null}
              </div>

              <div style={{ display: "flex", gap: "10px", alignItems: "center", marginLeft: "auto", flexWrap: "wrap" }}>
                <input
                  type="text"
                  placeholder="Search products or specs..."
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                  style={{
                    background: "var(--d-bg-2)",
                    border: "1px solid var(--d-line)",
                    color: "var(--d-txt)",
                    padding: "8px 14px",
                    borderRadius: "6px",
                    fontSize: "12.5px",
                    width: "220px",
                    height: "38px",
                    boxSizing: "border-box",
                    outline: "none",
                  }}
                />

                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  style={{
                    background: "var(--d-bg-2)",
                    border: "1px solid var(--d-line)",
                    color: "var(--d-txt)",
                    padding: "8px 14px",
                    borderRadius: "6px",
                    fontSize: "12.5px",
                    width: "200px",
                    height: "38px",
                    boxSizing: "border-box",
                    outline: "none",
                    cursor: "pointer",
                  }}
                >
                  <option value="all">All Categories ({categories.length})</option>
                  {categories.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "40px" }}>
              {Object.keys(groupedProducts).length > 0 ? (
                Object.entries(groupedProducts).map(([catName, prodList]) => {
                  const open = !collapsedCats.has(catName);
                  return (
                    <div key={catName} style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
                      {/* Category title -- click to collapse / expand this category's list */}
                      <button
                        type="button"
                        onClick={() => toggleCat(catName)}
                        aria-expanded={open}
                        title={open ? `Collapse ${catName}` : `Expand ${catName}`}
                        style={{
                          display: "flex", alignItems: "center", gap: "10px", width: "100%",
                          background: "none", border: "none", borderBottom: "1px solid var(--d-line)",
                          padding: "0 0 10px", cursor: "pointer", textAlign: "left", font: "inherit",
                        }}
                      >
                        {/* a drawn chevron: the ▾/▸ glyphs render tiny in this font at any size */}
                        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 20 20"
                             style={{ flexShrink: 0, transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>
                          <path d="M7 4 L13 10 L7 16" fill="none" stroke="var(--d-txt-2)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span style={{ fontFamily: "var(--mono)", fontSize: "13px", color: "var(--d-txt)", fontWeight: "600", letterSpacing: ".06em", textTransform: "uppercase" }}>
                          {catName}
                        </span>
                        <span style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", background: "var(--d-bg-2)", border: "1px solid var(--d-line)", padding: "1px 7px", borderRadius: "10px" }}>
                          {prodList.length}
                        </span>
                      </button>

                      {open ? (
                        <div
                          className="product-cards-grid"
                          style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "28px" }}
                        >
                          {prodList.map((p) => (
                            <div
                              key={p.id}
                              onClick={() => setSelectedProduct(p)}
                              role="button"
                              tabIndex={0}
                              title={`Open ${p.name}`}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setSelectedProduct(p);
                                }
                              }}
                              className="product-card"
                              style={{
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                background: "var(--d-bg-1)",
                                border: "1px solid var(--d-line)",
                                borderRadius: "12px",
                                overflow: "hidden",
                                cursor: "pointer",
                                transition: "transform .15s, box-shadow .15s, border-color .15s",
                              }}
                            >
                              {/* the name of the product */}
                              <div style={{ padding: "16px 18px", display: "flex", alignItems: "center", minHeight: "56px" }}>
                                <div
                                  style={{
                                    fontSize: "15px",
                                    fontWeight: "700",
                                    color: "#ffffff",
                                    lineHeight: 1.35,
                                    display: "-webkit-box",
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: "vertical",
                                    overflow: "hidden",
                                  }}
                                >
                                  {p.name}
                                </div>
                              </div>

                              {/* the card's action, bottom corner */}
                              <div
                                style={{
                                  padding: "14px 18px",
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  background: "var(--d-bg-1)",
                                  borderTop: "1px solid var(--d-line)",
                                  marginTop: "auto",
                                }}
                              >
                                <Review src={p._src} />
                                <span
                                  className="product-card-view-specs"
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "5px",
                                    fontFamily: "var(--mono)",
                                    fontSize: "12px",
                                    fontWeight: "600",
                                    color: "var(--fav-badge, #38bdf8)",
                                    padding: "6px 14px",
                                    borderRadius: "6px",
                                    background: "rgba(56, 189, 248, 0.08)",
                                    border: "1px solid rgba(56, 189, 248, 0.25)",
                                    transition: "all .15s ease",
                                  }}
                                >
                                  View Specs →
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div
                  style={{
                    padding: "32px",
                    textAlign: "center",
                    background: "var(--d-bg-1)",
                    border: "1px solid var(--d-line)",
                    borderRadius: "8px",
                    color: "var(--d-txt-3)",
                    fontSize: "13px",
                  }}
                >
                  {companyProducts.length
                    ? "No products match the search or category."
                    : `No products on record for ${selectedCompany.name}.`}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
