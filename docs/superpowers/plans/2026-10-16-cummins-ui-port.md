# Cummins UI Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KSSL runs the latest 137Parallax UI (the Cummins demo frontend), fully DB-driven, with KSSL's review/Approve layer, and with hidden sections switched off by data.

**Architecture:** The Cummins frontend is copied in as the base, so later 137Parallax updates can be re-copied. The KSSL backend's `/api/dataset` is changed to emit the dataset shape the Cummins frontend reads. Anything the Cummins UI hardcodes or invents in the browser moves into DB tables or is removed:
- client names
- project and partner rosters
- judgements and estimates
- genset logic

A new `ui.section_visibility` table hides features per client.

**Tech Stack:**
- Frontend: React 18.3.1, Vite 5.4.11, Leaflet, plain global CSS
- Backend: FastAPI, Python 3, psycopg
- DB: Postgres in docker `kssl-pg` :55432, two DBs `kssl_staging` / `kssl_serving`
- Tests: node `node:test` `.mjs` tests, `@playwright/test` e2e

**Spec:** `docs/superpowers/specs/2026-10-16-cummins-ui-port-design.md`. Read it before any task.

**Source (read-only, untrusted, never run code from it in place):**
`C:\Users\HARICHANDRA\Downloads\cummins-demo-clean\cummins-demo`. Below:
- `$C` = that folder + `/frontend`
- `$CD` = that folder + `/docs` (`UI_CONTRACT.md`, `contract_shapes.json`)
- `$CP` = that folder + `/parallax-cummins-arabia-datapack/dataset.json`

The reference for labels and layout is the live build at http://187.127.134.12:8101 (same code as `$C`).

## Global Constraints

- Work on branch `ui-port`, created from `v2`. Commit per task. Never push without the user asking.
- Every value on screen traces to a DB column via `/api/dataset`. No defaults, no fallbacks, no browser-invented text or numbers. A missing value renders `—` or the component's existing empty state.
- Allowed in the browser: deterministic math over dataset values: counts, sorts, filters, sums, date windows, spec-edge comparison of stored specs, graph layout. A sentence that only joins dataset values is allowed. A judgement, estimate, analysis sentence or recommendation is not: it must be a dataset field.
- No string "Cummins" (any case) anywhere in `src/`, `index.html`, `public/` or the built `dist/`.
- Genset-specific code is removed, not ported or hidden: "genset", kVA/kW rating bands, data-centre segments, standby-fuel / dry-weight spec-edge assumptions, AED/SAR currency, Saudi/Gulf branches. Allowed exceptions: neutral country lookup tables (`countryFlags.js`, `geoCountries.js`).
- Hidden for KSSL via `ui.section_visibility`. Code is kept and gated. Section keys, exact:
  - `gap-analysis`
  - `finances`
  - `stock`
  - `parallax-read`
  - `swot`
  - `strategic-positioning`
  - `product-images`
  - `chat` (covers MalloryChat, ScopeChat, AskBox)

  A missing key = hidden.
- Exception: `mockStockHistory.js` and `public/product-images/*` (Cummins photos) are deleted. They are fabricated or foreign data, not features.
- KSSL-only behaviour must survive:
  - review mode (`npm run dev:review` → :5180, backend `KSSL_VIEW=review` :8601), with `<Review src={item._src}/>` on every card
  - `ReviewList` on list pages, `ReviewProvider` in `DataProvider`
  - Trace via `fact_source`
  - live Google News headlines through the Vite `/api/pulse` lane
- Writes to `serving.*` / `ui.*` happen only through Approve (guard triggers in `db/migrations/001_staging.sql` stay).
- New tables exist in both DBs: `staging.X` + `serving.X`, or `staging_ui.X` + `ui.X`. Each content table gets `source_url text` and `source_tier text`. They are added to `backend/review.py` `GRAPH` and to the full test seed.
- Real DBs (`kssl_staging`, `kssl_serving`) are never truncated or reseeded by this work. Tests use `bash db/make_test_pair.sh --approve-all` (`kssl_test_staging` / `kssl_test_serving`) and test backends on :8610 (live) / :8611 (review).
- The test seed stays fictional: names end "(TEST)" and links go to example.com/.org/.net.
- The parallax-agent widget is out of scope.

