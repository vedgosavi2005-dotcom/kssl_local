import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import { projectFeed, projectMetrics, day } from "./projects.js";
import { PROJECT_FILTERS } from "./chrome.js";

const d = JSON.parse(fs.readFileSync(new URL("../../fixtures/kssl_dataset.json", import.meta.url), "utf8"));
const P = d.projects;
const cfg = { ...d.projectsConfig, filters: PROJECT_FILTERS };

test("the project constants are gone from the code", () => {
  assert.ok(!fs.existsSync(new URL("./competitorProjects.js", import.meta.url)), "competitorProjects.js is deleted");
  const src = fs.readFileSync(new URL("./projects.js", import.meta.url), "utf8");
  assert.ok(!/export const PROJECTS_DATA|PROJECT_STAGES|PROJECT_FILTERS|PROJECT_SEQ|Worldwide/.test(src));
});

test("every fixture project belongs to a tracked competitor and stands on a configured stage and filter", () => {
  assert.ok(P.length > 0);
  const ids = new Set();
  P.forEach((p) => {
    assert.ok(!ids.has(p.id), `duplicate ${p.id}`);
    ids.add(p.id);
    assert.ok(d.competitors[p.cid], `${p.id}: unknown competitor`);
    assert.ok(cfg.stageSteps.includes(p.stage) && cfg.stageSteps.indexOf(p.stage) + 1 === p.stageRank, `${p.id} stage`);
    assert.ok(cfg.filters.some((f) => f.f === p.region), `${p.id} region ${p.region}`);
  });
});

test("the feed filters by competitor and configured region, counts agree", () => {
  const all = projectFeed({ projects: P, filters: cfg.filters });
  assert.equal(all.rows.length, P.length);
  const cid = P[0].cid;
  const mine = projectFeed({ projects: P, filters: cfg.filters, cid });
  assert.ok(mine.rows.every((p) => p.cid === cid) && mine.counts.all === mine.rows.length);
  assert.equal(cfg.filters.reduce((n, f) => n + mine.counts[f.f], 0), mine.counts.all);
  assert.equal(Object.values(all.perCompetitor).reduce((a, b) => a + b, 0), P.length);
  const region = cfg.filters[0].f;
  assert.ok(projectFeed({ projects: P, filters: cfg.filters, filter: region }).rows.every((p) => p.region === region));
});

test("sorting by stage puts the furthest stage first; no sort is offered that has no data behind it", () => {
  const rows = projectFeed({ projects: P, filters: cfg.filters, seq: "stage" }).rows;
  assert.ok(rows.every((p, i) => !i || rows[i - 1].stageRank >= p.stageRank));
  const dated = projectFeed({ projects: P, filters: cfg.filters, seq: "recent" }).rows.map((p) => day(p.latest && p.latest.date));
  assert.deepEqual(dated, [...dated].sort().reverse());
});

test("metrics are counted from the rows, with no region tile", () => {
  const m = projectMetrics(P);
  assert.equal(m[0].v, String(P.length));
  assert.equal(m[1].v, String(new Set(P.map((p) => p.cid)).size));
  assert.equal(m.length, 3);
  assert.ok(!m.some((t) => /region/i.test(t.act)), "no region tile");
  assert.equal(projectMetrics([])[0].v, "0");
});
