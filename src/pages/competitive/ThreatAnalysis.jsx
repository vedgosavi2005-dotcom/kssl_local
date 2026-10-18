import { useEffect, useMemo, useState } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { clientShort } from "../../lib/client.js";
import { stanceOf, STANCE_WORD, MOMENT_PRESETS as PRESETS, momentStance } from "../../lib/chrome";
import { rosterOf } from "../../lib/profile";
import { momentsOf } from "../../lib/moments";
import { competitorFullName } from "../../lib/companyNames";
import { formatDate } from "../../utils/formatDate";
import { NO_DATE_LABEL } from "../../lib/overview";
import Thumb from "../../components/thumb/Thumb.jsx";
import { sourceHref } from "../../components/sourceLink/SourceLink.jsx";
import { srcChips } from "../../lib/html";
import { Review } from "../../components/review/Review.jsx";

/* Competitor Movement (code name: moment): what each tracked competitor has just done, newest first, with what it
   means for the client. Every row is one dated, sourced move from `competitorNews` (the same
   list the Competitor Profile reads); nothing is computed beyond counting them. Moves are plain rows: the article's picture and date
   on the left, what happened on the right; a click opens the analysis in the white panel beside the list. Today / Week / Month (or a From-To range) window them, counted
   back from the newest move on record, so the window reads the same however late it is opened. */

/* A moment's stored level (serving.competitive_competitor_moment.grade) is a judgement of the data. It draws a pill
   only when it reads as a threat or a watch (momentStance); any other stored level draws no pill. */
const keyOf = (m) => `${m.cid}|${m.url}|${m.title}`;
const DAY = 86400000;
const ALL = "__all";
const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
const dateOf = (s) => {
  const t = Date.parse(s || "");
  return Number.isFinite(t) ? t : 0;
};

