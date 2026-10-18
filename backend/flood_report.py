"""Data-flood analytics: one self-contained HTML page from staging.prompt_run + the staging tables.

    python -m backend.flood_report            # writes db/excel_reports/flood_report.html (gitignored)
    python -m backend.flood_report --out X.html --no-pending

Reads only (kssl_staging). Pending counts come from `python -m prompts.run --list` (skip with --no-pending).
Times are shown in IST. Charts: Chart.js from cdnjs.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import yaml

ROOT = Path(__file__).resolve().parent.parent
DSN = os.environ.get("KSSL_STAGING_DSN", "host=127.0.0.1 port=55432 dbname=kssl_staging user=kssl password=kssl")
TZ = "Asia/Kolkata"

# which flood lane owned each prompt (2026-10-17 flood)
LANE = {
    "triage_route": "A", "news": "A", "signal": "A", "client_subtype": "A",
    "tender": "B", "tender_assessment": "B", "opportunity": "B", "global_requirement": "B",
    "top_opportunity": "B", "segment_assessment": "B",
    "partnership": "C", "project": "C", "geo": "C", "geo_analysis": "C", "matchup": "C", "moment": "C",
    "spec_enrich": "C", "client_partner_research": "C",
    "tech_article": "D", "innovation_discovery": "D", "innovation_detail": "D", "patent_classification": "D",
    "product_program": "E", "client_product_program": "E", "synthesis": "E", "field_synthesis": "E",
    "swot": "E", "stock_listing": "E",
    "product_status": "C", "client_spec_enrich": "C",
}
LANE_NAME = {"A": "News & signals", "B": "Market", "C": "Competitive research", "D": "Technology", "E": "Remaining tables"}
LANE_CAP = {"A": 400, "B": 400, "C": 400, "D": 300, "E": 200}
HIDDEN = {"competitive_competitor_swot", "competitive_stock_quote", "competitive_stock_series"}
SUPERSEDED = {"competitive_product_evaluation", "competitive_product_evaluation_spec"}

# data age per pillar: what date each table's row carries (future = planned steps)
AGE_SRC = [
    ("Competitive", "News articles", "published_date", "competitive_news_article"),
    ("Competitive", "Signals", "event_date", "competitive_signal"),
    ("Competitive", "Product news", "coalesce(event_date, published_date)", "competitive_product_news"),
    ("Competitive", "Movements", "movement_date", "competitive_competitor_moment"),
    ("Competitive", "Partnerships", "as_of_date", "competitive_partnership"),
    ("Competitive", "Partnership evidence", "as_of_date", "competitive_partnership_evidence"),
    ("Competitive", "Projects (latest milestone)", "latest_milestone_date", "competitive_project"),
    ("Competitive", "Project timeline steps", "event_date", "competitive_project_timeline"),
    ("Competitive", "Story steps", "step_date", "story_step"),
    ("Market", "Tenders (published)", "published_date", "market_tender"),
    ("Market", "Awards", "award_date", "market_award"),
    ("Market", "Opportunities", "as_of_date", "market_opportunity"),
    ("Market", "Global requirements", "last_confirmed", "market_global_requirement"),
    ("Technology", "Tech articles", "article_date", "technology_overview_article"),
    ("Technology", "Innovation milestones", "step_date", "technology_innovation_milestone"),
    ("Raw layer", "Harvested documents", "published_at::date", "source_document"),
    ("Raw layer", "Tender notices (raw)", "published_at::date", "tender_raw"),
]
AGE_SQL = "WITH d(pillar, what, dt) AS (" + " UNION ALL ".join(
    f"SELECT '{p}', '{w}', ({c})::date FROM staging.{t}" for p, w, c, t in AGE_SRC) + """)
    SELECT pillar, what, count(*) n, min(dt) oldest, max(dt) newest,
      count(*) FILTER (WHERE dt > current_date) future,
      count(*) FILTER (WHERE dt <= current_date AND dt >= current_date - 30) m1,
      count(*) FILTER (WHERE dt < current_date - 30 AND dt >= current_date - 90) m3,
      count(*) FILTER (WHERE dt < current_date - 90 AND dt >= current_date - 180) m6,
      count(*) FILTER (WHERE dt < current_date - 180 AND dt >= current_date - 365) m12,
      count(*) FILTER (WHERE dt < current_date - 365 AND dt >= current_date - 1095) y3,
      count(*) FILTER (WHERE dt < current_date - 1095) y3p,
      count(*) FILTER (WHERE dt IS NULL) nodate
    FROM d GROUP BY 1, 2 ORDER BY 1, 2"""

LIVE = "status IN ('open','closing')"
# Frontend changes (docs/ui_port/DB_CHANGE_NOTES.md + commits it does not cover) -> DB / prompt / code impact.
# `measure` is one SQL on kssl_staging returning one text value, so the numbers are always today's.
# notes: "noted" = in the notes as written; "corrected" = in the notes but the DB says otherwise; "missed" = not in the notes.
# rerun: (prompt, SQL counting the subjects to run) -> cost = subjects x the prompt's observed average cost.
IMPACT = [
    dict(area="Competitive · Movement", change="'Competitor Moment' renamed 'Competitor Movement'", notes="noted",
         measure="""SELECT ((SELECT count(*) FROM staging.competitive_competitor_moment x WHERE x::text ILIKE '%moment%')
                  + (SELECT count(*) FROM staging.competitive_competitor_moment_analysis x WHERE x::text ILIKE '%moment%'))
                  || ' stored rows show the word moment'""",
         db="None. Table names stay competitive_competitor_moment*; no stored text says 'moment'.",
         prompt="moment.yml: title / shows_on comments say 'Movement'. The task text is unchanged, so no version bump and no re-run.",
         code="None.", decision="Rename the tables only if you want names to match (no user-visible gain)."),
    dict(area="Competitive · Profile", change="Global locations row removed from Company details", notes="noted",
         measure="SELECT count(*) || ' location rows, ' || count(DISTINCT competitor_id) || ' competitors' FROM staging.competitive_competitor_location",
         db="None. competitive_competitor_location stays: the country filter still reads it.",
         prompt="None (filled by backend/location_load.py from the workbook, not a prompt).", code="None.",
         decision="Keep the old-workbook locations? (open decision)"),
    dict(area="Competitive · Geo", change="Overlap table: 'Overlapping categories'", notes="corrected",
         measure="""SELECT count(matched_ranges) || ' of ' || count(*) || ' presence rows have matched_ranges; '
                  || count(*) FILTER (WHERE overlap_status='category') || ' are category-only, '
                  || count(*) FILTER (WHERE overlap_status='confirmed') || ' confirmed' FROM staging.competitive_geo_company_presence""",
         db="No new column. matched_ranges is written by code (derive.geo_rollup), only from 'matched' product pairs; almost all pairs are category-only.",
         prompt="geo.yml: no change.",
         code="derive.geo_rollup: also write the categories of category-only pairs (overlap_status already says which kind). Re-run the derive step only, no AI cost.",
         decision=""),
    dict(area="Competitive · Geo / Product Evaluation", change="Verdict pill + 'Datasheet outcome' need edge_score", notes="corrected",
         measure="SELECT count(edge_score) || ' of ' || count(*) || ' matchups have edge_score' FROM staging.competitive_matchup",
         db="None. edge_score is computed by code from better_side; it is NULL because almost no spec is comparable (next row).",
         prompt="matchup.yml: no task change; re-run only the pairs whose specs change after the spec fill.",
         code="matchup_code.py recomputes better_side / gap_value / edge_score after the spec fill (free).",
         decision="Load KSSL spec figures (open decision)."),
    dict(area="Competitive · Geo / Product Evaluation", change="▲ marks, Gap column, 'ahead on' lines need better_side / gap_value", notes="corrected",
         measure="""SELECT count(*) FILTER (WHERE comparability_state='comparable') || ' of ' || count(*) || ' spec rows comparable; one-sided: '
                  || count(*) FILTER (WHERE comparability_state='one_sided' AND client_value_text IS NULL AND client_value_numeric IS NULL) || ' miss the KSSL value, '
                  || count(*) FILTER (WHERE comparability_state='one_sided' AND competitor_value_text IS NULL AND competitor_value_numeric IS NULL) || ' miss the rival value'
                  FROM staging.competitive_matchup_specification""",
         db="None (columns are better_side and gap_value; the notes' 'win' / 'gap' are payload names). Root cause is missing values on both sides.",
         prompt="spec_enrich.yml (rival side): finish the pending products. KSSL side: load the client spec figures (Excel / client_product_specification), not a prompt.",
         code="Then matchup_code.py + derive.matchup_edge recompute (free).", decision="KSSL spec figures: who supplies them?",
         rerun=("spec_enrich", None)),
    dict(area="Competitive · Geo", change="Per-comparison datasheet links ('<rival> datasheet ↗ · <client> datasheet ↗')", notes="corrected",
         measure="""SELECT count(*) || ' matchups: ' || count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.fact_source f WHERE f.table_name='competitive_product'
                  AND f.row_id = m.competitor_product_id::text AND f.source_url LIKE 'http%')) || ' rival products and '
                  || count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.client_product_source c WHERE c.client_product_id = m.client_product_id))
                  || ' client products already have a source URL' FROM staging.competitive_matchup m""",
         db="No new table: rival product URLs are in fact_source (competitive_product), client ones in client_product_source.",
         prompt="None.", code="backend: ship the distinct source URLs per side with each matchup (a_competitive / geo payload).", decision=""),
    dict(area="Competitive · Geo", change="Product class line (rating band · rating · type)", notes="corrected",
         measure="SELECT count(*) || ' rows in staging.product_class (sub_type, calibre, barrel, weight class); not in serving' FROM staging.product_class",
         db="product_class exists in staging only. Add serving.product_class (same columns) and approve it as a whole table, or ship its fields with the product.",
         prompt="None (filled by code: client_subtype.py / matchup_class.py).", code="review.py SERVING_TABLES += product_class; backend ships class fields.", decision=""),
    dict(area="Competitive · Geo", change="Presence words (builds here / exports in / partner)", notes="noted",
         measure="""SELECT string_agg(code || ' = ' || label, ' · ') FROM staging_ui.code_label
                  WHERE table_name='competitive_geo_company_presence' AND column_name='activity_type'""",
         db="None: the words live in ui.code_label; edit the labels there to use the reference wording.", prompt="None.", code="None.", decision="Which wording?"),
    dict(area="Market · Global requirements", change="WATCH pill / OPPORTUNITY tag are lane words; no per-row stance", notes="noted",
         measure="SELECT count(*) || ' requirements, no stance column' FROM staging.market_global_requirement",
         db="Only if per-row stance is wanted: market_global_requirement.direction (threat | watch).",
         prompt="global_requirement.yml: none if the stance is a code rule (kssl_fit + stage, like the signal rule s1).",
         code="Optional derive step 'requirement_stance'.", decision="Do requirements need their own stance? (recommend: no, keep the lane word)"),
    dict(area="Market · Global requirements", change="Key points: 1-4 bullets", notes="noted",
         measure="""SELECT count(*) FILTER (WHERE strategic_assessment ~ '[.!?]\\s+\\S') || ' of ' || count(*)
                  || ' assessments already have 2+ sentences' FROM staging.market_global_requirement""",
         db="None. The prompt already writes 1-3 sentences; one bullet per sentence.",
         prompt="global_requirement.yml: none (a child table of points would need a version bump and ~140 re-runs).",
         code="backend: split strategic_assessment into sentences -> bullets.", decision=""),
    dict(area="Market · Tenders", change="Matched products / Competitor fit sections missing on most live tenders", notes="noted",
         measure=f"""SELECT count(*) || ' live tenders: ' || count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.market_tender_fit_assessment a WHERE a.tender_id=t.tender_id)) || ' assessed, '
                  || count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.market_tender_product_match m WHERE m.tender_id=t.tender_id)) || ' with matched products, '
                  || count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.market_tender_competitor_fit m WHERE m.tender_id=t.tender_id)) || ' with competitor fit'
                  FROM staging.market_tender t WHERE {LIVE}""",
         db="None.", prompt="tender_assessment.yml: no task change; run it on the live tenders not yet assessed.", code="None.",
         decision="Spend on the remaining assessments?",
         rerun=("tender_assessment", f"""SELECT count(*) FROM staging.market_tender t WHERE {LIVE}
                AND NOT EXISTS (SELECT 1 FROM staging.market_tender_fit_assessment a WHERE a.tender_id=t.tender_id)""")),
    dict(area="Market · Tenders", change="One-line reason under each matched product", notes="corrected",
         measure="""SELECT count(DISTINCT row_id) || ' of ' || (SELECT count(*) FROM staging.market_tender_product_match)
                  || ' matches already have a reason (fact_source judgement on fit_grade)' FROM staging.fact_source
                  WHERE table_name='market_tender_product_match' AND column_name='fit_grade' AND source_tier='judgement'""",
         db="No match_rationale column needed: the prompt's _reason for each match's fit_grade is already stored in fact_source.",
         prompt="None.", code="backend: ship that judgement quote as the match's reason line.", decision=""),
    dict(area="Market · Tenders", change="fit_percent pill (falls back to the fit word)", notes="noted",
         measure="""SELECT count(fit_percent) || ' of ' || count(*) || ' matches have fit_percent; '
                  || count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM staging.market_tender_product_match_line l WHERE l.tender_match_id=m.tender_match_id))
                  || ' have no check lines' FROM staging.market_tender_product_match m""",
         db="None (the loader computes fit_percent from the checked lines).",
         prompt="tender_assessment.yml: optional version bump: every matched product carries at least one checked line. Re-runs every assessed tender.",
         code="None.", decision="Worth it? The fit word already shows (recommend: no).",
         rerun=("tender_assessment", "SELECT count(DISTINCT tender_id) FROM staging.market_tender_fit_assessment")),
    dict(area="Technology · Innovations", change="'<client> behind / at parity / ahead' pill", notes="noted",
         measure="""SELECT count(*) FILTER (WHERE client_position='unknown') || ' of ' || count(*)
                  || ' detailed innovations: position unknown' FROM staging.technology_innovation WHERE status IS DISTINCT FROM 'candidate'""",
         db="None.", prompt="innovation_detail.yml: no task change. The rule needs a KSSL figure; re-run after the KSSL spec figures load.",
         code="None.", decision="Same as KSSL spec figures.",
         rerun=("innovation_detail", "SELECT count(*) FROM staging.technology_innovation WHERE status IS DISTINCT FROM 'candidate'")),
    dict(area="Technology · Innovations", change="Stage pill (LAB / IN DEVELOPMENT / IN PRODUCTION / FIELDED)", notes="noted",
         measure="""SELECT string_agg(l || ' ' || n, ', ') FROM (SELECT coalesce(c.tag_class, 'none') l, count(*) n FROM staging.technology_innovation i
                  LEFT JOIN staging_ui.code_label c ON c.table_name='technology_innovation' AND c.column_name='maturity_level' AND c.code = i.maturity_level::text
                  WHERE i.status IS DISTINCT FROM 'candidate' GROUP BY 1 ORDER BY 1) x""",
         db="None (maturity_level 1-5 -> chip class via code_label).", prompt="None: 'In production' simply has no innovation yet.", code="None.", decision=""),
    dict(area="Technology · Innovations", change="Domain tabs empty except 3", notes="noted",
         measure="""SELECT count(DISTINCT category_id) || ' of ' || (SELECT count(*) FROM staging.technology_category)
                  || ' domains have a detailed innovation; ' || (SELECT count(*) FROM staging.technology_innovation WHERE status='candidate')
                  || ' candidates wait for innovation_detail' FROM staging.technology_innovation WHERE status IS DISTINCT FROM 'candidate'""",
         db="None.", prompt="innovation_discovery.yml then innovation_detail.yml: run for the empty domains (Artillery first).", code="None.",
         decision="", rerun=("innovation_detail", "SELECT count(*) FROM staging.technology_innovation WHERE status='candidate'")),
    dict(area="All · Money", change="Values shown in rupees (₹ Cr / L) from stored rates (dataset key fxRates)", notes="noted",
         measure="""SELECT CASE WHEN to_regclass('staging.fx_rate') IS NULL THEN 'no fx_rate table; ' ELSE '' END
                  || count(DISTINCT value_currency) || ' tender currencies: ' || string_agg(DISTINCT value_currency, ', ')
                  FROM staging.market_tender WHERE value_currency IS NOT NULL""",
         db="New table fx_rate (currency_code char(3) PK, inr_per_unit numeric NOT NULL, as_of_date date NOT NULL, source_url text) in staging + serving, approved as a whole table.",
         prompt="None (a rate is a fetched number, not a judgement).",
         code="Small loader: official daily reference rates (e.g. RBI or ECB) -> staging.fx_rate; backend ships fxRates.",
         decision="Which rate source?"),
    dict(area="Market · Top opportunity", change="'Tender value' tile in rupees", notes="corrected",
         measure="SELECT formatted_value FROM staging.market_top_opportunity_metric WHERE metric_key='tender_value'",
         db="None beyond fx_rate.", prompt="top_opportunity.yml: none. The tile is written by backend/market_rollups.py (code), not the prompt.",
         code="market_rollups.py: convert each currency's sum with fx_rate, write formatted_value in ₹ Cr, amount_value in rupees, currency_code INR.", decision=""),
    dict(area="Competitive · Profile", change="Revenue-tier filter always shown", notes="corrected",
         measure="""SELECT count(nullif(revenue_tier, '')) || ' of ' || count(*) || ' competitors have revenue_tier; ' || count(annual_revenue)
                  || ' have annual_revenue in ' || count(DISTINCT revenue_currency) || ' currencies' FROM staging.competitive_competitor""",
         db="Column is revenue_tier (revenue_filter is only the payload name). No schema change.",
         prompt="None.", code="Code fills revenue_tier from annual_revenue x fx_rate with tier bands you set.",
         decision="Tier bands (e.g. < ₹1,000 Cr / 1,000-10,000 / > 10,000)?"),
    dict(area="Market", change="Stage codes (need_stated, approved_funded, rfi) shown as words", notes="corrected",
         measure="SELECT count(*) || ' stage labels already in code_label' FROM staging_ui.code_label WHERE column_name='stage'",
         db="None: the labels already exist in ui.code_label (market_global_requirement / market_opportunity .stage).",
         prompt="None.", code="backend: ship code_label words instead of the frontend's own mapping.", decision=""),
    dict(area="Market · Top opportunity", change="Page reads ONLY the stored rank tables (commit 8b68806)", notes="missed",
         measure="""SELECT (SELECT count(*) FROM staging.market_top_opportunity_tender) || ' top tenders, ' || (SELECT count(*) FROM staging.market_top_opportunity_project)
                  || ' projects, ' || (SELECT count(*) FROM staging.market_next_move) || ' next moves; tiles: '
                  || (SELECT string_agg(metric_key || ' = ' || formatted_value, ' · ' ORDER BY metric_key) FROM staging.market_top_opportunity_metric)""",
         db="None. Tables filled: market_top_opportunity_tender / _project, market_next_move (top_opportunity.yml) + market_top_opportunity_metric (market_rollups.py).",
         prompt="top_opportunity.yml: no change; it must re-run after tender_assessment so the ranking sees new fits.",
         code="None.", decision="'Strong fits' tile reads 0: no tender is graded strong under the current rule. Relax the rule? (open decision)"),
    dict(area="Competitive · Signals", change="Drawer: Facts + Risk removed; risk = probability × impact as a hidden sort key (this session)", notes="missed",
         measure="SELECT count(*) FILTER (WHERE probability IS NOT NULL AND impact IS NOT NULL) || ' of ' || count(*) || ' signals can be risk-sorted' FROM staging.competitive_signal",
         db="None (computed in backend/areas/a_competitive.py).", prompt="signal.yml: none.", code="Done.", decision=""),
    dict(area="Competitive · Leadership", change="Excel leader rows shown without a quote (this session)", notes="missed",
         measure="SELECT count(*) || ' leader records' FROM staging.competitive_leader_record",
         db="None. Rows from the Excel have a URL but no quote; Trace shows the URL only.", prompt="None.", code="Done (profile.js).", decision=""),
    # ---- 2026-10-18 (DB_CHANGE_NOTES sections of that day)
    dict(area="Competitive · Cards", change="Card date = the article's publication date, not the event date (user-approved DB change)", notes="noted",
         measure="""SELECT count(published_date) || ' of ' || count(*) || ' signals dated; ' || count(*) FILTER (WHERE published_date IS NULL)
                  || ' undated (the page states no date or refuses even a browser)' FROM staging.competitive_signal""",
         db="New column competitive_signal.published_date (db/setup/15_signal_published_date.sql, staging + serving).",
         prompt="signal.yml: loader token article_published_date (source_document.published_at, else the news job's date; never a future date).",
         code="Harvester reads JSON-LD dateCreated, date-classed elements, 'Date:' labels, the knds listing's publicationDate; today's date in a header is ignored. Backfills: scripts/backfill_published_dates.py (+ --pages browser reads).",
         decision="spslandforces prints only an issue ('Issue 2 - 2019'): a published_precision column is only an idea."),
    dict(area="Market · Tenders", change="Tenders list: stored client fit first (stored % else strong > partial > weak), then deadline", notes="noted",
         measure=f"""SELECT count(*) || ' live tenders, ' || count(*) FILTER (WHERE kssl_fit IS NOT NULL) || ' with a stored client fit; ui.market_tenders_view rows: '
                  || (SELECT count(*) FROM staging_ui.market_tenders_view) FROM staging.market_tender WHERE {LIVE}""",
         db="None. ui.market_tenders_view is empty and was never read by the page (candidate to drop).",
         prompt="tender_assessment.yml: the order is only as good as the fit coverage (see the Tenders rows above).", code="Frontend sort (kssl-40).", decision=""),
    dict(area="Competitive · Overview", change="At most 10 threats, risk order (p × i, sooner effect, client market) + 5 × 5 probability-impact matrix", notes="noted",
         measure="SELECT count(*) FILTER (WHERE classification='threat') || ' threats, ' || count(*) FILTER (WHERE classification='watch') || ' watch, ' || count(*) FILTER (WHERE classification='none') || ' hidden (none)' FROM staging.competitive_signal",
         db="None (cards ship probability / impact / timeToEffect / inClientMarket).", prompt="signal.yml: none.", code="Frontend (kssl-40).", decision=""),
    dict(area="Competitive · Spec", change="Threat and watch only: a done event with impact 1-2 (or a done favourable move) is 'none', stored but not shown (rule s2)", notes="noted",
         measure="SELECT count(*) FILTER (WHERE rule_version='s2') || ' of ' || count(*) || ' signals labelled by rule s2' FROM staging.competitive_signal",
         db="code_label: classification 'none' added, 'fav' inactive (db/setup/16_signal_rule_s2.sql).",
         prompt="signal.yml v4 (title rules); the label itself is code (derive.signal_label).", code="backend skips 'none' cards.", decision=""),
    dict(area="Competitive · Spec", change="Funding as an indicator of change (seventh impact dimension)", notes="noted",
         measure="SELECT count(impact_funding) || ' of ' || count(*) || ' signals scored on funding (new signals only, by choice)' FROM staging.competitive_signal",
         db="competitive_signal.impact_funding (staging + serving).", prompt="signal.yml v4 scores it with anchors.", code="derive: funding is market-free.", decision=""),
    dict(area="Competitive · Spec", change="Competitor qualifies only with the same product line AND the same market", notes="noted",
         measure="SELECT count(*) FILTER (WHERE qualifies) || ' qualify, ' || count(*) FILTER (WHERE NOT qualifies) || ' do not, ' || count(*) FILTER (WHERE qualifies IS NULL) || ' not testable' FROM staging.competitive_competitor",
         db="competitive_competitor.qualifies + qualification_reason (staging + serving).", prompt="None (code: derive_comp.qualify_competitors, hook on geo).",
         code="Shipped as competitors[].qualifies / qualificationReason; not shown yet.", decision="Show it on the profile? New-entrant discovery later?"),
]

IMPACT += [
    dict(area="Market · Tenders", change="One procurement = one tender: duplicate re-publications / corrigenda merged (user decision)", notes="noted",
         measure="""SELECT count(*) || ' tenders; ' || (SELECT count(*) FROM staging.market_tender_source) || ' notices kept as source rows, '
                  || (SELECT count(*) FROM staging.market_tender_source WHERE is_primary IS FALSE) || ' of them merged re-publications' FROM staging.market_tender""",
         db="market_tender_source.notice_reference (db/setup/18_tender_notice_merge.sql, staging + serving).",
         prompt="tender.yml subject: one run per tender (primary source, latest raw notice).",
         code="harvest_tenders: merge_duplicate_tenders + stage() attaches re-publications; market_rollups 'merge' step; awards one per tender.", decision=""),
    dict(area="All · Competitors", change="Only qualifying competitors are shown; the database keeps all (user decision)", notes="noted",
         measure="SELECT count(*) FILTER (WHERE qualifies) || ' shown of ' || count(*) || ' stored' FROM staging.competitive_competitor",
         db="None (competitive_competitor.qualifies decides).", prompt="None; qualification re-tested after every load (run.py, Excel, product class, geo).",
         code="backend/areas/a_competitive.visible_database (called in app.build_dataset).", decision=""),
]

# Red-team audit 2026-10-18 (client's-eye break test, split: kssl-52 = DB / prompts / builders / deploy, kssl-40 = frontend / HTTP API).
# status: fixed | open (needs work) | decision (needs the user). `measure` (optional) re-counts the problem live, so a fixed one reads 0.
RED_TEAM = [
    dict(lane="DB", sev="high", area="Integrity", finding="Duplicate signals: one article queued once per competitor it names came back twice for the same company (4 pairs, two cards each)",
         fix="Extra signal of each pair dropped; new derive hook signal_dedupe stops it recurring", status="fixed",
         measure="SELECT count(*) FROM (SELECT d.source_url FROM staging.competitive_signal_detail d JOIN staging.competitive_signal s USING (signal_id) GROUP BY d.source_url, s.company_id HAVING count(*) > 1) x"),
    dict(lane="DB", sev="high", area="Stories", finding="A planned / future step (up to 2038) set a story's current label and last_step_at: 34 stories sorted as newest, 36 labels came from plans",
         fix="story.rebuild_timeline: planned or future steps never set state, label changes or escalation; all 1,133 stories rebuilt", status="fixed",
         measure="SELECT count(*) FROM staging.story WHERE last_step_at > current_date"),
    dict(lane="DB", sev="med", area="Integrity", finding="346 technology_innovation_* child rows (+38 fact_source rows) pointed at innovations replaced on a re-run",
         fix="Orphans deleted. Root cause open: an innovation re-key does not cascade to its children", status="fixed",
         measure="SELECT count(*) FROM staging.technology_innovation_status s WHERE NOT EXISTS (SELECT 1 FROM staging.technology_innovation i WHERE i.innovation_id = s.innovation_id)"),
    dict(lane="DB", sev="med", area="Vocabulary", finding="code_label had drifted from the prompt enums (partner_type JV vs 'Joint venture', geo activity Manufactures vs 'Export'); story stage / step codes had no label",
         fix="db/setup/17_vocab_sync.sql adds the written codes, deactivates the stale ones", status="fixed"),
    dict(lane="DB", sev="low", area="Vocabulary", finding="A free-text value in a code column (market_opportunity.stage = 'first batch order expected soon')", fix="Set NULL", status="fixed",
         measure="SELECT count(*) FROM staging.market_opportunity WHERE stage IS NOT NULL AND stage NOT IN (SELECT code FROM staging_ui.code_label WHERE table_name='market_opportunity' AND column_name='stage')"),
    dict(lane="DB", sev="med", area="Duplicates", finding="Tenders with the same title, buyer and closing date but different TED notice numbers (re-publications / corrigenda) showed as separate tenders (102 groups)",
         fix="User decision: merged. 84 groups, 110 duplicates into their kept tender (1,626 -> 1,516); every notice kept as a source row with its notice number; harvester attaches future re-publications; 19 groups stay separate by rule (Prozorro / DECP records, different UK ocid, different winners)",
         status="fixed"),
    dict(lane="DB", sev="low", area="Integrity", finding="331 raw tender notices point at tenders an older prune removed (status 'staged', so never re-staged)",
         fix="Re-stage them or mark them pruned", status="open",
         measure="SELECT count(*) FROM staging.tender_raw r WHERE r.tender_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM staging.market_tender t WHERE t.tender_id = r.tender_id)"),
    dict(lane="Builders", sev="high", area="Visibility", finding="User decision: the UI shows only competitors that qualify (same product line AND same market); the database keeps all",
         fix="visible_database() filters the dataset before every area (ids, GRAPH cascade, rival names, tech companies); re-tested after every load; leak check scripts/check_hidden_competitors.py: 0 hidden ids",
         status="fixed",
         measure="SELECT count(*) FILTER (WHERE qualifies IS NOT TRUE) FROM staging.competitive_competitor"),
    dict(lane="DB", sev="med", area="Dates", finding="An award notice's publication date stands in for a missing award date", fix="Proposed: a separate notice_date column, award_date only when stated", status="decision",
         measure="SELECT count(*) FROM staging.market_award a WHERE NOT EXISTS (SELECT 1 FROM staging.market_tender t WHERE t.award_date IS NOT NULL AND t.title = a.title)"),
    dict(lane="Prompts", sev="high", area="Fabrication", finding="award_to_signal used the run date as the event date when an award had none, and wrote rule scores with no reason; invented 'Tender award notice' source name",
         fix="No award date, no signal; each rule score writes its judgement reason; no invented source name", status="fixed"),
    dict(lane="Prompts", sev="med", area="Fabrication", finding="tech_rollups wrote 'No KSSL filings are on record' without querying the client's filings", fix="Sentence removed", status="fixed"),
    dict(lane="Prompts", sev="med", area="Fabrication", finding="Technology glance stored placeholders ('None named', 'Unknown') and showed the model's reason beside a value the rule had changed",
         fix="Empty rows omitted; a demoted client_position gets a 'by rule' reason", status="fixed"),
    dict(lane="Prompts", sev="med", area="Fabrication", finding="Developer fallback: the first listed company became the developer when the model named none", fix="None instead", status="fixed"),
    dict(lane="Prompts", sev="low", area="Traceability", finding="Default 'watch' for unscored signals and 'no model answer' product classes (client_subtype, matchup_class) looked like model output",
         fix="Rule reason row written; model = 'code:no_answer'", status="fixed"),
    dict(lane="Prompts", sev="med", area="Hardcoded", finding="Client name typed as 'KSSL' in stored text (matchup level words, tech position label, geo findings, market tiles / next moves, drawer glance label)",
         fix="derive.client_name reads client_account; every sentence built from it", status="fixed"),
    dict(lane="Prompts", sev="low", area="Fabrication", finding="market_award.source_tier hardcoded 'primary'", fix="backend.sources.classify (all four hosts classify primary)", status="fixed"),
    dict(lane="Prompts", sev="low", area="Wording", finding="Codes and unfinished titles in model-written text (wording audit)", fix="Shared prompt rule 10 + signal.yml v4; existing text changes on re-run",
         status="open"),
    dict(lane="Prompts", sev="low", area="Traceability", finding="derive_comp overlap_kind / reason_state and matchup_code unify_keys change a judgement without replacing the model's reason row",
         fix="Same 'by rule' reason pattern as derive_tech", status="open"),
    dict(lane="Prompts", sev="low", area="Stories", finding="story.py defaults an unknown move family to 'programme', so unrelated moves can merge into one story", fix="Leave the family blank", status="open"),
    dict(lane="Builders", sev="med", area="Fabrication", finding="risk = (probability or 0) × (impact or 0): a missing score became 0", fix="risk only when both scores exist", status="fixed"),
    dict(lane="Builders", sev="med", area="Fabrication", finding="Patent number fell back to the internal filing_id", fix="publication_number only", status="fixed"),
    dict(lane="Builders", sev="low", area="Fabrication", finding="revenueMid: an invented midpoint of the revenue range (unused by the UI)", fix="Removed", status="fixed"),
    dict(lane="Builders", sev="low", area="Contract", finding="The signal glance ships English labels ([label, value]); product news merges event and publication date under one key",
         fix="Code-keyed contract + chrome.js wording; left to the user by both lanes ('ago' = deadline fixed by kssl-40)", status="decision"),
    dict(lane="Security", sev="high", area="Exposure", finding="VPS IP and root SSH user hardcoded in deploy / sync scripts of a public repo",
         fix="Read from the gitignored .env. History keeps the old value: disable root SSH + key-only + fail2ban, or move / firewall the host", status="decision"),
    dict(lane="Security", sev="med", area="Deploy", finding="deploy_vps.sh applied setup SQL from the working tree (untracked files included) while shipping a committed ref",
         fix="SQL read with git show $REF:file", status="fixed"),
    dict(lane="Security", sev="low", area="Repo", finding="Logs with DSNs, routines.7z, news aliases, test-data files, Excel files were untracked but not ignored", fix=".gitignore entries added", status="fixed"),
    dict(lane="Security", sev="med", area="Local DB", finding="Local kssl-pg listens on 0.0.0.0:55432; its superuser password is the public dev default", fix="Recreate with -p 127.0.0.1:55432:5432 or change the password", status="decision"),
    dict(lane="Security", sev="med", area="Roles", finding="The live API uses the same write-capable role as review (GRANT ALL on serving / staging)", fix="A read-only role for the live API", status="decision"),
    dict(lane="DB", sev="info", area="Guards", finding="Approve guard (only_via_approve) on every serving / ui table; staging and serving schemas identical; no blocked source cited",
         fix="Checked: 174 of 174 guarded and enabled, 0 drift, 0 blocked sources", status="fixed"),
]
RED_TEAM_PEER: list = [          # kssl-40's half (frontend / HTTP API): docs/ui_port/DB_CHANGE_NOTES.md, "Red-team audit, frontend + API half"
    dict(lane="Frontend / API", sev="high", area="Security", finding='CSRF: review write routes accepted any non-GET request from any page', fix='Middleware needs the X-KSSL-Write: 1 header (403 without); evil-origin preflight refused (400); committed', status="fixed"),
    dict(lane="Frontend / API", sev="high", area="Security", finding='SSRF: /api/img fetched any URL (internal API, metadata 169.254.169.254, local DB port) and followed redirects', fix='src/lib/imgGuard.js: public http(s) on 80/443 only, DNS-resolved private / loopback / link-local / CGNAT blocked, every redirect re-checked, 3 hops, 8 MB; test_img_guard.mjs. Ceiling: DNS rebinding', status="fixed"),
    dict(lane="Frontend / API", sev="low", area="Security", finding="Trace 'sql' display string did not escape quotes (queries were already parameterised)", fix='Quotes doubled; injected keys return 0 rows', status="fixed"),
    dict(lane="Frontend / API", sev="info", area="Security", finding='Probe: unknown / injected table, action or schema; live write routes; /docs; /api/news parameters', fix='400 / 404 / off / validated (bad uuid 400, limit > 1000 422, bad date 400)', status="fixed"),
    dict(lane="Frontend / API", sev="info", area="UI crawl", finding='Every pillar and view on :5180 (1600 px and 390 px) and :5178, drawers open, bad hash, hostile search', fix='0 page errors, 0 undefined / NaN / [object Object] / Invalid Date, 0 phone-width overflow, no XSS', status="fixed"),
    dict(lane="Frontend / API", sev="med", area="UI crawl", finding="Boot self-checks: 'Thales flagged shared but absent from roster'; market palette folded 'Protected & Armoured Vehicles' into 'Other'", fix="Roster reads the stored overlap_client_partner_id; no-category '—' and stored 'Other' take no colour", status="fixed"),
    dict(lane="Frontend / API", sev="high", area="Fabrication", finding="formatDate() with no value printed TODAY: undated moves showed today's date", fix="'date not known'", status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding='Partner overlap guessed by folding names in the browser', fix='Stored overlap_kind / overlap_client_partner_id', status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding="Product verdicts (AHEAD / PARITY / BEHIND, Geo 'superior product') cut from edge_score at 58 / 42 in code", fix="Stored competitive_matchup.decision_level (shipped as 'decision')", status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding="Spec bars graded 'decisive / clear' with a 5 % parity band in code", fix='Stored better_side only', status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding="Geo printed 'KSSL Absent ⚠' when there was simply no row", fix="'KSSL not on record here'", status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding="Leaders with no end date read '– Present'", fix="'From YYYY' unless 'present' is stored", status="fixed"),
    dict(lane="Frontend / API", sev="high", area="Fabrication", finding='Tech feed forced every card to watch, hiding 52 stored threats', fix='Stored stance shown', status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding="Undated tenders defaulted to open / active; a tender closing today read 'Closed / Expired'", fix="Stored status decides; 'closes today'", status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Fabrication", finding="Requirement card date was the future deadline (the 'ago' field)", fix='Stored stage_date (d_market_tech)', status="fixed"),
    dict(lane="Frontend / API", sev="low", area="Wording", finding="'Where demand is heading' only counts collected records; Movement header count differed from the rail badge; '12 Cr' tile animated as '12'", fix="Renamed 'Activity by segment'; counts equal; value kept whole", status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Hardcoded", finding='Client name typed in partners.js and chrome.js', fix='Read from client_account', status="fixed"),
    dict(lane="Frontend / API", sev="med", area="Data", finding='Local kssl_serving holds only the test seed (invented companies, img.example.com), so local :5178 shows fake data (the VPS serving DB is clean)', fix='Reseed local serving from staging via Approve, or empty it', status="decision"),
    dict(lane="Frontend / API", sev="low", area="Data", finding="176 tech cards store the stance 'fav' (shown as watch); the competitive spec is threat / watch only", fix='tech_article / tech_direction to write threat / watch, if the spec applies to Technology too', status="decision"),
    dict(lane="Frontend / API", sev="low", area="Data", finding='723 of 1,626 tenders have no category', fix='tender prompt / category mapping for the uncategorised notices', status="open"),
]

# planned change per prompt (from IMPACT); a prompt not listed keeps its current task
PLANNED = {
    "moment": "Wording only (title / shows_on say Movement). No version bump.",
    "tender_assessment": "No task change; run on live tenders not yet assessed. Optional v+1: ≥1 checked line per matched product (fills fit_percent).",
    "top_opportunity": "No change; re-run after each tender_assessment batch.",
    "matchup": "No change; re-run pairs whose specs change after the spec fill.",
    "spec_enrich": "No change; finish the pending rival products (fills one-sided specs).",
    "innovation_detail": "No change; re-run after KSSL spec figures load (client_position); run the waiting candidates.",
    "innovation_discovery": "No change; run for the empty domains (Artillery first).",
    "geo": "No change; derive.geo_rollup to also list category-only categories.",
    "global_requirement": "No change; key-point bullets split by code.",
}
# code steps that write tables the UI reads (not prompts)
CODE_STEPS = [
    ("backend/routine.py", "every step below and every prompt, in flow order", "nothing itself; db/flood_logs/routine_<stamp>.log/.json",
     "Ready, NOT scheduled: python -m backend.routine (--plan / --check)"),
    ("backend/market_rollups.py", "stored tenders, fits, awards, fx_rate", "market_top_opportunity_metric, market rollups", "Done 18 Oct: tender value in ₹ via stored rates"),
    ("scripts/load_fx_rates.py", "ECB / NBU daily reference rates", "fx_rate", "In the routine before market_rollups"),
    ("backend/excel_load.py descriptions", "product spec workbook Description column", "competitive_product.description, client_product.description", "New 18 Oct"),
    ("backend/harvest_specs.py --routine", "like-for-like pairs with nothing comparable", "source_document (spec pages, PDFs)", "New 18 Oct: no static pair list"),
    ("backend/location_load.py", "competitor workbook", "competitive_competitor_location", ""),
    ("prompts/derive.py hooks", "loaded rows", "labels, edge_score, overlap_status, matched_ranges, fit_percent, story links", "Planned: geo_rollup category-only ranges"),
    ("prompts/matchup_code.py", "product specs", "competitive_matchup, competitive_matchup_specification", ""),
    ("prompts/client_subtype.py, matchup_class.py", "products, specs", "product_class", "Planned: copy to serving"),
    ("planned: revenue tier", "annual_revenue × fx_rate", "competitive_competitor.revenue_tier", "Needs tier bands"),
]

# Model trial (user 18 Oct: "try Haiku 5.5 just for testing ... check the quality difference"). Same subjects, same documents,
# KSSL_MODEL=claude-haiku-5-5; product_status loaded for real then re-run with Sonnet (the data kept is Sonnet's), matchup and
# tech_article as dry runs on subjects Sonnet had loaded. Numbers below are measured from prompt_run; the findings are the read-back.
TRIAL_PROMPTS = ("product_status", "matchup", "tech_article")
TRIAL_FINDINGS = [
    "product_status (44 companies, both models loaded): 101 products flagged by both, 98 with the same status. Haiku flagged 11 more "
    "(some right, e.g. 'CROSSBOW - DEVELOPMENT'; some wrong, e.g. the Chukavin rifle, which is in service, as a prototype); Sonnet flagged 4 Haiku missed.",
    "matchup (1 pair, dry run): same decision level and the same reading (bore level, range not comparable); wording equally plain. "
    "4 more pairs could not be compared because the subject key changed mid-trial (fingerprint keys).",
    "tech_article (4 articles, dry run): same facts and key points; Haiku copied the headline as the title more often and missed details "
    "Sonnet kept (Rafael as partner and the 40-48 t combat weight on the Niedzwiedz IFV).",
    "Cost and speed: Haiku 5.5 wrote 2.5-3.5x more output tokens (it fills _sources on every field), so each run cost 3-4x more and took "
    "about twice as long. Verdict: keep Sonnet 5.5 as the default; no prompt is switched to Haiku.",
]

# 18 Oct round (user: "check every area like Product Evaluation, make sure something is populated in a decent amount, prompt correct
# and updated, tokens and cost logged; run a small flood of 20-30"). Filled from the four lane reports.
ROUND = [
    {"area": "Tenders", "prompt": "tender_assessment v2", "runs": 30, "cost": 3.31,
     "fixed": "Prompt covers every field the page shows; no change. 30 open / closing tenders without a fit, KSSL lines first.",
     "counts": "fits 645 → 675; open / closing without a fit 151 → 121",
     "open": "73 of the 121 have no category, so the prompt cannot pick them. 0 strong fits: a strong fit needs 3 checked requirement lines and notices state few."},
    {"area": "Market", "prompt": "opportunity v3 → v4", "runs": 22, "cost": 5.00,
     "fixed": "Full KSSL product names (cut names dropped 23 fit rows); tracked rival products as rows; credible-source subjects only.",
     "counts": "fits 41 → 62 (2 strong)", "open": "Rival product empty when the article names no tracked product."},
    {"area": "Market", "prompt": "global_requirement v3 → v4", "runs": 27, "cost": 6.29,
     "fixed": "Full names, de-duplication against every stored requirement, 120-character value rule; runs one at a time in the routine.",
     "counts": "requirements 139 → 151 (before the source purge)", "open": "Old duplicates from the parallel flood (5 'Medium Transport Aircraft')."},
    {"area": "Market", "prompt": "segment_assessment v1 → v2 · top_opportunity", "runs": 19, "cost": 0.55,
     "fixed": "Market outlook (the default Market view) showed '—' for every segment; counts now use active tenders only.",
     "counts": "segment reads 0 → 9; top lists rebuilt", "open": ""},
    {"area": "Competitive", "prompt": "signal v4", "runs": 29, "cost": 7.77,
     "fixed": "4 cards without a drawer re-run; never-run articles about direct rivals, credible outlets only.",
     "counts": "signals 470 → 488, shown 151 → 156, cards with a drawer 148 / 148", "open": "The chosun.com article body sits in page JSON (reader fix needed)."},
    {"area": "Competitive", "prompt": "moment v3 → v4", "runs": 20, "cost": 4.95,
     "fixed": "Qualifying competitors only; grade high / watch only; a 'none' signal is not a move.",
     "counts": "moments 8 → 45, competitors 3 → 14", "open": ""},
    {"area": "Competitive", "prompt": "project v2 → v3", "runs": 10, "cost": 14.04,
     "fixed": "Qualifying competitors only; stance threat / watch only (no fav). Web-search prompt, about $1.40 a run.",
     "counts": "projects 72 → 100 (page 60 → 96)", "open": "Next routine re-runs ~45 project subjects (~$65) at the new version, $6 per run."},
    {"area": "Network", "prompt": "client_partner_research v3 → v5", "runs": 2, "cost": 5.49,
     "fixed": "Asks for the full list each run (a re-run used to wipe it); country and buyer body; role mapping fixed in the builder.",
     "counts": "KSSL partners 12 → 20, all with a role, 19 with a country", "open": "No credible source names a supplier to KSSL."},
    {"area": "Network / Geo", "prompt": "partnership v3 · geo v3 · synthesis · field_synthesis", "runs": 30, "cost": 24.54,
     "fixed": "Visible competitors with no ties or no geo rows; geo white space no longer lists a rival's home country.",
     "counts": "ties 333 → 398; geo presence 371 → 404; geo analysis 11 → 137; competitor reads 13 → 26",
     "open": "Invalid JSON wasted 3 partnership runs (IDV, Otokar, Kalashnikov); tie verdict pill never written."},
    {"area": "Technology", "prompt": "innovation_discovery · innovation_detail v3", "runs": 24, "cost": 4.29,
     "fixed": "A discovery --rerun on 17 Oct deleted 38 finished innovations; the loader now keeps finished ones (keep_previous).",
     "counts": "innovations shown 15 in 3 categories → 36 in 9", "open": "Milestones are served but the page does not draw them."},
    {"area": "Technology", "prompt": "tech_article v2", "runs": 19, "cost": 3.77,
     "fixed": "Blog / copy-aggregator hosts kept out of subjects; 176 'fav' stances relabelled watch.",
     "counts": "tech cards 620 → 636 (before the source purge)", "open": ""},
    {"area": "Products", "prompt": "product_status v1 (new) · excel_load descriptions", "runs": 88, "cost": 4.92,
     "fixed": "Description column of the product workbook loaded for every product; status in brackets after the name.",
     "counts": "descriptions 0 → 4,602 (4,520 rival + 82 KSSL); statuses 105", "open": ""},
    {"area": "Products", "prompt": "product_category v1 (new) · catalogue display rules", "runs": 96, "cost": 11.56,
     "fixed": "Every competitor product's category checked; 4 catalogue-only categories added (Aircraft & Aerostructures, Sensors & "
              "Electro-optics, C4ISR Comms & EW, Training & Simulation). Tech-spec table shows measured figures only; descriptive specs under "
              "Features and capabilities; 'not published' lines dropped; spec-less and not-a-product rows hidden; categories A-Z, Other last.",
     "counts": "1,481 products moved; Other 1,429 → 325; matchup pairs 343 → 295 (24 verdicts kept, 0 stale)",
     "open": "A handler bug failed the first load; the stored answers were re-applied at no model cost."},
    {"area": "Sources", "prompt": "db/purge_blog_sources.py (owner decision)", "runs": 0, "cost": 0,
     "fixed": "Blocked indiandefensenews.in (Blogger blog) and vpk.name, 19fortyfive.com, defenseworld.net, military.africa (commentary); "
              "israeldefense.co.il listed as trade press. 9,138 raw pages from them taken out of every prompt's reach.",
     "counts": "3,019 rows and 6,566 source links removed (opportunities 126 → 70, requirements 151 → 85, tech cards 636 → 540). "
               "Credible-only refill, 32 runs, $6.04: opportunities → 74, requirements → 92, tech cards → 545 (half the documents fail the prompts' own tests)",
     "open": "twz.com, edrmagazine.eu, militaryleak.com, chakranewz.com, saairforce.co.za, angelone.in, iaspoint.com left as they are."},
]

ERR_CLASS = """CASE WHEN status IN ('loaded','skipped','dry_run') THEN NULL
     WHEN error ILIKE '%%weekly limit%%' OR error ILIKE '%%rate limit%%' THEN 'usage limit'
     WHEN error ILIKE '%%timed out%%' THEN 'timeout'
     WHEN error ILIKE 'load:%%' THEN 'database load error'
     WHEN status = 'rejected' OR error ILIKE 'validate%%' THEN 'rejected by validation'
     WHEN error ILIKE 'model:%%' THEN 'other model error'
     ELSE 'other' END"""


def q(cur, sql, args=None):
    cur.execute(sql, args)
    return [dict(r) for r in cur.fetchall()]


def safe(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001  one broken section must not stop the report
        print(f"  section skipped: {type(e).__name__}: {e}", file=sys.stderr)
        return default


def pending_counts() -> dict:
    """{prompt: pending} parsed from the runner's --list table."""
    env = {**os.environ, "KSSL_STAGING_DSN": DSN}
    out = subprocess.run([sys.executable, "-m", "prompts.run", "--list"], cwd=ROOT, env=env,
                         capture_output=True, text=True, encoding="utf-8", timeout=900).stdout
    res = {}
    for line in out.splitlines()[1:]:
        m = re.match(r"(\S+)\s+\d+\s+\S+\s+\S+\s+(?:never|\S+ \S+ \S+)\s+(\d+)\s", line)
        if m:
            res[m.group(1)] = int(m.group(2))
    return res


