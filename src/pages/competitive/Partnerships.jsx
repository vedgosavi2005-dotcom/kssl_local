import { useEffect, useMemo, useRef, useState } from "react";
import HtmlBlock from "../../components/htmlBlock/HtmlBlock";
import ScopeChat from "../../components/scopeChat/ScopeChat";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { formatSectorName, formatCompanyName } from "../../lib/profile";
import { ReviewList } from "../../components/review/Review";
/* A SELECTION IS REMEMBERED WHILE YOU STAY IN THIS PILLAR, not for ever. This page
   persisted to localStorage, which survives the tab, the browser and the machine's
   next reboot -- so a company opened once was still the landing selection weeks
   later, on a dashboard whose job is "what is new". Same key/value shape, held in
   memory, cleared on a pillar change. See lib/viewState. */
import * as viewState from "../../lib/viewState";

/* `sector` is escaped at write time ("Defence &amp; Aerospace") and is formatted consistently here. */
const sectorText = (co) => formatSectorName(co && co.sector);

/* Competitor-centric relationship graph. Three panes: the rival list, the alliance
   network with the shared-partner read beneath it, and a drawer that switches between
   the competitor-level synthesis, a single tie, and the field-level read.

   The graph is raw SVG built by lib/partners — one node per partner COMPANY, each on
   its own angle, so no two lines coincide and no line runs through another node. */