## Review Focus

1. **Empty serving DB** (nothing approved yet): every route renders its empty state, with no ErrorBoundary and no crash. Test is in Task 11, `e2e: empty dataset`.
2. **Null field inside a record** (tender with no value, competitor with no HQ): it shows `—`, never `undefined`, `NaN`, `null` or `0`. Test is in Task 11, a body-text scan on every route.
3. **Card with no `_src`** in review mode: the buttons disappear silently, so the card can never be approved. Task 4's contract check asserts every card-list item has `_src.t` and `_src.id`.
4. **Hidden section opened by deep link** (`#p=competitive&v=gap-analysis`): it falls back to the pillar's first visible view and never renders the hidden one. Test is in Task 8.
5. **Non-ASCII and HTML-special names** (Arabic issuer text, "L&T (TEST)"): they render literally, not escaped twice and not dropped. The fixture includes both (Task 3 seed). Task 11 asserts they show.

---

### Task 1: Field-by-field mapping (analysis only, no code)

**Files:**
- Create: `docs/ui_port/MAPPING.md`

**Interfaces:**
- Produces `docs/ui_port/MAPPING.md`, which every later task reads. It has four sections, with these exact headings:
  - **`## A. Dataset globals`**: one row per field that `$C/src` reads. Columns:
    - `global`
    - `field`
    - `read by` (file)
    - `disposition`
    - `KSSL source` (`schema.table.column` or the new table name)

    `disposition` is one of:
    - `existing`: a column already exists
    - `derived-ok`: allowed math
    - `new-table`: a judgement, estimate or hardcoded data, so it needs a column
    - `remove-genset`
    - `hidden:<key>`
  - **`## B. Hardcoded data in code`**: every exported constant array or object in `$C/src/lib/*.js` that holds records, for example:
    - `PROJECTS_DATA` / `PROJECT_STAGES` in `competitorProjects.js`
    - the rosters in `partners.js`
    - the lens text in `newsLenses.js`
    - the report text in `reports.js`
    - the tables in `glance.js`

    Each gets its target global and table.
  - **`## C. New tables`**: the final DDL-level list, each line `schema.table(col type, …)` for both DBs. It includes `ui.section_visibility(section_key text primary key, visible boolean not null, note text)`.
  - **`## D. Strings`**: every `/cummins|genset|kva|data.?cent|\bAED\b|\bSAR\b|saudi|gulf/i` hit in `$C/src` (file:line), with its disposition: `client-field`, `dataset-field`, `remove-genset` or `allowlisted`.

- [ ] **Step 1: Create branch.** Run `git checkout v2 && git checkout -b ui-port`. Expected: `Switched to a new branch 'ui-port'`.
- [ ] **Step 2: Fill sections A–D.** Sources, in this order:
  1. `$CD/UI_CONTRACT.md` §15 and §18
  2. `$CD/contract_shapes.json`
  3. grep of `$C/src` for `d\.\w+`, `data\.\w+` and `dataset\.\w+`
  4. the KSSL side: `curl -s http://127.0.0.1:8600/api/dataset` keys, `backend/areas/*.py`, and `/api/manifest` for the table and column list

  Reuse existing tables wherever one fits. Create `new-table` only when no column holds the value.
- [ ] **Step 3: Self-check.** Every global in `$CP` keys and every global the `$C/src` grep finds appears in section A. Every exported record constant appears in section B. Run `grep -ciE "cummins|genset" docs/ui_port/MAPPING.md`. Expected: non-zero (section D lists them).
- [ ] **Step 4: Commit.** `git add docs/ui_port/MAPPING.md && git commit -m "docs(ui-port): dataset field mapping, new tables, string dispositions"`

