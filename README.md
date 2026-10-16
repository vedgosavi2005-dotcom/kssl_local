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
