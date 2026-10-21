# Filling every table: plan (2026-10-17)

Rule for every source: **harvest raw first, then a prompt turns it into table rows, then a human approves.**
Nothing goes from a source straight into a page table. Everything below writes to `kssl_staging`; the review
site's Approve copies it to `kssl_serving`.

```
 sources ──harvest──▶ raw layer (staging.source_document / staging.tender_raw)
                          │ attribution (aliases → competitor_ids)
                          ▼
                    prompts (news, signal, moment, partnership, project, geo, tech_article,
                             opportunity, global_requirement, innovation_*, tender, ...)
                          ▼
                    staging tables + fact_source ──Approve──▶ serving ──▶ live UI
```

## 1. Sources and harvesters
| Source | Harvester | Raw table | Status |
|---|---|---|---|
| Google News RSS per competitor/product | `backend/news.py` | `staging.news_candidate` | built; aliases pending |
| Company newsrooms (P1–P3 list), government (PIB/MoD/DRDO/DDP/DoD), trade press (Janes, Defense News, …) — last 9 months | `backend/harvest_sites.py` (RSS → sitemap → listing pages) | `staging.source_document` | building |
| Walled newsrooms (Anduril, BAE, Elbit, Rafael) | DC crawler farm | `staging.source_document` | later (farm) |
| DC corpus, `document_triage` scores (p_spec / p_deal / p_sales_geo / p_tech) | `backend/import_dc_corpus.py` (read-only on DC) | `staging.source_document` (already attributed) | building |
| Tender APIs (TED, GeM, SAM*, Canada, UK OCDS, Prozorro, DECP, Diavgeia, …) | `backend/harvest_tenders.py` (adapts `mallery/cralwer/scripts/pull_*.py`) | `staging.tender_raw` → `market_tender` stubs | building |
| Client Excel files | `backend/excel_load.py` | direct (verified data) | done: leadership, company details, 4,520 competitor products, KSSL portfolio |

\* SAM.gov needs an API key.

## 2. Raw → tables (prompt routing)
| Raw signal | Prompt(s) | Tables |
|---|---|---|
| news story / newsroom post / trade-press article about a competitor | `news` (merge + category) → `signal`, `moment`, `partnership`, `project` | competitive_news_article, competitive_signal*, competitive_competitor_moment*, competitive_partnership*, competitive_project* |
| DC doc with high p_deal | `partnership`, `project`, `signal` | as above |
| DC doc with high p_sales_geo | `geo` | competitive_geo_* |
| DC doc / trade press with high p_tech | `tech_article`, `innovation_discovery` → `innovation_detail` | technology_overview_*, technology_innovation_* |
| DC doc with high p_spec | spec enrichment (new small prompt: add missing specs to an existing product, sourced) | competitive_product_specification |
| government / demand articles | `opportunity`, `global_requirement` | market_opportunity*, market_global_requirement* |
| tender notices | `tender` → `tender_assessment` → `top_opportunity` | market_tender*, market_top_opportunity_* |
| products both sides | `matchup` | competitive_matchup* |

The prompts read the raw layer through their subject queries (one run per document / per competitor / per
category, as today) and mark `source_document.processed_by`.

## 3. Order of work
1. Harvest (free): sites, DC corpus, tenders — running now.
2. Attribution: aliases (`db/news_aliases.csv`, waiting for the user's 7 answers) → `competitor_ids`.
3. Count what each prompt would get, estimate cost, run in priority order (P0/P1 docs and client-relevant
   tenders first), review in batches on the review site.
4. Count tables (the four count tables: market_category_summary, market_top_opportunity_metric,
   technology_metric, competitive_patent_portfolio) — SQL roll-ups, not prompts.

## 4. Cost and limits (Claude CLI on the user's plan)
| Job | Units | Approx. cost |
|---|---|---|
| matchup, all client × competitor pairs | 27,235 pairs × ~$0.17, ~60 s each | ~$4,600, ~450 h sequential |
| news merge (`news`) | per competitor batch, headlines only | ~$0.05–0.15 per batch |
| signal / tech_article / opportunity | per story or document | ~$0.03–0.25 each |
| research prompts (project, geo, partnership, ...) | per competitor | ~$0.3–1.5 each |

Matchups at that scale need a cheaper design: one model pass builds a canonical spec dictionary per category
(25k free-text labels → shared keys + units), code compares all pairs (better side, gap, edge score — the
`derive.py` rules), and the model writes verdict text only for the pairs people open or the top pairs per
product. Decision pending with the user.
