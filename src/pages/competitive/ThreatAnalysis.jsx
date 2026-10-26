import { useEffect, useMemo, useState } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { stanceOf, STANCE_WORD, MOMENT_PRESETS as PRESETS } from "../../lib/chrome";
import { competitorFullName } from "../../lib/companyNames";
import { categoryImage } from "../../lib/categoryImage";
import { formatDate } from "../../utils/formatDate";
import { NO_DATE_LABEL } from "../../lib/overview";
import Thumb from "../../components/thumb/Thumb.jsx";
import { Review } from "../../components/review/Review.jsx";
import DetailPanel from "../../components/detailPanel/DetailPanel";
import ErrorBoundary from "../../components/ErrorBoundary";

/* Competitor Movement (owner 2026-10-25): competitor -> EVENTS -> EPISODES -> side card.
   An event is a story (the signal prompt links every article into one: "Hanwha's XM1776 for the US Army"), an update is one
   threat or watch signal of that story, oldest first, and a click on an episode opens its signal card (DetailPanel). Only
   threat and watch signals (the owner's answer: analysed signals only); a story with one article is an event of one episode.
   Today / Week / Month count back from the REAL date, not from the newest move (owner: "make it live"), and a country filter
   narrows the events to where they happened (the card's "Where"). No "All competitors" row: a competitor is always picked. */
const DAY = 86400000;
const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
const dateOf = (s) => {
  const t = Date.parse(s || "");
  return Number.isFinite(t) ? t : 0;
};
const ALL = "__all";
const glanceOf = (det, key) => ((det && det.glance) || []).find((g) => String(g[0]).toLowerCase() === key);

