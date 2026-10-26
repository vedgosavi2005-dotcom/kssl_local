import { clientShort } from "../../lib/client.js";
import { useEffect, useMemo, useState } from "react";
import { useHeaderReport, useAppState } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { rosterOf } from "../../lib/profile";
import { competitorFullName } from "../../lib/companyNames";
import FeedFilters from "../../components/subHead/FeedFilters.jsx";
import { stanceOf, stanceWords, competitiveLane, PROJECT_SEQ, PROJECT_SEQ_DEFAULT, PROJECT_OPTION_WORD } from "../../lib/chrome";
import { projectFeed, sortableSeq, latestWhen, day, projectTitle, projectStage, sentenceCase, plainDates, projectCountries, projectValue, specLabel, specValue, timelineSteps } from "../../lib/projects";
import { facetOptionsByName } from "../../lib/countryFacet";
import { srcChips } from "../../lib/html";
import { formatDate } from "../../utils/formatDate";
import { Review, REVIEW } from "../../components/review/Review";

/* Projects: what each competitor is working on or pursuing. The competitors are
   listed down the left; each project is a row in the Overview's layout, and its panel says what it is, where
   it stands, its specs, its dated timeline and what it means for the client. Everything is read from the
   dataset's own records (data.projects); a fact a record does
   not carry is left out, not filled in. */

const ALL = "__all";
const TODAY = new Date().toISOString().slice(0, 10);

const Sec = ({ title, children }) => (
  <div className="ctx-sec">
    <span className="eyebrow">{title}</span>
    {children}
  </div>
);
/* A spec label used to be cut at 42% of the row with an ellipsis ("German funding for full pro…"); on this page it wraps
   (projects.css .pj-page .cd-fk) and carries the full text as a tooltip too (functional test G15, 2026-10-25). */
const Facts = ({ rows, glance }) => (
  <div className={glance ? "cd-facts cd-glance" : "cd-facts"}>
    {rows.filter((r) => r[1]).map(([k, v], i) => (
      <div className="cd-frow" key={`${k}-${i}`}>
        <span className="cd-fline"><span className="cd-fk" title={k}>{k}</span><span className="cd-fv">{v}</span></span>
      </div>
    ))}
  </div>
);

/* The project card in the BLUF order of the signal card (owner 2026-10-25): title -> at a glance (Who / Customer / What /
   Where / When / Stage / Value, only the rows that hold a value) -> the bottom line (what the project is, then what it
   means for the client, both stored text) -> details (where it stands, specs, the timeline folded shut) -> sources.
   No "->" change-log text, no "…", no Domestic/Export word: Where is the project's country (projectCountries). */
