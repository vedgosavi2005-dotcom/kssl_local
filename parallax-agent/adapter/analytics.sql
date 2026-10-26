-- ANALYTICS LAYER FOR THE PARALLAX ANALYST AGENT (KSSL_Deploy v2, the live kssl_serving database)
--
-- The SQL agent reads ONLY this schema. Every view flattens the live serving.* tables (one row
-- per card plus child tables, no foreign keys) into typed, plainly named columns, so the agent
-- never has to know the card graph or the kssl_* column names (kssl_ always means the client).
-- The COMMENTs are the agent's schema documentation: the service reads them from pg_description
-- and puts them in the data agent's prompt.
--
-- What the views show is what the live UI shows: competitors that do not qualify
-- (competitive_competitor.qualifies IS NOT TRUE) are hidden with everything that names them,
-- signals classified 'none' and candidate innovations are left out, as backend/areas does.
--
-- Ids are text: competitor-side ids are uuids, everything else 63-bit integers (beyond int and
-- beyond what a browser can hold exactly).
--
-- Idempotent: the service applies this file on startup (agent/db.py ensure_analytics). Views
-- only: Approve and make_test_pair.sh never touch this schema. The serving guard triggers
-- (kssl_only_via_approve) block writes, not SELECT or DDL in another schema.
--
-- The agent connects as parallax_agent: SELECT on analytics.* and nothing else, read-only
-- transactions, 5 s statement timeout. Views run with their owner's privileges.

CREATE SCHEMA IF NOT EXISTS analytics;
COMMENT ON SCHEMA analytics IS 'Read-only analytics views for the Parallax analyst agent (the live competitive-intelligence data).';

-- ---------------------------------------------------------------- helpers

-- text -> numeric, NULL for 'n/d', ranges and prose (thousands separators allowed)
CREATE OR REPLACE FUNCTION analytics.to_num(t text) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN t ~ '^\s*-?[0-9][0-9,]*(\.[0-9]+)?\s*$' THEN replace(t, ',', '')::numeric END
$$;

