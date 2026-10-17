# KSSL_Deploy frontend

React (Vite + React 18) dashboard, adapted from `KSSL-Parallax/web`. The only
functional change from that app: the dataset is **fetched from the backend**
(`GET /api/dataset`) instead of read from an embedded `window.__EMBEDDED_DATASET__`
blob. Everything downstream of the fetch — the 35-global wiring in
`src/lib/dataset.js`, hash routing (`#p=...&v=...`), localStorage route restore,
and the ErrorBoundary around the app and the detail panel — is unchanged.

## Dev

    npm install
    npm run dev          # http://localhost:5178

The dev server proxies `/api` to `http://127.0.0.1:8600` (see `vite.config.js`),
so the FastAPI backend must be running there:

    python -m uvicorn backend.app:app --host 127.0.0.1 --port 8600

Set `KSSL_DSN` to the PostgreSQL connection string before starting the backend;
see `.env.example` for the local format. `GET /api/dataset`
loads every table in the `ui` and `serving` schemas under `database`, includes
all table and column metadata under `databaseSchema`, then builds the UI
contract from those rows. `GET /api/manifest` exposes the same metadata for
verification. With empty tables, the UI shows zero counts and empty states.

## Two databases and the review copy

Everything is written to **kssl_staging** (schemas `staging`, `staging_ui`): Excel loaders, prompt
loaders, the news job, hand inserts (`db/test_inserts_staging.sql`). The live UI reads
**kssl_serving** (`serving`, `ui`), which only Approve / Unpublish in the review copy can write.

    bash db/make_databases.sh                       # create both DBs (idempotent, never drops)
    # live API (:8600) + live UI (:5178)
    KSSL_SERVING_DSN="host=127.0.0.1 port=55432 dbname=kssl_serving user=kssl password=kssl"       python -m uvicorn backend.app:app --host 127.0.0.1 --port 8600
    npm run dev
    # review API (:8601) + review copy (:5180, localhost only)
    KSSL_VIEW=review KSSL_STAGING_DSN="...dbname=kssl_staging..." KSSL_SERVING_DSN="...dbname=kssl_serving..."       python -m uvicorn backend.app:app --host 127.0.0.1 --port 8601
    npm run dev:review

News: `python -m backend.news --competitor all --products --from 2026-09-01 --to 2026-09-30`
(or `--date 2026-09-03`; API `POST /api/news/refresh?...`) writes candidates to `staging.news_candidate`
(holding table, never shown). `python -m prompts.run news` groups the publishers that report the same story and
writes one row per story with its `category` to the news tables (other publishers become extra sources in
`staging.fact_source`); those rows are what the review copy approves.
Audits, rules, plan and answers: `docs/audit_v2/`.

## Tests

Everything runs from the repo root. The unit tests are hermetic; the browser tests need the throwaway test pair.

    npm test                                   # node --test test_*.mjs src/lib/*.test.mjs (hermetic, reads fixtures/kssl_dataset.json)

Static checks (each exits 0 when clean):

    node check_contract.mjs fixtures/kssl_dataset.json   # the dataset carries every global of docs/ui_port/MAPPING.md A with its container type
    node check_data.mjs fixtures/kssl_dataset.json       # market and profile self-checks over the wired dataset
    node check_no_genset.mjs                             # no genset-specific code or words, and no reference-client name, in src/ index.html public/
    npm run build && node check_no_fabrication.mjs       # no browser-invented values in dist/ (run AFTER the build)
    node check_no_undefined_names.mjs                    # no reference to an undefined name
    node check_no_control_bytes.mjs                      # no stray control bytes (a "\b" eaten into 0x08)
    node check_no_emoji.mjs

### The test pair and the two Playwright configs

`db/make_test_pair.sh` builds two throwaway databases, `kssl_test_staging` and `kssl_test_serving` (never the real
`kssl_staging` / `kssl_serving`), and loads the fully fictional seed `db/test_seed_full/*.sql` (every name ends "(TEST)",
every link points at example.com / .org / .net) into staging. It prints a row count per table and a `FAIL` line for every
empty table; a clean run prints "coverage OK".

    bash db/make_test_pair.sh --approve-all    # copy staging -> serving too: the live UI shows data; 0 FAIL lines expected
    bash db/make_test_pair.sh                  # serving stays EMPTY: the live UI is empty, the review copy shows every card as "new"

