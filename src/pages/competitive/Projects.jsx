import { clientShort } from "../../lib/client.js";
import { useEffect, useMemo, useState } from "react";
import { useHeaderReport, useAppState } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { rosterOf } from "../../lib/profile";
import { competitorFullName } from "../../lib/companyNames";
import FeedFilters from "../../components/subHead/FeedFilters.jsx";
import { stanceOf, stanceWords, PROJECT_FILTERS, PROJECT_SEQ, PROJECT_SEQ_DEFAULT, PROJECT_OPTION_WORD } from "../../lib/chrome";
import { projectFeed, sortableSeq, latestWhen, day } from "../../lib/projects";
import { srcChips } from "../../lib/html";
import { formatDate } from "../../utils/formatDate";
import { Review } from "../../components/review/Review";

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
const Facts = ({ rows }) => (
  <div className="cd-facts">
    {rows.filter((r) => r[1]).map(([k, v]) => (
      <div className="cd-frow" key={k}>
        <span className="cd-fline"><span className="cd-fk">{k}</span><span className="cd-fv">{v}</span></span>
      </div>
    ))}
  </div>
);

function ProjectPanel({ p, steps, regionLabel, words, onClose }) {
  const stance = p.assessment.stance;
  const cls = stanceOf(stance);   // no threat/watch stance stored, no stance class
  const STANCE_WORD = words;
  return (
    <div className="ctx v-overview revealed">
      <div className="ctx-scroll" key={p.id}>
        <div className={cls ? `ctx-h dir-${cls}` : "ctx-h"}>
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">✕</button>
            {cls && STANCE_WORD[cls] ? <span className={`dirpill dir-${cls}`}>{STANCE_WORD[cls]}</span> : null}
          </div>
          <div className="ct">{p.name}</div>
          <Review src={p._src} />
        </div>

        <Sec title="At a glance">
          <Facts rows={[
            ["Competitor", p.company], ["Kind", p.kind], ["Customer", p.customer], ["Location", p.location],
            ["Region", regionLabel], ["Stage", p.stage],
            ["Latest milestone", p.latest && (p.latest.date || p.latest.label) ? [p.latest.date ? formatDate(p.latest.date) : "", p.latest.label].filter(Boolean).join(": ") : ""],
          ]} />
        </Sec>

        <Sec title="What the project is">
          {p.overview.map((t, i) => <div className="cd-prose" key={i} style={i ? { marginTop: "8px" } : undefined}>{t}</div>)}
        </Sec>

        <Sec title="Current stage">
          <ol className="pj-steps">
            {steps.map((s, i) => (
              <li className={i + 1 < p.stageRank ? "done" : i + 1 === p.stageRank ? "now" : ""} key={s}><span>{s}</span></li>
            ))}
          </ol>
          <div className="cd-prose">{p.stageNote}</div>
        </Sec>

        <Sec title="Specs">
          <Facts rows={p.specs.map((s) => [s.k, s.v])} />
        </Sec>

        <Sec title="Timeline">
          {Array.isArray(p.steps) && p.steps.length ? (
            /* a project is a story: dated steps, each with what changed and where it was reported */
            <ol className="pj-time">
              {p.steps.filter((t) => t.type !== "label_change").map((t, i) => (
                <li className={t.type === "planned" || day(t.date) > TODAY ? "next" : ""} key={i}>
                  <span className="pj-d">{/^\d/.test(t.date) ? formatDate(t.date) : t.date}</span>
                  <span className="pj-e">
                    {t.line}{t.type === "planned" || day(t.date) > TODAY ? " (expected)" : ""}
                    {t.changed ? <span className="pj-note"> {t.changed}</span> : null}
                    {t.url ? <span dangerouslySetInnerHTML={{ __html: " " + srcChips([{ label: "Source", url: t.url }]) }} /> : null}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
          <ol className="pj-time">
            {p.timeline.map((e, i) => (
              <li className={e.expected || day(e.date) > TODAY ? "next" : ""} key={i}>
                <span className="pj-d">{/^\d/.test(e.date) ? formatDate(e.date) : e.date}</span>
                <span className="pj-e">{e.label}{e.expected || day(e.date) > TODAY ? " (expected)" : ""}</span>
              </li>
            ))}
          </ol>
          )}
          {p.researchedAsOf ? <div className="pj-note">Researched to {formatDate(p.researchedAsOf)}.</div> : null}
        </Sec>

        <Sec title="Strategic assessment">
          {p.assessment.read.length ? p.assessment.read.map((t, i) => (
            <div className="cd-prose" key={i} style={i ? { marginTop: "8px" } : undefined}>{t}</div>
          )) : <div className="cd-prose">No assessment on record.</div>}
          {p.ksslOption && p.ksslOption !== "unknown" ? <div className="pj-note">What {clientShort() || "the client"} can do: {PROJECT_OPTION_WORD[p.ksslOption] || p.ksslOption}.</div> : null}
          {clientShort() ? <div className="pj-note">The analyst's read for {clientShort()}, from the dataset's record of this item.</div> : null}
        </Sec>

        {p.sources.length ? (
          <Sec title="Source">
            <span dangerouslySetInnerHTML={{ __html: srcChips(p.sources) }} />
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
  const projects = (data && data.projects) || [];
  const cfgFilters = PROJECT_FILTERS;
  const seqOptions = useMemo(() => sortableSeq(PROJECT_SEQ), []);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [seq, setSeq] = useState(PROJECT_SEQ_DEFAULT);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");

  const roster = useMemo(() => (data && data.competitors ? rosterOf(data) : [])
    .filter((r) => projects.some((p) => p.cid === r.cid))
    .map((r) => ({ cid: r.cid, name: competitorFullName(r.cid, r.name, data.competitors) || r.name, threat: r.threat })), [data, projects]);

  const { rows, counts, perCompetitor } = useMemo(
    () => projectFeed({ projects, filters: cfgFilters, cid: cid === ALL ? null : cid, filter, query, seq }), [projects, cfgFilters, cid, filter, query, seq]);
  const shown = useMemo(() => {
    const q = search.toLowerCase().trim();
    return roster.filter((r) => !q || r.name.toLowerCase().includes(q)).sort((a, b) => (perCompetitor[b.cid] || 0) - (perCompetitor[a.cid] || 0));
  }, [roster, search, perCompetitor]);
  const total = Object.values(perCompetitor).reduce((n, v) => n + v, 0);
  const co = roster.find((r) => r.cid === cid) || null;
  const sel = selected ? projects.find((p) => p.id === selected) || null : null;

  useEffect(() => { onSelectionChange?.(!!sel); }, [sel, onSelectionChange]);
  useEffect(() => () => onSelectionChange?.(false), [onSelectionChange]);
  useEffect(() => {
    setScope("competitive", { projects: rows.length, competitor: co ? co.cid : null }, {
      pillar: "Competitive", view: "Projects", selection: sel ? sel.name : co ? co.name : null,
    });
  }, [rows.length, co, sel, setScope]);

  const report = useMemo(() => ({
    title: sel ? sel.name : `${co ? co.name : "All competitors"}: projects`,
    subtitle: sel ? `${sel.company} · ${sel.stage}` : `${rows.length} projects`,
    sections: [{ heading: sel ? "Project" : "Projects on record", facts: (sel ? [sel] : rows).map((p) => [`${p.company}: ${p.name}`, `${p.stage}. ${p.stageNote}`]) }],
    payload: { projects: sel ? [sel] : rows },
  }), [sel, rows, co]);
  useHeaderReport(report);

  const item = (id, name, n, dot) => (
    <div
      className={`pat-li${id === cid ? " active" : ""}`}
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
        </div>
        <div id="patc-list">
          {item(ALL, "All competitors", total, null)}
          {shown.map((r) => item(r.cid, r.name, perCompetitor[r.cid] || 0, r.threat))}
        </div>
      </div>

      <div className="ov-wrap">
        <div className="feed-grp-h ov-fixed-header">
          <span className="eyebrow">{co ? co.name : "All competitors"}</span>
          <FeedFilters
            active={filter}
            counts={counts}
            filters={[{ f: "all", l: "All" }, ...cfgFilters]}
            onFilter={setFilter}
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
                      <div className="ttl">{p.name}</div>
                      <div className="sowhat">{p.stageNote}</div>
                      <div className="koel-prod-highlight-row">
                        <span className="kph-label">{p.stage}:</span>
                        <span className="kph-val">{[cid === ALL ? p.company : null, p.customer, p.location].filter(Boolean).join(" · ")}</span>
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
          {sel ? <ProjectPanel onClose={() => setSelected(null)} words={words} p={sel} regionLabel={((cfgFilters.find((f) => f.f === sel.region) || {}).l) || sel.region || ""} steps={cfg.stageSteps || []} /> : null}
        </div>
      </div>
    </div>
  );
}
