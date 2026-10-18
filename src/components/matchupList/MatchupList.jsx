import { clientShort } from "../../lib/client.js";
import { useMemo, useState } from "react";
import { useAppState } from "../../state/AppState";
import { titleCaseHeadline } from "../../lib/profile";
import { companyShort } from "../../lib/companyNames";
import { Review } from "../review/Review";

/* Split "Maker · Product" the way the dataset stores it (product after the LAST "·"),
   so the row can headline the PRODUCT and drop the maker to a small line beneath it. */
function splitComp(comp) {
  const s = String(comp || "");
  const i = s.lastIndexOf("·"); // "·"
  if (i < 0) return { company: "", product: s.trim() };
  return { company: s.slice(0, i).trim(), product: s.slice(i + 1).trim() };
}

/* POS_CATS labels are served already cased ("UAVs & Drones"). The splitter that used to
   live here broke a word on every lower-to-upper boundary and re-cased the pieces, so
   the category filter offered "Ua Vs & Drones" -- a label no row carries. Raise only,
   through the same function the product names go through, and eat no acronym. */
const formatCategoryLabel = (str) => {
  if (!str) return "—";
  return titleCaseHeadline(String(str).replace(/&amp;/g, "&").trim());
};

/* The competitor-product list: category → KSSL anchor product → the rivals paired
   against it. Groups collapse; the four selects narrow each other, so a combination
   that matches nothing can't be chosen. */
