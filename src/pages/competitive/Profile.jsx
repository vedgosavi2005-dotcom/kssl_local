import { proxied, thumbUsable } from "../../components/thumb/Thumb.jsx";
import { revenueOptions } from "../../lib/revenueFacet";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { buildProfile, rosterOf, formatSectorName } from "../../lib/profile";
import { companyNews, FEED_N, collapseThreads,
         NEWS_MAX, NEWS_WINDOWS, NEWS_WINDOW_DEFAULT, NEWS_LIST_RANGES, windowDays, withinWindow, capNews, newsDate } from "../../lib/news";
import { facetOptionsByName, tidyHq } from "../../lib/countryFacet";
import { INDEX, INDEX_NOTE } from "../../lib/articleUrl";
import Thumb from "../../components/thumb/Thumb.jsx";
/* SourceLink and SourceChip are no longer imported here. They rendered the publisher as
   its own <a>, which was right while the CARD opened an in-app panel and the chip was the
   only way out to the publisher. Now the card is that link, so a chip inside it would be
   an anchor inside an anchor -- invalid, and resolved by browsers in a way that kills the
   rest of the card. Both are still exported and still used by the pages that have no
   whole-row link. */
import { ArticleLink } from "../../components/sourceLink/SourceLink.jsx";
import { isVisible } from "../../lib/visibility";
import { competitorFullName } from "../../lib/companyNames";
/* A SELECTION IS REMEMBERED WHILE YOU STAY IN THIS PILLAR, not for ever. This page
   persisted to localStorage, which survives the tab, the browser and the machine's
   next reboot -- so a company opened once was still the landing selection weeks
   later, on a dashboard whose job is "what is new". Same key/value shape, held in
   memory, cleared on a pillar change. See lib/viewState. */
import * as viewState from "../../lib/viewState";
import { Review } from "../../components/review/Review.jsx";

// Helper function to extract clean company short name without full form or legal suffixes
const cleanCompanyName = (rawName) => {
  if (!rawName) return "";
  let name = rawName.split("(")[0].split("-")[0].trim();
  name = name.replace(/,?\s*(Private|Pvt|Limited|Ltd|Inc|Corp|Corporation)\b.*/gi, "").trim();
  return name || rawName;
};

// Helper function to extract executive initials for avatar
const getInitials = (name) => {
  if (!name) return "EX";
  const clean = name.replace(/^(Mr\.|Ms\.|Dr\.|Shri|Prof\.|Commodore|Cdre\.|Retd)\s+/i, "").trim();
  const parts = clean.split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  return parts[0].slice(0, 2).toUpperCase();
};

const fmtNewsDate = (item) => {
  /* a publisher-index row carries the listing page's date, not the story's: it prints the dash */
  if (item && item.sourceKind !== INDEX && item.date) {
    try {
      const d = new Date(item.date);
      if (!isNaN(d.getTime())) {
        const day = String(d.getDate()).padStart(2, "0");
        const month = d.toLocaleString("en-US", { month: "short" });
        return `${day} ${month} ${d.getFullYear()}`;
      }
    } catch (e) {}
  }
  return "—";
};

const formatNewsSource = (item) => {
  if (item && item.source && item.source) {
    return item.source;
  }
  if (item && item.url) {
    try {
      const u = new URL(item.url);
      return u.hostname.replace(/^www\./, "");
    } catch (e) {}
  }
  return "—";
};

/* A NEWS ROW'S PRODUCT CATEGORY, from the dataset's own keyword map (CAT_ALIASES:
   "howitzer" -> Artillery, "ammo" -> Ammunition ...). Whole words only, longest keyword
   first, so "small arms" wins over "arms". The headline is read first; a headline that
   names no product falls back to the company's own sector line. */
export function productCategoryOf(text, aliases) {
  const t = ` ${String(text || "").toLowerCase().replace(/[^a-z0-9&/ ]+/g, " ")} `;
  const keys = Object.keys(aliases || {}).sort((a, b) => b.length - a.length);
  for (const k of keys) {
    if (t.includes(` ${k} `) || t.includes(` ${k}/`) || t.includes(`/${k} `)) return aliases[k];
  }
  return null;
}
// sector tag colours: one per news sector the feed filters on
const SECTOR_CLASS = { defence: "def", financial: "fin", government: "gov", workforce: "wrk", markets: "mkt" };
const sectorClass = (c) => SECTOR_CLASS[String(c || "").toLowerCase()] || "oth";

/* ONE EXECUTIVE, FULL PAGE. Opened from a Leadership card; replaces the profile in the
   right-hand column until "Back". Every section prints only what the leadership row
   carries (`experience`, `education`) and says so plainly when a section has nothing --
   no career is inferred from a job title. */