export default function ThreatAnalysis() {
  const { setScope } = useAppState();
  const { data } = useData();
  const [selectedCid, setSelectedCid] = useState(null);
  const [search, setSearch] = useState("");
  const [preset, setPreset] = useState("all");
  const [custom, setCustom] = useState({ from: "", to: "" });
  const [country, setCountry] = useState(ALL);
  const [openEvent, setOpenEvent] = useState(null);
  const [sel, setSel] = useState(null);

  /* every threat / watch signal as an episode, with its country and story */
  const episodes = useMemo(() => (data.competitiveCards || [])
    .filter((c) => stanceOf(c.classification || c.dir))
    .map((c) => {
      const det = (data.details || {})[c.id];
      const where = glanceOf(det, "where");
      return { ...c, stance: stanceOf(c.classification || c.dir), country: where ? String(where[1]) : "", det,
               story: (det && det.story) || null, date: c.eventDate || c.ago };
    }), [data]);

  // the window as dates, counted back from today (the real date)
  const today = useMemo(() => {
    const d = new Date();
    return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  }, []);
  const range = useMemo(() => {
    if (preset === "custom") return custom;
    const days = (PRESETS.find((p) => p[0] === preset) || [])[2];
    return days == null ? { from: "", to: "" } : { from: iso(today - days * DAY), to: iso(today) };
  }, [preset, custom, today]);
  const inRange = (e) => {
    const t = dateOf(e.date);
    return t >= (range.from ? Date.parse(range.from) : -Infinity) && t <= (range.to ? Date.parse(range.to) + DAY - 1 : Infinity);
  };
  // no future date (functional test G12): a typed date past today is cut back to today
  const setDate = (k, v) => { setCustom({ ...range, [k]: v && v > iso(today) ? iso(today) : v }); setPreset("custom"); };

  /* events per competitor: the episodes of one story, oldest first; the event's stance is its latest episode's */
  const roster = useMemo(() => {
    const byCo = new Map();
    for (const e of episodes) {
      if (!e.companyId) continue;
      const co = byCo.get(e.companyId) || { cid: e.companyId, name: competitorFullName(e.companyId, e.company, data.competitors) || e.company, events: new Map() };
      const key = e.storyId || e.id;
      const ev = co.events.get(key) || { id: key, title: (e.story && e.story.title) || "", eps: [] };
      ev.eps.push(e);
      co.events.set(key, ev);
      byCo.set(e.companyId, co);
    }
    return [...byCo.values()].map((co) => ({
      ...co,
      events: [...co.events.values()].map((ev) => {
        const eps = ev.eps.sort((a, b) => dateOf(a.date) - dateOf(b.date));
        const last = eps[eps.length - 1];
        /* the event's summary: what its latest article says (one article = the whole event); ponytail: a story-level
           summary written by a prompt would read better for multi-update events */
        const summary = (last.det && (last.det.summary || last.det.what)) || last.sowhat || "";
        return { ...ev, eps, last, summary, title: ev.title || last.title, first: eps[0].date, end: last.date, stance: last.stance,
                 countries: [...new Set(eps.map((x) => x.country).filter(Boolean))] };
      }),
    }));
  }, [episodes, data.competitors]);

  /* the filters applied: an event stays when one of its episodes is in the window (and in the country) */
  const filtered = useMemo(() => roster.map((co) => ({
    ...co,
    shown: co.events
      .map((ev) => ({ ...ev, eps: ev.eps.filter((x) => inRange(x) && (country === ALL || x.country === country)) }))
      .filter((ev) => ev.eps.length)
      .sort((a, b) => dateOf(b.eps[b.eps.length - 1].date) - dateOf(a.eps[a.eps.length - 1].date)),
  })).sort((a, b) => b.shown.length - a.shown.length || b.events.length - a.events.length || a.name.localeCompare(b.name)),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [roster, range, country]);
  const countries = useMemo(() => [...new Set(episodes.map((e) => e.country).filter(Boolean))].sort(), [episodes]);
  const list = useMemo(() => {
    const q = search.toLowerCase().trim();
    return q ? filtered.filter((r) => r.name.toLowerCase().includes(q)) : filtered;
  }, [filtered, search]);
  const co = filtered.find((r) => r.cid === selectedCid) || filtered[0] || null;
  const events = co ? co.shown : [];
  const openDetail = sel ? (data.details || {})[sel] || null : null;

  useEffect(() => {
    setScope("competitive", { events: events.length, competitor: co ? co.cid : null }, {
      pillar: "Competitive",
      view: "Competitor Movement",
      selection: co ? co.name : "",
    });
  }, [events.length, co, setScope]);

  const report = useMemo(() => ({
    title: `${co ? co.name : "Competitor"}: competitor movement`,
    subtitle: `${events.length} event${events.length === 1 ? "" : "s"} ${range.from ? `from ${range.from} to ${range.to}` : "on record"}`,
    sections: events.map((ev) => ({
      heading: ev.title,
      facts: ev.eps.map((x) => [[x.date, STANCE_WORD[x.stance]].filter(Boolean).join(" · "), x.title]),
    })),
    payload: { competitor: co ? co.cid : null, events: events.map((ev) => ({ id: ev.id, title: ev.title, signals: ev.eps.map((x) => x.id) })) },
  }), [co, events, range]);
  useHeaderReport(report);

  if (!roster.length) return <div className="empty-note">No competitor movements on record.</div>;

  const pill = (stance) => (STANCE_WORD[stance] ? <span className={`proj-tag-pill ${stance}`}>{STANCE_WORD[stance]}</span> : null);
  const span = (ev) => {
    const a = formatDate(ev.first), b = formatDate(ev.end);
    return a && b && a !== b ? `${a} – ${b}` : b || a || NO_DATE_LABEL;
  };

  return (
    <div className="pos-view v-projects" style={{ gridTemplateColumns: openDetail ? "300px minmax(0, 1fr) 440px" : "300px 1fr" }}>
      <div className="mu-list">
        <div className="mu-list-h">
          <div className="proj-sidebar-h">
            <span className="eyebrow">Competitors ({list.length})</span>
          </div>
          <div className="mu-search" style={{ marginTop: "10px" }}>
            <span className="si">⌕</span>
            <input type="text" placeholder="Search competitor…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="mu-fsel" value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Filter events by country"
            style={{ width: "100%", marginTop: "8px" }}>
            <option value={ALL}>All countries ({countries.length})</option>
            {countries.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div id="patc-list">
          {list.map((r) => (
            <div
              key={r.cid}
              className={`pat-li${co && r.cid === co.cid ? " active" : ""}`}
              onClick={() => { setSelectedCid(r.cid); setOpenEvent(null); setSel(null); }}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedCid(r.cid); setOpenEvent(null); setSel(null); } }}
              role="button"
              tabIndex={0}
            >
              <span className="pli-n" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</span>
                <span className="pli-ct" title={`${r.shown.length} events in this window, ${r.events.length} on record`}>{r.shown.length}</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="proj-main" style={{ overflowY: "auto", padding: "22px 28px 40px" }}>
        <div className="proj-co-header">
          <div className="proj-co-title-group">
            <span className="proj-co-eyebrow">Competitor Movement</span>
            <h1 className="proj-co-name">{co ? co.name : ""}</h1>
            <div className="proj-co-sub">
              <span>{events.length} {events.length === 1 ? "event" : "events"} in this window · {events.filter((ev) => ev.stance === "threat").length} a threat</span>
            </div>
          </div>
        </div>

        <div className="cm-bar">
          <div className="cm-chips" role="group" aria-label="Time window">
            {PRESETS.map(([id, text]) => (
              <button key={id} type="button" className={`cm-chip${preset === id ? " on" : ""}`} aria-pressed={preset === id} onClick={() => setPreset(id)}>{text}</button>
            ))}
          </div>
          <label className="cm-date">From <input type="date" value={range.from} max={range.to || iso(today)} onChange={(e) => setDate("from", e.target.value)} /></label>
          <label className="cm-date">To <input type="date" value={range.to} min={range.from || undefined} max={iso(today)} onChange={(e) => setDate("to", e.target.value)} /></label>
        </div>

        {events.length ? (
          <div className="cm-list">
            {events.map((ev) => {
              const isOpen = openEvent === ev.id;
              return (
                <div key={ev.id} className={`ev-block${isOpen ? " open" : ""}`}>
                  <div
                    className="ev-row"
                    onClick={() => setOpenEvent(isOpen ? null : ev.id)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpenEvent(isOpen ? null : ev.id); } }}
                    role="button"
                    tabIndex={0}
                    aria-expanded={isOpen}
                  >
                    <span className="ev-caret" aria-hidden="true">▸</span>
                    <div className="ev-main">
                      <div className="ev-title">{ev.title}</div>
                      {ev.summary ? <div className="ev-sum">{ev.summary}</div> : null}
                      <div className="ev-sub">
                        {[span(ev), `${ev.eps.length} ${ev.eps.length === 1 ? "update" : "updates"}`, ev.countries.join(", ")].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                    {pill(ev.stance)}
                  </div>
                  {isOpen ? (
                    <div className="ev-eps">
                      {ev.eps.map((x) => (
                        <div
                          key={x.id}
                          className={`cm-row${sel === x.id ? " sel" : ""}`}
                          onClick={() => setSel(x.id)}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSel(x.id); } }}
                          role="button"
                          tabIndex={0}
                          title="Open the signal"
                        >
                          <div className="cm-left">
                            <Thumb src={x.image || categoryImage(x.meta)} alt="" className="cm-img" caption="" />
                            <div className="cm-when">
                              <b>{formatDate(x.date) || NO_DATE_LABEL}</b>
                              {[x.meta, x.country].filter(Boolean).join(" · ")}
                            </div>
                          </div>
                          <div className="cm-main">
                            <div className="cm-top">
                              <span className="cm-co">Update</span>
                              <span className="cm-tag">{pill(x.stance)}</span>
                            </div>
                            <div className="cm-title">{x.title}</div>
                            {x.sowhat || x.ksslImpact ? <div className="cm-desc">{x.sowhat || x.ksslImpact}</div> : null}
                            <Review src={x._src} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="proj-section-block">
            <table className="proj-data-table">
              <tbody>
                <tr><td className="proj-table-val">
                  No event for {co ? co.name : "this competitor"} in this window{co && co.events.length ? `; ${co.events.length} on record` : ""}.{" "}
                  <button type="button" className="cm-chip on" onClick={() => { setPreset("all"); setCountry(ALL); }}>Show all</button>
                </td></tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openDetail ? (
        <ErrorBoundary label="signal detail">
          <DetailPanel detail={openDetail} onClose={() => setSel(null)} />
        </ErrorBoundary>
      ) : null}
    </div>
  );
}