export default function MatchupList({ data, selected, onSelect, products = [], compare = null, onCompare }) {
  const { matchups, POS_CATS, CAT_KEY } = data;
  const { searchQuery } = useAppState();
  const [query, setQuery] = useState("");
  /* "Compare any two products": the two picks, pre-filled from an open comparison */
  const [pickA, setPickA] = useState(compare ? compare.a : "");
  const [pickB, setPickB] = useState(compare ? compare.b : "");
  // KSSL's own products first, then one group per category
  const productGroups = useMemo(() => {
    const g = new Map();
    products.forEach((p) => {
      const k = p.side === "client" ? `${clientShort()} products` : p.cat;
      if (!g.has(k)) g.set(k, []);
      g.get(k).push(p);
    });
    return [...g.entries()];
  }, [products, data.client]);
  const productOptions = productGroups.map(([label, list]) => (
    <optgroup key={label} label={label}>
      {list.map((p) => (
        <option key={p.key} value={p.key}>
          {p.name}{p.side === "rival" && p.maker ? ` — ${p.maker}` : ""}
        </option>
      ))}
    </optgroup>
  ));
  const [co, setCo] = useState("");
  const [cat, setCat] = useState("");
  const [koel, setKoel] = useState("");
  const [country, setCountry] = useState("");
  const [collapsed, setCollapsed] = useState({});

  /* label lookups, built once from the corpus */
  const labels = useMemo(() => {
    const catLabel = {};
    POS_CATS.forEach(([v, lab]) => {
      catLabel[v] = formatCategoryLabel(lab);
    });
    const coLabel = {};
    const ctLabel = {};
    const koelLabel = {};
    Object.keys(matchups).forEach((id) => {
      const m = matchups[id];
      if (m.compBy) coLabel[m.compBy.toLowerCase()] = m.compBy;
      if (m.country) ctLabel[m.country.toLowerCase()] = m.country;
      const a = m.anchor || m.bf;
      if (a) koelLabel[a.toLowerCase()] = a;
    });
    return { catLabel, coLabel, ctLabel, koelLabel };
  }, [matchups, POS_CATS]);

  /* Given the current selections, which values remain valid for each dimension —
     computed excluding that dimension's own filter, so choosing one never empties
     the others. */
  const options = useMemo(() => {
    const cosSet = new Set();
    const catSet = new Set();
    const koelSet = new Set();
    const ctSet = new Set();
    Object.keys(matchups).forEach((id) => {
      const m = matchups[id];
      const mco = (m.compBy || "").toLowerCase();
      const mcat = CAT_KEY[m.cat];
      const mct = (m.country || "").toLowerCase();
      const mk = (m.anchor || m.bf || "").toLowerCase();
      if ((!cat || mcat === cat) && (!koel || mk === koel) && (!country || mct === country))
        cosSet.add(mco);
      if ((!co || mco === co) && (!koel || mk === koel) && (!country || mct === country) && mcat)
        catSet.add(mcat);
      if ((!co || mco === co) && (!cat || mcat === cat) && (!country || mct === country) && mk)
        koelSet.add(mk);
      if ((!co || mco === co) && (!cat || mcat === cat) && (!koel || mk === koel) && mct)
        ctSet.add(mct);
    });
    const sortBy = (set, map) =>
      [...set].sort((a, b) => (map[a] || a).localeCompare(map[b] || b));
    return {
      co: sortBy(cosSet, labels.coLabel),
      cat: sortBy(catSet, labels.catLabel),
      koel: sortBy(koelSet, labels.koelLabel),
      country: sortBy(ctSet, labels.ctLabel),
    };
  }, [matchups, CAT_KEY, co, cat, koel, country, labels]);

  /* band → anchor → matchups, filtered. Anchors are ordered by how many rivals they
     face, and within an anchor rivals are alphabetical by company (global primes lead
     only among rows of the same company). */
  const groups = useMemo(() => {
    const q = (query || searchQuery || "").toLowerCase().trim();
    const tokens = q.split(/\s+/).filter(Boolean);
    /* An unknown cat must still render somewhere — mirror how wireDataset appends a
       chip for unknown techCats. Without this, the row counts in the nav badge but
       appears in no group. */
    const catDefs = [...POS_CATS, ["__uncat", "—"]];
    return catDefs.map(([key, label]) => {
      const items = Object.keys(matchups).filter((id) =>
        key === "__uncat"
          ? CAT_KEY[matchups[id].cat] == null
          : CAT_KEY[matchups[id].cat] === key,
      );
      if (!items.length) return null;
      const byAnchor = {};
      items.forEach((id) => {
        const m = matchups[id];
        const a = m.anchor || m.bf;
        (byAnchor[a] = byAnchor[a] || []).push(id);
      });
      const anchors = Object.keys(byAnchor)
        .sort((a, b) => byAnchor[b].length - byAnchor[a].length)
        .map((anchor) => {
          const ids = byAnchor[anchor]
            .sort((a, b) =>
              String(matchups[a].compBy || matchups[a].comp || "").localeCompare(
                String(matchups[b].compBy || matchups[b].comp || ""), "en", { sensitivity: "base" })
              || (matchups[b].global ? 1 : 0) - (matchups[a].global ? 1 : 0))
            .filter((id) => {
              const m = matchups[id];
              const search = `${m.title || ""} ${m.comp || ""} ${m.compBy || ""} ${m.cat || ""} ${m.country || ""} ${m.anchor || ""}${
                m.global ? " global prime benchmark" : ""
              }`.toLowerCase();
              if (tokens.length > 0 && !tokens.every((tok) => search.includes(tok))) return false;
              if (co && (m.compBy || "").toLowerCase() !== co) return false;
              if (cat && CAT_KEY[m.cat] !== cat) return false;
              if (koel && (m.anchor || m.bf || "").toLowerCase() !== koel) return false;
              if (country && (m.country || "").toLowerCase() !== country) return false;
              return true;
            });
          return { anchor, ids };
        })
        .filter((a) => a.ids.length);
      const shown = anchors.reduce((n, a) => n + a.ids.length, 0);
      if (!shown) return null;
      /* The badge counts the rows under the heading -- the SHOWN ones. It carried
         items.length, so under a search it read 78 over a group listing 14. */
      return { key, label, total: shown, anchors };
    }).filter(Boolean);
    /* searchQuery belongs here because line 88 reads it. Without it the context change
       re-rendered the component, this memo did NOT recompute, and the Positioning list
       never moved -- while the local box on the same page worked. That asymmetry is
       exactly what "the search bar is not working" looked like. */
  }, [matchups, POS_CATS, CAT_KEY, query, searchQuery, co, cat, koel, country]);

  const select = (setter) => (e) => setter(e.target.value);

  return (
    <div className="mu-list">
      <div className="mu-list-h">
        <span className="eyebrow">Competitor Products</span>
        <div className="mu-search">
          <span className="si">⌕</span>
          <input
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search product or competitor…"
            type="text"
            value={query}
          />
        </div>
        <div className="mu-filters">
          <select className="mu-fsel" onChange={select(setCo)} value={co}>
            <option value="">All Companies</option>
            {options.co.map((v) => (
              <option key={v} value={v}>
                {labels.coLabel[v] || v}
              </option>
            ))}
          </select>
          <select className="mu-fsel" onChange={select(setCat)} value={cat}>
            <option value="">All Categories</option>
            {options.cat.map((v) => (
              <option key={v} value={v}>
                {labels.catLabel[v] || v}
              </option>
            ))}
          </select>
          <select className="mu-fsel" onChange={select(setKoel)} value={koel}>
            <option value="">All {clientShort()} Products</option>
            {options.koel.map((v) => (
              <option key={v} value={v}>
                {labels.koelLabel[v] || v}
              </option>
            ))}
          </select>
          <select className="mu-fsel" onChange={select(setCountry)} value={country}>
            <option value="">All Countries</option>
            {options.country.map((v) => (
              <option key={v} value={v}>
                {labels.ctLabel[v] || v}
              </option>
            ))}
          </select>
        </div>
        {/* FREE COMPARISON: any two products, not only the matched pairs below */}
        {onCompare && products.length ? (
          <div className="mu-compare">
            {/* its own section, headed exactly like "Competitor Products" above */}
            <span className="eyebrow">Compare Any Two Products</span>
            <div className="mu-compare-fields">
            <select className="mu-fsel" value={pickA} onChange={(e) => setPickA(e.target.value)} aria-label="First product to compare">
              <option value="">Product A…</option>
              {productOptions}
            </select>
            <span className="mu-compare-vs">vs</span>
            <select className="mu-fsel" value={pickB} onChange={(e) => setPickB(e.target.value)} aria-label="Second product to compare">
              <option value="">Product B…</option>
              {productOptions}
            </select>
            <button
              type="button"
              className="mu-compare-btn"
              disabled={!pickA || !pickB || pickA === pickB}
              title={pickA && pickA === pickB ? "Pick two different products" : "Compare the two products"}
              onClick={() => onCompare(pickA, pickB)}
            >
              Compare
            </button>
            </div>
          </div>
        ) : null}
      </div>

      <div id="mu-list-body">
        {groups.map((g) => (
          <div key={g.key}>
            <div
              className={`mu-cat${collapsed[g.key] ? " collapsed" : ""}`}
              data-cat={g.key}
              onClick={() => setCollapsed((c) => ({ ...c, [g.key]: !c[g.key] }))}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setCollapsed((c) => ({ ...c, [g.key]: !c[g.key] }));
                }
              }}
            >
              <span className="cleft">
                <i className="chev">▾</i> {formatCategoryLabel(g.label)}
              </span>
              <span className="ccount">{g.total}</span>
            </div>
            <div className={`mu-group${collapsed[g.key] ? " collapsed" : ""}`} data-group={g.key}>
              {g.anchors.map(({ anchor, ids }) => (
                <div key={anchor}>
                  <div className="mu-anchor">
                    <span className="ma-koel">{clientShort()}</span> {anchor}{" "}
                    <span className="ma-count">
                      {ids.length} rival{ids.length > 1 ? "s" : ""}
                    </span>
                  </div>
                  {ids.map((id) => {
                    const m = matchups[id];
                    /* Product is the headline; the maker sits under it, small and
                       abbreviated. No leading bullet and no "·" separator -- the row is
                       the product, attributed. The KSSL side it is paired against is the
                       anchor heading above this group, so it is not repeated per row. */
                    const { company, product } = splitComp(m.comp);
                    return (
                      <div
                        className={`mu-item${selected === id ? " active" : ""}`}
                        data-mu={id}
                        key={id}
                        onClick={() => onSelect(id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onSelect(id);
                          }
                        }}
                      >
                        <div className="comp-prod">{product}</div>
                        {company ? <div className="cp-co">{companyShort(company)}</div> : null}
                        <Review src={m._src} />
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        ))}
        {!groups.length ? (
          <div className="pat-li-none" style={{ padding: "18px" }}>
            {query.trim() || co || cat || koel || country
              ? "No product matches these filters"
              : "No competitor products served yet"}
          </div>
        ) : null}
      </div>
    </div>
  );
}
