/* Projects feed: what each competitor is working on or pursuing. Pure -- the page renders what this returns.
   The rows are data.projects (serving.competitive_project and its child tables); the region filters and the
   sequence menu are front-end chrome (chrome.js); the stage steps are data.projectsConfig.stageSteps (the stages the
   projects carry). Nothing here is a record. */
import { formatDate } from "../utils/formatDate.js";

/* The stance of a project is its stored `assessment.stance`: threat or watch, nothing else (chrome.stanceOf). */

export const day = (d) => (d && /^\d{4}/.test(d) ? (/^\d{4}$/.test(d) ? `${d}-01-01` : /^\d{4}-\d{2}$/.test(d) ? `${d}-01` : d) : "");

export const latestWhen = (p) => (p.latest && p.latest.date ? formatDate(p.latest.date) : "");

/* The sorts the browser can do on stored values. A menu entry whose code is not here (a size or value
   sort: no numeric column holds it) is not offered -- see sortableSeq. */
const SEQ = {
  recent: (a, b) => day(b.latest && b.latest.date).localeCompare(day(a.latest && a.latest.date)),
  stage: (a, b) => (b.stageRank || 0) - (a.stageRank || 0) || SEQ.recent(a, b),
};
export const sortableSeq = (options) => (options || []).filter((o) => o && SEQ[o[0]]);

const haystack = (p) =>
  [p.name, p.company, p.customer, p.location, p.kind, p.stage, p.stageNote, (p.overview || []).join(" "), (p.specs || []).map((s) => s.v).join(" ")].join(" ").toLowerCase();

/* `cid` null = every competitor. `filters` is the chrome filter list (chrome.js; their codes are matched against the stored `region`). `counts` is what each button would show
   under the current competitor and search, so no button promises rows it lacks; `perCompetitor` is each
   rival's count under the current region filter and search. */
export function projectFeed({ projects, filters = [], cid = null, filter = "all", query = "", seq = "recent" } = {}) {
  projects = projects || [];
  const tokens = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
  const searched = projects.filter((p) => tokens.every((t) => haystack(p).includes(t)));
  const mine = cid ? searched.filter((p) => p.cid === cid) : searched;
  const counts = { all: mine.length };
  filters.forEach(({ f }) => { counts[f] = mine.filter((p) => p.region === f).length; });
  const inRegion = (p) => filter === "all" || p.region === filter;
  const perCompetitor = {};
  searched.filter(inRegion).forEach((p) => { perCompetitor[p.cid] = (perCompetitor[p.cid] || 0) + 1; });
  const rows = mine.filter(inRegion).slice().sort(SEQ[seq] || SEQ.recent);
  return { rows, counts, perCompetitor, total: projects.length };
}

/* the tiles above the list, counted from the rows */
export function projectMetrics(projects) {
  projects = projects || [];
  const rivals = new Set(projects.map((p) => p.cid)).size;
  return [
    { act: "all", l: "Projects tracked", v: String(projects.length), unit: " projects" },
    { act: "rivals", l: "Competitors covered", v: String(rivals), unit: " companies" },
    { act: "threat", l: "Read as a threat", v: String(projects.filter((p) => p.assessment && p.assessment.stance === "threat").length), unit: " projects" },
  ];
}
