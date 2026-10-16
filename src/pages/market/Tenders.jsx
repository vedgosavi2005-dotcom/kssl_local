import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import ScopeChat from "../../components/scopeChat/ScopeChat";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { srcChips } from "../../lib/html";
import { formatLabel, smartTitleCase } from "../../lib/profile";
import { facetOptions } from "../../lib/countryFacet";
import { NOT_ON_RECORD, resolveTenderRow, tenderFactRows } from "../../lib/tenderRow";
import { formatDate } from "../../utils/formatDate";
import { Review } from "../../components/review/Review";

const has = (v) => v != null && String(v).trim() !== "";
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
/* The fit word is shown as stored; its CSS class is the stored word, lower-cased. */
const fitClass = (v) => (has(v) ? String(v).trim().toLowerCase() : "");

/* The facts of a notice: the fixed nine (src/lib/tenderRow.js), then the other stored
   notice columns. Rows are [label, text, resolved]; the detail hides an unresolved one. */
const factRows = (t) => {
  if (!t) return [];
  const rows = tenderFactRows(t);
  [
    ["Notice ref.", t.noticeRef],
    ["Latest milestone", t.milestone],
    ["Extension confirmed", typeof t.extension === "boolean" ? (t.extension ? "yes" : "no") : null],
    ["Submission method", t.submissionMethod],
    ["Registration", t.registration],
    ["Local presence", t.localPresence],
    ["Frequency", t.frequency],
  ].forEach(([k, v]) => rows.push([k, has(v) ? v : NOT_ON_RECORD, has(v)]));
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

/* url_kind (stored) says what the link lands on: 'notice' = this tender's own page,
   'portal' = the listing it was found in, 'award' = an already-decided contract. */
const tpUrl = (t) => (t && t.url) || (t && t.srcs && t.srcs.length ? t.srcs[0].url : null);
const kindOf = (t) => String((t && t.urlKind) || "").toLowerCase();
const ctaLabel = (t) =>
  kindOf(t) === "award"
    ? "Read the award announcement"
    : kindOf(t) === "portal"
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
    }[kindOf(t)] || "opens ") + u.replace(/^https?:\/\/(www\.)?/, "").split("/")[0]
  );
};

/* The chip: days left to the stored closing date; concluded tenders say so. */
const countdownText = (row) => {
  if (row.bucket === "awarded") return "awarded";
  if (row.bucket === "closed") return "closed";
  const d = row.dl;
  if (d == null) return row.deadline || row.status || "";
  if (d < 0) return "closing date passed";
  if (d === 0) return "closes today";
  return `${d} day${d === 1 ? "" : "s"} left`;
};

/* Only essential summary parameters are kept on the card face; the rest is in the
   side assessment panel. */
const DASHBOARD_PARAM_KEYS = new Set(["buyer", "country", "category", "value", "status"]);