-- strip inline HTML and collapse whitespace
CREATE OR REPLACE FUNCTION analytics.plain(t text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(btrim(regexp_replace(regexp_replace(coalesce(t, ''), '<[^>]*>', '', 'g'), '\s+', ' ', 'g')), '')
$$;

-- 'Partner Type' -> 'partner-type' (the key ui.partner_category uses)
CREATE OR REPLACE FUNCTION analytics.slug(t text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(btrim(regexp_replace(lower(coalesce(t, '')), '[^a-z0-9]+', '-', 'g'), '-'), '')
$$;

-- ---------------------------------------------------------------- views
-- Dropped and recreated so a column change in a later version of this file does not fail.

DROP VIEW IF EXISTS
  analytics.swot, analytics.leader, analytics.patent, analytics.project, analytics.tech_area,
  analytics.innovation, analytics.site, analytics.signal, analytics.matchup_spec, analytics.matchup,
  analytics.news, analytics.partnership, analytics.tender_product_match, analytics.tender_competitor,
  analytics.tender, analytics.award, analytics.product_spec, analytics.product, analytics.category,
  analytics.company_alias, analytics.company
  CASCADE;

-- company ---------------------------------------------------------------------------
CREATE VIEW analytics.company AS
SELECT a.client_id::text                                     AS comp_id,
       coalesce(a.client_name, a.legal_name, a.brand_name)   AS name,
       coalesce(a.brand_name, a.client_name)                 AS short_name,
       true                                                  AS is_client,
       'client'::text                                        AS stance,
       NULL::text                                            AS threat_level,
       a.headquarters,
       a.country                                             AS home_country,
       a.industry_sector                                     AS sectors,
       NULL::int                                             AS founded_year,
       NULL::text                                            AS employees_text,
       NULL::text                                            AS revenue_text,
       NULL::text                                            AS revenue_tier,
       a.legal_name,
       analytics.plain(a.strategic_positioning)              AS positioning,
       NULL::text                                            AS parallax_read,
       NULL::text                                            AS ticker,
       0                                                     AS sort_order
FROM (SELECT * FROM serving.client_account ORDER BY client_id LIMIT 1) a
UNION ALL
SELECT c.competitor_id::text,
       c.display_name,
       c.short_name,
       false,
       coalesce(c.threat_level, 'watch'),
       c.threat_level,
       c.headquarters,
       c.origin_country,
       c.industry_sector,
       coalesce(c.starting_year::int, substring(c.starting_year_text from '(\d{4})')::int),
       coalesce(c.employee_count_text, c.employee_count::text),
       coalesce(c.revenue_text, CASE WHEN c.annual_revenue IS NOT NULL
                                     THEN c.annual_revenue::text || ' ' || coalesce(trim(c.revenue_currency), '') END),
       c.revenue_tier,
       c.legal_name,
       analytics.plain(c.strategic_positioning),
       analytics.plain(c.parallax_read),
       (SELECT q.ticker FROM serving.competitive_stock_quote q
         WHERE q.competitor_id = c.competitor_id AND q.ticker IS NOT NULL LIMIT 1),
       (row_number() OVER (ORDER BY lower(c.display_name)))::int
FROM serving.competitive_competitor c
WHERE c.qualifies IS TRUE;

COMMENT ON VIEW analytics.company IS 'The client (is_client, one row) and every competitor the platform shows (qualifying competitors only). comp_id is the id pages open by.';
COMMENT ON COLUMN analytics.company.stance IS 'client | threat | watch | fav (the competitor''s threat level)';
COMMENT ON COLUMN analytics.company.revenue_text IS 'Revenue as published, with currency and year where known; text, not summable.';
COMMENT ON COLUMN analytics.company.parallax_read IS 'The platform''s own assessment of the competitor.';

-- company_alias ---------------------------------------------------------------------
CREATE VIEW analytics.company_alias AS
SELECT DISTINCT ON (lower(alias)) alias, lower(alias) AS alias_lower, comp_id
FROM (
  SELECT comp_id, btrim(name) AS alias, 1 AS pri FROM analytics.company
  UNION ALL SELECT comp_id, btrim(short_name), 2 FROM analytics.company
  UNION ALL SELECT comp_id, btrim(legal_name), 3 FROM analytics.company
  -- without a bracketed suffix: "Aurora Defence (TEST)" -> "Aurora Defence"
  UNION ALL SELECT comp_id, btrim(regexp_replace(name, '\s*\([^)]*\)', '', 'g')), 4 FROM analytics.company
) a
WHERE coalesce(alias, '') <> ''
ORDER BY lower(alias), pri;

COMMENT ON VIEW analytics.company_alias IS 'Every spelling of a company name (display, short, legal) -> comp_id. Join on alias_lower = lower(text) to resolve a name.';

-- category --------------------------------------------------------------------------
CREATE VIEW analytics.category AS
SELECT c.category_id::text                              AS category_id,
       c.category_code,
       coalesce(c.category_name, c.canonical_name)      AS category,
       c.canonical_name,
       analytics.plain(c.category_description)          AS description,
       c.display_order                                  AS sort_order,
       c.innovation_count
FROM serving.technology_category c
WHERE c.is_active IS NOT FALSE;

COMMENT ON VIEW analytics.category IS 'The product / technology categories the platform groups everything by. Products, matchups, tenders and awards carry the category NAME as text (category / segment columns).';

-- product ---------------------------------------------------------------------------
CREATE VIEW analytics.product AS
SELECT p.client_product_id::text   AS product_id,
       p.client_id::text           AS comp_id,
       co.name                     AS company,
       true                        AS is_client,
       p.product_name              AS model,
       p.model_code,
       p.product_family            AS series,
       p.category,
       p.subcategory,
       p.product_kind,
       p.technology,
       p.status,
       p.rated_power_value,
       p.rated_power_unit,
       analytics.plain(p.description) AS description,
       p.market_availability,
       NULL::text                  AS country,
       (SELECT count(*) FROM serving.client_product_specification s WHERE s.client_product_id = p.client_product_id)::int AS spec_count
FROM serving.client_product p
JOIN analytics.company co ON co.comp_id = p.client_id::text
UNION ALL
SELECT p.product_id::text, p.competitor_id::text, co.name, false, p.product_name, NULL, NULL, p.category, p.subcategory,
       NULL, NULL, p.status, NULL, NULL, analytics.plain(p.description), NULL, p.country,
       (SELECT count(*) FROM serving.competitive_product_specification s WHERE s.product_id = p.product_id)::int
FROM serving.competitive_product p
JOIN analytics.company co ON co.comp_id = p.competitor_id::text;

COMMENT ON VIEW analytics.product IS 'Product catalogue, one row per model: the client''s products (is_client) and each shown competitor''s. Specs are rows in analytics.product_spec.';
COMMENT ON COLUMN analytics.product.subcategory IS 'Sub-type within the category: the like-for-like level for comparisons.';

-- product_spec ----------------------------------------------------------------------
CREATE VIEW analytics.product_spec AS
SELECT s.client_product_id::text AS product_id, p.comp_id, p.company, true AS is_client, p.model, p.category, p.subcategory,
       s.spec_group, s.spec_name AS spec, s.unit,
       coalesce(s.value_text, s.value_numeric::text)                AS value_text,
       coalesce(s.value_numeric, analytics.to_num(s.value_text))    AS value_numeric,
       NULL::text AS source_url
FROM serving.client_product_specification s
JOIN analytics.product p ON p.product_id = s.client_product_id::text AND p.is_client
UNION ALL
SELECT s.product_id::text, p.comp_id, p.company, false, p.model, p.category, p.subcategory,
       NULL, s.spec_label, s.unit, s.spec_value, analytics.to_num(s.spec_value), s.source_url
FROM serving.competitive_product_specification s
JOIN analytics.product p ON p.product_id = s.product_id::text AND NOT p.is_client;

COMMENT ON VIEW analytics.product_spec IS 'One row per product and specification (label, unit, value as text and as a number when it is one). Spec labels differ between makers: match them with ILIKE.';

-- award -----------------------------------------------------------------------------
CREATE VIEW analytics.award AS
SELECT a.award_id::text AS award_id, a.award_year AS year, a.award_date, a.country_name AS country, a.segment, a.buyer,
       a.title, a.programme, a.site, a.tender_number, a.winner, a.brand,
       a.value_amount AS value_local, upper(btrim(a.value_currency)) AS currency, a.value_text,
       CASE WHEN upper(btrim(a.value_currency)) = 'INR' THEN a.value_amount ELSE a.value_amount * fx.inr_per_unit END AS value_inr,
       a.bids, a.source_url AS url, a.source_tier
FROM serving.market_award a
LEFT JOIN serving.fx_rate fx ON btrim(fx.currency_code) = upper(btrim(a.value_currency));

COMMENT ON VIEW analytics.award IS 'Historical contract awards (programme, buyer, winner, value). value_local is in the award''s own currency; value_inr only where an official rate is stored.';
COMMENT ON COLUMN analytics.award.value_inr IS 'value_local converted at the stored official rate (fx_rate); NULL when no rate is stored: then report the amount in its own currency, never guess a rate.';

-- tender ----------------------------------------------------------------------------
CREATE VIEW analytics.tender AS
SELECT t.tender_id::text                                  AS tender_id,
       t.title,
       t.title_localized,
       coalesce(t.issuer_display, t.buyer_name)           AS buyer,
       t.country_name                                     AS country,
       btrim(t.country_code)                              AS country_code,
       t.category_text                                    AS segment,
       t.status,
       t.lean_code                                        AS recommendation,
       analytics.plain(t.lean_text)                       AS recommendation_text,
       coalesce(t.kssl_fit, f.kssl_fit)                   AS client_fit,
       analytics.plain(f.kssl_fit_rationale)              AS client_fit_rationale,
       f.fit_grade                                        AS fit_label,
       f.fit_score,
       f.pursue_label,
       f.revenue_tier                                     AS opportunity_tier,
       f.attractiveness, f.ability, f.value_score, f.strategic_score, f.time_to_award,
       coalesce(t.kssl_model, f.kssl_model)               AS client_offer,
       t.rank_position                                    AS priority_rank,
       t.published_date,
       coalesce(t.closing_date, w.closing_date)           AS closing_date,
       coalesce(t.days_remaining, w.days_remaining)       AS days_remaining,
       t.value_amount,
       upper(btrim(t.value_currency))                     AS value_currency,
       t.value_text                                       AS notice_value_text,
       CASE WHEN upper(btrim(t.value_currency)) = 'INR' THEN t.value_amount ELSE t.value_amount * fx.inr_per_unit END AS value_inr,
       f.revenue_estimate_min, f.revenue_estimate_max,
       upper(btrim(f.revenue_currency))                   AS revenue_currency,
       coalesce(f.revenue_estimate_text, t.expected_revenue_text) AS revenue_estimate_text,
       (t.status IN ('open', 'closing')
        AND (coalesce(t.closing_date, w.closing_date) IS NULL OR coalesce(t.closing_date, w.closing_date) >= current_date)) AS counts_in_pipeline,
       nullif(btrim(concat_ws(' ', t.quantity::text, t.quantity_unit)), '') AS quantity_text,
       s.portal_name                                      AS portal,
       coalesce(t.tender_number, t.notice_reference)      AS tender_number,
       t.awarded_to, t.award_date, t.award_value_text,
       analytics.plain(t.description)                     AS description,
       t.source_url                                       AS url
FROM serving.market_tender t
LEFT JOIN LATERAL (SELECT * FROM serving.market_tender_fit_assessment a WHERE a.tender_id = t.tender_id
                   ORDER BY a.assessed_at DESC NULLS LAST LIMIT 1) f ON true
LEFT JOIN LATERAL (SELECT * FROM serving.market_tender_closing_window c WHERE c.tender_id = t.tender_id
                   ORDER BY c.as_of_date DESC NULLS LAST LIMIT 1) w ON true
LEFT JOIN LATERAL (SELECT portal_name FROM serving.market_tender_source x WHERE x.tender_id = t.tender_id
                   ORDER BY x.is_primary DESC NULLS LAST LIMIT 1) s ON true
LEFT JOIN serving.fx_rate fx ON btrim(fx.currency_code) = upper(btrim(t.value_currency));

COMMENT ON VIEW analytics.tender IS 'Tenders tracked for the client, with the latest fit assessment and closing window. The Tenders page opens one by title.';
COMMENT ON COLUMN analytics.tender.status IS 'open | closing | awarded | closed. Open bids: status IN (''open'',''closing''); counts_in_pipeline also requires a closing date not in the past.';
COMMENT ON COLUMN analytics.tender.recommendation IS 'The platform''s bid lean: go | maybe | watch | pass | won | closed.';
COMMENT ON COLUMN analytics.tender.client_fit IS 'How well the client''s products fit: strong | partial | weak.';
COMMENT ON COLUMN analytics.tender.pursue_label IS 'pursue | position | monitor | pass.';
COMMENT ON COLUMN analytics.tender.value_amount IS 'Value stated by the notice, in value_currency (full units). Most notices state none.';
COMMENT ON COLUMN analytics.tender.value_inr IS 'value_amount at the stored official rate; NULL when no rate is stored (report the original currency then, never guess a rate).';
COMMENT ON COLUMN analytics.tender.revenue_estimate_min IS 'Analyst revenue estimate for the client (low end), in revenue_currency. An estimate: say so.';

-- tender_competitor -----------------------------------------------------------------
CREATE VIEW analytics.tender_competitor AS
SELECT f.tender_id::text                                      AS tender_id,
       coalesce(co.name, f.competitor_name)                   AS company,
       coalesce(p.competitor_id::text, al.comp_id)            AS comp_id,
       f.basis,
       f.fit_label,
       f.rank_position,
       coalesce(f.competitor_product_display, f.competitor_products_text) AS products,
       analytics.plain(f.fit_rationale)                       AS rationale
FROM serving.market_tender_competitor_fit f
LEFT JOIN serving.competitive_product p ON p.product_id = f.competitor_product_id
LEFT JOIN analytics.company_alias al ON al.alias_lower = lower(btrim(f.competitor_name))
LEFT JOIN analytics.company co ON co.comp_id = coalesce(p.competitor_id::text, al.comp_id)
WHERE NOT EXISTS (SELECT 1 FROM serving.competitive_competitor h
                  WHERE h.qualifies IS NOT TRUE
                    AND (h.competitor_id = p.competitor_id OR lower(h.display_name) = lower(btrim(f.competitor_name))));

COMMENT ON VIEW analytics.tender_competitor IS 'Competitors assessed as able to bid for each tender, with their candidate products and why.';
COMMENT ON COLUMN analytics.tender_competitor.basis IS 'selected (won / was selected) | shortlisted | offered | presence (could bid from local presence).';

-- tender_product_match --------------------------------------------------------------
CREATE VIEW analytics.tender_product_match AS
SELECT m.tender_id::text AS tender_id, m.match_label AS client_offer, m.fit_grade AS fit_level, m.fit_percent, m.display_order
FROM serving.market_tender_product_match m;

COMMENT ON VIEW analytics.tender_product_match IS 'The client''s products matched to each tender, with fit grade and percent.';

-- partnership -----------------------------------------------------------------------
CREATE VIEW analytics.partnership AS
SELECT p.competitor_id::text            AS comp_id,
       co.name                          AS company,
       false                            AS is_client,
       p.partner_name,
       analytics.slug(p.partner_type)   AS relationship_code,
       p.partner_type                   AS relationship,
       p.region                         AS country,
       p.as_of_date                     AS relationship_date,
       extract(year FROM p.as_of_date)::int AS year,
       p.status,
       p.relationship_confidence,
       analytics.plain(p.relationship_scope) AS scope,
       analytics.plain(p.description)   AS note,
       analytics.plain(coalesce(p.kssl_read, p.client_impact)) AS implication,
       analytics.plain(p.client_verdict) AS client_verdict,
       p.overlap_kind,
       p.value_to_competitor,
       p.value_to_partner
FROM serving.competitive_partnership p
JOIN analytics.company co ON co.comp_id = p.competitor_id::text
UNION ALL
SELECT cp.client_id::text, co.name, true, cp.partner_name, analytics.slug(cp.partner_type), cp.partner_type,
       coalesce(cp.country, cp.region), cp.relationship_start_date, extract(year FROM cp.relationship_start_date)::int,
       coalesce(r.status, cp.relationship_status), cp.relationship_confidence, analytics.plain(cp.relationship_scope),
       analytics.plain(r.description), analytics.plain(r.kssl_read), NULL, NULL, NULL, NULL
FROM serving.client_partner cp
JOIN analytics.company co ON co.comp_id = cp.client_id::text
LEFT JOIN LATERAL (SELECT * FROM serving.client_partner_relationship r WHERE r.client_partner_id = cp.client_partner_id
                   ORDER BY r.start_date NULLS LAST LIMIT 1) r ON true;

COMMENT ON VIEW analytics.partnership IS 'Partners of each competitor (alliance network) and of the client (is_client): dealers, JVs, licences, suppliers, technology partners.';
COMMENT ON COLUMN analytics.partnership.implication IS 'What the tie means for the client, as the platform reads it.';

-- news ------------------------------------------------------------------------------
CREATE VIEW analytics.news AS
SELECT a.article_id::text AS news_id, a.competitor_id::text AS comp_id, co.name AS company, false AS is_client,
       'article'::text AS kind, a.headline, analytics.plain(a.description) AS summary, a.category,
       NULL::text AS impact_level, NULL::text AS country, a.published_date AS news_date, a.publisher AS source,
       a.article_url AS url, NULL::text AS analysis
FROM serving.competitive_news_article a
JOIN analytics.company co ON co.comp_id = a.competitor_id::text
-- defence news only, the site's rule (owner 2026-10-26; backend/areas/a_competitive.build_news + src/lib/news.js hiddenNews):
-- not a story judged not about the company, not Non-defence business, and Other only with a defence headline or a product of
-- the company in it (the word list mirrors backend/news.py DEFENCE_TERMS)
WHERE NOT EXISTS (SELECT 1 FROM serving.fact_source f WHERE f.table_name = 'competitive_news_article'
                    AND f.column_name = 'not_about_company' AND f.row_id = a.article_id::text)
  AND coalesce(a.category, '') <> 'Non-defence business'
  AND (coalesce(a.category, '') <> 'Other'
       OR a.headline ~* '\m(army|navy|naval|air force|defen[cs]e|military|missiles?|drones?|uav|uas|ucav|tanks?|rifles?|guns?|howitzers?|artillery|radars?|armou?red|armou?r|combat|weapons?|drdo|torpedo|submarines?|frigates?|warships?|aircraft|helicopters?|ammunition|munitions?|rockets?|launchers?|interceptors?|troops|soldiers|aerospace|warhead|infantry|marines|coast guard|pentagon|dod|nato|procurement|sidm|eurosatory|dsei|ausa|defexpo|aero india|idex|farnborough|paris air show|adex|cansec|ndia|loitering|counter-drone|shipyard|corvettes?|destroyers?|fighters?|jets?|satellites?|space force|security forces)\M'
       OR EXISTS (SELECT 1 FROM serving.competitive_product p WHERE p.competitor_id = a.competitor_id
                    AND length(split_part(p.product_name, ' (', 1)) >= 4
                    AND position(lower(split_part(p.product_name, ' (', 1)) IN lower(a.headline)) > 0))
UNION ALL
SELECT m.moment_id::text, m.competitor_id::text, co.name, false, 'moment', m.title,
       analytics.plain(coalesce(m.what_happened, m.description, m.card_summary)), m.category,
       m.grade, m.country_name, m.movement_date, coalesce(m.source_label, m.source_domain), m.source_url,
       analytics.plain(m.kssl_analysis)
FROM serving.competitive_competitor_moment m
JOIN analytics.company co ON co.comp_id = m.competitor_id::text;

COMMENT ON VIEW analytics.news IS 'Competitor news: kind ''article'' (profile news) and kind ''moment'' (the Competitor Moment page: a dated move with impact_level and the analysis of what it means for the client). The client has no news rows.';
COMMENT ON COLUMN analytics.news.impact_level IS 'Moments only: high | watch | opportunity.';

-- matchup / matchup_spec --------------------------------------------------------------
CREATE VIEW analytics.matchup AS
SELECT m.matchup_id::text                           AS matchup_id,
       m.category_code                              AS category,
       m.decision_level,
       CASE m.decision_level WHEN 1 THEN 'client behind' WHEN 2 THEN 'near parity' WHEN 3 THEN 'client ahead' END AS stance,
       m.edge_score,
       m.competitor_id::text                        AS rival_comp_id,
       coalesce(co.name, m.competitor_name)         AS rival_company,
       m.competitor_product_name                    AS rival_product,
       m.competitor_product_id::text                AS rival_product_id,
       m.client_product_name                        AS client_product,
       m.client_product_id::text                    AS client_product_id,
       m.verdict_headline,
       analytics.plain(m.verdict)                   AS verdict,
       m.match_basis,
       m.comparable_spec_count,
       m.competitor_country,
       (SELECT string_agg(analytics.plain(x.advantage_text), ' | ' ORDER BY x.display_order)
          FROM serving.competitive_matchup_advantage x WHERE x.matchup_id = m.matchup_id AND x.side = 'competitor') AS rival_advantages,
       (SELECT string_agg(analytics.plain(x.advantage_text), ' | ' ORDER BY x.display_order)
          FROM serving.competitive_matchup_advantage x WHERE x.matchup_id = m.matchup_id AND x.side = 'client')     AS client_advantages
FROM serving.competitive_matchup m
JOIN analytics.company co ON co.comp_id = m.competitor_id::text
WHERE coalesce(m.comparable_spec_count, 0) > 0 OR m.verdict IS NOT NULL;

COMMENT ON VIEW analytics.matchup IS 'Head-to-head product matchups: a rival model against the client''s closest model, with the platform''s verdict. The Product Evaluation page opens one by matchup_id.';
COMMENT ON COLUMN analytics.matchup.edge_score IS '0-100 from the client''s side; 50 is parity, above 50 the client leads.';

CREATE VIEW analytics.matchup_spec AS
SELECT s.matchup_id::text AS matchup_id, m.rival_comp_id, m.rival_company, m.category, s.spec_group, s.spec_label AS spec, s.unit,
       s.competitor_value_text AS rival_value_text, s.client_value_text,
       s.competitor_value_numeric AS rival_value, s.client_value_numeric AS client_value,
       s.better_side AS leader, s.comparability_state, s.gap_value AS gap_pct
FROM serving.competitive_matchup_specification s
JOIN analytics.matchup m ON m.matchup_id = s.matchup_id::text;

COMMENT ON VIEW analytics.matchup_spec IS 'Specification rows of each matchup: rival vs client value, who is better.';
COMMENT ON COLUMN analytics.matchup_spec.leader IS 'client | competitor | equal';
COMMENT ON COLUMN analytics.matchup_spec.comparability_state IS 'comparable | one_sided | not_comparable';

-- signal ----------------------------------------------------------------------------
CREATE VIEW analytics.signal AS
SELECT s.signal_id::text                         AS signal_id,
       'competitive'::text                       AS lane,
       s.classification                          AS direction,
       s.impact,
       s.probability,
       (s.impact * s.probability)                AS risk_score,
       s.sequence_no                             AS rank,
       coalesce(co.name, cc.display_name)        AS company,
       s.company_id::text                        AS comp_id,
       NULL::text                                AS lens,
       s.title,
       analytics.plain(s.summary)                AS summary,
       analytics.plain(d.why_it_matters)         AS so_what,
       analytics.plain(d.what_article_says)      AS what_it_says,
       coalesce(s.published_date, s.event_date)  AS signal_date,
       s.category,
       d.glance_where                            AS country,
       NULL::text                                AS stage,
       NULL::text                                AS client_fit,
       d.source_name                             AS source,
       d.source_url                              AS url
FROM serving.competitive_signal s
LEFT JOIN serving.competitive_signal_detail d ON d.signal_id = s.signal_id
LEFT JOIN serving.competitive_competitor cc ON cc.competitor_id = s.company_id
LEFT JOIN analytics.company co ON co.comp_id = s.company_id::text
WHERE s.classification IS DISTINCT FROM 'none'
  AND NOT (cc.competitor_id IS NOT NULL AND cc.qualifies IS NOT TRUE)
UNION ALL
SELECT 'tech-' || a.article_id, 'technology', a.direction, a.relevance, NULL, NULL, a.sequence_no, tc.display_name, NULL,
       a.lens, a.title, analytics.plain(coalesce(a.summary, a.card_summary)), analytics.plain(a.client_narrative),
       analytics.plain(a.article_says), coalesce(a.published_on, a.article_date), a.category_text, btrim(a.country_code),
       a.horizon, a.client_position,
       src.publisher, coalesce(src.source_url, src.url)
FROM serving.technology_overview_article a
LEFT JOIN serving.technology_company tc ON tc.company_id = a.primary_company_id
LEFT JOIN LATERAL (SELECT ts.publisher, ts.source_url, ts.url FROM serving.technology_overview_source os
                   JOIN serving.technology_source ts ON ts.source_id = os.source_id
                   WHERE os.article_id = a.article_id ORDER BY os.is_primary DESC NULLS LAST, os.display_order LIMIT 1) src ON true
UNION ALL
SELECT 'req-' || r.requirement_id, 'market', NULL, NULL, NULL, NULL, NULL, r.buyer_name, NULL, NULL, r.title,
       analytics.plain(r.description), analytics.plain(r.strategic_assessment), NULL, coalesce(r.stage_date, r.last_confirmed),
       r.category, r.country_name, r.stage, r.kssl_fit, NULL, NULL
FROM serving.market_global_requirement r
UNION ALL
SELECT 'upd-' || u.update_id, 'market', NULL, NULL, NULL, NULL, NULL, o.buyer_name, NULL, NULL,
       coalesce(u.headline, o.title), analytics.plain(u.narrative), analytics.plain(o.description), NULL, u.update_date,
       NULL, btrim(o.country_code), o.stage, NULL, NULL, NULL
FROM serving.market_opportunity_update u
LEFT JOIN serving.market_opportunity o ON o.opportunity_id = u.opportunity_id;

COMMENT ON VIEW analytics.signal IS 'The intelligence feed in three lanes: competitive (rival moves), technology (technology developments) and market (global requirements req-* and opportunity updates upd-*). Navigable: each pillar overview opens a card by signal_id.';
COMMENT ON COLUMN analytics.signal.direction IS 'competitive / technology lanes: threat | watch | fav (favourable).';
COMMENT ON COLUMN analytics.signal.risk_score IS 'competitive lane: probability x impact (higher = more serious).';
COMMENT ON COLUMN analytics.signal.so_what IS 'Why it matters to the client (competitive), the client narrative (technology) or the strategic assessment (market).';

-- site ------------------------------------------------------------------------------
CREATE VIEW analytics.site AS
SELECT l.competitor_id::text AS comp_id, co.name AS company, false AS is_client, l.country, l.location_type AS facility_type,
       NULL::text AS activity, l.location_name AS site_name, NULL::text AS presence_status, NULL::text AS overlap_status,
       NULL::text AS products_summary, NULL::text AS region, NULL::numeric AS latitude, NULL::numeric AS longitude,
       NULL::text AS note, l.source_url AS url, 'location'::text AS kind
FROM serving.competitive_competitor_location l
JOIN analytics.company co ON co.comp_id = l.competitor_id::text
UNION ALL
SELECT coalesce(p.competitor_id::text, p.client_id::text), coalesce(co.name, p.company_name), p.company_role = 'client',
       g.country_name, NULL, p.activity_type, coalesce(g.map_label, g.country_name), p.presence_status, p.overlap_status,
       analytics.plain(p.products_summary), g.region_name, g.latitude, g.longitude, analytics.plain(p.relationship_text),
       NULL, 'presence'
FROM serving.competitive_geo_company_presence p
JOIN serving.competitive_geo_location g ON g.location_id = p.location_id
LEFT JOIN analytics.company co ON co.comp_id = coalesce(p.competitor_id::text, p.client_id::text)
WHERE NOT EXISTS (SELECT 1 FROM serving.competitive_competitor h WHERE h.competitor_id = p.competitor_id AND h.qualifies IS NOT TRUE);

COMMENT ON VIEW analytics.site IS 'Footprint: kind ''location'' = a company''s offices and plants; kind ''presence'' = a company''s presence in a country on the Geo Footprint map (client included), with activity and products supplied.';
COMMENT ON COLUMN analytics.site.activity IS 'Local production | Licensed production | Export | Sales and service | Sourcing';

-- innovation / tech_area ---------------------------------------------------------------
CREATE VIEW analytics.innovation AS
SELECT i.innovation_id::text AS innovation_id,
       i.category_id::text   AS area_id,
       c.category            AS area,
       i.title,
       i.technology_kind,
       coalesce(i.maturity, i.maturity_level::text) AS maturity,
       i.maturity_level,
       i.client_position,
       i.stance,
       (SELECT string_agg(ic.display_name, ', ' ORDER BY ic.display_order) FROM serving.technology_innovation_company ic
         WHERE ic.innovation_id = i.innovation_id AND ic.relationship_type = 'driver') AS company,
       i.horizon_year AS year,
       analytics.plain(i.summary)             AS summary,
       analytics.plain(i.why_matters_to_kssl) AS impact,
       analytics.plain(i.whats_new)           AS whats_new,
       analytics.plain(i.competitive_note)    AS competitive_note,
       analytics.plain(i.action_note)         AS action_note,
       i.status
FROM serving.technology_innovation i
LEFT JOIN analytics.category c ON c.category_id = i.category_id::text
WHERE i.status IS DISTINCT FROM 'candidate';

COMMENT ON VIEW analytics.innovation IS 'Technology developments by area (category). The Innovations page opens an area by area_id with an item title.';
COMMENT ON COLUMN analytics.innovation.client_position IS 'The client''s position: behind | parity | ahead.';
COMMENT ON COLUMN analytics.innovation.maturity IS 'lab | dev | prod | fielded (or a 1-5 level).';

CREATE VIEW analytics.tech_area AS
SELECT c.category_id AS area_id, c.category AS area, c.description AS why_it_matters,
       count(i.innovation_id)::int                                           AS innovations,
       count(i.innovation_id) FILTER (WHERE i.client_position = 'behind')::int AS gaps,
       string_agg(DISTINCT i.company, ', ')                                  AS leaders
FROM analytics.category c
LEFT JOIN analytics.innovation i ON i.area_id = c.category_id
GROUP BY c.category_id, c.category, c.description, c.sort_order
ORDER BY c.sort_order;

COMMENT ON VIEW analytics.tech_area IS 'Per technology area: number of developments, how many the client is behind on, the companies driving them.';

-- project ---------------------------------------------------------------------------
CREATE VIEW analytics.project AS
SELECT p.project_id::text AS project_id, p.competitor_id::text AS comp_id, coalesce(co.name, p.company_display) AS company,
       p.project_title AS project, p.kind, p.region AS market, p.location, p.customer, p.stage,
       analytics.plain(p.stage_note) AS stage_note, analytics.plain(p.latest_milestone) AS latest_milestone,
       p.latest_milestone_date, p.estimated_value, p.grade, p.assessment_stance,
       analytics.plain(coalesce(p.strategic_assessment, p.assessment_read)) AS assessment,
       analytics.plain(coalesce(p.what_the_project_is, p.card_summary))     AS summary,
       p.kssl_platform AS client_platform, analytics.plain(p.kssl_advantage) AS client_advantage, p.researched_as_of
FROM serving.competitive_project p
LEFT JOIN analytics.company co ON co.comp_id = p.competitor_id::text
WHERE NOT EXISTS (SELECT 1 FROM serving.competitive_competitor h WHERE h.competitor_id = p.competitor_id AND h.qualifies IS NOT TRUE);

COMMENT ON VIEW analytics.project IS 'Competitor projects (Projects page): what each rival is building, supplying or pursuing, with stage, latest milestone and the assessment for the client.';
COMMENT ON COLUMN analytics.project.market IS 'Domestic | Export';
COMMENT ON COLUMN analytics.project.estimated_value IS 'Estimated value as stored, currency not recorded: quote it as given and say the currency is not stated.';

-- patent ----------------------------------------------------------------------------
CREATE VIEW analytics.patent AS
SELECT coalesce(f.publication_number, f.filing_id::text) AS patent_no,
       f.title,
       pf.competitor_id::text AS comp_id,
       co.name                AS company,
       coalesce(f.area_label, f.category_label, f.classification_text) AS technology_area,
       f.status,
       f.filed_date,
       extract(year FROM f.filed_date)::int AS filed_year,
       f.jurisdiction         AS filing_office,
       f.classification_code  AS ipc_class,
       f.threat_level,
       analytics.plain(f.client_relevance) AS client_relevance,
       f.patent_url           AS url
FROM serving.competitive_patent_filing f
JOIN serving.competitive_patent_portfolio pf ON pf.portfolio_id = f.portfolio_id
JOIN analytics.company co ON co.comp_id = pf.competitor_id::text;

COMMENT ON VIEW analytics.patent IS 'Patent filings of the shown competitors, by technology area (Patent page). Tracked filings, not a full IP census.';
COMMENT ON COLUMN analytics.patent.status IS 'granted | pending | filed';

-- leader ----------------------------------------------------------------------------
CREATE VIEW analytics.leader AS
SELECT l.leader_id::text AS leader_id, l.competitor_id::text AS comp_id, co.name AS company, l.full_name, l.role_title,
       l.organization, l.role_source_url AS url
FROM serving.competitive_leader l
JOIN analytics.company co ON co.comp_id = l.competitor_id::text;

COMMENT ON VIEW analytics.leader IS 'Leadership of each shown competitor (Competitor Profile, Leadership).';

-- swot ------------------------------------------------------------------------------
CREATE VIEW analytics.swot AS
SELECT s.competitor_id::text AS comp_id, co.name AS company, s.swot_type, analytics.plain(s.statement) AS statement
FROM serving.competitive_competitor_swot s
JOIN analytics.company co ON co.comp_id = s.competitor_id::text
WHERE analytics.plain(s.statement) IS NOT NULL;

COMMENT ON VIEW analytics.swot IS 'Strengths, weaknesses, opportunities and threats per competitor.';
COMMENT ON COLUMN analytics.swot.swot_type IS 'strength | weakness | opportunity | threat';

-- ---------------------------------------------------------------- the agent's role

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parallax_agent') THEN
    CREATE ROLE parallax_agent LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20;
  END IF;
END $$;

ALTER ROLE parallax_agent SET default_transaction_read_only = on;
ALTER ROLE parallax_agent SET statement_timeout = '5s';
ALTER ROLE parallax_agent SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE parallax_agent SET search_path = analytics;

REVOKE ALL ON SCHEMA public FROM parallax_agent;
GRANT USAGE ON SCHEMA analytics TO parallax_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO parallax_agent;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA analytics TO parallax_agent;
