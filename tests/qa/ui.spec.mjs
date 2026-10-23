// @ts-check
import { test, expect } from "@playwright/test";

/* QA suite, UI layer: the database data the API sends is what the screen shows (the database -> API half is
   tests/qa/test_trace.py). Runs on both sites (playwright.qa.config.mjs projects "live" :5178 and "review" :5180).
   Read-only: the usage tracker and page recorder are muted (window.__ksslReplay), so a run leaves no visits behind.
   Each title is "ID · what"; steps and expected result are annotations, collected into the QA workbook. */

const ROUTES = [
  ["competitive", "overview"], ["competitive", "profile"], ["competitive", "threat-analysis"], ["competitive", "products"],
  ["competitive", "positioning"], ["competitive", "partnerships"], ["competitive", "projects"], ["competitive", "geo"],
  ["competitive", "patents-comp"], ["market", "m-overview"], ["market", "tender"], ["market", "global-requirement"],
  ["market", "m-report"], ["technology", "t-overview"], ["technology", "innovation"],
];
const BAD_TEXT = /\bundefined\b|\bNaN\b|\[object Object\]|\{\{|\}\}/;
const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const site = () => test.info().project.name;
const doc = (steps, expected) => {
  test.info().annotations.push({ type: "steps", description: steps }, { type: "expected", description: expected });
};

const DATA = {};   // per site: one worker can run tests of both projects
const data = async (request) => (DATA[site()] ||= await (await request.get("/api/dataset", { timeout: 180000 })).json());

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__ksslReplay = true;                                    // tracker + recorder muted
    try { localStorage.setItem("kssl_user", "qa-bot"); } catch (e) { /* storage blocked */ }
  });
});

const open = async (page, pillar, view) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`/#p=${pillar}&v=${view}`);
  await page.locator(".rail .svc").first().waitFor({ state: "visible", timeout: 60000 });
  await page.waitForTimeout(1200);
  return errors;
};

// every string in the dataset: a link on screen must be one of them (the UI never makes up a link)
const allStrings = (o, out = new Set()) => {
  if (typeof o === "string") out.add(o);
  else if (Array.isArray(o)) o.forEach((v) => allStrings(v, out));
  else if (o && typeof o === "object") Object.values(o).forEach((v) => allStrings(v, out));
  return out;
};
const CHROME_LINKS = /^https:\/\/(www\.esri\.com|www\.openstreetmap\.org|leafletjs\.com)/;

for (const [pillar, view] of ROUTES) {
  test(`UI-001 · ${pillar}/${view} renders without errors`, async ({ page }) => {
    doc(`Open #p=${pillar}&v=${view}; wait for the app; read the page text and script errors.`,
      "No script error, no leaked program value (undefined, NaN, [object Object], {{ }}), the page has content.");
    const errors = await open(page, pillar, view);
    const text = await page.locator("main, .shell").first().innerText();
    expect(errors, "script errors").toEqual([]);
    expect(text.match(BAD_TEXT), "leaked program value").toBeNull();
    expect(text.replace(/\s+/g, "").length).toBeGreaterThan(200);
  });

  test(`UI-002 · ${pillar}/${view} links only to sources the database holds`, async ({ page, request }) => {
    doc(`Open #p=${pillar}&v=${view}; collect every external link (a[href^=http]); compare with every string in /api/dataset.`,
      "Every link on screen is a url the API sent (taken from the database); none is invented or rewritten.");
    const known = allStrings(await data(request));
    await open(page, pillar, view);
    const hrefs = await page.locator("a[href^='http']").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
    const strange = [...new Set(hrefs)].filter((h) => !known.has(h) && !CHROME_LINKS.test(h));
    expect(strange, "links not in the dataset").toEqual([]);
  });
}