### Task 2: Import the Cummins frontend as the base

**Files:**
- Replace with `$C` copies:
  - `src/**`
  - `index.html`
  - `vite.config.js`
  - `playwright.config.mjs`
  - `tests/e2e/**`
  - the root `test_*.mjs` / `check_*.mjs` / `ui_audit.mjs` / `build_html.mjs` / `fixture_partner_overlap.json`
- Keep the KSSL versions: `src/components/review/Review.jsx`, `src/styles/review.css`
- Delete:
  - `src/pages/market/TopOpportunity.jsx`
  - `src/lib/mockStockHistory.js`
  - `public/product-images/`
  - `public/local-photos/bel-*`
- Copy `$C/public/ops`, and `$C/public/local-photos` minus any Cummins product photos.
- Modify `package.json`:
  - add devDependency `"@playwright/test": "^1.63.0"`
  - keep script `"dev:review": "vite --mode review"`
  - add `"test": "node --test test_*.mjs src/lib/*.test.mjs"`

**Interfaces:**
- Produces: the Cummins tree at the repo root with KSSL's review files present but not yet wired. Tasks 4–10 edit these files.

- [ ] **Step 1: Copy.** Use `cp -r` from `$C`. Do not copy `node_modules/` or `dist/`. Run `npm install`.
- [ ] **Step 2: Restore the KSSL-only files** listed above. Remove imports of deleted modules. A stock chart that imported `mockStockHistory` now reads the dataset's stock global (named in MAPPING.md A) and renders nothing when it is absent.
- [ ] **Step 3: Verify the build.** Run `npm run build`. Expected: exits 0. Runtime against the KSSL backend may fail until Task 4. That is expected.
- [ ] **Step 4: Commit.** `git add -A && git commit -m "feat(ui-port): import latest 137Parallax frontend (Cummins demo) as base"`

### Task 3: Schema for the new tables

**Files:**
- Create: `db/migrations/003_ui_port.sql`
- Modify:
  - `db/make_databases.sh` (only if it lists migrations explicitly)
  - `backend/review.py` (`GRAPH`)
- Create: `db/test_seed_full/90_ui_port.sql`

**Interfaces:**
- Consumes: MAPPING.md section C.
- Produces:
  - every table in section C, in both DBs, with the guard triggers on `serving`/`ui` copies (same pattern as `001_staging.sql`)
  - `GRAPH` entries so Approve copies the new card tables with their children and `fact_source`
  - `ui.section_visibility` seeded in the test seed with the 8 keys from Global Constraints, all `visible=false`, plus one non-hidden key, `visible=true`, so the gating is exercised
  - seed rows that include an Arabic-script string and "L&T (TEST)" (Review Focus 5)