export default function ThreatAnalysis() {
  const { setScope } = useAppState();
  const { data } = useData();
  const [selectedCid, setSelectedCid] = useState(ALL);
  const [search, setSearch] = useState("");
  const [preset, setPreset] = useState("all");
  const [custom, setCustom] = useState({ from: "", to: "" });
  const [sel, setSel] = useState(null);

  const roster = useMemo(() => {
    const news = (data && data.competitorNews) || {};
    return (data && data.competitors ? rosterOf(data) : [])
      .map((r) => {
        const name = competitorFullName(r.cid, r.name, data.competitors) || r.name;
        const moves = momentsOf(news[r.cid]).map((m) => ({ ...m, cid: r.cid, company: name }));
        return { cid: r.cid, name, threat: r.threat, moves };
      });
  }, [data]);

  // "today" is the newest dated move on record, so the window reads the same however late it is opened
  const newest = useMemo(() => Math.max(0, ...roster.flatMap((r) => r.moves.map((m) => dateOf(m.date)))), [roster]);

  // the window as dates, so the From / To boxes always show what the preset means
  const range = useMemo(() => {
    if (preset === "custom") return custom;
    const days = (PRESETS.find((p) => p[0] === preset) || [])[2];
    return days == null || !newest ? { from: "", to: "" } : { from: iso(newest - days * DAY), to: iso(newest) };
  }, [preset, custom, newest]);
  const inRange = (m) => {
    const t = dateOf(m.date);
    const from = range.from ? Date.parse(range.from) : -Infinity;
    const to = range.to ? Date.parse(range.to) + DAY - 1 : Infinity;
    return t >= from && t <= to;
  };
  const setDate = (k, v) => { setCustom({ ...range, [k]: v }); setPreset("custom"); };

  const counted = useMemo(
    () => roster.map((r) => ({ ...r, all: r.moves.length, moves: r.moves.filter(inRange).sort((a, b) => dateOf(b.date) - dateOf(a.date)) }))
      .sort((a, b) => b.moves.length - a.moves.length),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [roster, range],
  );
  const shown = useMemo(() => {
    const q = search.toLowerCase().trim();
    return q ? counted.filter((r) => r.name.toLowerCase().includes(q) || r.cid.toLowerCase().includes(q)) : counted;
  }, [counted, search]);
  const co = counted.find((r) => r.cid === selectedCid) || null;
  const total = counted.reduce((n, r) => n + r.moves.length, 0);
  const moves = useMemo(
    () => (co ? co.moves : counted.flatMap((r) => r.moves).sort((a, b) => dateOf(b.date) - dateOf(a.date))),
    [co, counted],
  );
  const open = sel ? moves.find((m) => keyOf(m) === sel) || null : null;
  // only a threat or watch level is a stance; any other stored level draws no word and no stance colour
  const levelTag = (l) => momentStance(l);
  const levelWord = (l) => STANCE_WORD[levelTag(l)] || "";
  const threats = moves.filter((m) => levelTag(m.level) === "threat").length;
  const label = co ? co.name : "All competitors";
  const clientName = clientShort();

  useEffect(() => {
    setScope("competitive", { moves: moves.length, competitor: co ? co.cid : null }, {
      pillar: "Competitive",
      view: "Competitor Movement",
      selection: label,
    });
  }, [moves.length, co, label, setScope]);

  // memoised: an inline object here made the header report re-fire on every render
  const report = useMemo(() => ({
    title: `${label}: competitor movement`,
    subtitle: `${moves.length} move${moves.length === 1 ? "" : "s"} ${range.from ? `from ${range.from} to ${range.to}` : "on record"}`,
    sections: [{
      heading: "Moves, newest first",
      facts: moves.map((m) => [[m.date, levelWord(m.level)].filter(Boolean).join(" · "), `${m.title}. ${m.analysis || ""}`]),
    }],
    payload: { competitor: co ? co.cid : null, moves },
  }), [co, label, moves, range]);
  useHeaderReport(report);

  if (!roster.length) {
    return <div className="empty-note">No competitor movements on record.</div>;
  }

  const row = (cid, name, n, dot, all) => (
    <div
      key={cid}
      className={`pat-li${cid === selectedCid ? " active" : ""}`}
      onClick={() => setSelectedCid(cid)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedCid(cid); } }}
      role="button"
      tabIndex={0}
    >
      <span className="pli-n" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "8px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {stanceOf(dot) ? <span className={`wdot ${dot}`} /> : null}
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
        </span>
        <span className="pli-ct" title={`${n} in this window, ${all} on record`}>{preset === "all" ? n : `${n}/${all}`}</span>
      </span>
    </div>
  );

  return (
    <div className="pos-view v-projects" style={{ gridTemplateColumns: open ? "300px minmax(0, 1fr) 440px" : "300px 1fr" }}>
      <div className="mu-list">
        <div className="mu-list-h">
          <div className="proj-sidebar-h">
            <span className="eyebrow">Competitors ({shown.length})</span>
          </div>
          <div className="mu-search" style={{ marginTop: "10px" }}>
            <span className="si">⌕</span>
            <input type="text" placeholder="Search competitor…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        <div id="patc-list">
          {row(ALL, "All competitors", total, null, roster.reduce((n, r) => n + r.moves.length, 0))}
          {shown.map((r) => row(r.cid, r.name, r.moves.length, r.threat, r.all))}
        </div>
      </div>

      <div className="proj-main" style={{ overflowY: "auto", padding: "22px 28px 40px" }}>
        <div className="proj-co-header">
          <div className="proj-co-title-group">
            <span className="proj-co-eyebrow">Competitor Movement</span>
            <h1 className="proj-co-name">{label}</h1>
            <div className="proj-co-sub">
              <span>{moves.length} {moves.length === 1 ? "move" : "moves"} in this window · {threats} graded a threat</span>
            </div>
          </div>
        </div>

        <div className="cm-bar">
          <div className="cm-chips" role="group" aria-label="Time window">
            {PRESETS.map(([id, text]) => (
              <button key={id} type="button" className={`cm-chip${preset === id ? " on" : ""}`} aria-pressed={preset === id} onClick={() => setPreset(id)}>{text}</button>
            ))}
          </div>
          <label className="cm-date">From <input type="date" value={range.from} max={range.to || undefined} onChange={(e) => setDate("from", e.target.value)} /></label>
          <label className="cm-date">To <input type="date" value={range.to} min={range.from || undefined} onChange={(e) => setDate("to", e.target.value)} /></label>
          {newest ? <span className="cm-anchor">Today = newest move, {formatDate(iso(newest))}</span> : null}
        </div>

        {moves.length ? (
          <div className="cm-list">
            {moves.map((m, i) => (
              <div
                key={`${m.url}${i}`}
                className={`cm-row${open && keyOf(m) === sel ? " sel" : ""}`}
                onClick={() => setSel(keyOf(m))}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(keyOf(m)); } }}
                role="button"
                tabIndex={0}
                title="Open the analysis"
              >
                <div className="cm-left">
                  <Thumb src={m.image} alt="" className="cm-img" caption={m.source || "No image published"} />
                  <div className="cm-when">
                    <b>{formatDate(m.date) || NO_DATE_LABEL}</b>
                    {[m.category, m.country].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="cm-main">
                  <div className="cm-top">
                    <span className="cm-co">{m.company}</span>
                    {levelWord(m.level) ? <span className={`proj-tag-pill ${levelTag(m.level) || "neutral"}`}>{levelWord(m.level)}</span> : null}
                    <span className="cm-src">{m.source || "Source"}</span>
                  </div>
                  <div className="cm-title">{m.title}</div>
                  {m.description ? <div className="cm-desc">{m.description}</div> : null}
                  {m.changeNote ? <div className="cm-desc"><b>What changed: </b>{m.changeNote}</div> : null}
                  <Review src={m._src} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="proj-section-block">
            <table className="proj-data-table">
              <tbody>
                <tr><td className="proj-table-val">
                  No move by {co ? co.name : "any competitor"} in this window{co && co.all ? `, but ${co.all} earlier ${co.all === 1 ? "move is" : "moves are"} on record` : ""}.{" "}
                  <button type="button" className="cm-chip on" onClick={() => setPreset("all")}>Show all dates</button>
                </td></tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
      {open ? (() => {
        const [meaning] = String(open.analysis || "").split(/\s*Action:\s*/);
        const lenses = Array.isArray(open.lenses) && open.lenses.length ? open.lenses : null;
        const dir = levelTag(open.level) || undefined;   // no stored level, no stance class
        const chips = srcChips(sourceHref(open.url) ? [{ label: open.source || "Source", url: open.url }] : null);
        return (
          <div className="ctx v-overview revealed">
            <div className="ctx-scroll">
              <div className={dir ? `ctx-h dir-${dir}` : "ctx-h"}>
                <div className="ctx-h-actions">
                  <button aria-label="Close" className="col-close" onClick={() => setSel(null)} title="Close" type="button">✕</button>
                </div>
                <div className="ct" style={{ paddingRight: "40px" }}>{open.title}</div>
                <div className="sub" style={{ marginTop: "8px" }}>{[open.company, formatDate(open.date)].filter(Boolean).join(" · ")}</div>
                <Review src={open._src} />
              </div>
              {sourceHref(open.image) || /^(product|news)-images\//.test(open.image || "") ? (
                <div className="ctx-sec">
                  <Thumb src={open.image} alt="" caption={open.source || ""} style={{ width: "100%", aspectRatio: "16 / 9", borderRadius: "6px", display: "block" }} />
                </div>
              ) : null}
              <div className="ctx-sec">
                <span className="eyebrow">At a glance</span>
                <div className="cd-facts">
                  {[["Company", open.company], ["Date", formatDate(open.date)], ["Category", open.category], ["Country", open.country], ["Source", open.source]]
                    .filter((f) => f && f[1])
                    .map(([k, v]) => (
                      <div className="cd-frow" key={k}>
                        <span className="cd-fline"><span className="cd-fk">{k}</span><span className="cd-fv">{v}</span></span>
                      </div>
                    ))}
                </div>
              </div>
              <div className="ctx-sec">
                <span className="eyebrow">What happened</span>
                <div className="cd-prose">{open.description || "Not on record"}</div>
              </div>
              {open.changeNote ? (
                <div className="ctx-sec">
                  <span className="eyebrow">What changed since the previous move</span>
                  <div className="cd-prose">{open.changeNote}</div>
                </div>
              ) : null}
              {Array.isArray(open.steps) && open.steps.length > 1 ? (
                <div className="ctx-sec">
                  <span className="eyebrow">Story so far</span>
                  <ol className="pj-time">
                    {open.steps.filter((t) => t.type !== "label_change").map((t, i) => (
                      <li key={i}>
                        <span className="pj-d">{formatDate(t.date) || NO_DATE_LABEL}</span>
                        <span className="pj-e">{t.line}{t.changed ? ` (${t.changed})` : ""}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
              <div className="ctx-sec">
                <span className="eyebrow">Analysis{clientName ? ` · what it means for ${clientName}` : ""}</span>
                <div className="cd-prose">{meaning || "Not assessed."}</div>
              </div>
              {lenses ? (
                <div className="ctx-sec">
                  <span className="eyebrow">Deeper analysis · by view</span>
                  {lenses.map((l) => (
                    <div key={l.view} style={{ marginTop: "16px" }}>
                      <div style={{ display: "block", width: "100%", fontFamily: "var(--mono)", fontSize: "11px", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--l-txt-2)", margin: "0 0 5px" }}>{l.view}</div>
                      <div className="cd-prose">{l.text}</div>
                    </div>
                  ))}
                </div>
              ) : null}
              {chips ? (
                <div className="ctx-sec">
                  <span className="eyebrow">Source</span>
                  <div dangerouslySetInnerHTML={{ __html: chips }} style={{ marginTop: "5px" }} />
                </div>
              ) : null}
            </div>
          </div>
        );
      })() : null}
    </div>
  );
}