Start the test backends and the two Vite servers by hand (ports 8610 / 8611 / 5190 / 5191 are reserved for the pair):

    KSSL_DSN="host=127.0.0.1 port=55432 dbname=kssl_test_serving user=kssl password=kssl" python -m uvicorn backend.app:app --port 8610
    KSSL_VIEW=review KSSL_STAGING_DSN="host=127.0.0.1 port=55432 dbname=kssl_test_staging user=kssl password=kssl" KSSL_SERVING_DSN="host=127.0.0.1 port=55432 dbname=kssl_test_serving user=kssl password=kssl" python -m uvicorn backend.app:app --port 8611
    KSSL_API_TARGET=http://127.0.0.1:8610 npx vite --port 5190                    # live build
    KSSL_API_TARGET=http://127.0.0.1:8611 npx vite --mode review --port 5191      # review build

| Config | Command | Covers |
|---|---|---|
| `playwright.config.mjs` (live, `:5190`) | `npx playwright test` | `tests/e2e/frontend.spec.mjs`: boot, routing, feed, search, every rail route renders (no ErrorBoundary, no `undefined` / `NaN` / `[object Object]` / `null` / "cummins" / "genset" in the visible text), special names (Arabic script, `L&T (TEST)`) shown literally |
| `playwright.review.config.mjs` (`:5191` + live `:5190`) | `npx playwright test -c playwright.review.config.mjs` | `tests/e2e/review.spec.mjs`: every card route carries review bars and the banner; the live build renders none; Approve returns 200 and the card turns "live" for a company, a market segment assessment, a field-level synthesis row and a competitor synthesis |

Run the pair with `--approve-all` for both configs (the review tests unpublish a live card before re-approving it, so they
also work on a pair built without it, except the four "live build" cases, which need live data). Empty-dataset case
(a different database): build the pair WITHOUT `--approve-all`, restart the :8610 backend, then
`KSSL_EMPTY=1 npx playwright test -g "empty dataset"`; afterwards rebuild with `--approve-all` and restart :8610.

## Section visibility (`ui.section_visibility`)

The database decides which sections of the app show. `ui.section_visibility(section_key, visible, note)` is shipped as
`sectionVisibility: {key: bool}` in `/api/dataset`. A key is visible ONLY when it is exactly `true`: a missing key,
`false`, or an empty table all mean hidden. The code behind a hidden section is kept, not deleted (`src/lib/visibility.js`).
KSSL ships all eight keys as `false`.

| section_key | What it gates when hidden |
|---|---|
| `gap-analysis` | the Gap Analysis route and rail item, the gap block in a matchup dossier, the gap strip under an innovation, the gap counts |
| `finances` | the Finances route and rail item and its overview count |
| `stock` | reserved; no stock panel is shipped (the stock lanes were removed) |
| `parallax-read` | the analyst assessment on the competitor profile, partnership drawer and print report |
| `swot` | the SWOT block on the competitor profile |
| `strategic-positioning` | the Strategic Positioning block on the competitor profile |
| `product-images` | product thumbnails and image credits in Products |
| `chat` | the chat widget, the Ask box in the detail panel and the scoped chat boxes on Tenders, Innovation and Geo |

The test seed also carries a ninth row, `competitor-moment` = `true`, so the gate is exercised both ways.

## Build

    npm run build        # emits dist/

The build fetches `/api/dataset` **relative to its own origin** — no baked-in
host. Serve `dist/` from any static server that also routes `/api/*` to the
backend on port 8600 (nginx `proxy_pass`, Caddy `reverse_proxy`, or the
docker-compose frontend service). `npm run preview` serves the build locally
but does not proxy `/api`, so use it only with a reverse proxy in front.

## How it talks to the backend

- One bootstrap read: `GET /api/dataset` (`src/api/client.js` +
  `src/api/datasetService.js`, consumed in `src/state/DataProvider.jsx`).
- The API returns the UI contract plus the complete database snapshot. The
  backend owns the shape adaptation; the frontend does not read PostgreSQL
  directly and does not repair missing data with a local snapshot.
- While the fetch is in flight the app shows an explicit loading screen; if the
  backend is down or returns a non-2xx / unusable payload, it shows a
  plain-English error screen with a Retry button — never a blank page.

The backend keeps `overviewConfig.competitive`, `market`, and `technology`
present even when their cards are empty. Detail lenses are represented as
lists of `[lead, html]` pairs when detail rows exist.
