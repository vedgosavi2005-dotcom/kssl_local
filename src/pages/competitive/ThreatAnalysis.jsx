import { useState, useMemo, useEffect } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { formatDate as fmtDate } from "../../utils/formatDate.js";
import Thumb from "../../components/thumb/Thumb.jsx";
import { Review } from "../../components/review/Review.jsx";

// the house date format; "Undated" (chrome) when the move carries no date
const formatDate = (v) => (v ? fmtDate(String(v)) : "Undated");

/* The dot beside a competitor: its stored threat_level (threat | watch | fav). Any other
   stored value has no colour; the stored text is the tooltip. */
const DOT = { threat: "threat", watch: "watch", fav: "fav" };
/* Drawer header colour from the level's stored tag_class (ui.competitive_competitor_moment_level). */
const HEAD_CLASS = { threat: "threat", opportunity: "fav", fav: "fav", kssl: "fav", watch: "watch" };

export default function ThreatAnalysis() {
  const { setScope } = useAppState();
  const { data } = useData();

  const competitorsData = data.competitorMoment?.competitors || [];
  const momentData = data.competitorMoment || { items: [], timeWindows: [], levels: {} };
  const allMoves = momentData.items || [];

  const [selectedCid, setSelectedCid] = useState("__all");
  const [searchQuery, setSearchQuery] = useState("");
  // the window the ui table marks as default (is_default); none marked = no window
  const [timeFilter, setTimeFilter] = useState(() => {
    const def = (data.competitorMoment?.timeWindows || []).find((w) => w.isDefault);
    return def ? def.id : "";
  });
  const [customRange, setCustomRange] = useState({ from: "", to: "" });
  const [selectedMoveId, setSelectedMoveId] = useState(null);

  // Determine newest date anchor
  const newestTimestamp = useMemo(() => {
    return Math.max(0, ...allMoves.map((m) => Date.parse(m.date) || 0));
  }, [allMoves]);

  // Compute active date boundaries
  const activeDateRange = useMemo(() => {
    if (timeFilter === "custom") return customRange;
    const windowDef = (momentData.timeWindows || []).find((w) => w.id === timeFilter);
    const days = windowDef ? windowDef.days : null;
    if (days == null || !newestTimestamp) {
      return { from: "", to: "" };
    }
    const fromTime = newestTimestamp - days * 86400000;
    return {
      from: new Date(fromTime).toISOString().slice(0, 10),
      to: new Date(newestTimestamp).toISOString().slice(0, 10),
    };
  }, [timeFilter, customRange, newestTimestamp, momentData.timeWindows]);

  // Date filter predicate
  const matchesDate = (item) => {
    const t = Date.parse(item.date) || 0;
    const fromT = activeDateRange.from ? Date.parse(activeDateRange.from) : -Infinity;
    const toT = activeDateRange.to ? Date.parse(activeDateRange.to) + 86399999 : Infinity;
    return t >= fromT && t <= toT;
  };

  // Competitor moves mapped & filtered
  const competitorStats = useMemo(() => {
    return competitorsData.map((comp) => {
      const compMoves = allMoves.filter((m) => m.cid === comp.cid);
      const filtered = compMoves.filter(matchesDate);
      return {
        ...comp,
        allCount: compMoves.length,
        filteredCount: filtered.length,
      };
    });
  }, [competitorsData, allMoves, activeDateRange]);

  // Filtered competitor list for sidebar search
  const visibleCompetitors = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return competitorStats;
    return competitorStats.filter(
      (c) => c.name.toLowerCase().includes(q) || (c.short || "").toLowerCase().includes(q)
    );
  }, [competitorStats, searchQuery]);

  // Active moves feed
  const displayedMoves = useMemo(() => {
    let list = allMoves.filter(matchesDate);
    if (selectedCid !== "__all") {
      list = list.filter((m) => m.cid === selectedCid);
    }
    // newest first; equal dates keep their stored display_order
    return list.slice().sort(
      (a, b) =>
        (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0) ||
        (a.order == null ? Infinity : a.order) - (b.order == null ? Infinity : b.order),
    );
  }, [allMoves, selectedCid, activeDateRange]);

  // Selected competitor metadata
  const selectedCompetitor = useMemo(() => {
    if (selectedCid === "__all") return null;
    return competitorsData.find((c) => c.cid === selectedCid) || null;
  }, [selectedCid, competitorsData]);

  const activeTitle = selectedCompetitor ? selectedCompetitor.name : "All competitors";
  const levelOf = (m) => (momentData.levels || {})[String(m.level || "").toLowerCase()] || { label: m.level, tagClass: "neutral" };
  // "graded a threat" = moves whose level's stored tag_class is "threat"
  const threatCount = displayedMoves.filter((m) => levelOf(m).tagClass === "threat").length;
  const windowedTotal = useMemo(() => allMoves.filter(matchesDate).length, [allMoves, activeDateRange]);

  // Selected detail move
  const selectedMove = useMemo(() => {
    if (!selectedMoveId) return null;
    return allMoves.find((m) => m.id === selectedMoveId) || null;
  }, [selectedMoveId, allMoves]);

  // Sync with the global header report (memoised: a new object every render re-publishes forever)
  const report = useMemo(
    () => ({
      title: `${activeTitle}: competitor moment`,
      subtitle: `${displayedMoves.length} move${displayedMoves.length === 1 ? "" : "s"} ${
        activeDateRange.from ? `from ${activeDateRange.from} to ${activeDateRange.to}` : "on record"
      }`,
      sections: [
        {
          h: "Moves, newest first",
          rows: displayedMoves.map((m) => [
            `${formatDate(m.date)} · ${m.company} [${levelOf(m).label || ""}]`,
            [m.title, m.summary].filter(Boolean).join(". "),
          ]),
        },
      ],
      payload: {
        competitor: selectedCompetitor ? selectedCompetitor.cid : null,
        moves: displayedMoves,
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeTitle, displayedMoves, activeDateRange, selectedCompetitor, momentData],
  );
  useHeaderReport(report);

  // Sync shell scope
  useEffect(() => {
    setScope(
      "competitive",
      { moves: displayedMoves.length, competitor: selectedCompetitor ? selectedCompetitor.cid : null },
      { pillar: "Competitive", view: "Competitor Moment", selection: activeTitle }
    );
  }, [displayedMoves.length, selectedCompetitor, activeTitle, setScope]);

  return (
    <div
      className="pos-view v-projects"
      style={{
        gridTemplateColumns: selectedMove ? "280px minmax(0, 1fr) 440px" : "280px 1fr",
      }}
    >
      {/* 1. LEFT SIDEBAR: COMPETITORS LIST */}
      <div className="mu-list">
        <div className="mu-list-h">
          <div className="proj-sidebar-h">
            <span className="eyebrow">Competitors ({competitorsData.length})</span>
          </div>
          <div className="mu-search" style={{ marginTop: "10px" }}>
            <span className="si">⌕</span>
            <input
              type="text"
              placeholder="Search competitor…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <div id="patc-list">
          {/* All competitors entry */}
          <div
            className={`pat-li${selectedCid === "__all" ? " active" : ""}`}
            onClick={() => {
              setSelectedCid("__all");
              setSelectedMoveId(null);
            }}
            role="button"
            tabIndex={0}
          >
            <span
              className="pli-n"
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span>All competitors</span>
              </span>
              <span className="pli-ct">{windowedTotal}</span>
            </span>
          </div>

          {/* Individual competitor items */}
          {visibleCompetitors.map((c) => (
            <div
              key={c.cid}
              className={`pat-li${selectedCid === c.cid ? " active" : ""}`}
              onClick={() => {
                setSelectedCid(c.cid);
                setSelectedMoveId(null);
              }}
              role="button"
              tabIndex={0}
            >
              <span
                className="pli-n"
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}
              >
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  <span
                    className={`wdot ${DOT[String(c.threat).toLowerCase()] || ""}`}
                    title={c.threat || undefined}
                  />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.name}
                  </span>
                </span>
                <span className="pli-ct">{c.filteredCount}</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 2. MAIN FEED: COMPETITOR MOMENT FEED */}
      <div className="proj-main" style={{ overflowY: "auto", padding: "22px 28px 40px" }}>
        {/* Header */}
        <div className="proj-co-header">
          <div className="proj-co-title-group">
            <span className="proj-co-eyebrow">Competitor Moment</span>
            <h1 className="proj-co-name">{activeTitle}</h1>
            <div className="proj-co-sub">
              <span>
                {displayedMoves.length} {displayedMoves.length === 1 ? "move" : "moves"} in this window ·{" "}
                {threatCount} graded a threat
              </span>
            </div>
          </div>
        </div>

        {/* Time Window & Date Range Bar */}
        <div className="cm-bar">
          <div className="cm-chips" role="group" aria-label="Time window">
            {(momentData.timeWindows || []).map((w) => (
              <button
                key={w.id}
                type="button"
                className={`cm-chip${timeFilter === w.id ? " on" : ""}`}
                onClick={() => setTimeFilter(w.id)}
              >
                {w.label}
              </button>
            ))}
          </div>

          <label className="cm-date">
            From{" "}
            <input
              type="date"
              value={activeDateRange.from}
              max={activeDateRange.to || undefined}
              onChange={(e) => {
                setCustomRange((prev) => ({ ...prev, from: e.target.value }));
                setTimeFilter("custom");
              }}
            />
          </label>

          <label className="cm-date">
            To{" "}
            <input
              type="date"
              value={activeDateRange.to}
              min={activeDateRange.from || undefined}
              onChange={(e) => {
                setCustomRange((prev) => ({ ...prev, to: e.target.value }));
                setTimeFilter("custom");
              }}
            />
          </label>

          {newestTimestamp ? (
            <span className="cm-anchor">
              Today = newest move, {formatDate(new Date(newestTimestamp).toISOString().slice(0, 10))}
            </span>
          ) : null}
        </div>

        {/* Moves List Stream */}
        {displayedMoves.length > 0 ? (
          <div className="cm-list">
            {displayedMoves.map((m) => {
              const levelCfg = levelOf(m);
              const isSelected = selectedMoveId === m.id;

              return (
                <div
                  key={m.id}
                  className={`cm-row${isSelected ? " sel" : ""}`}
                  onClick={() => setSelectedMoveId(m.id)}
                  role="button"
                  tabIndex={0}
                  title="Open the strategic analysis"
                >
                  <div className="cm-left">
                    {m.image ? (
                      <div className="cm-img">
                        <Thumb src={m.image} alt="" caption="no image" />
                      </div>
                    ) : null}
                    <div className="cm-when">
                      <b>{formatDate(m.date)}</b>
                      <span>{[m.category, m.country].filter(Boolean).join(" · ")}</span>
                    </div>
                  </div>

                  <div className="cm-main">
                    <div className="cm-top">
                      <span className="cm-co">{m.company}</span>
                      <span className={`proj-tag-pill ${levelCfg.tagClass}`}>
                        {levelCfg.label}
                      </span>
                      {m.source ? <span className="cm-src">{m.source}</span> : null}
                    </div>

                    <div className="cm-title">{m.title}</div>
                    {m.summary ? <div className="cm-desc">{m.summary}</div> : null}
                    <Review src={m._src} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="proj-section-block" style={{ marginTop: "20px" }}>
            <table className="proj-data-table">
              <tbody>
                <tr>
                  <td className="proj-table-val">
                    No move by {activeTitle} in this window.{" "}
                    <button
                      type="button"
                      className="cm-chip on"
                      style={{ display: "inline-block", marginLeft: "8px", verticalAlign: "middle" }}
                      onClick={() => {
                        // every date: an open custom range
                        setCustomRange({ from: "", to: "" });
                        setTimeFilter("custom");
                      }}
                    >
                      Show all dates
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 3. RIGHT DETAIL DRAWER: STRATEGIC ANALYSIS */}
      {selectedMove && (
        <div className="ctx v-overview revealed">
          <div className="ctx-scroll">
            {/* Header: colour from the level's stored tag_class */}
            <div className={`ctx-h dir-${HEAD_CLASS[levelOf(selectedMove).tagClass] || "none"}`}>
              <div className="ctx-h-actions">
                <button
                  type="button"
                  className="col-close"
                  onClick={() => setSelectedMoveId(null)}
                  title="Close"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>
              <div className="ct" style={{ paddingRight: "40px" }}>
                {selectedMove.title}
              </div>
              <div className="sub" style={{ marginTop: "8px" }}>
                {[selectedMove.company, selectedMove.date ? formatDate(selectedMove.date) : ""].filter(Boolean).join(" · ")}
              </div>
              <Review src={selectedMove._src} />
            </div>

            {/* At a glance: only the columns the move carries */}
            <div className="ctx-sec">
              <span className="eyebrow">At a glance</span>
              <div className="cd-facts">
                {[
                  ["Company", selectedMove.company],
                  ["Date", selectedMove.date ? formatDate(selectedMove.date) : ""],
                  ["Category", selectedMove.category],
                  ["Country", selectedMove.country],
                  ["Region", selectedMove.region],
                  ["Strategic Program", selectedMove.program],
                  ["Source", selectedMove.source],
                ]
                  .filter(([, val]) => val)
                  .map(([label, val]) => (
                    <div key={label} className="cd-frow">
                      <span className="cd-fline">
                        <span className="cd-fk">{label}</span>
                        <span className="cd-fv">{val}</span>
                      </span>
                    </div>
                  ))}
              </div>
            </div>

            {selectedMove.whatHappened ? (
              <div className="ctx-sec">
                <span className="eyebrow">What happened</span>
                <div className="cd-prose">{selectedMove.whatHappened}</div>
              </div>
            ) : null}

            {selectedMove.analysis ? (
              <div className="ctx-sec">
                <span className="eyebrow">Analysis · what it means for KSSL</span>
                <div className="cd-prose">{selectedMove.analysis}</div>
              </div>
            ) : null}

            {/* Deeper analysis · by view (competitive_competitor_moment_analysis) */}
            {(selectedMove.deeper || []).filter((l) => l.text).length > 0 && (
              <div className="ctx-sec">
                <span className="eyebrow">Deeper analysis · by view</span>
                {selectedMove.deeper.filter((l) => l.text).map((lens, i) => (
                  <div key={`${lens.view}-${i}`} style={{ marginTop: "14px" }}>
                    {lens.view ? (
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: "11px",
                          fontWeight: 700,
                          letterSpacing: ".08em",
                          textTransform: "uppercase",
                          color: "var(--l-txt-2)",
                          marginBottom: "4px",
                        }}
                      >
                        {lens.view}
                      </div>
                    ) : null}
                    <div className="cd-prose">{lens.text}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Sources: the move's own source link, then competitive_competitor_moment_source rows */}
            {(() => {
              const links = [];
              if (selectedMove.url) links.push({ label: selectedMove.source || selectedMove.url, url: selectedMove.url });
              (selectedMove.sources || []).forEach((x) => {
                if (x.url && !links.some((l) => l.url === x.url)) links.push({ label: x.publisher || x.url, url: x.url });
              });
              if (!links.length && !selectedMove.source) return null;
              return (
                <div className="ctx-sec">
                  <span className="eyebrow">Source</span>
                  <div style={{ marginTop: "6px", display: "flex", flexDirection: "column", gap: "4px" }}>
                    {links.length ? links.map((l) => (
                      <a
                        key={l.url}
                        href={l.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          color: "var(--brand)",
                          fontFamily: "var(--mono)",
                          fontSize: "12px",
                          textDecoration: "underline",
                          wordBreak: "break-all",
                        }}
                      >
                        {l.label} ↗
                      </a>
                    )) : (
                      <span style={{ color: "var(--l-txt-2)", fontSize: "12px" }}>{selectedMove.source}</span>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