def collect(conn, with_pending: bool) -> dict:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    d: dict = {"generated": datetime.now().strftime("%d %b %Y %H:%M")}

    d["kpi"] = q(cur, f"""SELECT count(*) runs, count(*) FILTER (WHERE status='loaded') loaded,
        count(*) FILTER (WHERE status='skipped') skipped, count(*) FILTER (WHERE status IN ('failed','rejected')) failed,
        count(*) FILTER (WHERE status='dry_run') dry_runs,
        round(coalesce(sum(cost_usd),0),2) cost, round(coalesce(sum(seconds),0)/3600,1) model_hours,
        coalesce(sum(tokens_in),0) tokens_in, coalesce(sum(tokens_out),0) tokens_out, coalesce(sum(rows_loaded),0) rows,
        to_char(min(started_at) AT TIME ZONE '{TZ}','DD Mon HH24:MI') first_run,
        to_char(max(started_at) AT TIME ZONE '{TZ}','DD Mon HH24:MI') last_run,
        count(*) FILTER (WHERE finished_at IS NOT NULL) full_logged FROM staging.prompt_run""")[0]

    # the flood window = today's runs (IST); rates over the active window
    d["window"] = q(cur, f"""WITH r AS (SELECT * FROM staging.prompt_run
          WHERE (started_at AT TIME ZONE '{TZ}')::date = (now() AT TIME ZONE '{TZ}')::date)
        SELECT count(*) runs, count(*) FILTER (WHERE status='loaded') loaded, round(coalesce(sum(cost_usd),0),2) cost,
          coalesce(sum(rows_loaded),0) rows, round(coalesce(sum(seconds),0)/3600,1) model_hours,
          round(extract(epoch FROM max(started_at)-min(started_at))/3600,2) wall_hours,
          to_char(min(started_at) AT TIME ZONE '{TZ}','HH24:MI') t0, to_char(max(started_at) AT TIME ZONE '{TZ}','HH24:MI') t1
        FROM r""")[0]

    d["timeline"] = q(cur, f"""SELECT to_char(to_timestamp(floor(extract(epoch FROM started_at)/600)*600) AT TIME ZONE '{TZ}',
          'DD Mon HH24:MI') t, prompt_id, count(*) runs, count(*) FILTER (WHERE status='loaded') loaded,
          count(*) FILTER (WHERE status IN ('failed','rejected')) failed,
          round(coalesce(sum(cost_usd),0),2) cost, coalesce(sum(rows_loaded),0) rows
        FROM staging.prompt_run WHERE started_at > now() - interval '36 hours'
        GROUP BY 1, 2, floor(extract(epoch FROM started_at)/600) ORDER BY floor(extract(epoch FROM started_at)/600)""")

    d["prompts"] = q(cur, f"""SELECT prompt_id, max(prompt_version) version, max(model) model, count(*) runs,
          count(*) FILTER (WHERE status='loaded') loaded, count(*) FILTER (WHERE status='skipped') skipped,
          count(*) FILTER (WHERE status IN ('failed','rejected')) failed,
          count(*) FILTER (WHERE error ILIKE '%%weekly limit%%') limit_failed,
          round(avg(seconds) FILTER (WHERE status IN ('loaded','skipped')),0) avg_s,
          round(percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds)::numeric,0) p50_s,
          round(percentile_cont(0.9) WITHIN GROUP (ORDER BY seconds)::numeric,0) p90_s,
          round(avg(tokens_in) FILTER (WHERE status IN ('loaded','skipped'))) avg_in,
          round(avg(tokens_out) FILTER (WHERE status IN ('loaded','skipped'))) avg_out,
          round(100.0*sum(tokens_cache_read)/nullif(sum(tokens_fresh_in+tokens_cache_read+tokens_cache_write),0),0) cache_pct,
          sum(web_searches) web_searches,
          round(avg(cost_usd) FILTER (WHERE status IN ('loaded','skipped') AND cost_usd>0),3) avg_cost,
          round(coalesce(sum(cost_usd),0),2) cost, coalesce(sum(rows_loaded),0) rows,
          round(coalesce(sum(seconds),0)/3600,2) model_hours,
          round(count(*)/nullif(extract(epoch FROM max(started_at)-min(started_at))/3600,0),0) runs_per_hour,
          to_char(max(started_at) AT TIME ZONE '{TZ}','DD Mon HH24:MI') last_run
        FROM staging.prompt_run GROUP BY prompt_id ORDER BY cost DESC""")
    # per subject, its LATEST run decides: ok (loaded/skipped) or still failed (needs a --rerun)
    latest = {r["prompt_id"]: r for r in q(cur, """WITH l AS (SELECT DISTINCT ON (prompt_id, subject_key) prompt_id, status
            FROM staging.prompt_run WHERE status <> 'dry_run' ORDER BY prompt_id, subject_key, started_at DESC)
        SELECT prompt_id, count(*) FILTER (WHERE status IN ('loaded','skipped')) subj_ok,
               count(*) FILTER (WHERE status IN ('failed','rejected')) subj_failed FROM l GROUP BY 1""")}
    pend = safe(pending_counts, {}) if with_pending else {}
    for p in d["prompts"]:
        p["lane"] = LANE.get(p["prompt_id"], "–")
        p.update(latest.get(p["prompt_id"], {"subj_ok": 0, "subj_failed": 0}))
        p["pending"] = pend.get(p["prompt_id"])
        rem = (p["pending"] or 0) + p["subj_failed"]          # never run + last run failed
        p["est_cost"] = round(rem * float(p["avg_cost"] or 0), 0) if rem else 0
        rph = float(p["runs_per_hour"] or 0)
        p["est_hours"] = round(rem / rph, 1) if rem and rph else None

    d["lanes"] = []
    for lane, name in LANE_NAME.items():
        ps = [p for p in d["prompts"] if p["lane"] == lane]
        d["lanes"].append({"lane": lane, "name": name, "cap": LANE_CAP[lane],
                           "cost": round(sum(float(p["cost"]) for p in ps), 2),
                           "runs": sum(p["runs"] for p in ps), "loaded": sum(p["loaded"] for p in ps),
                           "rows": sum(int(p["rows"]) for p in ps),
                           "pending": sum((p["pending"] or 0) + p["subj_failed"] for p in ps),
                           "est_cost": sum(p["est_cost"] for p in ps),
                           "prompts": ", ".join(p["prompt_id"] for p in ps)})

    d["errors"] = q(cur, f"""SELECT {ERR_CLASS} cls, count(*) n, round(coalesce(sum(cost_usd),0),2) cost
        FROM staging.prompt_run GROUP BY 1 HAVING {ERR_CLASS} IS NOT NULL ORDER BY 2 DESC""")
    d["error_samples"] = q(cur, f"""SELECT DISTINCT ON (cls) cls, prompt_id, left(error, 220) error FROM
        (SELECT {ERR_CLASS} cls, prompt_id, error, started_at FROM staging.prompt_run) x
        WHERE cls IS NOT NULL ORDER BY cls, started_at DESC""")

    # raw layer funnel
    d["docs"] = safe(lambda: q(cur, """SELECT source_kind kind, count(*) total,
          count(*) FILTER (WHERE cardinality(competitor_ids) > 0) attributed,
          count(*) FILTER (WHERE triage ? 'route') routed,
          count(*) FILTER (WHERE triage ? 'route' AND NOT (triage->'route') @> '["none"]'::jsonb) useful,
          count(*) FILTER (WHERE processed_by IS NOT NULL AND processed_by <> '{}'::jsonb) processed
        FROM staging.source_document GROUP BY 1 ORDER BY 2 DESC"""), [])
    d["routes"] = safe(lambda: q(cur, """SELECT r route, count(*) n FROM staging.source_document,
          jsonb_array_elements_text(triage->'route') r GROUP BY 1 ORDER BY 2 DESC"""), [])
    d["tenders"] = safe(lambda: q(cur, """SELECT
          (SELECT count(*) FROM staging.tender_raw) raw,
          (SELECT count(*) FROM staging.tender_raw WHERE NOT defence_tags <@ ARRAY['general_defence']::text[]) kssl_tagged,
          (SELECT count(*) FROM staging.market_tender) tenders,
          (SELECT count(DISTINCT subject_key) FROM staging.prompt_run WHERE prompt_id='tender' AND status='loaded') extracted,
          (SELECT count(*) FROM staging.market_tender_fit_assessment) assessed,
          (SELECT count(*) FROM staging.market_top_opportunity_tender) top""")[0], {})
    d["fit"] = safe(lambda: q(cur, """SELECT coalesce(fit_grade,'none') k, count(*) n
        FROM staging.market_tender_fit_assessment GROUP BY 1 ORDER BY 2 DESC"""), [])
    d["signal_labels"] = safe(lambda: q(cur, """SELECT coalesce(classification,'none') k, count(*) n
        FROM staging.competitive_signal GROUP BY 1 ORDER BY 2 DESC"""), [])
    d["tech_labels"] = safe(lambda: q(cur, """SELECT coalesce(classification,'none') k, count(*) n
        FROM staging.technology_overview_article GROUP BY 1 ORDER BY 2 DESC"""), [])

    # every staging table: rows + who fills it
    fills: dict = {}
    for f in sorted((ROOT / "prompts").glob("*.yml")):
        try:
            spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for t in spec.get("fills") or []:
            fills.setdefault(t, []).append(spec.get("id", f.stem))
    tables = [r["table_name"] for r in q(cur, """SELECT table_name FROM information_schema.tables
        WHERE table_schema='staging' AND table_type='BASE TABLE' ORDER BY 1""")]
    union = " UNION ALL ".join(f"SELECT '{t}' t, count(*) n FROM staging.\"{t}\"" for t in tables)
    counts = {r["t"]: r["n"] for r in q(cur, union)}
    d["tables"] = []
    for t in tables:
        state = ("hidden section" if t in HIDDEN else "superseded" if t in SUPERSEDED
                 else "filled" if counts[t] else "empty")
        d["tables"].append({"table": t, "rows": counts[t], "by": ", ".join(fills.get(t, [])) or "code / Excel / setup",
                            "state": state})

    d["age"] = safe(lambda: q(cur, AGE_SQL), [])
    avg = {p["prompt_id"]: float(p["avg_cost"] or 0) for p in d["prompts"]}
    pend_of = {p["prompt_id"]: (p["pending"] or 0) + p["subj_failed"] for p in d["prompts"]}
    d["impact"] = []
    for it in IMPACT:
        conn.rollback()                                   # a failed measure must not poison the next one
        row = {k: v for k, v in it.items() if k not in ("measure", "rerun")}
        row["now"] = safe(lambda: list(q(cur, it["measure"])[0].values())[0], "–")
        if it.get("rerun"):
            pid, sql = it["rerun"]
            n = safe(lambda: list(q(cur, sql)[0].values())[0], None) if sql else pend_of.get(pid)
            row["rerun"] = {"prompt": pid, "subjects": n, "cost": round((n or 0) * avg.get(pid, 0)) if avg.get(pid) else None}
        d["impact"].append(row)
    d["catalogue"] = catalogue(counts, {p["prompt_id"]: p for p in d["prompts"]})
    d["redteam"] = []
    for it in RED_TEAM + RED_TEAM_PEER:
        conn.rollback()
        row = {k: v for k, v in it.items() if k != "measure"}
        row["now"] = safe(lambda: list(q(cur, it["measure"])[0].values())[0], None) if it.get("measure") else None
        d["redteam"].append(row)
    d["code_steps"] = [dict(zip(("step", "reads", "writes", "plan"), s)) for s in CODE_STEPS]
    conn.rollback()
    d["trial"] = safe(lambda: q(cur, """WITH h AS (SELECT DISTINCT prompt_id, subject_key FROM staging.prompt_run
            WHERE model = 'claude-haiku-5-5' AND prompt_id = ANY(%s) AND status IN ('loaded','skipped','dry_run')),
          r AS (SELECT DISTINCT ON (p.prompt_id, p.subject_key, p.model) p.* FROM staging.prompt_run p JOIN h USING (prompt_id, subject_key)
            WHERE p.model IN ('claude-haiku-5-5','claude-sonnet-5-5') AND p.status IN ('loaded','skipped','dry_run')
            ORDER BY p.prompt_id, p.subject_key, p.model, p.started_at DESC)
        SELECT prompt_id, model, count(*) runs, round(sum(cost_usd), 3) cost, round(avg(cost_usd), 4) avg_cost, round(avg(seconds), 1) avg_s,
               round(avg(tokens_out)) avg_out, coalesce(sum(rows_loaded), 0) rows FROM r GROUP BY 1, 2 ORDER BY 1, 2""", (list(TRIAL_PROMPTS),)), [])
    d["trial_findings"] = TRIAL_FINDINGS
    d["round"] = ROUND
    d["routine"] = {"plan": [], "problems": [], "notes": []}
    if with_pending:
        def _routine():
            from backend import routine
            rc = routine.connect()
            try:
                problems, notes = routine.check(rc)
                return {"plan": routine.plan_rows(rc), "problems": problems, "notes": notes}
            finally:
                rc.close()
        d["routine"] = safe(_routine, d["routine"])
    return d


