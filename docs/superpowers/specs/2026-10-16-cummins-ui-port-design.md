# Port the latest 137Parallax UI (Cummins demo) into KSSL — design

Date: 2026-10-16 · Repo: kssl_local, branch v2

## 1. Intent

The Cummins demo (`C:\Users\HARICHANDRA\Downloads\cummins-demo-clean\cummins-demo\frontend`,
live at http://187.127.134.12:8101) is the newest version of our own 137Parallax UI.
KSSL's frontend (`kssl_local/src`) is an older branch of the same app: same file tree,
but almost every file has diverged.

**Goal: one UI, two clients.** KSSL and Cummins run the same frontend code and differ
only by data. Every client-specific word ("Cummins Arabia", product names, categories,
labels) comes from the database. KSSL's DB-driven rule is what makes this work: if a
value is on screen, it traces to a column.

## 2. Goals

1. Copy the Cummins frontend in full, including:
   - structure, layout and styles
   - every component, including the new ones: `MarketOutlook`, `TenderCockpit`,
     tender-intel, `newsLenses`, `shortlist`, competitor projects and the reworked pages
   - labels and wording as seen on the live demo at :8101
2. Top opportunity (`m-overview`) uses the Cummins version (`MarketOverview` +
   `TenderCockpit`: tiles, "Top tenders", "Projects to win before they tender").
   It replaces KSSL's `TopOpportunity.jsx`.
3. Every hardcoded "Cummins" / "Cummins Arabia" / Cummins product or category string in
   the frontend becomes a value read from the dataset, for example `client.name` and
   `client.short`. There are about 300 hits across `lib/`, `pages/` and `components/`.
   KSSL then shows "KSSL" from its own client row.
4. Every new thing in the Cummins UI that has no KSSL table gets a table:
   - in `staging` / `staging_ui` (DB `kssl_staging`), and the same table in
     `serving` / `ui` (DB `kssl_serving`)
   - with a `source_url` and tier column, like every other table
   - hooked into the review/Approve flow
5. The backend's `/api/dataset` returns the shape the Cummins frontend expects
   (`docs/UI_CONTRACT.md` and `docs/contract_shapes.json` in the Cummins repo, plus
   whatever the Cummins frontend reads beyond those). The backend adapts to the UI; the
   UI is not edited to fit our old dataset shape. This keeps the frontend files nearly
   identical to Cummins, so later 137Parallax updates can be re-copied.
6. **Genset-specific code is removed, not ported** (user, 2026-10-16). Removed:
   - logic and wording that only makes sense for power generation or Cummins' market:
     "genset", kVA/kW rating bands, data-centre segments, standby fuel / dry-weight
     assumptions in spec-edge, AED/SAR currency, Saudi/Gulf-specific branches
   - if a feature exists only for that logic, the feature goes too

   What stays is the neutral, data-driven UI. Any category, unit, country or currency
   it shows comes from the dataset. No new tables are created to keep genset logic alive.
7. KSSL-only features survive the port:
   - review mode: :8601/:5180, `KSSL_VIEW=review`, approve/reject/Trace buttons on
     every card, `Review.jsx`
   - two databases, with serving written only by Approve
   - `fact_source` / Trace
   - live Google News headlines (the agreed exception to the DB-only rule)

## 3. Hidden in KSSL (kept in code, switched off by data)

These stay hidden for KSSL, as decided in earlier sessions:

- Gap Analysis
- Finances
- stock price and history (including `mockStockHistory.js`)
- Parallax Read box
- SWOT strengths and weaknesses
- Strategic Positioning paragraph
- product images (`Thumb` photos, keyword stock images)

Because the code is shared with Cummins, these are **hidden, not deleted**. Visibility
comes from a new UI table (my call): `ui.section_visibility(section_key text primary key,
visible boolean not null, note text)`, shipped in the dataset as `sectionVisibility`.

- KSSL's rows set these keys to `false`.
- A section whose key is missing or `false` does not render. The same goes for its nav
  item, count badge and search entries.

## 4. The DB-only rule applied to Cummins code

Cummins computes some things in the browser. The line (my call):

- **Allowed in the frontend:** deterministic math over DB values, for example
  - counts, sorts, filters and sums
  - the spec-edge comparison from stored specs
  - date windows
  - graph layout
- **Must come from a DB column** (and therefore a table, if none exists):
  - anything that writes words or a judgement
  - estimates, for example
    - threat ratings and rules (`threat.js`)
    - analysis sentences (`partners.js`, `gapAnalysis.js`, `reports.js`, `newsLenses.js`
      lens text)
    - fit grades (GOOD/PARTIAL)
    - "revenue Cummins Arabia can win" estimates (`tenderIntel.js`, `shortlist.js`)
    - recommendations

  The Cummins function that produced the value becomes the spec for what the new
  column holds. Filling those columns (prompts, Excel, loader) is a later round. This
  round they ship empty. An empty value shows the existing honest empty state (`—`,
  "no data"), never a computed stand-in.

### 4a. Settled after the builder check (my calls)

- **Source of truth:** the local folder `cummins-demo-clean/.../frontend` matches the
  live :8101 build. Checked: the live bundle has 252 × "Cummins Arabia", 148 × "genset"
  and no `setClient`/`clientShort` layer. `docs/CLIENT_PACKS.md` describes a
  `lib/client.js` that exists in neither, so that client layer has to be built (goal 3).
- **Cummins regression:** the code stays client-agnostic, but this round verifies
  against KSSL only. Judgement logic moved to DB columns (§4) means a Cummins deployment
  would need those columns filled. That is accepted.
- **Template sentences:** a sentence that only joins DB values ("5 tenders in Saudi
  Arabia", "3 partners shared") is allowed math. A sentence that asserts a judgement or
  a fact not in the DB is not.
- **Offline chat:** `lib/chat.js` writes answer sentences offline and falls back to
  "Cummins Arabia". So `MalloryChat`, `ScopeChat` and `AskBox` are hidden via
  `sectionVisibility`. No chat this round (parallax-agent deferred).

## 5. Non-goals

- Filling the new tables with real data, writing prompts for them, or running the Excel
  loaders against them. That is a later round.
- Redesigning anything. This is a copy, not a new look.
- Deploying to the VPS. Do it only when asked.
- Changing Cummins' own deployment or repo.
- The parallax-agent chat widget (user: leave for this round). Its source isn't in the
  Cummins folder; only the built bundle is on VPS2 (`/parallax-agent/widget.js`, calls
  `/api/agent/*`).

## 6. Anti-goals (a failure even if it runs)

- Any fabricated or browser-invented text/number showing on KSSL. That includes Cummins
  wording, figures, product names or photos, and default or fallback values.
- A Cummins-specific string left in the frontend code.
- Losing review mode buttons, Trace, or the staging → Approve → serving flow.
- Writing to `serving.*` / `ui.*` other than through Approve (the guard triggers stay).
- Breaking the full test seed: `bash db/make_test_pair.sh --approve-all` must still
  leave zero empty tables, with the new tables added to it.

## 7. Approach (decided)

1. Cummins `frontend/src` becomes the base. Bring across `index.html`, `src/`, `public/`
   (minus Cummins product photos) and the Cummins `vite.config.js` dev middleware, except
   the Google/Yahoo stock lanes. Keep KSSL's `package.json` deps unless Cummins needs more.
2. Re-apply the KSSL-only layer on top: review mode, Trace/`SourceLink` to `fact_source`,
   `sectionVisibility`, and live headlines.
3. Replace the Cummins strings with dataset values.
4. Diff the dataset the Cummins frontend reads against what our backend ships, field by
   field. The output is a mapping table (UI field → serving/ui column, or "new table
   needed", or "derived in browser, allowed").
5. Create the migrations for the new tables in both DBs, and add them to review
   `GRAPH`, the guard triggers and the full test seed.
6. Change the backend `/api/dataset` to emit the Cummins shape.
7. Remove the genset-specific code (goal 6).
8. Verify page by page against :8101: same layout and labels, KSSL data, hidden
   sections gone, review buttons present.

## 8. Left to the builder

- Order of work and how to split it across Sonnet coder agents.
- Exact new table and column names (follow the existing `serving` naming:
  `<area>_<thing>`, `source_url`, `source_tier`).
- How `sectionVisibility` keys are named.
- Whether `lib/` derivation modules that only do allowed math are kept verbatim
  (preferred) or trimmed.

## 9. Open

Nothing. The user approved the version and testing calls in §4a.
