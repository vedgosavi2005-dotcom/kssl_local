# QA suite: database → API → screen

One command tests the whole pipeline and writes the QA workbook:

```
python tests/qa/run_qa.py            # needs the local servers: APIs :8600 / :8601, sites :5178 / :5180
python tests/qa/run_qa.py --no-ui    # database + API only (about a minute)
```

Output: `tests/qa/out/KSSL_QA_report.xlsx`. It has four sheets: Summary, Test cases (steps, expected result and outcome), Results (every single check) and Findings (each failure with its triage).

| Layer | File | What it proves |
|---|---|---|
| 1 Database | `test_db.py` | Every table in both databases. It checks: the schemas exist; each card table is in both databases with the same columns; keys are present and unique; no orphan rows; no duplicate rows; no filler values; URLs, dates and numeric ranges are valid; every view runs; live tables can only be written through Approve; live cards still exist in staging; and every card has a source. |
| 2 Backend API | `test_api.py` | Every route (API-000 fails when a new route has no test). It checks the contract, speed, the review-only split, the write guards, input validation, the usage log and recordings, trace, the pipeline log, analytics, news, CORS and 404s. |
| 3 Database → API | `test_trace.py` | Every object in `/api/dataset` is a real database row (via its `_src`), its fields equal the row's columns, and collections are complete. Hidden competitors never appear, ui tables arrive whole, dead links are swapped, images exist, and live data is a subset of review. |
| 4 Screen | `ui.spec.mjs` | Every page renders with no errors and links only to URLs the database holds. Items found through search show their data, full lists show every row, a signal shows its source, and review tools appear only on the review site. |

Each test case's docstring or annotations hold its ID, steps and expected result; the workbook is built from them.

**Safety:**
- Database sessions are read-only.
- The usage-log tests delete the rows they write (visitor `…a11a`).
- The page tests mute the tracker.
- Write routes are only called in ways that are refused before anything is written.

**Another target (e.g. the VPS, read-only):** set these variables.
- `KSSL_QA_STAGING_DSN`, `KSSL_QA_SERVING_DSN`
- `KSSL_QA_LIVE_API`, `KSSL_QA_REVIEW_API`
- `KSSL_QA_LIVE_UI`, `KSSL_QA_REVIEW_UI`
- `KSSL_QA_REVIEW_AUTH=user:password`

Add or update a triage note: `FINDINGS` in `run_qa.py`.