def catalogue(counts: dict, stats: dict) -> list:
    """Every prompt file -> input (subject, documents, context, web search), output (tables + columns), rules, plan."""
    sets = yaml.safe_load((ROOT / "prompts" / "sets.yml").read_text(encoding="utf-8")) or {}
    set_of = {p: s.get("title", k) for k, s in sets.items() for p in s.get("prompts", [])}
    shared = yaml.safe_load((ROOT / "prompts" / "_shared.yml").read_text(encoding="utf-8")) or {}
    ctx_desc = shared.get("context_blocks") or {}
    tabs = lambda s: sorted(set(re.findall(r"staging(?:_ui)?\.(\w+)", s or "")))
    out = []
    for f in sorted((ROOT / "prompts").glob("*.yml")):
        spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if "id" not in spec:
            continue
        sub = spec.get("subject") or {}
        docs = sub.get("documents") or []
        doc_txt = [f"{x.get('from')}: {x.get('field') or ', '.join(tabs(x.get('query')))}" for x in docs if isinstance(x, dict)]
        outputs = []
        for t, o in (spec.get("output") or {}).items():
            o = o if isinstance(o, dict) else {}
            cols = o.get("columns") or {}
            kids = o.get("children") or {}
            outputs.append({"table": t, "rows": counts.get(t),
                            "model": list(cols) if isinstance(cols, (dict, list)) else [],
                            "loader": list(o.get("loader") or []),
                            "children": [{"table": k, "rows": counts.get(k),
                                          "cols": (v.get("columns") if isinstance(v, dict) else None) or []}
                                         for k, v in (kids.items() if isinstance(kids, dict) else ((k, {}) for k in kids))]})
        st = stats.get(spec["id"], {})
        out.append({"id": spec["id"], "title": spec.get("title"), "version": spec.get("version"), "set": set_of.get(spec["id"], "–"),
                    "cadence": spec.get("cadence"), "web": bool(spec.get("web_search")), "shows_on": spec.get("shows_on"),
                    "subject_key": sub.get("key"), "subject_from": tabs(sub.get("query")), "documents": doc_txt,
                    "context": [{"name": c, "desc": str(ctx_desc.get(c, ""))[:160]} for c in spec.get("context") or []],
                    "fills": spec.get("fills") or [], "outputs": outputs, "derive": spec.get("derive") or [],
                    "handler": spec.get("handler"), "hidden": any(t in HIDDEN for t in spec.get("fills") or []),
                    "runs": st.get("runs", 0), "avg_cost": st.get("avg_cost"), "pending": (st.get("pending") or 0) + st.get("subj_failed", 0),
                    "plan": PLANNED.get(spec["id"], "No change.")})
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KSSL Flood Analytics</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mute:#5d6470;--line:#e3e6ea;--acc:#2f6fed;--ok:#1f9d55;--warn:#d98b00;--bad:#d64545}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111317;--card:#1a1d23;--ink:#e8eaee;--mute:#9aa3ae;--line:#2a2f37;--acc:#6b9bff;--ok:#3cc47c;--warn:#f0ad3a;--bad:#ef6b6b}}
:root[data-theme="dark"]{--bg:#111317;--card:#1a1d23;--ink:#e8eaee;--mute:#9aa3ae;--line:#2a2f37;--acc:#6b9bff;--ok:#3cc47c;--warn:#f0ad3a;--bad:#ef6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1280px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:32px 0 10px}.sub{color:var(--mute);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}
.k{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.k b{display:block;font-size:22px}.k span{color:var(--mute);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;overflow-x:auto}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--mute);font-weight:600;position:sticky;top:0;background:var(--card)}td:first-child,th:first-child,.l{text-align:left}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;border:1px solid var(--line)}
.filled{color:var(--ok)}.empty{color:var(--bad)}.hidden,.superseded{color:var(--mute)}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;min-width:80px}.bar i{display:block;height:100%;background:var(--acc)}
.bar.over i{background:var(--bad)}canvas{max-height:300px}
.flow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px}.flow span{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.note{color:var(--mute);font-size:12.5px;margin-top:6px}code{font-size:12px}
.tbl-wrap{max-height:520px;overflow:auto}
td.w,th.w{white-space:normal;text-align:left;vertical-align:top;min-width:160px}td.w{max-width:340px}
.n-noted{color:var(--mute)}.n-corrected{color:var(--warn);border-color:var(--warn)}.n-missed{color:var(--bad);border-color:var(--bad)}
nav{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}nav a{font-size:12.5px;color:var(--acc);text-decoration:none;border:1px solid var(--line);border-radius:8px;padding:3px 9px;background:var(--card)}
.pc{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:8px}.pc summary{cursor:pointer;padding:10px 14px;display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.pc summary b{font-size:14px}.pc .body{padding:0 14px 14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.pc h4{margin:6px 0 4px;font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}.pc ul{margin:0;padding-left:18px;font-size:12.5px}
.chip{display:inline-block;font-family:ui-monospace,Consolas,monospace;font-size:11px;background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin:1px}
.plan{border-left:3px solid var(--acc);padding-left:8px}
</style></head><body><main>
<h1>KSSL data flood: analytics</h1>
<div class="sub">Generated __GEN__ (IST) from <code>staging.prompt_run</code> and the staging tables · local <code>kssl_staging</code> · status: routine ready, not scheduled</div>
<nav><a href="#routine">Routine</a><a href="#trial">Model trial</a><a href="#round">18 Oct round</a><a href="#age">Data age</a><a href="#lanes-h">Lanes</a><a href="#prompts-h">Per prompt</a><a href="#tables-h">Tables</a><a href="#impact">Frontend → DB impact</a><a href="#cat">Prompt catalogue</a><a href="#code">Code steps</a><a href="#redteam">Red-team audit</a></nav>
<div id="kpis" class="kpis"></div>

<h2 id="age">Data age by pillar (staging, counted from today)</h2>
<div class="card tbl-wrap"><table id="age-t"></table>
<div class="note">Future = planned steps (expected deliveries, programme ends). No date = the source gave none; those rows drop out of time filters such as "Last 30 days". Partnership and project history is old by nature (a 2015 agreement can still be active).</div></div>

<h2>How the flood works</h2>
<div class="card"><div class="flow">
<span>Harvest (free): site RSS / sitemaps, DC corpus (triage), tender APIs, Google News</span>→
<span>Raw layer: <code>source_document</code>, <code>tender_raw</code></span>→
<span>Attribution by code (aliases → competitor)</span>→
<span>Triage pass (cheap model, batched): route each document to a prompt</span>→
<span>Prompts (Sonnet via claude CLI): one run per subject</span>→
<span>Loader: validate, quotes checked, derive rules (labels by code)</span>→
<span>Staging tables + <code>fact_source</code></span>→
<span>Review site :5180 → Approve → serving (live)</span></div>
<div class="note">Every run is one transaction: it is logged in <code>prompt_run</code> (prompt, subject, model, time, tokens, cost, rows, full prompt and reply) and loads all-or-nothing.</div></div>

<h2 id="routine">Routine: the scheduled flow, step by step</h2>
<div class="card"><div class="note" style="margin:0 0 8px">One command runs the whole flow above in order: <code>python -m backend.routine</code> (budget cap
per run, default $60; each prompt step has its own cap, so a backlog drains over several runs, newest first). <code>--plan</code> shows what would run,
<code>--check</code> lists what would break or leave a page empty. Nothing is scheduled: a Windows task or cron line starts it when you decide.
What makes it repeatable: rolling harvest windows (no fixed dates), cadence per prompt, fingerprint keys (a matchup or spec subject re-runs only
when its compared rows or documents change), per-run budgets (the matchup engine no longer counts all past spend), hidden-section prompts marked
<code>routine: false</code>, and a model usage limit stops model steps while code steps still run.</div>
<div id="rt-check" class="note"></div>
<div class="tbl-wrap"><table id="routine-t"></table></div></div>

<h2 id="trial">Model trial: Haiku 5.5 vs Sonnet 5.5 (same subjects)</h2>
<div class="card"><table id="trial-t"></table><ul id="trial-f" style="font-size:12.5px;margin:10px 0 0;padding-left:18px"></ul>
<div class="note">Cost is what the claude CLI reports per run. Latest run per subject and model.</div></div>

<h2 id="round">18 Oct round: every area checked, small floods (20-30 subjects)</h2>
<div class="card tbl-wrap"><table id="round-t"></table></div>

<h2 id="lanes-h">Lanes (parallel workers, spend vs cap)</h2>
<div class="card"><table id="lanes"></table></div>

<h2>Flood rate over time (10-minute buckets, IST)</h2>
<div class="grid2"><div class="card"><canvas id="cRuns"></canvas><div class="note">Prompt runs started per 10 minutes, by lane.</div></div>
<div class="card"><canvas id="cCum"></canvas><div class="note">Cumulative spend (USD) and rows loaded.</div></div></div>

<h2 id="prompts-h">Per prompt: done, remaining, speed, tokens, cost</h2>
<div class="card tbl-wrap"><table id="prompts"></table>
<div class="note">Per subject, the latest run counts. Subjects done = latest run loaded or skipped; To re-run = latest run failed (mostly the usage limit; needs <code>--rerun</code>); Never run = not yet run at the current prompt version (runner <code>--list</code>). Done % = done ÷ (done + to re-run + never run). Estimates = (to re-run + never run) × average cost, and ÷ observed runs per hour.</div></div>

<h2>Raw layer → tables (funnel)</h2>
<div class="grid2"><div class="card"><table id="docs"></table></div>
<div class="card"><canvas id="cRoutes"></canvas><div class="note">Triage routes: which prompt each document was sent to (a document can go to several).</div></div></div>
<div class="grid2" style="margin-top:12px"><div class="card"><table id="tenders"></table></div>
<div class="card"><canvas id="cLabels"></canvas><div class="note">Output mix: signal labels, tender KSSL fit, tech article kinds.</div></div></div>

<h2>Failures</h2>
<div class="grid2"><div class="card"><table id="errors"></table></div><div class="card"><table id="errsamp"></table></div></div>

<h2 id="tables-h">Every staging table</h2>
<div class="card tbl-wrap"><table id="tables"></table></div>

<h2 id="impact">Frontend changes → database, prompt and code impact</h2>
<div class="card"><div class="note" style="margin:0 0 8px">Source: <code>docs/ui_port/DB_CHANGE_NOTES.md</code>, checked against the commits and today's staging data. <span class="pill n-noted">noted</span> as in the notes · <span class="pill n-corrected">corrected</span> the notes' assumption differs from the DB · <span class="pill n-missed">missed</span> not in the notes. "Now" is measured live. Re-run cost = subjects × the prompt's observed average cost. Nothing here has been applied.</div>
<div id="impact-sum" class="kpis" style="margin:0 0 10px"></div>
<div class="tbl-wrap" style="max-height:none"><table id="impact-t"></table></div></div>

<h2 id="cat">Prompt catalogue: input → output → tables (final, with planned changes)</h2>
<div class="note">Read from <code>prompts/*.yml</code> at generation time. Input = one run per subject row + its documents + context blocks. Output = the tables the model writes (model columns), what the loader fills by code, child tables, then the derive rules. Row counts are staging today.</div>
<div id="cat-l" style="margin-top:8px"></div>

<h2 id="code">Code steps that write UI tables (no AI)</h2>
<div class="card"><table id="code-t"></table></div>

<h2 id="redteam">Red-team audit (18 Oct 2026): findings, fixes, what is left</h2>
<div class="card"><div class="note" style="margin:0 0 8px">The product attacked as a client would use it, at every level, under the standing rule: nothing hardcoded, defaulted or fabricated; data only from the tables, wording only in the UI chrome. Split: <b>kssl-52</b> = database, prompts / loader, data builders, deploy; <b>kssl-40</b> = frontend and HTTP API. <span class="pill filled">fixed</span> done and checked · <span class="pill n-corrected">open</span> needs more work · <span class="pill n-missed">decision</span> needs you. Tests: npm test 128 / 128, all Python self-checks pass. Commits 0bb043e, f139446 (frontend + API, local only); database / prompt fixes uncommitted. "Now" re-counts the problem live (0 = gone). Local only: nothing synced or deployed.</div>
<div id="rt-sum" class="kpis" style="margin:0 0 10px"></div>
<div class="tbl-wrap" style="max-height:none"><table id="rt-t"></table></div></div>
</main>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id), f = n => n == null ? '–' : Number(n).toLocaleString('en-IN');
const usd = n => n == null ? '–' : '$' + Number(n).toLocaleString('en-IN', {maximumFractionDigits: 2});
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const K = D.kpi, W = D.window;
$('kpis').innerHTML = [
  [f(K.runs), 'prompt runs (all time)'], [f(K.loaded), 'loaded'], [f(K.skipped), 'skipped (nothing to add)'],
  [f(K.failed), 'failed / rejected'], [usd(K.cost), 'total spend'], [f(K.rows), 'rows loaded'],
  [K.model_hours + ' h', 'model time (summed)'], [f(Math.round(K.tokens_in/1e6)) + ' M / ' + f(Math.round(K.tokens_out/1e3)) + ' k', 'tokens in / out'],
  [W.t0 + '–' + W.t1, "today's flood window"], [f(Math.round(W.runs / Math.max(W.wall_hours, .01))) + ' /h', 'runs per hour today'],
  [usd(W.cost / Math.max(W.wall_hours, .01)) + ' /h', 'spend per hour today'], [f(Math.round(W.model_hours / Math.max(W.wall_hours, .01))) + '×', 'average parallel calls'],
  [f(K.full_logged), 'runs with full logging'],
].map(([b, s]) => `<div class="k"><b>${b}</b><span>${s}</span></div>`).join('');

const head = cols => '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>';
$('lanes').innerHTML = head(['Lane', 'Prompts', 'Runs', 'Loaded', 'Rows', 'Spend', 'Cap', 'Spend vs cap', 'Remaining subjects', 'Est. $ left']) +
  D.lanes.map(l => { const p = l.cost / l.cap * 100; return `<tr><td>${l.lane} · ${esc(l.name)}</td><td class="l" style="white-space:normal;max-width:260px">${esc(l.prompts)}</td><td>${f(l.runs)}</td><td>${f(l.loaded)}</td><td>${f(l.rows)}</td><td>${usd(l.cost)}</td><td>${usd(l.cap)}</td><td><div class="bar ${p > 100 ? 'over' : ''}"><i style="width:${Math.min(p, 100)}%"></i></div></td><td>${f(l.pending)}</td><td>${usd(l.est_cost)}</td></tr>`; }).join('');

$('prompts').innerHTML = head(['Prompt', 'Lane', 'Ver', 'Runs', 'Loaded', 'Skipped', 'Failed', 'Limit fails', 'Subjects done', 'To re-run', 'Never run', 'Done %', 'Avg s', 'p50 / p90 s', 'Runs/h', 'Avg tokens in / out', 'Cache %', 'Web', 'Avg $', 'Spend', 'Rows', 'Est. $ left', 'Est. h left', 'Last run']) +
  D.prompts.map(p => { const done = p.subj_ok, tot = done + p.subj_failed + (p.pending || 0), pc = tot ? Math.round(done / tot * 100) : null;
    return `<tr><td>${esc(p.prompt_id)}</td><td>${p.lane}</td><td>${esc(p.version)}</td><td>${f(p.runs)}</td><td>${f(p.loaded)}</td><td>${f(p.skipped)}</td><td>${f(p.failed)}</td><td>${f(p.limit_failed)}</td><td>${f(p.subj_ok)}</td><td>${f(p.subj_failed)}</td><td>${f(p.pending)}</td><td>${pc == null ? '–' : pc + '%'}</td><td>${f(p.avg_s)}</td><td>${f(p.p50_s)} / ${f(p.p90_s)}</td><td>${f(p.runs_per_hour)}</td><td>${f(p.avg_in)} / ${f(p.avg_out)}</td><td>${p.cache_pct == null ? '–' : p.cache_pct + '%'}</td><td>${f(p.web_searches)}</td><td>${usd(p.avg_cost)}</td><td>${usd(p.cost)}</td><td>${f(p.rows)}</td><td>${usd(p.est_cost)}</td><td>${p.est_hours == null ? '–' : p.est_hours}</td><td>${esc(p.last_run)}</td></tr>`; }).join('');

$('docs').innerHTML = head(['Documents by kind', 'Total', 'Linked to a competitor', 'Triaged', 'Useful route', 'Processed']) +
  D.docs.map(r => `<tr><td>${esc(r.kind)}</td><td>${f(r.total)}</td><td>${f(r.attributed)}</td><td>${f(r.routed)}</td><td>${f(r.useful)}</td><td>${f(r.processed)}</td></tr>`).join('');
const T = D.tenders || {};
$('tenders').innerHTML = head(['Tender funnel', 'Count']) + [['Defence notices harvested (raw)', T.raw], ['Tagged to a KSSL product area', T.kssl_tagged], ['In the Tenders table', T.tenders], ['Extracted by the tender prompt', T.extracted], ['Assessed for KSSL fit', T.assessed], ['In the Top opportunity list', T.top]]
  .map(([a, b]) => `<tr><td>${a}</td><td>${f(b)}</td></tr>`).join('');
$('errors').innerHTML = head(['Failure class', 'Runs', 'Spend wasted']) + D.errors.map(e => `<tr><td>${esc(e.cls)}</td><td>${f(e.n)}</td><td>${usd(e.cost)}</td></tr>`).join('');
$('errsamp').innerHTML = head(['Latest example', 'Prompt', 'Error']) + D.error_samples.map(e => `<tr><td>${esc(e.cls)}</td><td>${esc(e.prompt_id)}</td><td class="l" style="white-space:normal">${esc(e.error)}</td></tr>`).join('');
$('tables').innerHTML = head(['Table', 'Rows', 'State', 'Filled by']) +
  D.tables.map(t => `<tr><td>${esc(t.table)}</td><td>${f(t.rows)}</td><td><span class="pill ${t.state.split(' ')[0]}">${esc(t.state)}</span></td><td class="l">${esc(t.by)}</td></tr>`).join('');

$('age-t').innerHTML = head(['Pillar', 'Data', 'Rows', 'Oldest', 'Newest', 'Future', '0–1 m', '1–3 m', '3–6 m', '6–12 m', '1–3 y', '3 y+', 'No date', 'Older than 1 y']) +
  (D.age || []).map(a => { const old = +a.y3 + +a.y3p; return `<tr><td>${esc(a.pillar)}</td><td class="l">${esc(a.what)}</td><td>${f(a.n)}</td><td>${esc(a.oldest)}</td><td>${esc(a.newest)}</td><td>${f(a.future)}</td><td>${f(a.m1)}</td><td>${f(a.m3)}</td><td>${f(a.m6)}</td><td>${f(a.m12)}</td><td>${f(a.y3)}</td><td>${f(a.y3p)}</td><td>${f(a.nodate)}</td><td>${a.n ? Math.round(old / a.n * 100) + '%' : '–'}</td></tr>`; }).join('');

const I = D.impact || [], cnt = k => I.filter(x => x.notes === k).length;
const reruns = I.filter(x => x.rerun && x.rerun.cost != null);
$('impact-sum').innerHTML = [[I.length, 'changes checked'], [cnt('missed'), 'missed in the notes'], [cnt('corrected'), 'notes corrected by the DB'],
  [I.filter(x => /^None/.test(x.db)).length, 'need no schema change'], [I.filter(x => /^None/.test(x.prompt)).length, 'need no prompt change'],
  [usd(reruns.reduce((s, x) => s + x.rerun.cost, 0)), 'all listed re-runs (est.)']].map(([b, s]) => `<div class="k"><b>${b}</b><span>${s}</span></div>`).join('');
$('impact-t').innerHTML = head(['Area', 'Frontend change', 'Notes', 'Now (measured)', 'Database', 'Prompt', 'Code', 'Re-run', 'Decision for you']).replace(/<th>/g, '<th class="w">') +
  I.map(x => `<tr><td class="w">${esc(x.area)}</td><td class="w">${esc(x.change)}</td><td class="l"><span class="pill n-${x.notes}">${x.notes}</span></td><td class="w">${esc(x.now)}</td><td class="w">${esc(x.db)}</td><td class="w">${esc(x.prompt)}</td><td class="w">${esc(x.code)}</td><td class="w">${x.rerun ? `${esc(x.rerun.prompt)}: ${f(x.rerun.subjects)} subjects${x.rerun.cost != null ? ' ≈ ' + usd(x.rerun.cost) : ''}` : '–'}</td><td class="w">${esc(x.decision) || '–'}</td></tr>`).join('');

const chips = a => a.map(c => `<span class="chip">${esc(c)}</span>`).join(' ');
$('cat-l').innerHTML = (D.catalogue || []).map(p => `<details class="pc"><summary><b>${esc(p.id)}</b><span class="pill">v${esc(p.version)}</span><span class="pill">${esc(p.cadence)}</span>${p.web ? '<span class="pill">web search</span>' : ''}${p.hidden ? '<span class="pill hidden">hidden section: not run</span>' : ''}<span class="sub">${esc(p.title)}</span><span class="sub" style="margin-left:auto">${f(p.runs)} runs · ${f(p.pending)} left · avg ${usd(p.avg_cost)}</span></summary>
<div class="body">
 <div><h4>Input</h4><ul><li>One run per <b>${esc(p.subject_key)}</b> from ${chips(p.subject_from)}</li>${p.documents.map(x => `<li>Documents: ${esc(x)}</li>`).join('')}<li>Context: ${p.context.map(c => `<span class="chip" title="${esc(c.desc)}">${esc(c.name)}</span>`).join(' ') || '–'}</li><li>Set: ${esc(p.set)}</li></ul></div>
 <div><h4>Output → tables</h4><ul>${p.outputs.map(o => `<li><b>${esc(o.table)}</b> (${f(o.rows)} rows)<br>model: ${chips(o.model) || '–'}${o.loader.length ? '<br>loader: ' + chips(o.loader) : ''}${o.children.map(k => `<br>↳ <b>${esc(k.table)}</b> (${f(k.rows)}) ${chips(k.cols)}`).join('')}</li>`).join('')}</ul></div>
 <div><h4>Rules after load</h4><ul><li>Derive: ${chips(p.derive) || '–'}</li><li>Handler: ${esc(p.handler) || 'generic loader'}</li><li>Shows on: ${esc(p.shows_on)}</li></ul>
 <h4>Planned change</h4><div class="plan">${esc(p.plan)}</div></div>
</div></details>`).join('');
const RT = D.redteam || [], rc = k => RT.filter(x => x.status === k).length;
$('rt-sum').innerHTML = [[RT.length, 'findings'], [rc('fixed'), 'fixed'], [rc('open'), 'open'], [rc('decision'), 'need your decision'],
  [RT.filter(x => x.sev === 'high').length, 'high severity'], [RT.filter(x => x.sev === 'high' && x.status !== 'fixed').length, 'high and not fixed']]
  .map(([b, s]) => `<div class="k"><b>${b}</b><span>${s}</span></div>`).join('');
const stPill = s => `<span class="pill ${s === 'fixed' ? 'filled' : s === 'open' ? 'n-corrected' : 'n-missed'}">${s}</span>`;
const sevOrd = {high: 0, med: 1, low: 2, info: 3}, stOrd = {decision: 0, open: 1, fixed: 2};
$('rt-t').innerHTML = head(['Lane', 'Severity', 'Area', 'Finding', 'Fix / proposal', 'Status', 'Now']).replace(/<th>/g, '<th class="w">') +
  [...RT].sort((a, b) => (stOrd[a.status] - stOrd[b.status]) || (sevOrd[a.sev] - sevOrd[b.sev])).map(x => `<tr><td class="l">${esc(x.lane)}</td><td class="l">${esc(x.sev)}</td><td class="l">${esc(x.area)}</td><td class="w">${esc(x.finding)}</td><td class="w">${esc(x.fix)}</td><td class="l">${stPill(x.status)}</td><td>${x.now == null ? '–' : f(x.now)}</td></tr>`).join('');
const R = D.routine || {plan: [], problems: [], notes: []};
$('rt-check').innerHTML = (R.problems.length ? `<b class="empty">${R.problems.length} problem(s)</b><ul>${R.problems.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : (R.plan.length ? '<b class="filled">Health check: no problems</b>' : 'Health check not run (--no-pending).'))
  + (R.notes.length ? `<div>Notes:</div><ul>${R.notes.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '');
$('routine-t').innerHTML = head(['#', 'Step', 'Kind', 'What', 'Pending now', 'Cap per run']) + R.plan.map((s, i) => `<tr><td>${i + 1}</td><td class="l">${esc(s.step)}</td><td class="l">${esc(s.kind)}</td><td class="l" style="white-space:normal">${esc(s.what)}${s.skipped ? ' <span class="pill hidden">skipped: ' + esc(s.skipped) + '</span>' : ''}</td><td>${s.kind === 'prompt' && !s.skipped ? f(s.pending) : '–'}</td><td>${s.kind === 'prompt' && !s.skipped ? usd(s.cap) : '–'}</td></tr>`).join('');
$('trial-t').innerHTML = head(['Prompt', 'Model', 'Subjects', 'Spend', 'Avg $ / run', 'Avg s', 'Avg tokens out', 'Rows']) + (D.trial || []).map(x => `<tr><td>${esc(x.prompt_id)}</td><td class="l">${esc(x.model)}</td><td>${f(x.runs)}</td><td>${usd(x.cost)}</td><td>${usd(x.avg_cost)}</td><td>${f(x.avg_s)}</td><td>${f(x.avg_out)}</td><td>${f(x.rows)}</td></tr>`).join('');
$('trial-f').innerHTML = (D.trial_findings || []).map(x => `<li>${esc(x)}</li>`).join('');
$('round-t').innerHTML = head(['Area', 'Prompt / step', 'Checked and fixed', 'Runs', 'Spend', 'Before → after', 'Open']).replace(/<th>/g, '<th class="w">') +
  (D.round || []).map(x => `<tr><td class="l">${esc(x.area)}</td><td class="l">${esc(x.prompt)}</td><td class="w">${esc(x.fixed)}</td><td>${f(x.runs)}</td><td>${usd(x.cost)}</td><td class="w">${esc(x.counts)}</td><td class="w">${esc(x.open) || '–'}</td></tr>`).join('');
$('code-t').innerHTML = head(['Step', 'Reads', 'Writes', 'Planned']) + (D.code_steps || []).map(s => `<tr><td class="l">${esc(s.step)}</td><td class="l">${esc(s.reads)}</td><td class="l" style="white-space:normal">${esc(s.writes)}</td><td class="l">${esc(s.plan) || '–'}</td></tr>`).join('');

// charts
Chart.defaults.color = css('--mute'); Chart.defaults.borderColor = css('--line'); Chart.defaults.font.size = 11;
const pal = {A: '#2f6fed', B: '#1f9d55', C: '#d98b00', D: '#8b5cf6', E: '#d64545', '–': '#888'};
const lane = p => (D.prompts.find(x => x.prompt_id === p) || {}).lane || '–';
const ts = [...new Set(D.timeline.map(r => r.t))];
const byLane = {}; D.timeline.forEach(r => { const l = lane(r.prompt_id); (byLane[l] ||= {})[r.t] = ((byLane[l] || {})[r.t] || 0) + r.runs; });
new Chart($('cRuns'), {type: 'bar', data: {labels: ts, datasets: Object.keys(byLane).sort().map(l => ({label: l + ' ' + (D.lanes.find(x => x.lane === l) || {name: ''}).name, data: ts.map(t => byLane[l][t] || 0), backgroundColor: pal[l], stack: 's'}))},
  options: {scales: {x: {stacked: true, ticks: {maxTicksLimit: 14}}, y: {stacked: true}}, plugins: {legend: {position: 'bottom'}}}});
let c = 0, r = 0; const cum = ts.map(t => { D.timeline.filter(x => x.t === t).forEach(x => { c += +x.cost; r += +x.rows; }); return [c, r]; });
new Chart($('cCum'), {type: 'line', data: {labels: ts, datasets: [{label: 'Spend USD', data: cum.map(x => x[0].toFixed(2)), borderColor: '#d64545', yAxisID: 'y', pointRadius: 0}, {label: 'Rows loaded', data: cum.map(x => x[1]), borderColor: '#1f9d55', yAxisID: 'y1', pointRadius: 0}]},
  options: {scales: {x: {ticks: {maxTicksLimit: 14}}, y: {position: 'left'}, y1: {position: 'right', grid: {drawOnChartArea: false}}}, plugins: {legend: {position: 'bottom'}}}});
new Chart($('cRoutes'), {type: 'bar', data: {labels: D.routes.map(x => x.route), datasets: [{label: 'documents', data: D.routes.map(x => x.n), backgroundColor: '#2f6fed'}]}, options: {indexAxis: 'y', plugins: {legend: {display: false}}}});
const lab = [...D.signal_labels.map(x => ['signal: ' + x.k, x.n]), ...D.fit.map(x => ['tender fit: ' + x.k, x.n]), ...D.tech_labels.map(x => ['tech: ' + x.k, x.n])];
new Chart($('cLabels'), {type: 'bar', data: {labels: lab.map(x => x[0]), datasets: [{data: lab.map(x => x[1]), backgroundColor: lab.map(x => x[0].startsWith('signal') ? '#2f6fed' : x[0].startsWith('tender') ? '#1f9d55' : '#8b5cf6')}]}, options: {indexAxis: 'y', plugins: {legend: {display: false}}}});
</script></body></html>"""


def render(d: dict) -> str:
    data = json.dumps(d, default=str).replace("</", "<\\/")
    return TEMPLATE.replace("__GEN__", html.escape(d["generated"])).replace("__DATA__", data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "db" / "excel_reports" / "flood_report.html"))
    ap.add_argument("--no-pending", action="store_true", help="skip the runner --list call (faster)")
    a = ap.parse_args(argv)
    with psycopg2.connect(DSN) as conn:
        d = collect(conn, not a.no_pending)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(render(d), encoding="utf-8")
    print(f"wrote {a.out}  ({d['kpi']['runs']} runs, {len(d['tables'])} tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
