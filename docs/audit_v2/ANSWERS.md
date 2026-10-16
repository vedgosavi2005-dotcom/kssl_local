# Answers: what comes from where, and what needs a script

Written 2026-10-16 after the audit + mapping round on branch v2. "Stored" = the page shows the column as it is. "Loader script" = a small deterministic step that runs after the prompt / Excel load and writes columns (no AI). "Browser" = presentation computed in the page from stored values.

## 1. The parity table on Product Evaluation ("KSSL behind / near parity / KSSL ahead")
Before: the page ignored stored values and recomputed an edge index in the browser from raw spec numbers (and the backend did not even send those numbers, so it would have shown "no edge" for every pair).
Now: the page shows **stored** values only.

| What you see | Column | Filled by |
|---|---|---|
| Per spec: KSSL value, rival value, unit | competitive_matchup_specification.client_value_*/competitor_value_*, unit | **Excel** specs copied in by the loader (KSSL = client_product_specification, rival = competitive_product_specification) |
| Per spec: who is better, and "comparable or not" | better_side (client / competitor / equal), comparability_state (comparable / one_sided / not_comparable) | **Prompt** (judgement: for weight or crew, lower can be better; the prompt states it with a reason) |
| Per spec: gap % and bar | gap_value = abs(client − rival) / mean × 100 | **Loader script** (arithmetic) |
| Overall edge score (0–100, 50 = parity) | competitive_matchup.edge_score | **Loader script** from the per-spec better_side counts |
| Ahead / parity / behind word | decision_level (1 behind, 2 parity, 3 ahead) | **Loader script** from edge_score (fixed cut-offs, written down once) |
| Counts "N comparable of M sourced" | comparable_spec_count, sourced_spec_count | **Loader script** (counts) |
| Verdict headline + text, advantages per side | verdict_headline, verdict, competitive_matchup_advantage | **Prompt** (judgement, with sources) |

So: prompt -> per-spec judgement + verdict text; loader script -> the numbers and the level; the page draws what is stored. No browser formula decides who is ahead.
Missing column (you decide): a "higher is better / lower is better" flag per spec. With it, better_side could be computed by the loader for most specs instead of asked from the prompt.

## 2. Does everything on the UI come straight from the prompt?
Three kinds of values:

**A. Stored, shown as is (most of the UI).** Company details, leaders, products, specs, programmes (Excel); signals, moments, partnerships, projects, geo, tenders, requirements, innovations, tech articles, opportunities (prompts); news (news job). The loader only maps names to ids and writes rows.

**B. Loader script (after the prompt, no AI):**
- ids and links (names -> uuid/bigint ids, parent ids), display_order / sequence_no where the prompt gives an order
- edge_score, decision_level, gap_value, spec counts (above)
- tender fit_percent from the prompt's per-requirement checks; rank_position if ranking is by a rule
- counts stored in columns (innovation_count, filing_count, granted/pending counts, mapped_partner_count, source_count, product_count)
- days_remaining is NOT stored by the loader (it goes stale); the page computes it from closing_date

**C. Browser presentation (kept, uses stored values only):** sorting and filtering, rail badge counts and metric tiles (counts of served rows), days left = closing_date − today, open/closing/awarded tab from the stored status, map marker colour (KSSL present there or not), date formatting, bar widths from stored numbers.

Removed from the browser because they were judgements made by invented rules: keyword threat/watch reclassification, shortlist scoring and the top-20 cut, fit bands, the edge formula, FX conversions and crore totals, keyword-based product images and categories, name-matching between company spellings (except one kept, documented rule: shared partners are matched by partner name, because no column links a rival's partner to KSSL's partner).

## 3. Facts vs judgements, and who produces them
| | Facts (stated somewhere, with a source) | Judgements (an assessment) |
|---|---|---|
| Excel (client) | competitor company details, leadership, competitor products + specs, KSSL company + products + specs | — |
| Prompts | extracted facts from articles/notices/filings with source_url + quote (signals' facts, tender requirements, partnership evidence, project timeline, geo presence...) | threat vs watch, verdicts, advantages, better_side per spec, KSSL fit, assessment stance, KSSL counter, "why it matters", moment grade — each with a `_reason` naming the facts it rests on |
| Loader script | ids, counts, derived numbers | the fixed-rule ones only: edge_score -> decision_level, fit_percent from checks |
| News job | article headline, date, publisher, URL, image | — |

Rule of thumb: if a judgement can be a fixed formula over stored facts, it is a loader script (repeatable, no AI); if it needs reading and weighing text, it is a prompt with a reason.

## 4. Which prompts are still needed (Excel covers the rest)
Not needed (Excel): company profile (old P01), leadership (P02), product catalogue (P03), product specs/programmes (P04), and all KSSL client data.
Still needed: product evaluation / matchup (P05), partnerships (P06), projects (P07), geo footprint (P08), patent classification (P09), competitive signal (P10), tender extraction + assessment (P11, P12), market opportunity (P13), global requirements (P14), innovations (P15), technology articles (P16), competitor moment (new, was parked). They will be re-pointed to the new tables in the "prompts + HTML" step.

## 5. Columns the pages would show if they existed (add column?)
Collected from the four group reports — each is hidden today:
- Profile: support-leadership flag, leader photo, revenue unit (thousand/million).
- Products: spec direction (higher/lower is better), product description, client product news, client product country.
- Partnerships: relationship type code, status/ended, deal value, strategic insight, partner image.
- Projects: unit for estimated_value.
- Geo: estimate flag, per-product activity code.
- Patents: assignee, English title, grant/publication dates, grant number, kind code, abstract, relevance, per-filing source, KSSL portfolio.
- Tenders: awardee, award date, contract value; match-line direction; product type; category name for category_id.
- Global requirements: closing date.
- News: image_local_path and source_tier columns (today in fact_source), image_url on product news; competitor website / aliases (needed for the news job to tell a company's own site from press).
