# Porting Parallax Analyst to a new product version

Everything that ties the chatbot to one version of the product lives in `adapter/`. The rest
(`service/`, `widget/`, `tests/run_scenarios.py`) is product-agnostic and should not need
changes. Porting means: copy this folder into the new product, fix `adapter/` until
`check_product.py` is clean, then run the live scenarios.

## What is in `adapter/`

| File | What it says about the product | Change it when |
|---|---|---|
| `product.json` | client and scope text, companies (aliases, colour slots), database catalogue order and live data facts, dataset endpoint, routes, **pages** (payload keys, focus headings), click targets, tool examples, DOM selectors, AppState paths, theme tokens and palette, suggestions, source paths for the check | a page, payload key, heading, class name, CSS token, company or data summary changes |
| `analytics.sql` | the views the SQL agent queries, over the product's `serving` schema; column comments are the agent's schema docs | a table, column or JSON field moves, or a new kind of data appears |
| `ui_index.py` | the product's `/api/dataset` → page blocks the agent can search, read and scroll to | the dataset shape changes, or a page shows something new |
| `navigation.py` | each payload key → the exact value its page matches on | a page gets a new payload key |
| `scenarios.py` | the live test suite (questions, expected pages and payloads) | pages, companies or data change |
| `run-product.sh` | how `run-local.sh` creates, seeds, builds and starts this product | the product's layout, seed command or build changes |
| `product-hook/` | the optional 7-line AppState hook and its apply/revert scripts | AppState.jsx changes |

## Steps

1. Copy the folder (without `.local/`) into the new product root, beside its `frontend/`/`backend/`.
2. `adapter/run-product.sh`: schema files, seed command and dataset file, backend folder and env,
   how the frontend is built (into `.local/`, never into the product), ports.
3. `./run-local.sh` (pick free ports: `PGPORT=... PRODUCT_PORT=... AGENT_PORT=... ./run-local.sh`).
4. `.local/venv/bin/python check_product.py --dsn "<DSN>" --api http://127.0.0.1:<PRODUCT_PORT>`
   and fix every FAIL, then the WARNs that matter. It writes `.local/check_product.md`.
5. New pages: add them to `product.json` pages (and `ui_index.py`, `navigation.py` if they
   take a payload); new data: a view in `analytics.sql` with comments, its name in
   `database.catalog_order`, a `facts` entry if the prompt should quote its count.
6. Rebuild the widget if `product.json` changed (`run-local.sh` does it when the file is newer).
7. Update `scenarios.py` and run `.local/venv/bin/python tests/run_scenarios.py --base http://127.0.0.1:<AGENT_PORT>`
   (real model calls; about USD 1 for the full suite).
8. Open the product with the chatbot and click through: Ask Parallax opens the dock, a
   question navigates and highlights, a comparison opens a view, ✕ closes it.

## What `check_product.py` checks (free, no model calls)

| Area | Check | Fix in |
|---|---|---|
| database | `analytics.sql` applies (rolled back), rows per view, empty views, data facts, companies vs `product.json` | `analytics.sql`, `product.json` database / companies |
| dataset | expected globals present, page index builds, blocks per kind, blocks pointing at unknown pages | `ui_index.py`, `product.json` product_api |
| routes | every mapped page exists in the route table; route views not mapped | `product.json` pages, `source_checks.views_not_mapped` |
| payloads | each payload key is read in the page code | `product.json` pages, `navigation.py` |
| app state | navigate function, route keys, selection / title / report paths; hook applied? | `product.json` frontend.app_state |
| dom | every class the bridge uses exists in the built product | `product.json` frontend.dom |
| theme | product CSS tokens and palette colours | `product.json` frontend.theme |
| blocks | focus headings appear in the built product (headings built at run time show as WARN) | `product.json` pages[].blocks |
| widget | built widget newer than `product.json` | `cd widget && npx vite build` |

## Hand-off prompt for a new session

Paste this into a new Claude Code session opened on the NEW product folder:

> The folder `<path-to-old-product>/parallax-agent` is an agentic chatbot (Parallax Analyst)
> attached to the previous version of this product. It is a separate, deletable service:
> product code is never edited (only the optional hook in `adapter/product-hook`). Read its
> `README.md` and `PORTING.md`. Copy it, without `.local/`, into this product as
> `parallax-agent/`, then port it: change only `parallax-agent/adapter/` (and copy `.env`
> with the model key), run `check_product.py` until it has no FAIL, add any new pages and
> data to the adapter, run it on free ports with `run-local.sh`, run the live scenarios,
> and report what changed, what passed and the remaining gaps. Keep the spend baseline
> (`.local/spend-baseline.json`) from the old copy so the budget cap carries over.