export default function Partnerships() {
  const { data, partners } = useData();
  const { setScope, searchQuery } = useAppState();
  const clientName = (data.client && (data.client.short || data.client.name)) || "";
  const clientId = data.client?.id;
  const lc = (v) => String(v == null ? "" : v).toLowerCase();
  const distinctPartners = (co) => new Set((co.partners || []).map((x) => x.pid || x.id)).size;
  const getSavedPart = () => {
    try {
      const s = viewState.getItem("kssl_part_state");
      return s ? JSON.parse(s) : {};
    } catch (e) { return {}; }
  };
  const savedPart = getSavedPart();
  /* A saved selection outlives the dataset that produced it: the stored id can be
     from an older export, or the client itself (which this list no longer shows).
     Restore it only if the row is still here, or the drawer renders an id with no
     competitor behind it and throws on the first field it reads. */
  const defaultCid =
    (data.compOrder && data.compOrder.find((k) => k !== clientId && data.competitors[k])) || null;
  const savedCid =
    savedPart.cid && data.competitors[savedPart.cid] && savedPart.cid !== clientId
      ? savedPart.cid
      : defaultCid;

  const [cid, setCid] = useState(savedCid);
  const [query, setQuery] = useState("");
  const [hq, setHq] = useState("");
  const [tie, setTie] = useState(savedCid ? savedPart.tie || null : null); // a partner row id, or null for the competitor read
  const [mode, setMode] = useState(savedPart.mode || "syn"); // 'syn' | 'field'
  const [relCardIndex, setRelCardIndex] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panCenter, setPanCenter] = useState(null);
  /* Step-by-step branch explorer: "root" (company only) -> "spread" (its partner types)
     -> "focus" (one type's partners open, the other branches dimmed). A different
     competitor starts again at the root. `anim` names what just appeared. */
  /* A company OPENS with its branches already spread (owner request): the reader lands on
     the partner types, not on a lone node they must click first. The company node / step
     bar still fold it back to the root. */
  const [graphView, setGraphView] = useState({ stage: "spread", type: null, anim: "types" });
  /* Group-by filter beside the zoom buttons: "type" = categories (partner type),
     "region" = the partner's country. Switching spreads the new branches at once. */
  const [groupMode, setGroupMode] = useState("type");
  const changeGroupMode = (m) => {
    setGroupMode(m);
    setTie(null);
    setMode("syn");
    setPanCenter(null);
    setZoomLevel(1);
    setGraphView({ stage: "spread", type: null, anim: "types" });
  };
  useEffect(() => {
    setGraphView((v) => (groupMode === "region" ? v : { stage: "spread", type: null, anim: "types" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid]);
  const goRoot = () => {
    setPanCenter(null);
    setZoomLevel(1);
    setGraphView({ stage: "root", type: null, anim: null });
  };
  const goSpread = () => {
    setPanCenter(null);
    setZoomLevel(1);
    setGraphView((v) => ({ stage: "spread", type: null, anim: v.stage === "root" ? "types" : null }));
  };
  // a new focus starts with no partner type open (Regions' middle level)
  const goFocus = (t) => {
    setPanCenter(null);
    setZoomLevel(1);
    setGraphView((v) => ({ stage: "focus", type: t, sub: null, anim: v.stage === "root" ? "types children" : "children" }));
  };
  // Regions: open / close one partner type inside the focused country
  const toggleSub = (k) => {
    setPanCenter(null);
    setZoomLevel(1);
    setGraphView((v) => ({ ...v, sub: v.sub === k ? null : k, anim: "children" }));
  };

  /* Responsive columns. The three panes were hardcoded at 290/1fr/380px, so on a small
     laptop (the reported Mac) 670px of fixed rails starved the centre and the graph shrank
     to nothing. Shrink the rails as the viewport narrows so the graph keeps its width. */
  const [vw, setVw] = useState(typeof window !== "undefined" ? window.innerWidth : 1440);
  useEffect(() => {
    const onResize = () => setVw(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const svgRef = useRef(null);
  const drawerRef = useRef(null);

  const viewBoxStr = useMemo(() => {
    const baseW = 960;
    const baseH = 540;
    const w = baseW / zoomLevel;
    const h = baseH / zoomLevel;
    const cx = panCenter ? panCenter.x : baseW / 2;
    const cy = panCenter ? panCenter.y : baseH / 2;
    const x = Math.max(0, Math.min(baseW - w, cx - w / 2));
    const y = Math.max(0, Math.min(baseH - h, cy - h / 2));
    return `${x.toFixed(1)} ${y.toFixed(1)} ${w.toFixed(1)} ${h.toFixed(1)}`;
  }, [zoomLevel, panCenter]);

  useEffect(() => {
    setRelCardIndex(null);
  }, [cid, tie, mode]);

  useEffect(() => {
    if (drawerRef.current) {
      drawerRef.current.scrollTop = 0;
    }
  }, [cid, tie, mode, relCardIndex]);

  useEffect(() => {
    try {
      if (cid) viewState.setItem("kssl_part_state", JSON.stringify({ cid, tie, mode }));
      else viewState.removeItem("kssl_part_state");
    } catch (e) {}
  }, [cid, tie, mode]);

  const selCo = cid ? data.competitors[cid] : null;
  const c = selCo ? { ...selCo, id: cid } : null;
  /* In Regions mode, display partners grouped by sovereign country flag.
     If a competitor is chosen, map that competitor by country; otherwise map KSSL's own alliance network. */
  const byRegion = groupMode === "region";
  const gc = c;
  const gcid = gc ? gc.id : null;
  // what the drawer / layout treat as "something is selected"
  const hasSel = !!c;

  /* The rival ids this list draws from -- the same population the options describe. */
  const rivalIds = useMemo(
    () => data.compOrder.filter((k) => k !== clientId && data.competitors[k]),
    [data],
  );
  /* The country filter offers the stored origin_country of each rival, one option per value. */
  const hqOptions = useMemo(() => {
    const counts = new Map();
    rivalIds.forEach((k) => {
      const o = (data.competitors[k].origin || "").trim();
      if (o) counts.set(o, (counts.get(o) || 0) + 1);
    });
    return [...counts.entries()].map(([v, n]) => ({ v, n })).sort((a, b) => a.v.localeCompare(b.v));
  }, [data, rivalIds]);
  /* What the header's Copy / Export / Print act on: the selected competitor's mapped
     partners, and the open tie in full. Memoised on selCo (the served record), not on
     `c`, which is re-spread every render. */
  const report = useMemo(() => {
    if (!selCo) {
      /* nothing selected: the roster the rail lists, each with its mapped-partner count */
      const roster = (data.compOrder || [])
        .filter((k) => k !== clientId && data.competitors[k])
        .map((k) => {
          const co = data.competitors[k];
          return { cid: k, name: co.name, partners: distinctPartners(co), hq: co.hq || null };
        });
      return {
        title: "Partnerships",
        subtitle: `${roster.length} competitors · none selected`,
        sections: [
          {
            h: "Competitors and mapped partnerships",
            rows: roster.map((r) => [r.name, `${r.partners} partner${r.partners === 1 ? "" : "s"}${r.hq ? ` · ${r.hq}` : ""}`]),
          },
        ],
        payload: { competitors: roster },
      };
    }
    const partners = selCo.partners || [];
    const tp = tie ? partners.find((x) => x.id === tie) : null;
    const nd = (v) => (v ? String(v) : "—");
    return {
      title: selCo.name,
      subtitle: `${distinctPartners(selCo)} mapped partner${distinctPartners(selCo) === 1 ? "" : "s"}${tp ? ` · ${tp.label}` : ""}`,
      sections: [
        tp
          ? {
              h: `Tie: ${selCo.name} and ${tp.label}`,
              rows: [
                ["Relationship", nd(tp.ptype)],
                ["Source confidence", nd(tp.confidence)],
                ["Region", nd(tp.country)],
                ["As of", nd(tp.as_of)],
                tp.scope ? ["Scope", tp.scope] : null,
                tp.note ? ["Note", tp.note] : null,
              ].filter(Boolean),
            }
          : null,
        {
          h: "Mapped partners",
          rows: partners.map((x) => [x.label, [x.ptype, x.country].filter(Boolean).join(" · ")]),
        },
        selCo.threat ? { h: "Threat read", rows: [selCo.threat] } : null,
      ].filter(Boolean),
      payload: {
        cid,
        name: selCo.name,
        partners,
        tie: tp || null,
        threat: selCo.threat || null,
      },
    };
  }, [selCo, cid, tie, data]);
  useHeaderReport(report);

  const activeQ = (query || searchQuery || "").trim().toLowerCase();
  const tokens = activeQ.split(/\s+/).filter(Boolean);

  const list = data.compOrder
    .filter((k) => k !== clientId)
    .filter((k) => {
      const co = data.competitors[k];
      if (!co) return false;
      const pNames = (co.partners || []).map((x) => x.label || "").join(" ");
      const search = `${(co.name || "").toLowerCase()} ${sectorText(co).toLowerCase()} ${(co.hq || "").toLowerCase()} ${pNames.toLowerCase()}`;
      if (tokens.length > 0 && !tokens.every((tok) => search.includes(tok))) return false;
      if (hq && (co.origin || "").trim() !== hq) return false;
      return true;
    });


  /* The competitor list collapses to a rail once a company is chosen, so the graph gets
     the width -- the user picks a company, then reads its network. A toggle reopens it. */
  const [listOpen, setListOpen] = useState(true);

  const selectCompetitor = (nextCid) => {
    const co = data.competitors[nextCid];
    if (!co) return;
    setCid(nextCid);
    setTie(null);
    setListOpen(false); // collapse the list so the graph has room
    if (groupMode === "region") setGroupMode("type");
    // a new company starts from a whole, un-zoomed view
    setPanCenter(null);
    setZoomLevel(1);
    setScope("partner", { type: "partner", comp: { ...co, id: nextCid }, partner: null }, {
      pillar: "Competitive",
      view: "Partnerships",
      selection: co.name,
    });
  };

  const selectPartner = (pid) => {
    if (!gc) return;
    const p = (gc.partners || []).find((x) => x.id === pid);
    if (!p) return;
    setTie(pid);
    // a partner picked from the drawer may sit on a branch that is not open yet
    const t = partners.pgTypeFor(gc, pid, groupMode);
    if (t) setGraphView((v) => (v.stage === "focus" && v.type === t ? v : { stage: "focus", type: t, sub: null, anim: "children" }));
    setScope("partner", { type: "partner", comp: gc, partner: p }, {
      pillar: "Competitive",
      view: "Partnerships",
      selection: `${gc.name} ↔ ${p.label}`,
    });

    // Auto-zoom to selected cluster
    const svg = svgRef.current;
    if (svg) {
      const nodeEl = svg.querySelector(`.pg-node[data-id="${CSS.escape(pid)}"]`);
      if (nodeEl) {
        const circle = nodeEl.querySelector("circle:not([fill*='url(#pg'])") || nodeEl.querySelector("circle");
        if (circle) {
          const nx = parseFloat(circle.getAttribute("cx") || "480");
          const ny = parseFloat(circle.getAttribute("cy") || "270");
          setPanCenter({ x: nx, y: ny });
          setZoomLevel(1.55);
        }
      }
    }
  };

  const deselectPartner = () => {
    setTie(null);
    setMode("syn");
    setPanCenter(null);
    setZoomLevel(1);
  };

  /* Highcharts network graph feature: clicking any bubble isolates that bubble and its
     connected network ties, while smoothly dimming all remaining unrelated bubbles.
     Clicking background or the selected bubble clears dimming back to full brightness. */
  const applyHighlight = (selectedNodeId, tracedNodeIds) => {
    const svg = svgRef.current;
    if (!svg) return;
    svg.querySelectorAll(".pg-node").forEach((n) => n.classList.remove("sel", "dim", "trace", "connected"));
    svg.querySelectorAll(".pg-edge").forEach((e) => e.classList.remove("hl", "dim", "trace"));

    if (selectedNodeId) {
      // Dim all nodes and edges by default
      svg.querySelectorAll(".pg-node").forEach((n) => n.classList.add("dim"));
      svg.querySelectorAll(".pg-edge").forEach((e) => e.classList.add("dim"));

      // 1. Keep selected node bright with glowing highlight
      const node = svg.querySelector(`.pg-node[data-id="${CSS.escape(selectedNodeId)}"]`);
      if (node) {
        node.classList.add("sel");
        node.classList.remove("dim");
        // keep the partner's type node lit too, so the path company -> type -> partner reads
        const t = node.getAttribute("data-type");
        if (t) {
          svg.querySelectorAll(`.pg-node.pg-type[data-type="${CSS.escape(t)}"]`).forEach((n) => n.classList.remove("dim"));
          svg.querySelectorAll(`.pg-type-edge[data-type="${CSS.escape(t)}"]`).forEach((e) => { e.classList.remove("dim"); e.classList.add("hl"); });
        }
      }

      // 2. Keep center root OEM node visible
      const centre = svg.querySelector(".pg-node.center-root");
      if (centre) centre.classList.remove("dim");

      // 3. Highlight connected edges and keep connected neighbor nodes bright
      svg.querySelectorAll(
        `.pg-edge[data-a="${CSS.escape(selectedNodeId)}"], .pg-edge[data-b="${CSS.escape(selectedNodeId)}"], .pg-edge[data-parent="${CSS.escape(selectedNodeId)}"]`
      ).forEach((e) => {
        e.classList.add("hl");
        e.classList.remove("dim");

        const a = e.getAttribute("data-a");
        const b = e.getAttribute("data-b");
        const otherId = a === selectedNodeId ? b : a;
        if (otherId) {
          const otherNode = svg.querySelector(`.pg-node[data-id="${CSS.escape(otherId)}"]`);
          if (otherNode) {
            otherNode.classList.remove("dim");
            otherNode.classList.add("connected");
          }
        }
      });

      // 4. Keep connected satellite nodes bright
      svg.querySelectorAll(`.pg-node[data-parent="${CSS.escape(selectedNodeId)}"]`).forEach((sat) => {
        sat.classList.remove("dim");
        sat.classList.add("connected");
      });
    }

    (tracedNodeIds || []).forEach((id) => {
      const node = svg.querySelector(`.pg-node[data-id="${CSS.escape(id)}"]`);
      if (node) node.classList.add("trace");
      svg.querySelectorAll(`.pg-edge[data-b="${CSS.escape(id)}"]`).forEach((e) =>
        e.classList.add("trace"),
      );
    });
  };

  useEffect(() => {
    if (!gc) return;
    applyHighlight(tie ? partners.pgNodeIdFor(gc, tie) : null, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tie, cid, graphView, groupMode]);

  // the drawer reads the same company the graph shows: KSSL in Regions mode
  const drawerBody = () => {
    if (!gc) return "";
    if (tie) return partners.tieHtml(gc, gcid, tie, clientName, relCardIndex);
    return partners.allPartnersRosterHtml(gc, gcid, clientName);
  };

  const drawerHeadText = () => {
    if (tie) return "Relationship detail";
    return gc ? `${gc.name} · Mapped Partners` : "Mapped Partners";
  };

  const nNode = gc ? partners.pgNodes(gc).length : 0;
  const typeGroups = gc ? partners.pgGroups(gc, groupMode) : [];
  // the legend always explains the node colours, which are the relationship types
  const relGroups = gc ? partners.pgTypeGroups(gc) : [];
  const nRow = gc && gc.partners ? gc.partners.length : 0;

  return (
    <div
      className={`pos-view v-partnerships ${hasSel ? "has-sel" : "no-sel"}${byRegion ? " has-graph" : ""}`}
      style={{
        position: "relative",
        gridTemplateColumns: hasSel
          ? (listOpen
              ? (vw < 900 ? "148px 1fr 264px" : vw < 1100 ? "176px 1fr 288px" : vw < 1350 ? "216px 1fr 320px" : "268px 1fr 356px")
              : (vw < 900 ? "40px 1fr 264px" : vw < 1100 ? "44px 1fr 288px" : vw < 1350 ? "44px 1fr 320px" : "48px 1fr 356px"))
          : (vw < 1200 ? "300px 1fr 0px" : "460px 1fr 0px"),
        transition: "grid-template-columns 0.28s cubic-bezier(0.22, 0.61, 0.36, 1)",
      }}
    >
      {/* LEFT: competitor list (collapses to a rail after a pick -- see listOpen) */}
      <div className="mu-list">
        {c && !listOpen ? (
          <button
            type="button"
            onClick={() => setListOpen(true)}
            title="Expand competitor list"
            aria-label="Expand competitor list"
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 8px",
              width: "28px", height: "28px", padding: 0,
              background: "var(--d-bg-2)", border: "1px solid var(--d-line)", color: "var(--d-txt-2)",
              borderRadius: "6px", fontSize: "12px", cursor: "pointer", lineHeight: 1,
            }}
          >
            ▶
          </button>
        ) : null}
        <div className="mu-list-h" style={c && !listOpen ? { display: "none" } : undefined}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
            <span className="eyebrow">Competitors</span>
            {c ? (
              <button
                type="button"
                onClick={() => setListOpen(false)}
                title="Collapse competitor list"
                aria-label="Collapse competitor list"
                style={{
                  flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center",
                  width: "22px", height: "22px", padding: 0,
                  background: "var(--d-bg-2)", border: "1px solid var(--d-line)",
                  color: "var(--d-txt-2)", borderRadius: "6px", fontSize: "11px",
                  cursor: "pointer", lineHeight: 1,
                }}
              >
                ◀
              </button>
            ) : null}
          </div>
          <div className="mu-search">
            <span className="si">⌕</span>
            <input
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search competitor…"
              type="text"
              value={query}
            />
          </div>
          <select
            aria-label="Filter competitors by country"
            className="mu-fsel"
            onChange={(e) => setHq(e.target.value)}
            style={{ width: "100%", marginTop: "8px" }}
            value={hq}
          >
            <option value="">All countries ({hqOptions.length})</option>
            {hqOptions.map((o) => (
              <option key={o.v} value={o.v}>
                {o.v} ({o.n})
              </option>
            ))}
          </select>
        </div>
        {/* the list sits OUTSIDE the header, so only the companies scroll (the filters stay put) */}
        <div id="patc-list" style={c && !listOpen ? { display: "none" } : undefined}>
          {list.map((k) => {
            const co = data.competitors[k];
            const nPartners = distinctPartners(co);
            return (
              <div
                className={`pat-li${cid === k ? " active" : ""}`}
                key={k}
                onClick={() => {
                  if (cid === k) {
                    setCid(null);
                    setTie(null);
                    setMode("syn");
                    setPanCenter(null);
                    setZoomLevel(1);
                    setGraphView({ stage: "spread", type: null, anim: "types" });
                  } else {
                    selectCompetitor(k);
                  }
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    if (cid === k) {
                      setCid(null);
                      setTie(null);
                      setMode("syn");
                      setPanCenter(null);
                      setZoomLevel(1);
                      setGraphView({ stage: "spread", type: null, anim: "types" });
                    } else {
                      selectCompetitor(k);
                    }
                  }
                }}
              >
                <span className="pli-n" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span className={`wdot ${lc(co.threat)}`} />
                  {co.name}
                </span>
                <span className="pli-c">{nPartners}</span>
              </div>
            );
          })}
          {/* The Competitor and Products sidebars say so when nothing matches; this
              one rendered an empty column, which reads as a list that failed to load. */}
          {!list.length ? (
            <div className="cp-empty">
              {activeQ ? <>no competitor matches “{activeQ}”</> : "no competitor matches this filter"}
            </div>
          ) : null}
          {/* review copy only: the client's own partners (they mark the overlapping partners) */}
          <ReviewList
            title="KSSL partners"
            items={(data.KSSL_PARTNERS || []).map((x) => ({ src: x._src, label: [x.label, x.ptype].filter(Boolean).join(" · ") }))}
          />
        </div>
      </div>

      {/* CENTER: thesis line + interactive graph + shared-partner read */}
      <div className="pg-canvas">
        <div className="pg-instrument-head">
          <div className="pg-i-title">{byRegion ? `${gc ? gc.name : ""} · partners by region` : c ? `${c.name} · alliance network` : "Alliance network"}</div>
        </div>
        <div className="pg-graph-wrap" style={{ position: "relative" }}>
          {!gc ? (
            <div className="pg-empty">
              <div className="pg-empty-ic">◆</div>
              <div className="pg-empty-t">Select a competitor</div>
              <div className="pg-empty-s">Choose from the list to map their alliance network, then group it by category or region</div>
            </div>
          ) : null}
          {(
            <div className="pg-canvas-toolbar">
              {/* A Network / Heatmap toggle stood here. `viewMode` was read by nothing
                  but the two buttons' own active class: "Heatmap" lit itself up and the
                  canvas stayed byte-for-byte the same, measured 2026-09-05. No heatmap
                  exists in this build; a control that promises one and delivers nothing
                  is worse than no control. If a heatmap is built, the toggle returns
                  with it. */}
              <div className="pg-zoom-box">
                {graphView.stage === "focus" ? (
                  <button
                    type="button"
                    className="pg-tb-pill active"
                    onClick={() => {
                      deselectPartner();
                      goSpread();
                    }}
                    title={`Back to all ${byRegion ? "regions" : "categories"}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                      cursor: "pointer",
                      padding: "3px 10px",
                      fontSize: "11px",
                      fontWeight: 600,
                      background: "rgba(30, 41, 59, 0.85)",
                      border: "1px solid rgba(255, 255, 255, 0.2)",
                      color: "#f1f5f9",
                    }}
                  >
                    <span>←</span>
                    <span>All {byRegion ? "Regions" : "Categories"}</span>
                  </button>
                ) : null}
                <select
                  aria-label="Group the graph by"
                  className="pg-group-sel"
                  value={groupMode}
                  onChange={(e) => changeGroupMode(e.target.value)}
                  title="Group partners by category or by region"
                >
                  <option value="type">Categories</option>
                  <option value="region">Regions</option>
                </select>
                <button
                  type="button"
                  className="pg-tb-btn"
                  onClick={() => setZoomLevel((z) => Math.min(1.6, Number((z + 0.15).toFixed(2))))}
                  title="Zoom In"
                >
                  +
                </button>
                <button
                  type="button"
                  className="pg-tb-btn"
                  onClick={() => setZoomLevel((z) => Math.max(0.7, Number((z - 0.15).toFixed(2))))}
                  title="Zoom Out"
                >
                  -
                </button>
                <button
                  type="button"
                  className="pg-tb-btn"
                  onClick={() => {
                    deselectPartner();
                    setGraphView((v) => ({ stage: "spread", type: null, anim: "types" }));
                  }}
                  title="Reset View"
                >
                  ⟲
                </button>
              </div>
            </div>
          )}
          <svg
            id="pg-svg"
            preserveAspectRatio="xMidYMid meet"
            ref={svgRef}
            viewBox={viewBoxStr}
            dangerouslySetInnerHTML={{ __html: gc ? partners.typeGraphSvg(gc, { ...graphView, mode: groupMode, coreSub: "" }) : "" }}
            onClick={(e) => {
              const g = e.target.closest(".pg-node");
              if (g && g.classList.contains("pg-subtype")) {
                // Regions: a partner type inside the country opens / closes its companies
                if (tie) deselectPartner();
                toggleSub(g.getAttribute("data-sub"));
                return;
              }
              if (g && g.classList.contains("pg-type")) {
                // a branch opens its partners (and dims the rest); clicking it again closes it
                const t = g.getAttribute("data-type");
                if (tie) deselectPartner();
                if (graphView.stage === "focus" && graphView.type === t) goSpread();
                else goFocus(t);
                return;
              }
              if (g && g.classList.contains("center-root")) {
                // the company: spread its branches, restore them from a focus, or fold them
                deselectPartner();
                if (graphView.stage === "spread") goRoot();
                else goSpread();
                return;
              }
              if (!g) {
                // Clicked on empty canvas -> clear dimming and return to spread if in focus
                deselectPartner();
                if (graphView.stage === "focus") {
                  goSpread();
                }
                return;
              }
              if (g.classList.contains("comp") || g.classList.contains("center-root")) {
                // Clicked central root OEM -> reset
                deselectPartner();
              } else {
                const nodeId = g.getAttribute("data-id") || g.getAttribute("data-parent");
                if (!nodeId) return;
                if (tie === nodeId) {
                  // Toggle off when clicking already selected bubble -> un-dim all & zoom out
                  deselectPartner();
                } else {
                  selectPartner(nodeId);
                }
              }
            }}
          />
          {gc && typeGroups.length ? (
            <div className="pg-legend-box" aria-label="Legend">
              <div className="lg">
                <span className="nd" style={{ background: "#0f6f7d" }} />
                <span className="lg-text">{gc.name}</span>
              </div>
              {byRegion ? (
                <div className="lg">
                  <span className="nd" style={{ background: "#23303f", border: "1.5px solid #7fa8c9" }} />
                  <span className="lg-text">Country / Region</span>
                </div>
              ) : null}
              {relGroups.map((g) => (
                <div className="lg" key={g.key}>
                  <span className="nd" style={{ background: g.fill, border: `1.5px solid ${g.color}` }} />
                  <span className="lg-text">{g.label}</span>
                </div>
              ))}
              {!byRegion ? (
                <div className="lg">
                  <span className="nd" style={{ background: "#ff2d2d" }} />
                  <span className="lg-text">Overlapping Partner</span>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        {/* The shared-partner read block that sat here ("Overlapping partners · N of M"
            + the tie card) was removed to give the graph its full height: overlaps are
            already marked red on the graph and read in full in the right-hand drawer. */}
        {/* the legend now sits inside the graph (bottom-left box) */}
      </div>


      {/* RIGHT: reactive intelligence drawer */}
      <div className={`pg-drawer${hasSel ? " open" : ""}`} id="pg-drawer">
        <div style={{ display: "flex", flex: 1, flexDirection: "column", height: "100%", overflow: "hidden" }}>
          <div className="pg-drawer-scroll" ref={drawerRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: "24px" }}>
            <div style={{ position: "absolute", top: "12px", right: "14px", display: "flex", alignItems: "center", gap: "6px", zIndex: 30, paddingBottom: "10px" }}>
              {(tie || mode === "field") && (
                <button
                  type="button"
                  className="col-close"
                  onClick={() => {
                    setTie(null);
                    setMode("syn");
                  }}
                  title="Back"
                  style={{
                    position: "static",
                    width: "auto",
                    height: "26px",
                    padding: "0 10px",
                    fontSize: "11.5px",
                    fontWeight: "600",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                    marginBottom: "8px",
                  }}
                >
                  ‹ Back
                </button>
              )}
              <button
                aria-label="Close"
                className="col-close"
                onClick={() => { setCid(null); setTie(null); }}
                title="Close"
                type="button"
                style={{ position: "static", height: "26px", width: "26px", marginBottom: "8px" }}
              >
                ✕
              </button>
            </div>
            <div className="pg-drawer-head" style={{ paddingRight: "110px", paddingBottom: "16px" }} dangerouslySetInnerHTML={{ __html: drawerHeadText() }} />
            {/* review copy only: the drawer draws its partners as HTML, so the same records are listed here */}
            {gc ? (
              <ReviewList
                title={`${gc.name} partners`}
                items={(gc.partners || [])
                  .filter((x) => !tie || x.id === tie)
                  .map((x) => ({ src: x._src, label: [x.label, x.ptype].filter(Boolean).join(" · ") }))}
              />
            ) : null}
            <HtmlBlock
              className="pg-drawer-body"
              handlers={{
                "[data-back]": () => {
                  setTie(null);
                  setMode("syn");
                },
                "[data-relcard]": (el) => {
                  const ix = Number(el.getAttribute("data-relcard"));
                  setRelCardIndex(ix);
                },
                "[data-backrelcards]": () => {
                  setRelCardIndex(null);
                },
                ".pg-partner-roster-card[data-pid]": (el) => selectPartner(el.getAttribute("data-pid")),
              }}
              html={drawerBody()}
              id="pg-r-body"
            />
          </div>
        </div>
      </div>

      {/* FULL-SCREEN OVERLAY COVERING GRAPH AND DRAWER WHEN A RELATIONSHIP CARD IS OPENED */}
      {relCardIndex !== null && tie && gc && (
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: "290px",
            right: 0,
            zIndex: 200,
            background: "#ffffff",
            overflowY: "auto",
            padding: "24px",
          }}
        >
          <HtmlBlock
            handlers={{
              "[data-backrelcards]": () => setRelCardIndex(null),
            }}
            html={partners.tieHtml(gc, gcid, tie, clientName, relCardIndex)}
          />
        </div>
      )}
    </div>
  );
}
