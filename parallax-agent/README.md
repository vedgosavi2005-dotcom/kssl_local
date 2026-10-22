# Parallax Analyst

An agentic chat assistant for 137Parallax (KSSL_Deploy v2), as a separate service in this folder:

- It answers questions about competitors, products and specifications, tenders, awards,
  partnerships, projects, patents and technology, from the same data the live site shows.
- It writes its own read-only SQL against the live database (`kssl_serving`).
- It builds charts and dashboards on the fly, on a canvas over the page.
- It opens the page that holds the answer, scrolls to the section and highlights it.

**The product's code is not modified.** The service serves the product's own built frontend
with two tags added (the chat widget's script and stylesheet) and forwards the product's API
calls untouched. Delete this folder (and run `uninstall.sql`) and the product is as before.

**The client is data.** Nothing here names a client: the client's name, the companies and their
chart colours are read from the database (`client_account`, `competitive_competitor`); the
prompts fill `{client_name}`-style slots from it.

## Using it

- **Ask Parallax** sits beside the page header's Print Report button (the product has no
  assistant button of its own; this is an overlay in the product's button style). The chat is
  closed until it is clicked; ✕ closes it; ↺ starts a new conversation; History keeps earlier
  conversations and saved views.
- **Answers come with the place that shows them**: a question about one company, product,
  tender, matchup, project or signal is answered in the chat while the page opens on that item
  and highlights the section. Comparisons, rankings and trends get a generated view.
- **Only what the site shows**: competitors that do not qualify, and sections the product hides
  (`sectionVisibility`: strategic positioning, Parallax read, SWOT...), are never used or pointed at.

## Run it locally

```bash
cp .env.example .env          # then put the model key in .env
./run-local.sh                # test databases, product API + web server, agent; prints the URL
./stop-local.sh
```

It runs the repo's fictional test pair (`db/make_test_pair.sh --approve-all`, every name
"(TEST)") in a local PostgreSQL 16 under `.local/` (no Docker needed: a stand-in runs the repo's
`docker exec kssl-pg psql` lines locally). Ports (`adapter/run-product.sh`): database 5699,
product API 8710, product web server 5779, product with the chat **http://localhost:8298**.
To use a real `kssl_serving` instead, point `KSSL_DSN` at it.

Requirements: PostgreSQL 16 binaries, Python 3.10+, Node 20+.

On a server, beside the product's `kssl2` stack: see `deploy/README.md`.

## How it works

```
 browser ── :8298 ──► gateway (service/main.py)
   │                    ├─ /             the product's built index.html + widget tags
   │                    ├─ /api/img, /api/pulse   → the product's web server (they live there)
   │                    ├─ /api/*        → the product API (untouched)
   │                    └─ /api/agent/*  → the agents (server-sent events)
   ├─ chat dock (right), canvas over the page body
 /api/agent/chat
   guard (in scope?)  ·  orchestrator ─ query_data → SQL agent over analytics.* (read-only role)
                                      ─ search_platform / read_platform → what the pages show
                                      ─ show_insight → UI designer → design reviewer
                                      ─ navigate → the product's own jumpTo(), scroll + highlight
                         answer verifier ─ checks every figure against data and pages read
 browser: layout guardian (no model) keeps the product undistorted
```

Numbers on the canvas are never typed by a model: every figure comes from a SQL result held
server-side by id.

## The product adapter

Everything specific to this product version is in `adapter/`; the rest is product-agnostic.

| File | What it holds |
|---|---|
| `product.json` | pages (payload keys, focus headings), routes, DOM selectors, AppState paths, theme, client texts with `{client_name}` slots, data facts, the paths served by the web server |
| `analytics.sql` | 21 read-only views over the live `serving` schema (company, product, product_spec, tender, matchup, signal, project, patent, leader, swot, ...), filtered to what the site shows |
| `ui_index.py` | `/api/dataset` → searchable page blocks (respects `sectionVisibility`) |
| `navigation.py` | page payload keys → exact values (all ids are text) |
| `scenarios.py` | the live test suite, for the test pair |
| `run-product.sh` | how `run-local.sh` builds and starts this product locally |
| `product-hook/` | the optional 7-line AppState hook (not needed; the bridge reads React state) |

`check_product.py` checks the adapter against the product (no model calls, writes nothing):
`.local/venv/bin/python check_product.py --dsn "<kssl_serving DSN>" --api http://127.0.0.1:8710`.
See `PORTING.md` for moving to a new product version.

## The data layer

`adapter/analytics.sql` creates the `analytics` schema: typed views over `serving.*` with
plain-English column comments, which the SQL agent reads as its schema documentation. The
agent's SQL runs as role `parallax_agent`: SELECT on `analytics.*` only, read-only transactions,
a 5-second statement timeout, plus a static guard that rejects anything but one SELECT. The
service applies the file on startup (idempotent); `uninstall.sql` removes it. The serving guard
triggers block writes only, so views in another schema are unaffected.

Known gaps the agents state: no market-share data; patents are tracked filings, not a census;
most notices publish no value; amounts are in their own currency (INR only where an official
rate is stored); the raw crawl (`staging.source_document`) is staging-only and not used.

## Configuration (`.env`)

| Variable | Default | |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `openrouter` or `anthropic` |
| `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` | | credentials |
| `AGENT_BUDGET_USD` | `20` | spend cap (OpenRouter), above the baseline in `.local/spend-baseline.json` |
| `AGENT_MODEL`, `AGENT_DATA_MODEL` | `claude-sonnet-5-5` | orchestrator, SQL agent |
| `AGENT_UI_MODEL`, `AGENT_GUARD_MODEL`, `AGENT_REVIEW_MODEL`, `AGENT_VERIFY_MODEL` | `claude-haiku-5-5` | |
| `AGENT_DEBUG_UI` | `0` | `1` shows SQL, timings and checks in the UI |
| `KSSL_DSN` | | the live database (set by the run scripts) |
| `PRODUCT_API`, `PRODUCT_WEB`, `PRODUCT_DIST` | | the product's API, web server and built frontend |
| `PRODUCT_API_ALLOW` | | on a public server: the only /api paths forwarded |

## Tests

```bash
.local/venv/bin/python tests/run_scenarios.py --base http://127.0.0.1:8298   # live, real model calls (about USD 0.6)
```

Results go to `tests/REPORT.md`.
