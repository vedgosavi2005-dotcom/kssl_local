import { useEffect, useMemo, useState } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { buildProfile, rosterOf } from "../../lib/profile";
import { revenueOptions } from "../../lib/revenueFacet";
import { companyNews, NEWS_MAX, NEWS_WINDOWS, NEWS_WINDOW_DEFAULT, windowDays, withinWindow, capNews } from "../../lib/news";
import { facetOptionsByName } from "../../lib/countryFacet";
import { formatDate } from "../../utils/formatDate.js";
import Thumb from "../../components/thumb/Thumb.jsx";
import { Review } from "../../components/review/Review.jsx";
/* The article card is the link: a news item goes to the news source (see ArticleLink). */
import { ArticleLink } from "../../components/sourceLink/SourceLink.jsx";
/* A SELECTION IS REMEMBERED WHILE YOU STAY IN THIS PILLAR, not for ever. See lib/viewState. */
import * as viewState from "../../lib/viewState";

/* The dot beside a competitor: its stored threat_level (threat | watch | fav). Any other
   stored value has no colour; the stored text is the tooltip. */
const DOT = { threat: "threat", watch: "watch", fav: "fav" };

// Initials for the avatar: the stored avatar_initials, else the first letters of the first and last word of the name
const getInitials = (name, stored) => {
  if (stored) return stored;
  const clean = String(name || "").replace(/^(Mr\.|Ms\.|Dr\.|Shri|Prof\.|Commodore|Cdre\.|Retd)\s+/i, "").trim();
  if (!clean) return "";
  const parts = clean.split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  return parts[0].slice(0, 2).toUpperCase();
};

/* ONE EXECUTIVE, FULL PAGE. Opened from a Leadership card; replaces the profile in the
   right-hand column until "Back". Every section prints only what the stored leader rows
   carry (competitive_leader + competitive_leader_record) and says so plainly when a
   section has nothing -- no career is inferred from a job title. */
const yearOf = (v) => {
  const m = String(v == null ? "" : v).match(/(19|20)\d{2}/);
  return m ? Number(m[0]) : null;
};
const isPresent = (v) => v == null || v === "" || /present|current|now/i.test(String(v));
// "2018 – Present · 8 yrs": a computed presentation of the stored start / end dates (end empty = present)
export function tenureText(from, to, now = new Date().getFullYear()) {
  const a = yearOf(from);
  const b = isPresent(to) ? now : yearOf(to);
  // a year the source did not state is left out, never shown as "?"
  if (!a) return isPresent(to) ? "Present" : b ? `Until ${b}` : "";
  const span = `${a} – ${isPresent(to) ? "Present" : b || ""}`;
  if (!b || b < a) return span;
  const n = b - a;
  return `${span} · ${n < 1 ? "under 1 yr" : `${n} yr${n === 1 ? "" : "s"}`}`;
}