- [ ] **Step 1: Write the failing check.** Run `bash db/make_test_pair.sh --approve-all`. Expected before the migration: no FAIL lines, and the new tables don't exist yet. After the migration but before the seed: a FAIL line for each new empty table. That is the red state.
- [ ] **Step 2: Write `003_ui_port.sql`.** Idempotent (`create table if not exists`), staging side and serving side.
- [ ] **Step 3: Write `90_ui_port.sql`.** Multi-row INSERTs, at least 3 rows per content table, deleting its own rows first like the other seed files.
- [ ] **Step 4: Verify.** Run `bash db/make_test_pair.sh --approve-all`. Expected: the coverage table lists every new table with rows > 0, and there are 0 FAIL lines.
- [ ] **Step 5: Verify Approve.** On the test pair (review backend :8611 per the script's printed commands), approve one card of a new table via `curl -X POST "http://127.0.0.1:8611/api/review?table=<t>&key=<id>&action=approve"`. Expected: HTTP 200, and the row appears in `kssl_test_serving`.
- [ ] **Step 6: Commit.** `git commit -m "feat(db): tables for ui-port (section_visibility + judgement/data tables) with seed"`

### Task 4: Backend emits the Cummins dataset shape, plus the contract check

**Files:**
- Modify: `backend/app.py` (`build_dataset`), `backend/areas/*.py`
- Create: `backend/areas/e_ui_port.py`, only for globals that fit no existing area
- Create: `check_contract.mjs` (repo root)
- Create: `scripts/snapshot_dataset.sh`
- Create: `fixtures/kssl_dataset.json` (generated)

**Interfaces:**
- Consumes: MAPPING.md section A; the tables from Task 3.
- Produces:
  - `/api/dataset` returns every global in MAPPING.md A with the container type the frontend indexes into (list vs dict, per UI_CONTRACT §15 "presence is not shape"). This includes `sectionVisibility: {[key: string]: boolean}` and `client: {id, name, short, …}` (fields per MAPPING).
  - Every card-list item keeps `_src: {t, k, id}`.
  - `scripts/snapshot_dataset.sh [url]`: default url `http://127.0.0.1:8610/api/dataset`. It writes `fixtures/kssl_dataset.json`.
  - `node check_contract.mjs <dataset.json>`: exits 0 if every MAPPING.md A global is present with the right container type and every card-list item has `_src.t` and `_src.id`. Otherwise it exits 1 and prints one line per violation.

- [ ] **Step 1: Write `check_contract.mjs`.** It reads the expected globals and types from a `const EXPECTED = {global: "list"|"dict", …}` built from MAPPING.md A, and from the card-list globals (`competitiveCards`, `marketCards`, `techCards` and the others MAPPING marks as cards).
- [ ] **Step 2: Run it against the current backend to see it fail.** Start the test backends, run `bash scripts/snapshot_dataset.sh`, then `node check_contract.mjs fixtures/kssl_dataset.json`. Expected: exit 1, with missing globals listed.
- [ ] **Step 3: Implement the backend changes** until the check passes. The backend maps columns into shape. It never fills a missing value with a default.
- [ ] **Step 4: Verify.** Re-snapshot, then run `node check_contract.mjs fixtures/kssl_dataset.json` (expected: exit 0) and `node check_data.mjs fixtures/kssl_dataset.json` (expected: runs to the end without throwing).
- [ ] **Step 5: Run it in the browser.** Run `KSSL_API_TARGET=http://127.0.0.1:8610 npx vite --port 5190`. Open `#p=competitive&v=overview`. Expected: the shell and the cards load. Cummins strings are still present; that is fixed in Task 5.
- [ ] **Step 6: Commit** the backend, check, script and fixture: `git commit -m "feat(api): dataset in 137Parallax shape + contract check + test fixture"`

### Task 5: Client layer; no "Cummins" anywhere

**Files:**
- Create: `src/lib/client.js`, `test_client.mjs`
- Modify:
  - every file listed as `client-field` in MAPPING.md D
  - `src/state/DataProvider.jsx` (calls `setClient(data.client)` after `wireDataset`)
  - `index.html` (neutral `<title>137Parallax</title>`; `document.title` is set from the client at load)
  - `check_no_fabrication.mjs` (BANNED gains `["Cummins", "client name hardcoded in UI"]`)

**Interfaces:**
- Produces, in `src/lib/client.js`:
  - `setClient(client: object|null): void`
  - `clientName(): string` (returns `client.name`, `""` if unset)
  - `clientShort(): string` (returns `client.short`, falling back to `client.name`, `""` if unset)

  It has no other fallback. Matches the API that `$CD/CLIENT_PACKS.md` describes.

- [ ] **Step 1: Write the failing test** `test_client.mjs`:
  - after `setClient({name:"KSSL Test", short:"KSSL"})`: `clientName()==="KSSL Test"` and `clientShort()==="KSSL"`
  - after `setClient({name:"X"})`: `clientShort()==="X"`
  - after `setClient(null)`: both return `""`
- [ ] **Step 2:** `node --test test_client.mjs`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `client.js`**, then replace every `client-field` string in MAPPING.md D with `clientName()` or `clientShort()`. That includes the `|| "Cummins Arabia"` fallbacks, such as `dataset.js:484`, which become no fallback.
- [ ] **Step 4: Verify.**
  - `node --test test_client.mjs` → PASS
  - `grep -rniI cummins src index.html public` → no output
  - `npm run build && node check_no_fabrication.mjs` → exit 0
- [ ] **Step 5: Commit.** `git commit -m "feat(ui-port): client name from data; no hardcoded Cummins"`

### Task 6: Hardcoded record data moves to the dataset

**Files:**
- Modify: every module in MAPPING.md B (at least `src/lib/competitorProjects.js`, `src/lib/partners.js`, `src/lib/newsLenses.js`, `src/lib/reports.js`) and their callers.
- Modify: the matching `test_*.mjs` / `src/lib/*.test.mjs`. They read `fixtures/kssl_dataset.json` instead of the Cummins datapack.

**Interfaces:**
- Consumes: the globals Task 4 ships for these records.
- Produces: the same function names and return shapes those modules exported before (so pages don't change). The difference is that they take the wired dataset `d` as a parameter, or read the global through the existing DataProvider context, rather than reading a module constant. Exported record constants are deleted.

- [ ] **Step 1: Repoint the tests to `fixtures/kssl_dataset.json`.** Take `src/lib/projects.test.mjs`, the partner tests and `test_partner_overlap*.mjs`. Expected: FAIL while the constants still exist. Add one assertion per module: the module source no longer contains the exported constant, e.g. `assert.ok(!/export const PROJECTS_DATA/.test(fs.readFileSync(...)))`.
- [ ] **Step 2: Implement:** delete the constants and read from `d`.
- [ ] **Step 3: Verify.** Run `npm test` and expect these modules' tests to PASS. Then run `npm run build && node check_no_fabrication.mjs`. Before running it, add to BANNED three distinctive project/partner names taken from the deleted Cummins constants. Expected: exit 0.
- [ ] **Step 4: Commit.** `git commit -m "feat(ui-port): projects/partners/lens/report records come from the dataset"`

### Task 7: Remove genset-specific code; move judgements to fields

**Files:**
- Modify: every MAPPING.md D `remove-genset` site, plus `src/lib/threat.js`, `src/lib/tenderIntel.js`, `src/lib/shortlist.js`, `src/lib/marketOutlook.js`, `src/lib/glance.js`, `src/lib/gapAnalysis.js` (gated, but must not invent), and `src/lib/specs.js` (the spec-edge assumptions).
- Create: `check_no_genset.mjs`
- Modify: `test_threat_logic.mjs`, `test_tender_intel.mjs`, `test_overview_shortlist.mjs`, `test_spec_units.mjs`

**Interfaces:**
- Consumes: the judgement fields from Task 4 (names per MAPPING.md A, `new-table` rows). Examples:
  - tender fit grade
  - revenue estimate
  - threat level/reason
  - outlook text
- Produces:
  - Each former browser judgement returns the dataset field, or `null`. Callers render `null` as `—` or the empty state.
  - `node check_no_genset.mjs`: exit 0 when `src/` has no match for `/genset|\bkva\b|\bkw\b band|data.?cent|\bAED\b|\bSAR\b|saudi|gulf/i` outside the allowlist (`src/lib/countryFlags.js`, `src/lib/geoCountries.js`). Otherwise exit 1, with file:line.

- [ ] **Step 1: Write the failing tests:**
  - `test_tender_intel.mjs`: a tender with no fit field → fit `null`; a tender with fit `"good"` → `"good"`; revenue estimate absent → `null`, never a computed number.
  - `test_threat_logic.mjs`: threat comes from the competitor's field; absent → `null`.
  - Run `node check_no_genset.mjs`. Expected: all FAIL.
- [ ] **Step 2: Implement.** Delete the genset branches and features that exist only for them (MAPPING D). Replace the computed judgements with field reads.
- [ ] **Step 3: Verify.** `npm test` (these tests PASS) and `node check_no_genset.mjs` (exit 0).
- [ ] **Step 4: Commit.** `git commit -m "feat(ui-port): remove genset-specific logic; judgements read from data"`

### Task 8: Section visibility gating

**Files:**
- Create: `src/lib/visibility.js`, `test_visibility.mjs`
- Modify:
  - `src/state/DataProvider.jsx` (`setVisibility(data.sectionVisibility)`)
  - `src/lib/route.js` (`RAIL` filtered; unknown or hidden view → first visible view of the pillar)
  - `src/lib/search.js` (hidden sections not indexed)
  - `src/lib/overview.js` `navCounts` (no badge for hidden views)
  - the components/pages hosting each key: Gap Analysis, Finances, the stock chart in Profile, the Parallax Read box, SWOT, Strategic Positioning, `Thumb` photos, `MalloryChat`/`ScopeChat`/`AskBox`

**Interfaces:**
- Produces:
  - `setVisibility(map: {[key]: boolean}|null): void`
  - `isVisible(key: string): boolean` (true only if `map[key] === true`)
  - `firstVisibleView(pillar: string): string`
- Each hidden section's wrapper renders `null` when `!isVisible(key)`.

- [ ] **Step 1: Write the failing test** `test_visibility.mjs`:
  - `isVisible("stock")` is `false` for `{}`, `null` and `{stock:false}`, and `true` for `{stock:true}`
  - with `{"gap-analysis":false}`, the route for `#p=competitive&v=gap-analysis` resolves to `firstVisibleView("competitive")` and is not `gap-analysis` (Review Focus 4)
  - the `navCounts` result has no `gap-analysis` key
- [ ] **Step 2:** `node --test test_visibility.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** `visibility.js` and gate every section listed.
- [ ] **Step 4: Verify.** `node --test test_visibility.mjs` → PASS. In the browser (Task 4's :5190), none of the 8 sections appears, the rail has no Gap Analysis or Finances, and Ctrl+K search for "SWOT" returns no section.
- [ ] **Step 5: Commit.** `git commit -m "feat(ui-port): ui.section_visibility gates hidden sections"`

### Task 9: Re-apply the review layer

**Files:**
- Modify:
  - `src/state/DataProvider.jsx` (wrap in `ReviewProvider initial={data.review}`, as the KSSL version did; copy that wiring from `git show v2:src/state/DataProvider.jsx`)
  - every card-rendering component and page: at least the 16 files that imported `Review`/`ReviewList` on `v2` (`git grep -l "review/Review" v2 -- src`), plus the new ones, `src/components/tenderCockpit/TenderCockpit.jsx`, `src/components/marketOutlook/MarketOutlook.jsx`, and any card list MAPPING marks as cards
- Create: `tests/e2e/review.spec.mjs`

**Interfaces:**
- Consumes: `Review`, `ReviewList` and `ReviewProvider` from `src/components/review/Review.jsx` (unchanged), and `_src` on items (Task 4).
- Produces: in review mode, a `.rv-bar` on every card of every card route. In the live build, nothing renders (`REVIEW` false).

- [ ] **Step 1: Write the failing e2e.** `tests/e2e/review.spec.mjs` uses baseURL `http://127.0.0.1:5191` (the review vite: `KSSL_API_TARGET=http://127.0.0.1:8611 npx vite --mode review --port 5191`). For each card route in `RAIL` (overview, profile, products, partnerships, projects, geo, patents-comp, m-overview, tender, global-requirement, t-overview, innovation): at least one `.rv-bar` is visible, and `.rv-banner` is visible. Run `npx playwright test tests/e2e/review.spec.mjs`. Expected: FAIL.
- [ ] **Step 2: Implement:** add `<Review src={x._src}/>` at each card's header, as on `v2`.
- [ ] **Step 2b: Carry over the other KSSL-only behaviour that Task 2 overwrote.** Run `git diff v2 -- src/components/sourceLink src/api/client.js src/components/ErrorBoundary.jsx src/components/thumb`. Re-apply the KSSL-only parts:
  - Trace / `fact_source` links in `SourceLink`
  - the API base and proxy handling in `api/client.js`
  - the error copy, which must not name a client

  Everything else stays as Cummins has it.
- [ ] **Step 3: Verify.** The same e2e command → PASS. Then `npm run build && grep -c rv-bar dist/assets/*.js`. The class name is present, but the live preview at :5190 shows no `.rv-bar`; check with a one-line Playwright assertion in the same spec, run against :5190.
- [ ] **Step 4: Commit.** `git commit -m "feat(ui-port): review/approve/trace controls on every card"`

### Task 10: Vite lanes: live headlines kept, stock removed

**Files:**
- Modify: `vite.config.js`, `src/lib/pulseFetch.js`

**Interfaces:**
- Produces:
  - `/api/pulse?cid=&name=&product=` keeps working (live Google News headlines, the agreed exception)
  - `/api/pulse/history` and every Yahoo/stock fetch are removed
  - `/api/img` stays only if a visible component still uses it; otherwise it is removed
  - `/api/dataset` is proxied to `KSSL_API_TARGET` (default `http://127.0.0.1:8600`), as on `v2`

- [ ] **Step 1: Write the failing check.** `grep -niE "yahoo|pulse/history" vite.config.js src -r`. Expected: matches (red).
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Verify.**
  - The grep above → no output.
  - With vite running: `curl -s "http://127.0.0.1:5190/api/pulse?cid=x&name=Larsen%20%26%20Toubro"` returns JSON with a headlines list.
  - `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5190/api/pulse/history` → `404`.
- [ ] **Step 4: Commit.** `git commit -m "feat(ui-port): keep live headlines lane, drop stock lanes"`

### Task 11: Port the remaining tests; full verification

**Files:**
- Modify: every remaining `test_*.mjs` / `src/lib/*.test.mjs` that still reads the Cummins datapack. It reads `fixtures/kssl_dataset.json` instead. A test whose subject was deleted in Tasks 6–7 is deleted with it.
- Modify: `tests/e2e/frontend.spec.mjs` (baseURL `http://127.0.0.1:5190`), and add the cases below.
- Modify: `README.md` (how to run tests, the visibility table, the test pair).

**Interfaces:**
- Consumes everything above.

- [ ] **Step 1: Add e2e cases** to `frontend.spec.mjs`:
  - `every route renders`: for each `RAIL` view, no `ErrorBoundary` text, and `document.body.innerText` does not match `/\bundefined\b|\bNaN\b|\[object Object\]|cummins|genset/i` (Review Focus 2).
  - `special names`: the Arabic-script seed string and `L&T (TEST)` are visible somewhere in their pages, not as `&amp;` (Review Focus 5).
  - `e2e: empty dataset`: run `bash db/make_test_pair.sh` without `--approve-all`, restart the :8610 backend, and confirm every route renders with no ErrorBoundary (Review Focus 1). Restore it with `--approve-all` afterwards.
- [ ] **Step 2: Run everything:**
  - `npm test` → all PASS
  - `node check_contract.mjs fixtures/kssl_dataset.json` → exit 0
  - `node check_no_genset.mjs` → exit 0
  - `npm run build && node check_no_fabrication.mjs` → exit 0
  - `node check_no_undefined_names.mjs` → exit 0
  - `npx playwright test` → all PASS
  - `bash db/make_test_pair.sh --approve-all` → 0 FAIL lines
- [ ] **Step 3: Visual comparison with :8101.** Take a Playwright screenshot of each `RAIL` route on :5190, and of the same route on http://187.127.134.12:8101. Save both under `docs/ui_port/screens/`. The layout, labels and components match, except for sections hidden by design and genset features removed by design. List every difference in `docs/ui_port/VERIFY.md` with its reason.
- [ ] **Step 4: Commit.** `git commit -m "test(ui-port): tests on KSSL fixture, e2e, verification notes"`