function ProjectPanel({ p, steps, words, fx, onClose }) {
  const stance = p.assessment.stance;
  const cls = stanceOf(stance);   // no threat/watch stance stored, no stance class
  const STANCE_WORD = words;
  const when = p.latest && (p.latest.date || p.latest.label)
    ? [p.latest.date ? formatDate(p.latest.date) : "", plainDates(p.latest.label)].filter(Boolean).join(": ") : "";
  const option = p.ksslOption && p.ksslOption !== "none" ? PROJECT_OPTION_WORD[p.ksslOption] : "";
  const time = timelineSteps(p, REVIEW);
  const specs = (p.specs || []).map((s) => [specLabel(s.k), specValue(s.k, s.v, fx)]);
  return (
    <div className="ctx v-overview revealed">
      <div className="ctx-scroll" key={p.id}>
        <div className={cls ? `ctx-h dir-${cls}` : "ctx-h"}>
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">✕</button>
            {cls && STANCE_WORD[cls] ? <span className={`dirpill dir-${cls}`}>{STANCE_WORD[cls]}</span> : null}
          </div>
          <div className="ct">{projectTitle(p)}</div>
          <Review src={p._src} />
        </div>

        <Sec title="At a glance">
          <Facts glance rows={[
            /* Kind is sentence-cased for display: 39 of 117 stored kinds start lower-case ("initial supply contract")
               (functional test G15, 2026-10-25); the stage falls back to the track step its stored rank points at */
            ["Who", p.company], ["Customer", p.customer], ["What", sentenceCase(p.kind)],
            ["Where", (p.countries || []).join(", ")], ["When", when],
            ["Stage", projectStage(p, steps)], ["Value", projectValue(p, fx)],
          ]} />
        </Sec>

        {p.overview.length ? (
          <Sec title="Bottom line">
            {p.overview.map((t, i) => <div className="cd-prose" key={i} style={i ? { marginTop: "8px" } : undefined}>{plainDates(t)}</div>)}
          </Sec>
        ) : null}

        {p.assessment.read.length || option ? (
          <Sec title={`Impact on ${clientShort() || "the client"}`}>
            {p.assessment.read.map((t, i) => (
              <div className="cd-prose" key={i} style={i ? { marginTop: "8px" } : undefined}>{plainDates(t)}</div>
            ))}
            {option ? <div className="pj-note">What {clientShort() || "the client"} can do: {option}.</div> : null}
          </Sec>
        ) : null}

        <Sec title="Where it stands">
          <ol className="pj-steps">
            {steps.map((s, i) => (
              <li className={i + 1 < p.stageRank ? "done" : i + 1 === p.stageRank ? "now" : ""} key={s}><span>{s}</span></li>
            ))}
          </ol>
          {/* ISO dates inside the stored note ("on 2026-10-13") read in the house format (functional test G15, 2026-10-25) */}
          {p.stageNote ? <div className="cd-prose">{plainDates(p.stageNote)}</div> : null}
        </Sec>

        {specs.some((r) => r[1]) || p.location ? (
          <Sec title="Details">
            <Facts rows={[...specs, ["Site", p.location]]} />
          </Sec>
        ) : null}

        {time.length ? (
          /* a project is a story: dated steps, each with what changed and where it was reported; folded shut like the
             signal card's timeline. "Researched to 17 Oct 2026." stays off the screen (functional test G15). */
          <details className="ctx-sec cd-fold">
            <summary className="eyebrow">Timeline</summary>
            <ol className="pj-time">
              {time.map((t, i) => {
                const later = t.expected || day(t.date) > TODAY;
                return (
                  <li className={later ? "next" : ""} key={i}>
                    <span className="pj-d">{/^\d/.test(t.date || "") ? formatDate(t.date) : t.date}</span>
                    <span className="pj-e">
                      {plainDates(t.line)}{later ? " (expected)" : ""}
                      {t.changed ? <span className="pj-note"> {plainDates(t.changed)}</span> : null}
                      {t.review ? <span className="pj-note"> Review only.</span> : null}
                      {t.url ? <span dangerouslySetInnerHTML={{ __html: " " + srcChips([{ label: "Source", url: t.url }]) }} /> : null}
                    </span>
                  </li>
                );
              })}
            </ol>
          </details>
        ) : null}

        {p.sources.length ? (
          <Sec title="Sources">
            <span dangerouslySetInnerHTML={{ __html: srcChips(p.sources, "pj-srcs", { full: true }) }} />
          </Sec>
        ) : null}
      </div>
    </div>
  );
}