const yearOf = (v) => {
  const m = String(v == null ? "" : v).match(/(19|20)\d{2}/);
  return m ? Number(m[0]) : null;
};
const isPresent = (v) => v == null || v === "" || /present|current|now/i.test(String(v));
// "2018 – Present · 8 yrs"
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
  const current = exp.find((e) => isPresent(e.to)) || null;

  return (
    <div className="cp-person">
      <button type="button" className="cp-person-back" onClick={onBack}>
        ← Back to {companyName}
      </button>
      <div className="cp-person-head">
        <PersonAvatar name={leader.name} photo={leader.photo} className="cp-person-avatar" />
        <div>
          <h1 className="cp-person-name">{leader.fullName || leader.name}</h1>
          <Review src={leader._src} />
          <div className="cp-person-now">
            {leader.role}
            <span className="cp-person-at"> · {current ? current.company : companyName}</span>
          </div>
        </div>
      </div>



      <section className="cp-person-sec">
        <h2 className="cp-person-h">Professional Experience</h2>
        {exp.length ? (
          <div className="cp-person-list">
            {exp.map((e, i) => (
              <div className="cp-person-row" key={`${e.company}-${e.role}-${i}`}>
                <span className="cp-person-dot" />
                <div className="cp-person-row-main">
                  <span className="cp-person-role">{e.role}</span>
                  <span className="cp-person-org">{e.company}</span>
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
              <div className="cp-person-row" key={`${e.institution}-${i}`}>
                <span className="cp-person-dot" />
                <div className="cp-person-row-main">
                  <span className="cp-person-role">{e.degree}</span>
                  <span className="cp-person-org">{e.institution}</span>
                </div>
                {e.from || e.to ? <span className="cp-person-when">{tenureText(e.from, e.to).split(" · ")[0]}</span> : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="cp-thin">No education on public record.</div>
        )}
      </section>





      {leader.source || leader.bioSource || leader.photoSource ? (
        <div className="cp-person-src" style={{ marginTop: "24px" }}>
          {[["Role", leader.source], ["Career & education", leader.bioSource], ["Photo", leader.photoSource]]
            .filter(([, u], i, arr) => u && arr.findIndex(([, v]) => v === u) === i)
            .map(([label, u]) => (
              <div key={label}>{label}: <a href={u} target="_blank" rel="noopener noreferrer">{u}</a></div>
            ))}
        </div>
      ) : null}
    </div>
  );
}


/* A person's avatar: their photo (through our own /api/img proxy, like every other image)
   when one is on record, else -- or if it fails to load -- their initials. */
function PersonAvatar({ name, photo, className }) {
  const [broken, setBroken] = useState(false);
  // same URL rule as every other image (http(s) only, not a known-dead link), and an onError fallback
  // a photo cached on our own origin (/local-photos/...) is served as-is, no proxy
  const local = typeof photo === "string" && /^\/local-photos\/[\w.-]+$/.test(photo);
  if ((local || thumbUsable(photo)) && !broken) {
    return (
      <div className={`cp-avatar cp-avatar-photo ${className || ""}`}>
        <img onError={() => setBroken(true)} alt={name} src={local ? photo : proxied(photo)} />
      </div>
    );
  }
  return <div className={`cp-avatar ${className || ""}`}>{getInitials(name)}</div>;
}

// Helper to derive exact metadata for BDL and all tracked competitors
/* Company facts, from the pipeline's own columns.
 *
 * This function used to hold a hand-written dossier for about eleven named firms
 * — founded date, headcount, revenue, site count, all typed in — and a fallback
 * that INVENTED the rest: "₹1,000 Cr+ (Published Financials)", "1,000–5,000
 * Employees". Every one of those values now has a column in serving.competitors
 * (starting_year, company_size, sales, global_locations, hq, sector, assess), so
 * the panel reads them instead. A fact the corpus does not state renders as a
 * dash. The markup below is untouched; only where the values come from changed.
 */
const DASH = "—";

const firstValue = (v) => {
  if (!v) return null;
  if (Array.isArray(v)) {
    const hit = v.find((x) => x && (typeof x === "string" ? x.trim() : x.value));
    if (!hit) return null;
    return typeof hit === "string" ? hit : hit.value || null;
  }
  return typeof v === "string" ? v.trim() || null : null;
};

/* A revenue figure without its year is ambiguous — "$68.9 billion" could be any of the
   six figures the corpus holds for a company. `detail` carries the reporting period the
   extractor tied the amount to, so show it. Undated figures (kept only when the sentence
   calls itself annual) have an empty `detail` and render as the bare amount. */
const firstFigure = (v) => {
  /* TWO WRITERS, TWO SHAPES. The corpus fill writes an array of {value, detail, url},
     newest first; the audited workbook writes one {text, fy, srcs} object. Both land in
     the same `sales` column, and reading only the array shape showed a dash for every
     company the workbook covered -- the value was in the database the whole time. */
  if (v && !Array.isArray(v) && typeof v === "object") {
    const text = (v.text || "").trim();
    if (!text) return null;
    const fy = (v.fy || "").trim();
    return fy ? `${text} (${fy})` : text;
  }
  if (!Array.isArray(v)) return firstValue(v);
  const hit = v.find((x) => x && (typeof x === "string" ? x.trim() : x.value));
  if (!hit) return null;
  if (typeof hit === "string") return hit.trim() || null;
  const period = (hit.detail || "").trim().replace(/^(?:in|for|during|of)\s+/i, "");
  return period ? `${hit.value} (${period})` : hit.value || null;
};

/* HEADQUARTERS, AT ONE GRANULARITY. The column holds three different things: a full
   postal address ("241 18th Street South, Suite 650, Arlington, Virginia 22202, United
   States"), a city/region/country chain, and a bare country ("Israel"). Rendered raw
   they read as different fields, and the street line is noise on a competitor profile.

   The rule itself moved to lib/countryFacet.js on 2026-09-06 -- unchanged -- because the
   geo map's "Head office" badge needed the same answer and had been doing raw
   full-string equality instead. It is imported at the top of this file. */

const joinList = (v) => {
  if (!Array.isArray(v) || !v.length) return null;
  const names = v
    .map((x) => (typeof x === "string" ? x : x && (x.value || x.name)))
    .filter(Boolean);
  return names.length ? names.join(" · ") : null;
};

/* feed cards opened per "View more" click */
/* Superseded by feedSplit/FEED_N in lib/news.js. The feed used to open at six and
   grow by six per click with no ceiling, so Rheinmetall's 56 articles became 55
   stacked cards in a 28%-wide column and pushed Facilities, Partnerships and
   everything else under it off the page. */
const NEWS_PAGE = FEED_N;

const getCompanyDetailsMeta = (p) => {
  if (!p) return null;
  return {
    founded: p.starting_year ? String(p.starting_year) : DASH,
    hq: tidyHq(p.hq) || DASH,
    globalLocs: joinList(p.global_locations) || DASH,
    size: p.company_size || DASH,
    revenue: firstFigure(p.sales) || DASH,
    sector: p.sector || DASH,
    /* assess is 100% filled and already grounded against the corpus. */
    assess: p.assess || null,
  };
};

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

const PROFILE_KEY = "kssl_profile_cid";

const UNKNOWN_ORIGIN = "Origin not established";

export default function Profile() {
  const { data } = useData();
  const { setScope, takePending, searchQuery } = useAppState();
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("all");
  const [revenue, setRevenue] = useState("all");
  const roster = useMemo(() => rosterOf(data), [data]);
  /* Finding T 3: no country-level filter on the competitor list.

     2026-09-06: this filters on ORIGIN -- the country a company is FROM -- and not
     on companyCountries, which unions the geo footprint, global_locations and hq to
     answer "where is it recorded". Those are different questions, and the union
     answered the wrong one out loud: Bharat Dynamics appeared under "France (6)"
     because a footprint row was earned from "produces MILAN-2T under license from
     MBDA Missile Systems, France". France is the licensor's country; BDL builds
     MILAN-2T in India.

     A company whose origin nobody has established is listed under its own option
     rather than dropped, because a filter that silently hides rows is worse than
     one that admits what it does not know. */
  const countryOptions = useMemo(
    () => facetOptionsByName(roster, (r) => [r.origin || UNKNOWN_ORIGIN]),
    [roster],
  );
  /* The selected competitor is remembered, as Positioning, Partnerships, Geo, Patents
     and the Tender Pipeline remember theirs: this page reset to roster[0] on every
     reload and every detour to another rail row, alone among the sidebars. A saved id
     that the served roster no longer carries falls back to the first row. */
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

  /* Opened from global search targeting one company. Without this the page took the
     jump but never read the payload, so picking "RENK" in the search box landed on
     roster[0] -- the search looked broken because it navigated to the wrong rival. */
  useEffect(() => {
    const pend = takePending("profile");
    if (pend && pend.cid && data.competitors && data.competitors[pend.cid]) {
      setCid(pend.cid);
    }
  }, [takePending, data.competitors]);

  // News category filter pill
  const [newsFilter, setNewsFilter] = useState("All");
  // the Leadership card opened as a full page in the right column (leader object), or null
  const [selectedLeader, setSelectedLeader] = useState(null);
  useEffect(() => { setSelectedLeader(null); }, [cid]);
  // opening or closing a person starts that page at its top
  useEffect(() => {
    let el = document.querySelector(".v-profile .cp-body");
    while (el) { el.scrollTop = 0; el = el.parentElement; }
  }, [selectedLeader]);
  /* How far back counts as current. The reader's choice, not a constant -- see
     lib/news.NEWS_WINDOWS. The 15-card cap below is the panel's and is not. */
  const [newsWindow, setNewsWindow] = useState(NEWS_WINDOW_DEFAULT);
  /* How many feed cards are open. "View More News" had no handler and the stack
     already listed every article, so the button could not have done anything; the
     stack now opens NEWS_PAGE at a time and the button says how many remain. */
  const [newsShown, setNewsShown] = useState(NEWS_PAGE);
  const [showAllNews, setShowAllNews] = useState(false);
  /* The full NEWS list's own filters (not the feed's): a keyword and a date window. */
  const [listQ, setListQ] = useState("");
  const [listRange, setListRange] = useState("all");   // all | 7d | 30d | 3m | 6m | 12m | custom
  const [listFrom, setListFrom] = useState("");
  const [listTo, setListTo] = useState("");
  useEffect(() => { setListQ(""); setListRange("all"); setListFrom(""); setListTo(""); }, [cid]);

  useEffect(() => {
    const pend = takePending("profile");
    if (pend && pend.cid) {
      setCid(pend.cid);
    }
  }, [takePending]);

  const list = useMemo(() => {
    const q = (query || searchQuery || "").trim().toLowerCase();
    const tokens = q.split(/\s+/).filter(Boolean);
    return roster.filter((r) => {
      if (country !== "all" && (r.origin || UNKNOWN_ORIGIN) !== country) return false;
      if (revenue !== "all" && r.revenueTier !== revenue) return false;
      if (!tokens.length) return true;
      const fn = competitorFullName(r.cid, r.name, data.competitors);
      const fullText = `${r.name || ""} ${fn || ""} ${r.sector || ""} ${r.hq || ""} ${r.cid || ""}`.toLowerCase();
      return tokens.every((tok) => fullText.includes(tok));
    });
  }, [data, roster, query, searchQuery, country, revenue]);
  const revenueOpts = useMemo(() => revenueOptions(roster), [roster]);

  const p = useMemo(() => (cid ? buildProfile(data, cid) : null), [data, cid]);
  // strengths and weaknesses as served on the competitor record (two lists of plain sentences)
  const swList = (key) => {
    const v = cid && data.competitors && data.competitors[cid] ? data.competitors[cid][key] : null;
    return Array.isArray(v) ? v.filter((x) => typeof x === "string" && x.trim()) : [];
  };
  const strengths = swList("strengths");
  const weaknesses = swList("weaknesses");
  const displayName = p ? competitorFullName(p.cid, p.name, data.competitors) : "";

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
    setNewsFilter("All");
    setNewsShown(NEWS_PAGE);
  }, [cid]);
  useEffect(() => {
    setNewsShown(NEWS_PAGE);
  }, [newsFilter, newsWindow]);

  /* Executive leadership.
   *
   * This block used to carry a hand-typed board for about six named firms --
   * "Shri Shailesh Vagerwal, Chairman & Managing Director" at Bharat Dynamics,
   * "Sukaran Singh" at TASL, "Gautam Adani" at Adani Defence -- returned before
   * the real branch could run. Named people in named roles at real companies is
   * the most damaging kind of invented content on this dashboard, and it was the
   * one I missed on the first pass: the strings survived into the deployed
   * bundle, which is where I found them.
   *
   * competitors.leadership is the column for this. It is 0% filled today, so the
   * section renders empty until enrichment writes it -- which is the correct
   * state, not a regression.
   */
  const leadershipList = useMemo(() => {
    if (!p || !p.leadership || !p.leadership.length) return [];
    return p.leadership.map((r) => ({
      name: r.value,
      fullName: r.full_name || r.value,
      role: r.detail || "—",
      source: r.url,
      photo: r.photo || null,
      photoSource: r.photo_source || null,
      bioSource: r.bio_source || null,
      experience: Array.isArray(r.experience) ? r.experience : [],
      education: Array.isArray(r.education) ? r.education : [],
    }));
  }, [p]);
  /* Facilities. Same fault: a hand-typed plant list for Bharat Dynamics
     (Kanchanbagh, Bhanur, Visakhapatnam, and an "Armenia (Deployed) / Philippines
     (Negotiation)" export pipeline) shadowed the harvested branch. Now: the
     facilities column if it has rows, else the country presence rows, else
     nothing. */
  /* Memoised because the header report below depends on it: a fresh object each
     render would republish the report each render, and each publish re-renders. */
  const companyMeta = useMemo(() => (p ? getCompanyDetailsMeta(p) : null), [p]);
  // Absent for a company no dated document names -- the tile then does not render
  // at all, rather than showing a confident zero.
  const metrics = (data.competitorMetrics || {})[cid] || null;
  const companyArticles = useMemo(
    () => (p && p.cid ? companyNews(data, p.cid) : []),
    [data, p],
  );

  /* A ROW SOURCED FROM A LISTING PAGE IS WRONG IN THREE WAYS, NOT ONE.
   *
   * These were reported as a missing image. The image was the symptom. Where the
   * extractor recorded a SECTION INDEX as a story's source document, everything the
   * row takes from "the document" is about the wrong page:
   *
   *   url    the section, not the story. Screenshotted: a card headlined "DOD Plans To
   *          Procure 500 Roadrunner Interceptors" opened the Air Warfare section.
   *   date   the LISTING's date, not the story's. Measured over the 73 such rows in
   *          the served feed: 44 carry the listing page's own published_at and 4 the
   *          day it was crawled. Resolved against the real articles, 7 of 8 were
   *          wrong, by a median of 192 days and a maximum of 1,552 -- an April 2022
   *          Lithuania/Boxer story was reading as 21 July 2026 news.
   *   image  none, because a listing page carries no article-level og:image. 63 of 73.
   *
   * THE REST OF THE FEED IS SOUND, which is what makes this safe to cut rather than a
   * reason to distrust every date: of the 232 rows whose url carries its own
   * publication date, 229 are dated exactly right and 3 are one day out on a timezone
   * boundary. The fault is specific to rows whose document was an index.
   *
   * SO THEY LEAVE THE FEED, AND NOTHING IS LOST. A card grid answers "what is new",
   * and a row that cannot say when it happened or link to what happened is not an
   * answer. Every one of them is still in the full record below, marked, because the
   * headline and the company attribution behind it are real -- it is the document
   * metadata that is wrong. The fix is upstream and in progress; this is what the UI
   * does until the rows come back attributed.
   */
  const unattributed = useMemo(
    () => companyArticles.filter((a) => a.sourceKind === INDEX),
    [companyArticles],
  );
  const attributed = useMemo(
    () => companyArticles.filter((a) => a.sourceKind !== INDEX),
    [companyArticles],
  );

  /* WINDOW, THEN CATEGORY, THEN CAP -- in that order, and the order matters. Capping
     before the category filter would show fewer than fifteen of a category that has
     more, for no reason a reader could see. */
  const windowedArticles = useMemo(
    () => withinWindow(attributed, windowDays(newsWindow)),
    [attributed, newsWindow],
  );

  // Filter articles based on selected Category Pill
  const filteredArticles = useMemo(() => {
    if (!newsFilter || newsFilter === "All" || !windowedArticles.some((a) => a.category === newsFilter)) {
      return capNews(windowedArticles, NEWS_MAX);
    }
    return capNews(windowedArticles.filter((a) => a.category === newsFilter), NEWS_MAX);
  }, [windowedArticles, newsFilter]);

  // the filter pills are the categories this company's articles actually carry, commonest first
  const newsCategories = useMemo(() => {
    const n = new Map();
    windowedArticles.forEach((a) => a.category && n.set(a.category, (n.get(a.category) || 0) + 1));
    return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([c]) => c);
  }, [windowedArticles]);

  /* The lead needs no special rule any more: nothing sourced from a listing page
     reaches `filteredArticles`, so it cannot reach the lead slot either. The
     fallback stays `attributed`, never `companyArticles` -- falling back to the
     whole list would put a row the feed just excluded into its biggest card. */
  const topStory = useMemo(() => {
    return filteredArticles.find((a) => a.isTopStory) || filteredArticles[0] || attributed[0];
  }, [filteredArticles, attributed]);

  /* One uniform grid: the newest story is no longer pulled into a bigger lead card,
     it threads in with the rest. topStory survives only as the "is there any news at
     all" gate for the section below. */
  const feedArticles = useMemo(() => filteredArticles, [filteredArticles]);

  /* THE FEED IS THREADED; THE FULL LIST BELOW IS NOT.
     Three PAC-3 stories in a fortnight are one running story, and the same wire piece
     from four outlets is one event reported four times. news_chain.py decides which,
     from spans the extraction layer typed -- not from a word in the headline. The full
     News section still lists every article, so collapsing here hides nothing.

     It has to sit BELOW feedArticles, not beside the useState calls at the top of the
     component. A const is in its temporal dead zone until its own line runs, so a
     useMemo declared earlier that reads it throws "Cannot access 'feedArticles' before
     initialization" -- at RENDER, not at build. esbuild compiled it happily and every
     name resolved to a binding; test_filter_counts.mjs, which actually renders the
     page, is what caught it. */
  const threadedFeed = useMemo(() => collapseThreads(feedArticles), [feedArticles]);

  /* What the header's Copy / Export / Print act on: this company's profile as shown --
     details, leadership, and every sourced article. Nothing is added to the record. */
  const report = useMemo(() => {
    if (!p) return null;
    const details = companyMeta
      ? [
          ["Starting year", companyMeta.founded],
          ["Headquarters", companyMeta.hq],
          ["Global locations", companyMeta.globalLocs],
          ["Company size", companyMeta.size],
          ["Annual revenue / sales", companyMeta.revenue],
          ["Industry / sector", formatSectorName(companyMeta.sector)],
        ]
      : [];
    return {
      title: displayName,
      subtitle: "Competitor profile",
      sections: [
        { h: "Company details", rows: details },
        /* "Strategic positioning & operations" removed (FE-COMP-100): unverified
           analyst placeholder prose, kept out of the profile and its export. */
        {
          h: "Leadership",
          rows: leadershipList.length
            ? leadershipList.map((l) => [l.name, l.role])
            : ["No executive officers published on public record."],
        },
        {
          h: `Company latest news (${companyArticles.length})`,
          rows: companyArticles.map((a) => [a.title, [a.source, a.ago, a.category].filter(Boolean).join(" · ")]),
        },
      ].filter(Boolean),
      payload: {
        cid: p.cid,
        name: displayName,
        details: companyMeta
          ? {
              startingYear: companyMeta.founded,
              hq: companyMeta.hq,
              globalLocations: companyMeta.globalLocs,
              companySize: companyMeta.size,
              revenue: companyMeta.revenue,
              sector: companyMeta.sector,
              assessment: isVisible("parallax-read") ? companyMeta.assess || null : null,
            }
          : null,
        leadership: leadershipList.map((l) => ({ name: l.name, role: l.role, source: l.source || null })),
        news: companyArticles.map((a) => ({
          title: a.title,
          source: a.source || null,
          date: a.date || null,
          category: a.category || null,
          url: a.url || null,
        })),
      },
    };
  }, [p, displayName, companyMeta, leadershipList, companyArticles]);
  useHeaderReport(report);

  /* The full NEWS list, narrowed by its own keyword + date filters. A date filter can only
     keep an article whose date is known (listing-page rows carry none). */
  const newsListDated = listRange !== "all";
  const newsListFiltered = listQ.trim().length > 0 || newsListDated;
  const listRows = useMemo(() => {
    const catOf = (item) =>
      productCategoryOf(`${item.title} ${item.excerpt || ""}`, data.CAT_ALIASES)
      || productCategoryOf(companyMeta && companyMeta.sector, data.CAT_ALIASES);
    const days = (NEWS_LIST_RANGES.find((r) => r.key === listRange) || {}).days;
    const since = days ? new Date(Date.now() - days * 86400000).toISOString().slice(0, 10) : null;
    const toks = listQ.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return (companyArticles || []).filter((item) => {
      const d = item.sourceKind === INDEX ? "" : String(item.date || "").slice(0, 10);
      if (listRange !== "all" && !d) return false;
      if (since && d < since) return false;
      if (listRange === "custom" && ((listFrom && d < listFrom) || (listTo && d > listTo))) return false;
      if (toks.length) {
        const hay = `${item.title} ${item.excerpt || ""} ${item.category || ""} ${catOf(item) || ""} ${item.source || ""}`.toLowerCase();
        if (!toks.every((t) => hay.includes(t))) return false;
      }
      return true;
    });
  }, [companyArticles, companyMeta, data.CAT_ALIASES, listQ, listRange, listFrom, listTo]);

  return (
    <div className="pos-view v-profile" style={{ gridTemplateColumns: "300px 1fr" }}>
      {/* 1. LEFT SIDEBAR: UNCHANGED COMPETITORS LIST */}
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
            <option value="all">All origins ({roster.length})</option>
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
              <option value="all">All revenue tiers ({roster.length})</option>
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
                <span className={`wdot${r.threat ? ` ${r.threat}` : ""}`} style={{ flexShrink: 0 }} />
                <span style={{ minWidth: 0, wordBreak: "break-word" }}>
                  <span>{competitorFullName(r.cid, r.name, data.competitors)}</span>
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

      {/* 2. RIGHT PANE.

          THE IN-APP ARTICLE WINDOW IS GONE. Every news item on this page used to open a
          white panel HERE that replaced the profile and re-hosted the story: the
          publisher's headline over `signal_detail.what` as the body, with the real
          article one further click away behind "Source Publisher". At the operator's
          request a news item now goes to the news source -- see ArticleLink in
          components/sourceLink. The panel and its `activeArticle` state went with it,
          along with the reason the profile could be replaced by something that was not
          a profile.

          What that removed is worth naming: the panel was the only surface printing the
          pipeline's own read of an article (`what` / `why`) as though it were the
          article. Those fields are still served and are still shown on the SIGNAL card
          detail, which is where a paraphrase belongs -- labelled as this system's
          analysis, not laid out as reporting. */}
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

            {/* 1. COMPANY DETAILS */}
            <Sec title="Company Details">
              {companyMeta && (
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

                  <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", borderBottom: "1px solid var(--d-line)", fontSize: "13px", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap" }}>
                      Starting Year
                    </span>
                    <span style={{ color: "var(--d-txt)", fontWeight: "600" }}>{companyMeta.founded}</span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", borderBottom: "1px solid var(--d-line)", fontSize: "13px", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap" }}>
                      Headquarters
                    </span>
                    <span style={{ color: "var(--d-txt)", fontWeight: "600" }}>{companyMeta.hq}</span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", borderBottom: "1px solid var(--d-line)", fontSize: "13px", alignItems: "start" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap", paddingTop: "3px" }}>
                      Global Locations
                    </span>
                    <span className="cp-loc-wrap">
                      {(Array.isArray(p.global_locations) ? p.global_locations : [])
                        .map((x) => (typeof x === "string" ? x : x && (x.value || x.name)))
                        .filter(Boolean)
                        .map((place) => (
                          <span className="cp-loc-chip" key={place}>{place}</span>
                        ))}
                      {!(Array.isArray(p.global_locations) && p.global_locations.length) ? <span className="cp-thin">—</span> : null}
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", borderBottom: "1px solid var(--d-line)", fontSize: "13px", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap" }}>
                      Company Size
                    </span>
                    <span style={{ color: "var(--d-txt)", fontWeight: "600" }}>{companyMeta.size}</span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", borderBottom: "1px solid var(--d-line)", fontSize: "13px", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap" }}>
                      Annual Revenue / Sales
                    </span>
                    <span style={{ color: "var(--d-txt)", fontWeight: "600" }}>{companyMeta.revenue}</span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: "12px", padding: "14px 18px", fontSize: "13px", alignItems: "center" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", color: "var(--d-txt-3)", fontWeight: "600", textTransform: "uppercase", letterSpacing: ".06em", whiteSpace: "nowrap" }}>
                      Industry / Sector
                    </span>
                    <span style={{ color: "var(--d-txt)", fontWeight: "600" }}>{formatSectorName(companyMeta.sector)}</span>
                  </div>
                </div>
              )}
            </Sec>

            {/* 2. STRATEGIC POSITIONING / PARALLAX READ / STRENGTHS & WEAKNESSES: each is its own
                ui.section_visibility key; the section itself shows only when one of them does */}
            {isVisible("strategic-positioning") || isVisible("parallax-read") || isVisible("swot") ? (
            <Sec title={isVisible("strategic-positioning") ? "Strategic Positioning" : isVisible("parallax-read") ? "Parallax Read" : "Strengths & Weaknesses"}>
              {isVisible("strategic-positioning") ? (
                <p className="cp-prose" style={{ fontSize: "13.5px", lineHeight: "1.65", color: "var(--d-read)", marginBottom: "18px" }}>
                  {p.strategic_positioning || "—"}
                </p>
              ) : null}

              {/* PARALLAX READ: the stored analyst read of the rival, or a dash */}
              {isVisible("parallax-read") ? (
                <div style={{ marginTop: "18px", marginBottom: "22px" }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: "11px", fontWeight: "700", letterSpacing: ".1em", color: "var(--d-txt-2)", textTransform: "uppercase", marginBottom: "8px" }}>
                    PARALLAX READ
                  </div>
                  <div style={{ padding: "16px 20px", background: "var(--d-bg-1)", border: "1px solid #f0593c", borderRadius: "8px", fontSize: "13.5px", lineHeight: "1.6", color: "var(--d-txt)" }}>
                    {(p.assess || "").replace(/<[^>]*>/g, "").trim() || "—"}
                  </div>
                </div>
              ) : null}

              {/* STRENGTHS & WEAKNESSES: the competitor record's own lists */}
              {isVisible("swot") ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                {/* STRENGTHS */}
                <div style={{ background: "var(--d-bg-1)", border: "1px solid rgba(52, 211, 153, 0.3)", borderTop: "2px solid #34d399", borderRadius: "8px", padding: "16px 18px", display: "flex", flexDirection: "column", gap: "10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "11px", fontWeight: "700", letterSpacing: ".08em", color: "#34d399", textTransform: "uppercase" }}>STRENGTHS</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "10px", padding: "1px 6px", background: "rgba(52, 211, 153, 0.15)", color: "#34d399", borderRadius: "4px" }}>{strengths.length}</span>
                  </div>
                  {strengths.length ? (
                    <ul style={{ margin: 0, paddingLeft: "18px", display: "flex", flexDirection: "column", gap: "9px", fontSize: "13px", lineHeight: 1.55, color: "var(--d-txt)" }}>
                      {strengths.map((t) => (
                        <li key={t}>{t}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="cp-thin" style={{ fontSize: "12px", fontStyle: "italic", padding: "8px 0" }}>
                      No strengths on record.
                    </div>
                  )}
                </div>

                {/* WEAKNESSES */}
                <div style={{ background: "var(--d-bg-1)", border: "1px solid rgba(248, 113, 113, 0.3)", borderTop: "2px solid #f87171", borderRadius: "8px", padding: "16px 18px", display: "flex", flexDirection: "column", gap: "10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "11px", fontWeight: "700", letterSpacing: ".08em", color: "#f87171", textTransform: "uppercase" }}>WEAKNESSES</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "10px", padding: "1px 6px", background: "rgba(248, 113, 113, 0.15)", color: "#f87171", borderRadius: "4px" }}>{weaknesses.length}</span>
                  </div>
                  {weaknesses.length ? (
                    <ul style={{ margin: 0, paddingLeft: "18px", display: "flex", flexDirection: "column", gap: "9px", fontSize: "13px", lineHeight: 1.55, color: "var(--d-txt)" }}>
                      {weaknesses.map((t) => (
                        <li key={t}>{t}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="cp-thin" style={{ fontSize: "12px", fontStyle: "italic", padding: "8px 0" }}>
                      No weaknesses on record.
                    </div>
                  )}
                </div>
              </div>
              ) : null}
            </Sec>
            ) : null}

            {/* 3. LEADERSHIP */}
            <Sec title="Leadership">
              {leadershipList.length > 0 ? (
                <div className="cp-leadership-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "14px" }}>
                  {leadershipList.map((leader, i) => (
                    <div
                      className="cp-lead-card cp-lead-card-link"
                      key={`${leader.name}-${i}`}
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
                      <PersonAvatar name={leader.name} photo={leader.photo} />
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

            

            {/* 5. COMPANY LATEST NEWS */}
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
              {!filteredArticles.length && !companyArticles.length ? (
                <div className="cp-thin" style={{ fontSize: "12px", padding: "8px 0" }}>
                  No sourced article in the corpus names {displayName}.
                </div>
              ) : null}
              {(filteredArticles.length > 0 || companyArticles.length > 0) && (
                <div className="ln-dashboard" style={{ marginTop: "6px" }}>

                  {/* Category Filter Pills */}
                  <div className="ln-pills" style={{ marginBottom: "14px" }}>
                    {["All", ...newsCategories].map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        className={`ln-pill${newsFilter === cat ? " on" : ""}`}
                        onClick={() => setNewsFilter(cat)}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>

                  {/* 3x3 Grid of exactly 9 Cards */}
                  <div className="ln-grid">
                    {(() => {
                      const displayList = filteredArticles.slice(0, 9);
                      return displayList.map((item, idx) => {
                        const imgUrl = item.image;   // none: the card's own "no image" tile, never another story's photo
                        return (
                          <div className="ln-feed-item" key={item.id || idx}>
                            <ArticleLink article={item} className="ln-feed-card">
                              <Thumb src={imgUrl} alt="" className="ln-feed-thumb" />
                              <div className="ln-feed-info">
                                <div className="ln-feed-meta">
                                  {item.category || "—"} · {item.ago || (item.date ? String(item.date).slice(0, 10) : "")}
                                </div>
                                <div className="ln-feed-title">{item.title}</div>
                                <span className="ln-feed-src">{item.source || "—"}</span>
                              </div>
                            </ArticleLink>
                            <Review src={item._src} />
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              )}
            </Sec>

            {/* 7. NEWS (LIST / TABULAR FORMAT) */}
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
                    {NEWS_LIST_RANGES.map((w) => (
                      <option key={w.key} value={w.key}>{w.label}</option>
                    ))}
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
                  <Fragment key={item.id || `all-${idx}`}>
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
                      {fmtNewsDate(item)}
                    </span>
                    <span className="ln-row-title" style={{ fontSize: "13px", color: "var(--d-txt)", fontWeight: "500", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.title}
                    </span>
                    <span className="ln-row-cat" style={{ display: "flex", justifyContent: "center" }}>
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
                        {item.category || "—"}
                      </span>
                    </span>
                    <span className="ln-row-url" style={{ fontFamily: "var(--mono)", fontSize: "11px", color: "var(--d-txt-3)", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {formatNewsSource(item)}
                    </span>
                  </ArticleLink>
                  <Review src={item._src} style={{ margin: "0 14px 6px" }} />
                  </Fragment>
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
          </>
        )}
      </div>
    </div>
  );
}