/* Search -> open: a sample of each searchable kind, found through the global search and opened, shows its data. */
const KINDS = {
  tenders: (j) => j.tenders.map((t) => ({ q: t.title, show: [t.title, t.issuer] })),
  signals: (j) => j.competitiveCards.map((c) => ({ q: c.title, show: [c.title, c.company] })),
  competitors: (j) => Object.values(j.competitors).map((c) => ({ q: c.name, show: [c.name] })),
  innovations: (j) => Object.values(j.innovations).flat().map((x) => ({ q: x.t, show: [x.t] })),
};
for (const [kind, pick] of Object.entries(KINDS)) {
  test(`UI-010 · ${kind}: found by search and shown with their data`, async ({ page, request }) => {
    doc(`Take 3 ${kind} from /api/dataset (first, middle, last); type each title into the top-bar search; click the hit;
      read the page.`, "Each is found, opens, and the page shows its title and its key field (e.g. tender issuer, signal company).");
    const raw = pick(await data(request)).filter((x) => x.q && x.q.length > 4 && !/[–—]/.test(x.q));   // dashes: UI-011
    const seen = {};
    raw.forEach((x) => { seen[x.q] = (seen[x.q] || 0) + 1; });
    const all = raw.filter((x) => seen[x.q] === 1);                    // a title shared by several rows is ambiguous
    const sample = [all[0], all[Math.floor(all.length / 2)], all[all.length - 1]];
    await open(page, "competitive", "overview");
    for (const it of sample) {
      await page.locator(".topbar-search-input").fill(it.q.slice(0, 60));
      const hit = page.locator(".topbar-search-item").filter({ hasText: new RegExp(it.q.slice(0, 20).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i") }).first();
      await expect(hit, `search finds "${it.q.slice(0, 50)}"`).toBeVisible({ timeout: 10000 });
      await hit.click();
      await page.waitForTimeout(1500);
      const body = norm(await page.locator("body").innerText());
      for (const s of it.show.filter((v) => v && v.length > 2)) expect(body, `page shows "${s.slice(0, 50)}"`).toContain(norm(s).slice(0, 30));
    }
  });
}

test("UI-011 · a title with a dash, as stored in the database, is found by search", async ({ page, request }) => {
  doc("Take a tender whose stored title has an en dash (–); type that exact title into the top-bar search.",
    "The tender is found. (The page shows such titles with a plain hyphen -- src/lib/dataset.js rewrites dashes -- so the search must treat both alike.)");
  const t = (await data(request)).tenders.find((x) => /\s–\s/.test(x.title || ""));
  test.skip(!t, "no tender title with an en dash");
  await open(page, "competitive", "overview");
  const at = t.title.search(/\s–\s/);
  const q = t.title.slice(Math.max(0, at - 15), at + 20);         // the words around the dash, dash included
  await page.locator(".topbar-search-input").fill(q);
  await page.waitForTimeout(1200);
  await expect(page.locator(".topbar-search-item").first(), `search for "${q}"`).toBeVisible({ timeout: 5000 });
});

/* Full lists: views that list every row of their collection. */
const FULL = [
  ["competitive", "profile", (j) => Object.values(j.competitors).map((c) => c.name), "every competitor (and KSSL)"],
  ["competitive", "projects", (j) => j.projects.map((p) => p.name), "every project"],
  ["competitive", "positioning", (j) => [...new Set(Object.values(j.matchups).map((m) => m.compBy))], "every competitor with a product match"],
  ["market", "m-overview", (j) => (j.topOpportunities.tenders || j.topOpportunities.top || Object.values(j.topOpportunities).flat())
    .map((x) => x.tenderTitle || x.title || x.action).filter(Boolean).slice(0, 15), "the top opportunities"],
];
for (const [pillar, view, pick, what] of FULL) {
  test(`UI-020 · ${pillar}/${view} lists ${what}`, async ({ page, request }) => {
    doc(`Open #p=${pillar}&v=${view}; for each name the API sends for this view, look for it on the page.`,
      `All of ${what} are on screen -- nothing the database holds is dropped by the page.`);
    const names = pick(await data(request)).filter((n) => typeof n === "string" && n.length > 3);
    await open(page, pillar, view);
    const body = norm(await page.locator("body").innerText());
    const missing = names.filter((n) => !body.includes(norm(n).slice(0, 30)));
    expect(missing, `${missing.length} of ${names.length} not shown`).toEqual([]);
  });
}

test("UI-030 · a signal shows its source, and it is the database's link", async ({ page, request }) => {
  doc("Competitive overview: open the first signal card; read its source chips (.srcchip).",
    "At least one source chip; every href is a url of that signal in the dataset (or its archive copy). Signals are news-derived, so both sites show sources.");
  const j = await data(request);
  const known = allStrings(j);
  await open(page, "competitive", "overview");
  await page.locator(".alert").first().click();
  const chips = page.locator(".srcchip");
  await expect(chips.first()).toBeVisible({ timeout: 10000 });
  const hrefs = await chips.evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  expect(hrefs.filter((h) => !known.has(h))).toEqual([]);
});

test("UI-031 · review tools only on the review site", async ({ page }) => {
  doc("Open the competitive overview; look for the review banner (.rv-banner) and Approve / Unpublish buttons.",
    "Review site: banner present. Live site: no banner, no review buttons.");
  await open(page, "competitive", "overview");
  const banner = await page.locator(".rv-banner").count();
  const buttons = await page.getByRole("button", { name: /^(Approve|Unpublish|Reject)/ }).count();
  if (site() === "review") expect(banner).toBeGreaterThan(0);
  else expect(banner + buttons).toBe(0);
});

test("UI-032 · rail counts match the data", async ({ page, request }) => {
  doc("Read the rail's per-view counts (.rail .svc .ct) on Market; compare Tenders and Global Requirements with the API collections.",
    "Each count is at most the size of its collection and greater than 0.");
  const j = await data(request);
  await open(page, "market", "tender");
  const items = await page.locator(".rail .svc").evaluateAll((els) => els.map((e) => ({ n: e.querySelector(".nm")?.textContent?.trim(), c: e.querySelector(".ct")?.textContent?.trim() })));
  const count = (name) => Number((items.find((i) => i.n && i.n.toLowerCase().startsWith(name)) || {}).c);
  const t = count("tender"), g = count("global");
  if (!Number.isNaN(t)) { expect(t).toBeGreaterThan(0); expect(t).toBeLessThanOrEqual(j.tenders.length); }
  if (!Number.isNaN(g)) { expect(g).toBeGreaterThan(0); expect(g).toBeLessThanOrEqual(j.globalRequirements.length); }
});

test("UI-040 · the app is usable within 15 seconds", async ({ page }) => {
  doc("Open the site cold; time until the rail shows.", "Under 15 s on the local machine.");
  const t = Date.now();
  await open(page, "competitive", "overview");
  expect(Date.now() - t).toBeLessThan(15000);
});