export default function Projects({ onSelectionChange }) {
  const { data } = useData();
  const words = stanceWords();
  const { setScope } = useAppState();
  const [cid, setCid] = useState(ALL);
  const cfg = (data && data.projectsConfig) || {};
  /* each project with the country it is in (where the customer is, not the company's home: lib/projects.projectCountries) */
  const projects = useMemo(() => ((data && data.projects) || []).map((p) => ({ ...p, countries: projectCountries(p, data) })), [data]);
  /* the Country filter replaces Domestic / Export (owner 2026-10-25): options are the countries the projects are in; a
     project whose record names no country is in no option (it shows under "All countries" only) */
  const countries = useMemo(() => facetOptionsByName(projects, (p) => p.countries), [projects]);
  const [country, setCountry] = useState(ALL);
  const seqOptions = useMemo(() => sortableSeq(PROJECT_SEQ), []);
  const [query, setQuery] = useState("");
  const [seq, setSeq] = useState(PROJECT_SEQ_DEFAULT);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  /* Threat / Watch beside the search, the competitor-signal pills (owner 2026-10-26) */
  const dirFilters = useMemo(() => competitiveLane().filters, []);
  const [dir, setDir] = useState("all");

  const roster = useMemo(() => (data && data.competitors ? rosterOf(data) : [])
    .filter((r) => projects.some((p) => p.cid === r.cid))
    .map((r) => ({ cid: r.cid, name: competitorFullName(r.cid, r.name, data.competitors) || r.name, threat: r.threat })), [data, projects]);

  const ofDir = (p) => dir === "all" || stanceOf(p.assessment && p.assessment.stance) === dir;
  const { perCompetitor } = useMemo(
    () => projectFeed({ projects: projects.filter(ofDir), cid: null, query, seq, country: country === ALL ? null : country }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projects, query, seq, country, dir]);
  const shown = useMemo(() => {
    const q = search.toLowerCase().trim();
    return roster.filter((r) => !q || r.name.toLowerCase().includes(q)).sort((a, b) => (perCompetitor[b.cid] || 0) - (perCompetitor[a.cid] || 0));
  }, [roster, search, perCompetitor]);
  /* no "All competitors" row (owner 2026-10-26): the list is the competitors only, and the one with the most projects
     opens first until another is clicked */
  const activeCid = cid !== ALL && roster.some((r) => r.cid === cid) ? cid : (shown[0] || roster[0] || {}).cid || null;
  const { rows: cidRows } = useMemo(
    () => projectFeed({ projects, cid: activeCid, query, seq, country: country === ALL ? null : country }), [projects, activeCid, query, seq, country]);
  const rows = useMemo(() => cidRows.filter(ofDir),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cidRows, dir]);
  const dirCounts = useMemo(() => Object.fromEntries(dirFilters.map((f) => [f.f, cidRows.filter((p) => f.f === "all" || stanceOf(p.assessment && p.assessment.stance) === f.f).length])),
    [cidRows, dirFilters]);
  const co = roster.find((r) => r.cid === activeCid) || null;
  const sel = selected ? projects.find((p) => p.id === selected) || null : null;

  useEffect(() => { onSelectionChange?.(!!sel); }, [sel, onSelectionChange]);
  useEffect(() => () => onSelectionChange?.(false), [onSelectionChange]);
  useEffect(() => {
    setScope("competitive", { projects: rows.length, competitor: co ? co.cid : null }, {
      pillar: "Competitive", view: "Projects", selection: sel ? projectTitle(sel) : co ? co.name : null,
    });
  }, [rows.length, co, sel, setScope]);

  const report = useMemo(() => ({
    /* no empty field printed with its separator ("SAAB · ", ". The note") -- functional test G15, 2026-10-25 */
    title: sel ? projectTitle(sel) : `${co ? co.name : "All competitors"}: projects`,
    subtitle: sel ? [sel.company, projectStage(sel, cfg.stageSteps)].filter(Boolean).join(" · ") : `${rows.length} projects`,
    sections: [{ heading: sel ? "Project" : "Projects on record", facts: (sel ? [sel] : rows).map((p) => [
      [p.company, projectTitle(p)].filter(Boolean).join(": "),
      [projectStage(p, cfg.stageSteps), plainDates(p.stageNote)].filter(Boolean).join(". "),
    ]) }],
    payload: { projects: sel ? [sel] : rows },
  }), [sel, rows, co, cfg.stageSteps]);
  useHeaderReport(report);

  const item = (id, name, n, dot) => (
    <div
      className={`pat-li${id === activeCid ? " active" : ""}`}
      key={id}
      onClick={() => { setCid(id); setSelected(null); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setCid(id); setSelected(null); } }}
      role="button"
      tabIndex={0}
    >
      <span className="pli-n" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "8px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {stanceOf(dot) ? <span className={`wdot ${dot}`} /> : null}
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
        </span>
        <span className="pli-ct">{n}</span>
      </span>
    </div>
  );

  return (
    <div className="pos-view v-projects pj-page" style={{ gridTemplateColumns: "260px 1fr" }}>
      <div className="mu-list">
        <div className="mu-list-h">
          <div className="proj-sidebar-h"><span className="eyebrow">Competitors ({roster.length})</span></div>
          <div className="mu-search" style={{ marginTop: "10px" }}>
            <span className="si">⌕</span>
            <input type="text" placeholder="Search competitor…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {/* placed and styled like the Competitor Movement country filter */}
          <select className="mu-fsel" value={country} onChange={(e) => { setCountry(e.target.value); setSelected(null); }} aria-label="Filter projects by country"
            style={{ width: "100%", marginTop: "8px" }}>
            <option value={ALL}>All countries ({countries.length})</option>
            {countries.map((o) => <option key={o.v} value={o.v}>{o.v} ({o.n})</option>)}
          </select>
        </div>
        <div id="patc-list">
          {shown.map((r) => item(r.cid, r.name, perCompetitor[r.cid] || 0, r.threat))}
        </div>
      </div>

      <div className="ov-wrap">
        <div className="feed-grp-h ov-fixed-header">
          <span className="eyebrow">{co ? co.name : "All competitors"}</span>
          <FeedFilters
            active={dir}
            counts={dirCounts}
            filters={dirFilters}
            onFilter={(f) => { setDir(f); setSelected(null); }}
            onSearch={setQuery}
            onSeq={setSeq}
            searchQuery={query}
            seqMode={seq}
            seqOptions={seqOptions}
          />
        </div>
        <div className={`ov-body${sel ? " has-sel" : ""}`}>
          <div className="feed v-overview" id="feed">
            <div className="feed-grp">
              {rows.map((p, i) => {
                const cls = stanceOf(p.assessment.stance);
                /* never ": Tata Advanced Systems": the stage label and its colon print only when a stage is known, and a
                   project with no stored name shows its best available headline (functional test G15, 2026-10-25) */
                const stage = projectStage(p, cfg.stageSteps);
                return (
                  <div
                    className={`alert${selected === p.id ? " sel" : ""}`}
                    data-dir={cls || undefined}
                    key={p.id}
                    onClick={() => setSelected(p.id)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(p.id); } }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="gut"><span className={cls ? `sig ${cls}` : "sig"} /><span className="rank">{String(i + 1).padStart(2, "0")}</span></div>
                    <div className="body">
                      <div className="ttl">{projectTitle(p)}</div>
                      <div className="sowhat">{plainDates(p.stageNote)}</div>
                      <div className="koel-prod-highlight-row">
                        {stage ? <span className="kph-label">{stage}:</span> : null}
                        <span className="kph-val">{[p.customer, p.location].filter(Boolean).join(" · ")}</span>
                      </div>
                      <Review src={p._src} />
                    </div>
                    <div className="aside">
                      {cls && words[cls] ? <span className={`dirtag ${cls}`}>{words[cls]}</span> : null}
                      <span className="ago">{latestWhen(p) || "—"}</span>
                    </div>
                  </div>
                );
              })}
            </div>
            {rows.length === 0 ? <div className="empty-note">No project matches {query ? `“${query}”` : "this filter"}{co ? ` for ${co.name}` : ""}.</div> : (
              <div className="pager"><div className="pager-range">showing 1–{rows.length} of {rows.length}{rows.length !== projects.length ? ` filtered · ${projects.length} total` : " projects"}</div></div>
            )}
          </div>
          {sel ? <ProjectPanel fx={data && data.fxRates} onClose={() => setSelected(null)} words={words} p={sel} steps={cfg.stageSteps || []} /> : null}
        </div>
      </div>
    </div>
  );
}