function LeaderPage({ leader, companyName, companyArticles, onBack }) {
  const exp = leader.experience || [];
  const edu = leader.education || [];
  // current position: the experience record with no end date; else the leader's stored role + organisation
  const current = exp.find((e) => isPresent(e.to)) || null;
  const nowRole = current ? current.role : leader.role;
  const nowOrg = current ? current.org : leader.org;

  /* NEWS NAMING THIS PERSON: the company's articles whose headline contains the leader's full
     name. No other article is offered as related; with none, the section is not shown. */
  const leaderNews = useMemo(() => {
    const full = String(leader.name || "").trim().toLowerCase();
    return full ? (companyArticles || []).filter((a) => String(a.title || "").toLowerCase().includes(full)) : [];
  }, [leader, companyArticles]);

  const sourceLinks = [["Role", leader.url], ["Career & education", [...exp, ...edu].map((r) => r.url).find(Boolean)]]
    .filter(([, u], i, arr) => u && arr.findIndex(([, v]) => v === u) === i);

  return (
    <div className="cp-person">
      <button type="button" className="cp-person-back" onClick={onBack}>
        ← Back to {companyName}
      </button>
      <div className="cp-person-head">
        <PersonAvatar name={leader.name} initials={leader.initials} className="cp-person-avatar" />
        <div>
          <h1 className="cp-person-name">{leader.name}</h1>
          <Review src={leader._src} />
          <div className="cp-person-now">
            {leader.role}
            {nowOrg ? <span className="cp-person-at"> · {nowOrg}</span> : null}
          </div>
        </div>
      </div>

      {nowRole || nowOrg ? (
        <section className="cp-person-sec">
          <h2 className="cp-person-h">Current Position</h2>
          <div className="cp-person-row">
            <div className="cp-person-row-main">
              <span className="cp-person-role">{nowRole}</span>
              <span className="cp-person-org">{nowOrg}</span>
            </div>
            {current ? <span className="cp-person-when">{tenureText(current.from, current.to)}</span> : null}
          </div>
        </section>
      ) : null}

      <section className="cp-person-sec">
        <h2 className="cp-person-h">Professional Experience</h2>
        {exp.length ? (
          <div className="cp-person-list">
            {exp.map((e, i) => (
              <div className="cp-person-row" key={e.id || `${e.org}-${e.role}-${i}`}>
                <span className="cp-person-dot" />
                <div className="cp-person-row-main">
                  <span className="cp-person-role">{e.role}</span>
                  <span className="cp-person-org">{e.org}</span>
                </div>
                <span className="cp-person-when">{tenureText(e.from, e.to)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="cp-thin">No career history on public record.</div>
        )}
      </section>

      <section className="cp-person-sec">
        <h2 className="cp-person-h">Education</h2>
        {edu.length ? (
          <div className="cp-person-list">
            {edu.map((e, i) => (
              <div className="cp-person-row" key={e.id || `${e.org}-${i}`}>
                <span className="cp-person-dot" />
                <div className="cp-person-row-main">
                  <span className="cp-person-role">{e.role}</span>
                  <span className="cp-person-org">{e.org}</span>
                </div>
                {e.from || e.to ? <span className="cp-person-when">{tenureText(e.from, e.to).split(" · ")[0]}</span> : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="cp-thin">No education on public record.</div>
        )}
      </section>

      {leaderNews.length ? (
        <section className="cp-person-sec">
          <h2 className="cp-person-h">News Related to {leader.name}</h2>
          <div className="cp-person-list">
            {leaderNews.map((item, idx) => (
              <ArticleLink
                article={item}
                key={item.id || idx}
                className="cp-person-row cp-lead-card-link"
                style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
              >
                <span className="cp-person-dot" />
                <div className="cp-person-row-main">
                  <span className="cp-person-role" style={{ fontSize: "13.5px" }}>{item.title}</span>
                  <span className="cp-person-org" style={{ fontSize: "11.5px" }}>
                    {[item.source, item.category].filter(Boolean).join(" · ")}
                  </span>
                </div>
                <span className="cp-person-when">{item.ago}</span>
              </ArticleLink>
            ))}
          </div>
        </section>
      ) : null}

      {sourceLinks.length ? (
        <div className="cp-person-src" style={{ marginTop: "24px" }}>
          {sourceLinks.map(([label, u]) => (
            <div key={label}>{label}: <a href={u} target="_blank" rel="noopener noreferrer">{u}</a></div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* A person's avatar: their initials (competitive_leader has no photo column). */
function PersonAvatar({ name, initials, className }) {
  return <div className={`cp-avatar ${className || ""}`}>{getInitials(name, initials)}</div>;
}

const DASH = "—";

/* One labelled row of the Company Details box. */
const ROW_STYLE = { display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", borderBottom: "1px solid var(--d-line)", fontSize: "13px", alignItems: "center" };
const LABEL_STYLE = { fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap" };
function MetaRow({ label, children, top }) {
  return (
    <div style={{ ...ROW_STYLE, alignItems: top ? "start" : "center" }}>
      <span style={{ ...LABEL_STYLE, paddingTop: top ? "3px" : undefined }}>{label}</span>
      {children}
    </div>
  );
}
const VALUE_STYLE = { color: "var(--d-txt)", fontWeight: "600" };

function Sec({ title, actions, children }) {
  return (
    <div className="cp-sec">
      <div className="cp-sec-h">
        <span className="eyebrow" style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
          {typeof title === "string" ? title.toUpperCase() : title}
        </span>
        {actions ? <div className="cp-sec-actions">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}

const UNKNOWN_ORIGIN = "Origin not established";
const NO_TIER = "__no_tier";
const PROFILE_KEY = "kssl_profile_cid";

export default function Profile() {
  const { data } = useData();
  const { setScope, takePending, searchQuery } = useAppState();
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("all");
  const [revenue, setRevenue] = useState("all");
  const roster = useMemo(() => rosterOf(data), [data]);
  /* The origin filter: the stored origin_country of each company, with how many rows carry
     it. A company with no stored origin is listed under its own option rather than dropped. */
  const countryOptions = useMemo(
    () => facetOptionsByName(roster, (r) => [r.origin || UNKNOWN_ORIGIN]),
    [roster],
  );
  /* The revenue filter: the stored revenue_tier text, as stored. Companies with no stored tier
     get a neutral bucket, offered only when at least one tier exists. */
  const revenueOpts = useMemo(() => {
    const opts = revenueOptions(roster);
    const none = roster.filter((r) => !r.revenueTier).length;
    return opts.length && none ? opts.concat([{ v: NO_TIER, n: none, l: "Revenue not on record" }]) : opts;
  }, [roster]);
  /* The selected competitor is remembered while the pillar stays open; a saved id that the
     served roster no longer carries falls back to the first row. */
  const [cid, setCidState] = useState(() => {
    try {
      const saved = viewState.getItem(PROFILE_KEY);
      if (saved && roster.some((r) => r.cid === saved)) return saved;
    } catch (e) {}
    return roster[0] ? roster[0].cid : "";
  });
  const setCid = (next) => {
    setCidState(next);
    try {
      if (next) viewState.setItem(PROFILE_KEY, next);
      else viewState.removeItem(PROFILE_KEY);
    } catch (e) {}
  };

  /* Opened from global search targeting one company. */
  useEffect(() => {
    const pend = takePending("profile");
    if (pend && pend.cid && data.competitors && data.competitors[pend.cid]) {
      setCid(pend.cid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takePending, data.competitors]);

  // News category pill: "" = all
  const [newsFilter, setNewsFilter] = useState("");
  // the Leadership card opened as a full page in the right column (leader object), or null
  const [selectedLeader, setSelectedLeader] = useState(null);
  useEffect(() => { setSelectedLeader(null); }, [cid]);
  // opening or closing a person starts that page at its top
  useEffect(() => {
    let el = document.querySelector(".v-profile .cp-body");
    while (el) { el.scrollTop = 0; el = el.parentElement; }
  }, [selectedLeader]);
  /* How far back counts as current: the reader's choice, see lib/news.NEWS_WINDOWS. */
  const [newsWindow, setNewsWindow] = useState(NEWS_WINDOW_DEFAULT);
  const [showAllNews, setShowAllNews] = useState(false);
  /* The full NEWS list's own filters: a keyword and a date window. */
  const [listQ, setListQ] = useState("");
  const [listRange, setListRange] = useState("all");   // all | 7d | 30d | 3m | 6m | 12m | custom
  const [listFrom, setListFrom] = useState("");
  const [listTo, setListTo] = useState("");
  useEffect(() => { setListQ(""); setListRange("all"); setListFrom(""); setListTo(""); setShowAllNews(false); }, [cid]);

  const list = useMemo(() => {
    const q = (query || searchQuery || "").trim().toLowerCase();
    const tokens = q.split(/\s+/).filter(Boolean);
    return roster.filter((r) => {
      if (country !== "all" && (r.origin || UNKNOWN_ORIGIN) !== country) return false;
      if (revenue !== "all" && (revenue === NO_TIER ? !!r.revenueTier : r.revenueTier !== revenue)) return false;
      if (!tokens.length) return true;
      const fullText = `${r.name} ${r.short || ""} ${r.legal || ""} ${r.sector || ""} ${r.hq || ""} ${r.cid}`.toLowerCase();
      return tokens.every((tok) => fullText.includes(tok));
    });
  }, [roster, query, searchQuery, country, revenue]);

  const p = useMemo(() => (cid ? buildProfile(data, cid) : null), [data, cid]);
  const displayName = p ? p.name : "";

  /* LIVE company pulse -- trending headlines (Google News), fetched server-side via
     /api/pulse. The one live, non-DB element (by decision); shown in its own block, never
     mixed with the stored news. null-safe so a dead feed never breaks the page. */
  const [pulse, setPulse] = useState(null);
  useEffect(() => {
    if (!p || !p.cid) { setPulse(null); return; }
    let cancelled = false;
    setPulse({ loading: true });
    fetch(`/api/pulse?cid=${encodeURIComponent(p.cid)}&name=${encodeURIComponent(p.name || "")}`)
      .then((r) => r.json())
      .then((j) => { if (!cancelled) setPulse(j || {}); })
      .catch(() => { if (!cancelled) setPulse({ trending: [] }); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p && p.cid]);
  const liveHeadlines = pulse && Array.isArray(pulse.trending) ? pulse.trending.filter((t) => t && t.title) : [];

  useEffect(() => {
    if (!p) return;
    setScope("profile", { company: p.name, cid: p.cid }, {
      pillar: "Competitive",
      view: "Competitor Profile",
      selection: displayName || p.name,
    });
  }, [p, displayName, setScope]);

  // Reset the news filter when switching company
  useEffect(() => {
    setNewsFilter("");
  }, [cid]);

  const leaders = p ? p.leaders : [];

  /* Memoised because the header report below depends on it. */
  const companyArticles = useMemo(
    () => (p && p.cid ? companyNews(data, p.cid) : []),
    [data, p],
  );

  /* Categories offered as pills: the distinct stored categories of this company's articles
     (none are offered when no article carries one). */
  const categories = useMemo(
    () => Array.from(new Set(companyArticles.map((a) => a.category).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [companyArticles],
  );

  /* WINDOW, THEN CATEGORY, THEN CAP -- in that order, and the order matters. */
  const windowedArticles = useMemo(
    () => withinWindow(companyArticles, windowDays(newsWindow)),
    [companyArticles, newsWindow],
  );
  const filteredArticles = useMemo(
    () => capNews(newsFilter ? windowedArticles.filter((a) => a.category === newsFilter) : windowedArticles, NEWS_MAX),
    [windowedArticles, newsFilter],
  );

  /* What the header's Copy / Export / Print act on: this company's profile as shown. */
  const report = useMemo(() => {
    if (!p) return null;
    const details = [
      p.legal && p.legal !== p.name ? ["Legal name", p.legal] : null,
      p.short && p.short !== p.name ? ["Short name", p.short] : null,
      ["Starting year", p.starting_year ? String(p.starting_year) : DASH],
      ["Headquarters", p.hq || DASH],
      ["Global locations", p.locations.length ? p.locations.map((l) => l.name).join(", ") : p.global_locations || DASH],
      ["Company size", p.company_size || DASH],
      ["Annual revenue / sales", p.revenue || DASH],
      ["Industry / sector", p.sector || DASH],
    ].filter(Boolean);
    return {
      title: displayName,
      subtitle: "Competitor profile",
      sections: [
        { h: "Company details", rows: details },
        {
          h: "Leadership",
          rows: leaders.length
            ? leaders.map((l) => [l.name, l.role])
            : ["No executive officers published on public record."],
        },
        {
          h: `Company latest news (${companyArticles.length})`,
          rows: companyArticles.map((a) => [a.title, [a.source, a.ago, a.category].filter(Boolean).join(" · ")]),
        },
      ],
      payload: {
        cid: p.cid,
        name: displayName,
        details: {
          legalName: p.legal || null,
          shortName: p.short || null,
          startingYear: p.starting_year || null,
          hq: p.hq || null,
          globalLocations: p.locations.map((l) => l.name),
          companySize: p.company_size,
          revenue: p.revenue || null,
          revenueTier: (data.competitors[p.cid] || {}).revenue_tier || null,
          sector: p.sector || null,
        },
        leadership: leaders.map((l) => ({ name: l.name, role: l.role, source: l.url || null })),
        news: companyArticles.map((a) => ({
          title: a.title,
          source: a.source || null,
          date: a.date || null,
          category: a.category || null,
          url: a.url || null,
        })),
      },
    };
  }, [p, displayName, leaders, companyArticles, data.competitors]);
  useHeaderReport(report);

  /* The full NEWS list, narrowed by its own keyword + date filters. A date filter can only
     keep an article whose date is known. */
  const newsListDated = listRange !== "all";
  const listRows = useMemo(() => {
    const days = { "7d": 7, "30d": 30, "3m": 91, "6m": 182, "12m": 365 }[listRange];
    const since = days ? new Date(Date.now() - days * 86400000).toISOString().slice(0, 10) : null;
    const toks = listQ.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return (companyArticles || []).filter((item) => {
      const d = String(item.date || "").slice(0, 10);
      if (listRange !== "all" && !d) return false;
      if (since && d < since) return false;
      if (listRange === "custom" && ((listFrom && d < listFrom) || (listTo && d > listTo))) return false;
      if (toks.length) {
        const hay = `${item.title} ${item.category || ""} ${item.source || ""}`.toLowerCase();
        if (!toks.every((t) => hay.includes(t))) return false;
      }
      return true;
    });
  }, [companyArticles, listQ, listRange, listFrom, listTo]);

  return (
    <div className="pos-view v-profile" style={{ gridTemplateColumns: "300px 1fr" }}>
      {/* 1. LEFT SIDEBAR: COMPETITORS LIST */}
      <div className="mu-list">
        <div className="mu-list-h">
          <span className="eyebrow">Competitors</span>
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
            aria-label="Filter competitors by country of origin"
            className="mu-fsel"
            onChange={(e) => setCountry(e.target.value)}
            style={{ width: "100%", marginTop: "8px" }}
            value={country}
          >
            <option value="all">All origins ({countryOptions.length})</option>
            {countryOptions.map((o) => (
              <option key={o.v} value={o.v}>
                {o.v} ({o.n})
              </option>
            ))}
          </select>
          {revenueOpts.length ? (
            <select
              aria-label="Filter competitors by revenue"
              className="mu-fsel"
              onChange={(e) => setRevenue(e.target.value)}
              style={{ width: "100%", marginTop: "8px" }}
              value={revenue}
            >
              <option value="all">All revenue tiers ({revenueOpts.length})</option>
              {revenueOpts.map((o) => (
                <option key={o.v} value={o.v}>
                  {o.l} ({o.n})
                </option>
              ))}
            </select>
          ) : null}
        </div>
        <div id="patc-list">
          {list.map((r) => (
            <div
              className={`pat-li${cid === r.cid ? " active" : ""}`}
              key={r.cid}
              onClick={() => {
                setCid(r.cid);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setCid(r.cid);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <span className="pli-n" style={{ display: "flex", alignItems: "center", gap: "8px", whiteSpace: "normal" }}>
                <span className={`wdot ${DOT[String(r.threat).toLowerCase()] || ""}`} title={r.threat || undefined} style={{ flexShrink: 0 }} />
                <span style={{ minWidth: 0, wordBreak: "break-word" }}>
                  <span>{r.name}</span>
                </span>
              </span>
            </div>
          ))}
          {!list.length ? (
            <div className="cp-empty">
              {query.trim() ? <>no competitor matches “{query}”</> : "no competitor matches this filter"}
            </div>
          ) : null}
        </div>
      </div>

      {/* 2. RIGHT PANE. A news item goes to the news source (ArticleLink); no in-app article window. */}
      <div className="cp-body" style={{ padding: "24px" }}>
        {!p ? (
          <div className="cp-empty">select a competitor</div>
        ) : selectedLeader ? (
          <LeaderPage
            leader={selectedLeader}
            companyName={displayName}
            companyArticles={companyArticles}
            onBack={() => setSelectedLeader(null)}
          />
        ) : (
          <>
            {/* 1. COMPANY NAME HEADER */}
            <div className="cp-head">
              <div className="cp-name">{displayName}</div>
              <Review src={p._src} />
            </div>

            {/* 2. COMPANY DETAILS: every value is a stored competitive_competitor column */}
            <Sec title="Company Details">
              <div
                className="cp-meta-rows"
                style={{
                  marginBottom: "20px",
                  display: "flex",
                  flexDirection: "column",
                  background: "var(--d-bg-1)",
                  border: "1px solid var(--d-line)",
                  borderRadius: "6px",
                  overflow: "hidden",
                }}
              >
                {p.legal && p.legal !== p.name ? (
                  <MetaRow label="Legal Name"><span style={VALUE_STYLE}>{p.legal}</span></MetaRow>
                ) : null}
                {p.short && p.short !== p.name ? (
                  <MetaRow label="Short Name"><span style={VALUE_STYLE}>{p.short}</span></MetaRow>
                ) : null}
                <MetaRow label="Starting Year"><span style={VALUE_STYLE}>{p.starting_year ? String(p.starting_year) : DASH}</span></MetaRow>
                <MetaRow label="Headquarters"><span style={VALUE_STYLE}>{p.hq || DASH}</span></MetaRow>
                <MetaRow label="Global Locations" top>
                  <span className="cp-loc-wrap">
                    {p.locations.length ? (
                      p.locations.map((l) => (
                        <span
                          className="cp-loc-chip"
                          key={l.id || l.name}
                          title={[l.type, l.country].filter(Boolean).join(" · ") || undefined}
                        >
                          {l.name}
                        </span>
                      ))
                    ) : (
                      <span style={VALUE_STYLE}>{p.global_locations || DASH}</span>
                    )}
                  </span>
                </MetaRow>
                <MetaRow label="Company Size"><span style={VALUE_STYLE}>{p.company_size || DASH}</span></MetaRow>
                <MetaRow label="Annual Revenue / Sales"><span style={VALUE_STYLE}>{p.revenue || DASH}</span></MetaRow>
                <div style={{ ...ROW_STYLE, borderBottom: "none" }}>
                  <span style={LABEL_STYLE}>Industry / Sector</span>
                  <span style={VALUE_STYLE}>{p.sector || DASH}</span>
                </div>
              </div>
            </Sec>

            {/* Strategic Positioning, Parallax Read and Strengths / Weaknesses are hidden by
                decision (2026-10-16); the columns exist but are not shown. */}

            {/* 3. LEADERSHIP (competitive_leader) */}
            <Sec title="Leadership">
              {leaders.length > 0 ? (
                <div className="cp-leadership-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "14px" }}>
                  {leaders.map((leader) => (
                    <div
                      className="cp-lead-card cp-lead-card-link"
                      key={leader.id}
                      role="button"
                      tabIndex={0}
                      title={`Open ${leader.name}'s profile`}
                      onClick={() => setSelectedLeader(leader)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedLeader(leader);
                        }
                      }}
                    >
                      <PersonAvatar name={leader.name} initials={leader.initials} />
                      <div className="cp-lead-info">
                        <span className="cp-lead-name">{leader.name}</span>
                        <span className="cp-lead-role">{leader.role}</span>
                        <Review src={leader._src} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="cp-thin" style={{ fontSize: "12px", padding: "8px 0" }}>
                  No executive officers published on public record.
                </div>
              )}
            </Sec>

            {/* 4. COMPANY LATEST NEWS (competitive_news_article) */}
            <Sec
              title={
                <span style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
                  <span className="ln-red-dot" style={{ flexShrink: 0 }} />
                  <span>COMPANY LATEST NEWS</span>
                </span>
              }
              actions={
                <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)" }}>
                    Published
                  </span>
                  <select
                    value={newsWindow}
                    onChange={(e) => setNewsWindow(e.target.value)}
                    aria-label="How far back to show news"
                    style={{
                      background: "var(--d-bg-2)",
                      color: "var(--d-txt)",
                      border: "1px solid var(--d-line)",
                      borderRadius: "6px",
                      padding: "5px 8px",
                      fontSize: "12px",
                      fontFamily: "var(--mono)",
                    }}
                  >
                    {NEWS_WINDOWS.map((w) => (
                      <option key={w.key} value={w.key}>{w.label}</option>
                    ))}
                  </select>
                </label>
              }
            >
              {!companyArticles.length ? (
                <div className="cp-thin" style={{ fontSize: "12px", padding: "8px 0" }}>
                  No news on record for {displayName}.
                </div>
              ) : (
                <div className="ln-dashboard" style={{ marginTop: "6px" }}>
                  {/* Category pills: the distinct stored categories, when any article carries one */}
                  {categories.length ? (
                    <div className="ln-pills" style={{ marginBottom: "14px" }}>
                      {[""].concat(categories).map((cat) => (
                        <button
                          key={cat || "all"}
                          type="button"
                          className={`ln-pill${newsFilter === cat ? " on" : ""}`}
                          onClick={() => setNewsFilter(cat)}
                        >
                          {cat || "All"}
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {filteredArticles.length ? (
                    <div className="ln-grid">
                      {filteredArticles.map((item, idx) => (
                        <div className="ln-feed-item" key={item.id || idx}>
                          <ArticleLink article={item} className="ln-feed-card">
                            {item.image ? <Thumb src={item.image} alt="" className="ln-feed-thumb" /> : null}
                            <div className="ln-feed-info">
                              <div className="ln-feed-meta">
                                {[item.category, item.ago].filter(Boolean).join(" · ")}
                              </div>
                              <div className="ln-feed-title">{item.title}</div>
                              {item.source ? <span className="ln-feed-src">{item.source}</span> : null}
                            </div>
                          </ArticleLink>
                          <Review src={item._src} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="cp-thin" style={{ fontSize: "12px", padding: "8px 0" }}>
                      No article matches this window{newsFilter ? ` and category` : ""}.
                    </div>
                  )}
                </div>
              )}

              {/* LIVE headlines: the one non-DB element, kept apart from the stored news above */}
              {liveHeadlines.length ? (
                <div className="ln-live" style={{ marginTop: "22px" }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: "11px", fontWeight: 700, letterSpacing: ".08em", color: "var(--d-txt-3)", textTransform: "uppercase", marginBottom: "8px" }}>
                    Live headlines (Google News, not reviewed)
                  </div>
                  {liveHeadlines.map((t, i) => (
                    <ArticleLink
                      article={{ url: t.url, source: t.source }}
                      className="ln-all-row"
                      key={`${t.url || t.title}-${i}`}
                      style={{ display: "flex", gap: "12px", padding: "8px 4px", borderBottom: "1px solid var(--d-line)", alignItems: "baseline" }}
                    >
                      <span style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", whiteSpace: "nowrap" }}>
                        {t.date ? formatDate(t.date) : ""}
                      </span>
                      <span style={{ fontSize: "13px", color: "var(--d-txt)", flex: 1, minWidth: 0 }}>{t.title}</span>
                      {t.source ? (
                        <span style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", whiteSpace: "nowrap" }}>{t.source}</span>
                      ) : null}
                    </ArticleLink>
                  ))}
                </div>
              ) : null}
            </Sec>

            {/* Company stock: removed by decision (stock is hidden; no live quotes). */}
            {/* 5. NEWS (LIST / TABULAR FORMAT) */}
            {companyArticles.length ? (
              <Sec
                title="News"
                actions={
                  <>
                    <div className="cp-news-search">
                      <svg className="si" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                        <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
                        <path d="M11 11 L14.5 14.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                      <input
                        type="text"
                        value={listQ}
                        onChange={(e) => setListQ(e.target.value)}
                        placeholder="Search news…"
                        aria-label="Search the news list"
                      />
                      {listQ ? <button type="button" className="cp-news-clear" onClick={() => setListQ("")} aria-label="Clear search">×</button> : null}
                    </div>
                    <select className="cp-news-range" value={listRange} onChange={(e) => setListRange(e.target.value)} aria-label="Filter the news list by date">
                      <option value="all">All dates</option>
                      <option value="7d">Last 7 days</option>
                      <option value="30d">Last 30 days</option>
                      <option value="3m">Last 3 months</option>
                      <option value="6m">Last 6 months</option>
                      <option value="12m">Last 12 months</option>
                      <option value="custom">Custom range…</option>
                    </select>
                    {listRange === "custom" ? (
                      <span className="cp-news-dates">
                        <input type="date" value={listFrom} max={listTo || undefined} onChange={(e) => setListFrom(e.target.value)} aria-label="From date" />
                        <span>to</span>
                        <input type="date" value={listTo} min={listFrom || undefined} onChange={(e) => setListTo(e.target.value)} aria-label="To date" />
                      </span>
                    ) : null}
                  </>
                }
              >
                <div id="all-company-news" style={{ marginTop: "10px" }}>
                  {!listRows.length ? (
                    <div className="cp-thin" style={{ padding: "16px 12px" }}>
                      No article matches{listQ.trim() ? <> “{listQ.trim()}”</> : null}{newsListDated ? " in this date range" : ""}.
                    </div>
                  ) : null}
                  {(showAllNews ? listRows : listRows.slice(0, 20)).map((item, idx) => (
                    <div key={item.id || `all-${idx}`}>
                    <ArticleLink
                      article={item}
                      className="ln-all-row"
                      style={{
                        display: "grid",
                        gridTemplateColumns: "110px 1fr 140px 220px",
                        gap: "16px",
                        alignItems: "center",
                        padding: "10px 14px",
                        borderBottom: "1px solid var(--d-line)",
                        background: idx % 2 === 0 ? "rgba(255, 255, 255, 0.015)" : "transparent",
                        textDecoration: "none",
                        color: "inherit",
                      }}
                    >
                      <span className="ln-row-date" style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", whiteSpace: "nowrap" }}>
                        {item.ago}
                      </span>
                      <span className="ln-row-title" style={{ fontSize: "13px", color: "var(--d-txt)", fontWeight: "500", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.title}
                      </span>
                      <span className="ln-row-cat" style={{ display: "flex", justifyContent: "center" }}>
                        {item.category ? (
                          <span
                            style={{
                              display: "inline-block",
                              padding: "3px 12px",
                              background: "var(--d-bg-2)",
                              border: "1px solid var(--d-line)",
                              borderRadius: "4px",
                              fontFamily: "var(--mono)",
                              fontSize: "11px",
                              color: "var(--d-txt-2)",
                              textAlign: "center",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {item.category}
                          </span>
                        ) : null}
                      </span>
                      <span className="ln-row-url" style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.source}
                      </span>
                    </ArticleLink>
                    <Review src={item._src} style={{ margin: "0 14px 6px" }} />
                    </div>
                  ))}
                </div>
                {!showAllNews && listRows.length > 20 ? (
                  <button
                    type="button"
                    onClick={() => setShowAllNews(true)}
                    style={{
                      width: "100%",
                      padding: "10px",
                      marginTop: "10px",
                      background: "var(--d-bg-2)",
                      border: "1px solid var(--d-line)",
                      borderRadius: "6px",
                      color: "var(--d-txt-2)",
                      fontFamily: "var(--mono)",
                      fontSize: "12px",
                      cursor: "pointer",
                    }}
                  >
                    Show the remaining {listRows.length - 20}
                  </button>
                ) : null}
              </Sec>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
