# Frontend acceptance — local Playwright run

Source plan: `frontend testcase (1).xlsx` (48 logical cases FE-* / PERF-*).
Implemented as Playwright (`tests/e2e/frontend.spec.mjs`), run against the local
client SPA (`vite` dev on :5178) serving the current `public/api/dataset` snapshot.

**Result: 32 passed · 0 failed · 16 skipped.** JUnit: `reports/e2e-results.xml`.
(The prior staging run recorded 1 failure — FE-051 — which was a false negative;
it passes here with a corrected wait strategy.)

## Passed (32)
FE-001,002,003,004,005,006 · FE-010,011,012,013,014,015,016 · FE-020,022,027,028,029 ·
FE-030,031,032,036 · FE-049,050,051 · FE-070,071,072 · PERF-010,011,012,013

Notable: **FE-051 Geo map** now passes (waits for `.geo-map-container` + `.leaflet-container`,
not `.shell`). **FE-036** confirms no fetch/XHR leaves the app origin. **PERF-011/012**
confirm exactly one `/api/dataset` round trip and no refetch on navigation.

## Skipped (16) — with reasons
| Case | Reason |
|---|---|
| FE-021 | On-screen feed count line was removed at the operator's request (print-only). Invariant `cards>0` still asserted. |
| FE-023 | No genuine empty-filter state exists in the snapshot (matches prior run). |
| FE-024 | No in-feed search control in this build (global search covered by FE-030/031/032). |
| FE-025, FE-026 | Feed fits one page in this dataset — no pagination control to exercise. |
| FE-033 | Export JSON was removed from this build at the operator's request. |
| FE-034 | Copy Summary was removed from this build at the operator's request. |
| FE-035 | No offline assistant in the hosted product (expected skip). |
| FE-052 | No empty panel present in the tested view. |
| FE-060…066 (7) | `/ops` operator console is a **separate application**, not part of this client repo. |

## Run it
```
cd frontend
npx playwright test            # auto-starts vite dev, runs the suite
```
