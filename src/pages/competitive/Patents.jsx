import { useEffect, useMemo, useState } from "react";
import HtmlBlock from "../../components/htmlBlock/HtmlBlock";
import { ReviewList } from "../../components/review/Review";
import { useData } from "../../state/DataProvider";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { patCompBody, patTechBody, patentAreas, inCategory } from "../../lib/patents";
/* A SELECTION IS REMEMBERED WHILE YOU STAY IN THIS PILLAR, not for ever. See lib/viewState. */
import * as viewState from "../../lib/viewState";

/* Both patent lenses live in the Competitive pillar: the same filings read two ways, by the
   rival that holds them and by the technology category they are classified under. */
export default function Patents() {
  const { data } = useData();
  const { takePending } = useAppState();
  const getSavedPat = () => {
    try {
      const s = viewState.getItem("kssl_pat_state");
      return s ? JSON.parse(s) : {};
    } catch (e) { return {}; }
  };
  const savedPat = getSavedPat();
  const pat = data.PATENTS || {};
  const byCompetitor = pat.byCompetitor || {};
  const byTechnology = pat.byTechnology || {};

  const [lens, setLens] = useState(savedPat.lens || "rival");
  const [compQuery, setCompQuery] = useState("");
  const [techQuery, setTechQuery] = useState("");
  const [cid, setCid] = useState(savedPat.cid && data.competitors[savedPat.cid] ? savedPat.cid : data.compOrder[0]);
  const [catFilter, setCatFilter] = useState(savedPat.catFilter || "");

  useEffect(() => {
    const pend = takePending("patents-comp");
    if (pend && pend.cid) {
      setCid(pend.cid);
    }
  }, [takePending]);

  /* The categories the filings are classified under, most-filed first. */
  const areas = useMemo(() => patentAreas(pat), [data]);
  const [area, setArea] = useState(savedPat.area && byTechnology[savedPat.area] ? savedPat.area : areas[0] || null);

  useEffect(() => {
    try {
      viewState.setItem("kssl_pat_state", JSON.stringify({ lens, cid, area, catFilter }));
    } catch (e) {}
  }, [lens, cid, area, catFilter]);

  const portfolio = byCompetitor[cid] || null;
  const cats = portfolio ? portfolio.categories || [] : [];
  useEffect(() => {
    setCatFilter("");
  }, [cid]);

  /* What the header's Copy / Export / Print act on: the filings the open lens lists, under the
     category filter in force. */
  const report = useMemo(() => {
    const recRow = (r) => [
      r.title || r.id,
      [r.id, r.status, r.filed, r.jurisdiction].filter(Boolean).join(" · "),
    ];
    const recs = lens === "rival" ? (portfolio ? portfolio.records : []) : (byTechnology[area] || {}).records || [];
    const shown = lens === "rival" ? recs.filter((r) => inCategory(r, catFilter)) : recs;
    const subject = lens === "rival" ? (data.competitors[cid] || {}).name || cid : area || "";
    return {
      title: `Patents · ${subject}`,
      subtitle: `${shown.length} filing${shown.length === 1 ? "" : "s"}${catFilter && lens === "rival" ? ` · ${catFilter}` : ""}`,
      sections: [
        {
          h: lens === "rival" ? `Filings by ${subject}` : `Filings in ${subject}`,
          rows: shown.length ? shown.map(recRow) : ["No filings on record."],
        },
      ],
      payload: {
        lens,
        competitor: lens === "rival" ? cid : null,
        technology: lens === "rival" ? null : area,
        filter: catFilter || null,
        filings: shown,
      },
    };
  }, [lens, cid, area, catFilter, portfolio, byTechnology, data.competitors]);
  useHeaderReport(report);

  const compList = data.compOrder.filter(
    (k) =>
      data.competitors[k] &&
      (!compQuery.trim() ||
        data.competitors[k].name.toLowerCase().includes(compQuery.trim().toLowerCase())),
  );
  const areaList = areas.filter(
    (a) => !techQuery.trim() || a.toLowerCase().includes(techQuery.trim().toLowerCase()),
  );

  if (!Object.keys(byCompetitor).length)
    return (
      <div className="pat-view v-patents-comp">
        <div className="pat-state" style={{ padding: "48px 32px" }}>
          <div className="ps-ic">⊟</div>
          <div className="ps-t">No patent portfolios on record</div>
        </div>
      </div>
    );

  return (
    <div className="pat-view v-patents-comp">
      <div className="pat-lens">
        <span className="pat-lens-lab">Lens</span>
        <button
          className={`pat-lens-b${lens === "rival" ? " active" : ""}`}
          onClick={() => setLens("rival")}
          type="button"
        >
          By rival
        </button>
        <button
          className={`pat-lens-b${lens === "field" ? " active" : ""}`}
          onClick={() => setLens("field")}
          type="button"
        >
          By technology field
        </button>
      </div>

      <div className="pat-pane" data-lens="rival" style={{ display: lens === "rival" ? "" : "none" }}>
        <div className="mu-list">
          <div className="mu-list-h">
            <span className="eyebrow">Competitors</span>
            <div className="mu-search">
              <span className="si">⌕</span>
              <input
                onChange={(e) => setCompQuery(e.target.value)}
                placeholder="Search competitor…"
                type="text"
                value={compQuery}
              />
            </div>
          </div>
          <div id="patc-list">
            {compList.length ? (
              compList.map((k) => {
                const pd = byCompetitor[k];
                return (
                  <div
                    className={`pat-li${cid === k ? " active" : ""}`}
                    key={k}
                    onClick={() => setCid(k)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setCid(k);
                      }
                    }}
                  >
                    <span className="pli-n">{data.competitors[k].name}</span>
                    <span className="pli-c">{pd ? (pd.filingCount != null ? pd.filingCount : pd.records.length) : ""}</span>
                  </div>
                );
              })
            ) : (
              <div className="pat-li-none">No match for “{compQuery.trim()}”</div>
            )}
          </div>
        </div>
        <div className="pat-canvas">
          <div className="pat-head">
            <span className="eyebrow">{`${(data.competitors[cid] || {}).name || cid} · patent portfolio`}</span>
            {cats.length > 1 ? (
              <select
                className="mu-fsel patc-cat-filter"
                onChange={(e) => setCatFilter(e.target.value)}
                style={{ marginTop: "8px", maxWidth: "280px" }}
                value={catFilter}
              >
                <option value="">
                  All product categories{portfolio && portfolio.filingCount != null ? ` (${portfolio.filingCount})` : ""}
                </option>
                {cats.map((c) => (
                  <option key={c.label} value={c.label}>
                    {c.label}{c.count != null ? ` (${c.count})` : ""}
                  </option>
                ))}
              </select>
            ) : null}
          </div>
          <HtmlBlock html={patCompBody(data, cid, catFilter)} id="patc-body" />
          {/* review copy only: the filings above are drawn as HTML, so the same records are listed here */}
          <ReviewList
            title="Patent filings"
            items={(portfolio ? portfolio.records : []).filter((r) => inCategory(r, catFilter)).map((r) => ({ src: r._src, label: r.title || r.id }))}
          />
        </div>
      </div>

      <div className="pat-pane" data-lens="field" style={{ display: lens === "field" ? "" : "none" }}>
        <div className="mu-list">
          <div className="mu-list-h">
            <span className="eyebrow">Technology fields</span>
            <div className="mu-search">
              <span className="si">⌕</span>
              <input
                onChange={(e) => setTechQuery(e.target.value)}
                placeholder="Search field…"
                type="text"
                value={techQuery}
              />
            </div>
          </div>
          <div id="patt-list">
            {areaList.length ? (
              areaList.map((a) => {
                const td = byTechnology[a];
                return (
                  <div
                    className={`pat-li${area === a ? " active" : ""}`}
                    key={a}
                    onClick={() => setArea(a)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setArea(a);
                      }
                    }}
                  >
                    <span className="pli-n">{a}</span>
                    <span className="pli-c">{td ? td.count : ""}</span>
                  </div>
                );
              })
            ) : (
              <div className="pat-li-none">{areas.length ? `No match for “${techQuery.trim()}”` : "No technology fields on record"}</div>
            )}
          </div>
        </div>
        <div className="pat-canvas">
          <div className="pat-head">
            <span className="eyebrow">{area ? `${area} · field analysis` : "Field analysis"}</span>
          </div>
          {area ? <HtmlBlock html={patTechBody(data, area)} id="patt-body" /> : null}
          <ReviewList
            title="Patent filings"
            items={((byTechnology[area] || {}).records || []).map((r) => ({ src: r._src, label: r.title || r.id }))}
          />
        </div>
      </div>
    </div>
  );
}