export default function Tenders({ mode = "tender" }) {
  const { data } = useData();
  const { setScope, takePending, searchQuery } = useAppState();
  const clientName = (data.client && (data.client.short || data.client.name)) || "KSSL";
  const getSavedTender = () => {
    try {
      const s = localStorage.getItem("kssl_tender_state");
      return s ? JSON.parse(s) : {};
    } catch (e) { return {}; }
  };
  const savedTender = getSavedTender();

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
      localStorage.setItem("kssl_tender_state", JSON.stringify({ country, cat }));
    } catch (e) {}
  }, [country, cat]);

  /* A tab CHANGE drops the selection -- a row from the open list is not on the awarded
     list. Guarded against the mount run so a selection restored on mount survives. */
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

  /* `scope` is the tab (the stored status, see lib/tenderCalc) and the search box --
     everything that is NOT one of the two dropdown facets. Each facet's option counts are
     taken from scope with the OTHER facet applied, so a badge can never describe a
     different set than the rows below it. */
  const scope = useMemo(
    () =>
      (data.tenders || [])
        .filter((t) =>
          t.bucket === (mode === "awarded-tenders" ? "awarded" : mode === "closed-tenders" ? "closed" : "open"),
        )
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
  };

  const applyFacets = (rows, except) =>
    rows.filter(
      (t) =>
        (except === "country" || facetOk.country(t, country)) &&
        (except === "cat" || facetOk.cat(t, cat)),
    );

  /* soonest closing first; tenders with no closing date last */
  const list = useMemo(
    () =>
      applyFacets(scope, null).sort(
        (a, b) => (a.dl == null) - (b.dl == null) || (a.dl || 0) - (b.dl || 0),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scope, country, cat],
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

  /* Another page can open a tender here by id (Top opportunity) or by title (search). */
  useEffect(() => {
    const p = takePending("tender");
    if (p && (p.tenderId || p.tenderTitle)) {
      const t = p.tenderId
        ? (data.tenders || []).find((x) => x.id === String(p.tenderId))
        : (data.tenders || []).find((x) => x.title === p.tenderTitle) ||
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

  /* What the header's Copy / Export / Print act on: the open tender's stored facts,
     requirements and matches, then every tender listed under the tab and facets in force. */
  const modeTitle =
    mode === "awarded-tenders" ? "Awarded Tenders" : mode === "closed-tenders" ? "Closed Tenders" : "Tenders";
  const report = useMemo(() => {
    const row = (x) => [
      x.title,
      resolveTenderRow(x).params.map((p) => `${p.label}: ${p.text}`).join(" · "),
    ];
    const sections = [];
    if (t) {
      sections.push({
        h: "Selected tender",
        rows: [["Title", t.title], ...factRows(t).filter((r) => r[2]).map(([k, v]) => [k, v])],
      });
      if (has(t.desc)) sections.push({ h: "Requirement", rows: [t.desc] });
      (t.requirements || []).forEach((r) => sections.push({ h: r.type, rows: r.rows }));
      if ((t.matches || []).length) {
        sections.push({
          h: `${clientName} match`,
          rows: t.matches.map((m) => [m.n, [m.fit, m.percent != null ? `${m.percent}%` : ""].filter(has).join(" · ")]),
        });
      }
    }
    sections.push({ h: `${modeTitle} (${list.length})`, rows: list.map(row) });
    return {
      title: modeTitle,
      subtitle: [country, cat].filter(Boolean).join(" · ") || "all tenders in this tab",
      sections,
      payload: {
        tab: mode,
        filters: { country: country || null, category: cat || null },
        selected: t || null,
        tenders: list,
      },
    };
  }, [t, list, mode, modeTitle, country, cat, clientName]);
  useHeaderReport(report);

  const menuItems = (which) => {
    /* Option values come from the SERVED tenders only; the stored filter options
       (market_filter_option -> d.tpAllCountries / d.tpAllCats) ORDER them and add nothing.
       Counted over `scope` with the OTHER facet applied. */
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
          All {which === "country" ? "countries" : "categories"} ({items.length})
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

  /* The detail's fit verdict: the stored fit word, else the best match's stored percentage. */
  const bestPct = (x) => {
    const p = (x.matches || []).map((m) => m.percent).filter((v) => v != null);
    return p.length ? Math.max(...p) : null;
  };
  const fitWord = (x) => x.ksslFit || x.fitGrade || "";

  return (
    <div className={`tp-view v-tender ${t ? "has-sel" : "no-sel"}`}>
      <div className="tp-list">
        <div className="tp-fbar">
          <span className="eyebrow">Filter</span>
          {dd("country", "Country", country, setCountry)}
          {dd("cat", "Category", cat, setCat)}
          <span className="sortnote">sorted by deadline</span>
        </div>
        <div id="tp-cards">
          {list.length ? (
            list.map((row) => {
              /* THE BAR'S LENGTH HAS TO BE THE MEASUREMENT: a stored match percentage sets
                 its own width. A fit WORD (stored kssl_fit / fit_grade) prints as the word,
                 with no track behind it. No fit stored at all: no fit line. */
              const word = fitWord(row);
              const pct = bestPct(row);
              const fitLabel = has(word) ? cap(word) : pct != null ? `${pct}%` : "";
              const cd = countdownText(row);

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
                    {cd ? <span className={`ddl ${row.statusClass || ""}`}>{cd}</span> : null}
                  </div>
                  <div className="tpgrid">
                    {/* The same parameters on every card, each a stored value; one the
                        record does not hold is hidden here. */}
                    {resolveTenderRow(row).params
                      .filter((p) => DASHBOARD_PARAM_KEYS.has(p.key) && p.value != null)
                      .map((p) => (
                        <div className="tpp" key={p.key}>
                          <span className="tpk">{p.label}</span>
                          <span className="tpv">{p.text}</span>
                        </div>
                      ))}
                  </div>
                  {fitLabel ? (
                    <div className="fitbar">
                      <span className="fitlab">{clientName} fit</span>
                      {pct != null ? (
                        <span className="fittrack">
                          <i className={fitClass(word)} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
                        </span>
                      ) : null}
                      <span className={`fitpct grade ${fitClass(word)}`}>{fitLabel}</span>
                    </div>
                  ) : null}
                  <Review src={row._src} />
                </div>
              );
            })
          ) : (
            <div className="tp-list-empty">
              {country || cat
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
                  <div>{metaLine([t.deadline || (t.closingDate ? `Closes ${formatDate(t.closingDate)}` : ""), t.milestone])}</div>
                </div>
              </div>

              {/* Client fit & rank section: stored words and numbers only */}
              {(() => {
                const word = fitWord(t);
                const pct = bestPct(t);
                const verdict = has(word) ? cap(word) : pct != null ? `${pct}%` : "";
                if (!verdict && !has(t.rank)) return null;
                return (
                  <div className="tp-asmt-sec">
                    <span className="eyebrow">{clientName} Fit{has(t.rank) ? ` · Rank #${t.rank}` : ""}</span>
                    {verdict ? <div className="tp-fit-verdict">{verdict}</div> : null}
                    {has(t.fitNote) ? <div className="req">{t.fitNote}</div> : null}
                  </div>
                );
              })()}

              {has(t.desc) || (t.requirements || []).length ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">What the tender requires</span>
                  {has(t.desc) ? <div className="req">{t.desc}</div> : null}
                  {(t.requirements || []).map((r, i) => (
                    <div key={`${r.type}-${i}`}>
                      <div className="req" style={{ marginTop: "8px", fontWeight: 600 }}>{r.type}</div>
                      {r.rows.map(([k, v], j) => (
                        <div className="kv" key={`${k}-${j}`}>
                          <span className="k">{k}</span>
                          <span className="v">{v}</span>
                        </div>
                      ))}
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
                        <span className="mn">{m.n}</span>
                        {has(m.fit) || m.percent != null ? (
                          <span className={`fit ${fitClass(m.fit)}`}>
                            {[has(m.fit) ? m.fit : null, m.percent != null ? `${m.percent}%` : null].filter(Boolean).join(" · ")} fit
                          </span>
                        ) : null}
                      </div>
                      {(m.lines || []).map((l, j) => (
                        <div className="mline" key={j}>
                          <span>{[l.label, l.value].filter(has).join(": ")}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              ) : null}

              {has(t.expectedRevenue) ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Expected revenue (estimate)</span>
                  <div className="req">{t.expectedRevenue}</div>
                </div>
              ) : null}

              {(t.competitorFit || []).length ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Competitor fit</span>
                  {t.competitorFit.map((c, i) => (
                    <div className="tp-comp-card" key={i}>
                      <div className="tp-comp-header">
                        <span className="tp-comp-name">{c.name}</span>
                        {has(c.fit) ? <span className={`fit ${fitClass(c.fit)}`}>{c.fit}</span> : null}
                      </div>
                      {has(c.products) ? (
                        <div className="tp-comp-line">
                          <span>{c.products}</span>
                        </div>
                      ) : null}
                      {has(c.rationale) ? <div className="tp-comp-desc">{c.rationale}</div> : null}
                    </div>
                  ))}
                </div>
              ) : null}

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

              <div className="tp-asmt-sec">
                {has(t.leanTxt) ? (
                  <div className={`tp-lean${has(t.lean) ? ` ${String(t.lean).toLowerCase()}` : ""}`}>
                    <span className="tl">Bid assessment</span>
                    <span>{t.leanTxt}</span>
                  </div>
                ) : null}
                {(() => {
                  const chips = srcChips(t.srcs && t.srcs.length ? t.srcs : t.url ? [{ label: "Source", url: t.url }] : null);
                  if (!chips) return null;
                  return (
                    <div style={{ marginTop: "10px" }}>
                      <span className="eyebrow">Source</span>
                      <div dangerouslySetInnerHTML={{ __html: chips }} style={{ marginTop: "5px" }} />
                      {(t.srcs || [])
                        .filter((s) => has(s.note) || has(s.portalAccess) || s.portalRegistration != null)
                        .map((s, i) => (
                          <div className="req" key={i} style={{ marginTop: "4px" }}>
                            {[
                              s.label,
                              has(s.note) ? s.note : null,
                              has(s.portalAccess) ? `access ${s.portalAccess}` : null,
                              s.portalRegistration != null ? (s.portalRegistration ? "registration required" : "no registration") : null,
                            ].filter(has).join(" · ")}
                          </div>
                        ))}
                    </div>
                  );
                })()}
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

            <ScopeChat placeholder="Ask about this tender…" scopeKey="tender" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
