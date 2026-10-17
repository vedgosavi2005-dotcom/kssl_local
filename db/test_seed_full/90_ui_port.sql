-- 90_ui_port.sql  Rows for the tables and columns of db/setup/09_ui_port_tables.sql (docs/ui_port/MAPPING.md section C). FICTIONAL, obviously test data.
-- Runs after 00-80, so it can point at their ids: competitors c0ffee00-...-00000000000N, partnerships d2000000-...-0000000000NN,
-- patent filings e3000000-..., news articles a5000000-..., tender categories (market_tender.category_text), metric tiles f1000000-...
-- New tables: staging_ui.section_visibility, partner_category, partner_overlap_kind, partner_overlap_effect;
--             staging.competitive_synthesis, competitive_synthesis_vulnerability, competitive_synthesis_vulnerability_trace,
--             competitive_field_synthesis, market_award, market_segment_assessment, patent_field_assessment.
-- New columns (UPDATEs of rows the earlier files inserted): competitive_partnership.client_verdict / client_impact, competitive_news_article.description,
--             competitive_patent_filing.threat_level / client_relevance / area_label, staging_ui.competitive_metric.metric_key.
-- Includes an Arabic-script string (market_award.title_local / buyer) and "L&T (TEST)" (market_award.winner, a vulnerability) for the display checks.
BEGIN;

DELETE FROM staging.fact_source WHERE table_name IN ('competitive_synthesis', 'competitive_synthesis_vulnerability',
    'competitive_synthesis_vulnerability_trace', 'competitive_field_synthesis', 'market_award', 'market_segment_assessment', 'patent_field_assessment')
    OR (table_name = 'competitive_partnership' AND column_name IN ('client_verdict', 'client_impact'));
DELETE FROM staging.patent_field_assessment;
DELETE FROM staging.market_segment_assessment;
DELETE FROM staging.market_award;
DELETE FROM staging.competitive_field_synthesis;
DELETE FROM staging.competitive_synthesis_vulnerability_trace;
DELETE FROM staging.competitive_synthesis_vulnerability;
DELETE FROM staging.competitive_synthesis;
DELETE FROM staging_ui.partner_overlap_effect;
DELETE FROM staging_ui.partner_overlap_kind;
DELETE FROM staging_ui.partner_category;
DELETE FROM staging_ui.section_visibility;
DELETE FROM staging_ui.filter_option;

-- Which sections of the app show. The eight KSSL keys are hidden; one other key is visible so the gate is exercised both ways.
INSERT INTO staging_ui.section_visibility (section_key, visible, note) VALUES
  ('gap-analysis',          false, 'Hidden for the Aurora Defence (TEST) client'),
  ('finances',              false, 'Hidden for the Aurora Defence (TEST) client'),
  ('stock',                 false, 'Hidden for the Aurora Defence (TEST) client'),
  ('parallax-read',         false, 'Hidden for the Aurora Defence (TEST) client'),
  ('swot',                  false, 'Hidden for the Aurora Defence (TEST) client'),
  ('strategic-positioning', false, 'Hidden for the Aurora Defence (TEST) client'),
  ('product-images',        false, 'Hidden for the Aurora Defence (TEST) client'),
  ('chat',                  false, 'Hidden for the Aurora Defence (TEST) client'),
  ('competitor-moment',     true,  'Shown: a section that is not in the hidden list (TEST DATA)');

-- Filter pills and badge words of the overview feeds, and the stance words (a stance is threat or watch only). Fictional wording.
INSERT INTO staging_ui.filter_option (filter_group, option_code, option_label, badge_label, display_order) VALUES
  ('stance',           'threat',              'Threat',                 'Threat',      1),
  ('stance',           'watch',               'Watch',                  'Watch',       2),
  ('market-feed',      'tenders',             'Latest Tenders',         'TENDER',      1),
  ('market-feed',      'opportunities',       'Perceived Opportunities','OPPORTUNITY', 2),
  ('technology-feed',  'competitor-advances', 'Competitor Advancements', NULL,         1),
  ('technology-feed',  'adoptable',           'Adoptable Advances',     'Adoptable',   2);

-- Relationship legend, one row per partner_type slug of competitive_partnership (Technology partner, MoU / strategic, Supplier, Joint venture).
INSERT INTO staging_ui.partner_category
  (category_key, group_key, group_label, category_label, short_label, definition, overlap_kind, display_order) VALUES
  ('supplier',           'supply-chain', 'Supply chain',        'Supplier',           'Supplier',  '{rival} buys parts, materials or services from this company; a shared supplier can tighten {client}''s own supply (TEST DATA).', 'supplier',   1),
  ('technology-partner', 'supply-chain', 'Supply chain',        'Technology partner', 'Tech',      '{rival} integrates this company''s technology into its products (TEST DATA).',                                                    'technology', 2),
  ('joint-venture',      'alliances',    'Alliances and ventures', 'Joint venture',    'JV',        '{rival} shares ownership of a local entity with this company to win and serve a market (TEST DATA).',                              'channel',    3),
  ('mou-strategic',      'alliances',    'Alliances and ventures', 'MoU / strategic',  'MoU',       '{rival} has signed a non-binding agreement to cooperate; it may become a bid team against {client} (TEST DATA).',                 'service',    4);

-- Heading and lead line of "what an overlapping <kind> partner costs the client".
INSERT INTO staging_ui.partner_overlap_kind (overlap_kind, kind_label, lead, display_order) VALUES
  ('channel',    'Overlapping channel partner',    'The same route to market serves {rival} and {client} (TEST DATA).',      1),
  ('supplier',   'Overlapping supplier',           'The same supplier feeds {rival} and {client} (TEST DATA).',              2),
  ('service',    'Overlapping service partner',    'The same support provider serves {rival} and {client} (TEST DATA).',     3),
  ('technology', 'Overlapping technology partner', 'The same technology house works with {rival} and {client} (TEST DATA).', 4);

INSERT INTO staging_ui.partner_overlap_effect (effect_id, overlap_kind, display_order, effect_title, effect_text) VALUES
  (1, 'channel',    1, 'Access to buyers',   'The shared channel may favour the larger order book when {client} and {rival} bid for the same buyer (TEST DATA).'),
  (2, 'channel',    2, 'Pricing pressure',   'Common channel margins make a price difference between the two offers easy to compare (TEST DATA).'),
  (3, 'supplier',   1, 'Capacity',           'When the supplier is short of capacity the larger customer is served first (TEST DATA).'),
  (4, 'supplier',   2, 'Cost visibility',    'A shared supplier can reveal cost levels of both sides to each other (TEST DATA).'),
  (5, 'service',    1, 'Support slots',      'One field-service team has to split time between the two fleets (TEST DATA).'),
  (6, 'technology', 1, 'Technology parity',  'Both sides can offer the same sub-system, so the difference moves to price and delivery (TEST DATA).'),
  (7, 'technology', 2, 'Roadmap exposure',   'Joint development roadmaps may leak {client} priorities to {rival} (TEST DATA).');

-- Written read of each competitor: thesis plus "what their web reveals" (pattern / so-what). Tessera (competitor 5) has no row on purpose.
INSERT INTO staging.competitive_synthesis
  (competitor_id, thesis, strategy_thesis, strategy_pattern, strategy_sowhat, source_url, source_tier) VALUES
  ('c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST) is a premium gun-and-munitions house that grows through allies rather than plants (TEST DATA).',
   'Its partner web concentrates on optics, barrel steel and one Indian MoU.', 'Three of three ties are supply or technology links, none is a sales channel.',
   'Expect it to lean on partners for India access, which touches Aurora export bids (TEST DATA).', 'https://borealis-arms.example.com/strategy', 'judgement'),
  ('c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST) competes on breadth: vehicles, loitering munitions and local assembly (TEST DATA).',
   'It buys local presence through joint ventures in the Gulf.', 'One joint venture and one MoU in the last 12 months, both in markets Aurora targets.',
   'Gulf APC tenders will see Cobalt with a local partner, unlike Aurora today (TEST DATA).', 'https://cobalt-dynamics.example.com/strategy', 'judgement'),
  ('c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST) wins on delivery speed and price in 155 mm systems (TEST DATA).',
   'Local final assembly in Romania shortens delivery for EU buyers.', 'Joint venture plus propellant supplier plus domestic fire control: an integrated chain.',
   'Aurora cannot match the delivery time without a comparable local chain (TEST DATA).', 'https://halcyon-land.example.com/strategy', 'judgement'),
  ('c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST) is a regional ammunition supplier with limited reach into India (TEST DATA).',
   'It focuses on Gulf supply agreements.', 'Two Gulf ties, no Indian tie.',
   'Low direct pressure on Aurora; watch for a Gulf price war (TEST DATA).', 'https://meridian-ordnance.example.com/strategy', 'judgement');

INSERT INTO staging.competitive_synthesis_vulnerability
  (vulnerability_id, competitor_id, display_order, title, intel, from_labels, source_url, source_tier) VALUES
  ('f9100000-0000-4000-8000-000000000001', 'c0ffee00-0000-4000-8000-000000000001', 1, 'Single source for barrel steel',
   'All barrel-grade steel comes from one Norwegian mill, so a mill outage stops production (TEST DATA).', E'Fjord Steelworks (TEST)\nSupplier', 'https://borealis-arms.example.com/supply', 'judgement'),
  ('f9100000-0000-4000-8000-000000000002', 'c0ffee00-0000-4000-8000-000000000001', 2, 'India access depends on a rival',
   'Its Indian route runs through an MoU with Tessera Aerospace (TEST), which also bids against it (TEST DATA).', E'Tessera Aerospace (TEST)\nMoU', 'https://news.example.com/borealis-tessera-mou', 'judgement'),
  ('f9100000-0000-4000-8000-000000000003', 'c0ffee00-0000-4000-8000-000000000002', 1, 'Gulf assembly rests on a young joint venture',
   'The Riyadh-Test joint venture was announced in October 2026 and has not delivered a vehicle yet; a delay would slip Gulf deliveries. L&T (TEST) is named as the possible alternative assembler (TEST DATA).', E'Gulf Vehicle Assembly (TEST)\nJoint venture\nL&T (TEST)', 'https://news.example.com/cobalt-gulf-assembly', 'judgement'),
  ('f9100000-0000-4000-8000-000000000004', 'c0ffee00-0000-4000-8000-000000000002', 2, 'Armour supply is single source',
   'Hull armour plate comes from one US alloy house (TEST DATA).', E'Redstone Armor Alloys (TEST)', 'https://cobalt-dynamics.example.com/supply', 'judgement'),
  ('f9100000-0000-4000-8000-000000000005', 'c0ffee00-0000-4000-8000-000000000003', 1, 'Propellant charges imported from India',
   'Modular charges for K-Shell are bought from an Indian producer, which exposes Halcyon to an Indian export licence (TEST DATA).', E'Helios Propellants (TEST)\nSupplier', 'https://halcyon-land.example.com/supply', 'judgement'),
  ('f9100000-0000-4000-8000-000000000006', 'c0ffee00-0000-4000-8000-000000000003', 2, 'Romanian assembly is a single line',
   'All SPH-155 for the EU is finished on one line at the Carpathia plant (TEST DATA).', E'Carpathia Defence Industries (TEST)\nJoint venture', 'https://news.example.com/halcyon-romania-line', 'judgement');

-- Partner ties each vulnerability traces to (relationship_id of competitive_partnership).
INSERT INTO staging.competitive_synthesis_vulnerability_trace
  (trace_id, vulnerability_id, relationship_id, source_url, source_tier) VALUES
  ('f9200000-0000-4000-8000-000000000001', 'f9100000-0000-4000-8000-000000000001', 'd2000000-0000-4000-8000-000000000003', 'https://borealis-arms.example.com/supply', 'judgement'),
  ('f9200000-0000-4000-8000-000000000002', 'f9100000-0000-4000-8000-000000000002', 'd2000000-0000-4000-8000-000000000002', 'https://news.example.com/borealis-tessera-mou', 'judgement'),
  ('f9200000-0000-4000-8000-000000000003', 'f9100000-0000-4000-8000-000000000003', 'd2000000-0000-4000-8000-000000000006', 'https://news.example.com/cobalt-gulf-assembly', 'judgement'),
  ('f9200000-0000-4000-8000-000000000004', 'f9100000-0000-4000-8000-000000000004', 'd2000000-0000-4000-8000-000000000005', 'https://cobalt-dynamics.example.com/supply', 'judgement'),
  ('f9200000-0000-4000-8000-000000000005', 'f9100000-0000-4000-8000-000000000005', 'd2000000-0000-4000-8000-000000000008', 'https://halcyon-land.example.com/supply', 'judgement'),
  ('f9200000-0000-4000-8000-000000000006', 'f9100000-0000-4000-8000-000000000006', 'd2000000-0000-4000-8000-000000000007', 'https://news.example.com/halcyon-romania-line', 'judgement');

-- "Field-level read" on Partnerships: three patterns and the bottom line.
INSERT INTO staging.competitive_field_synthesis
  (synthesis_id, row_kind, display_order, field_title, pattern, implication, support_count, support_total, bottom_line, source_url, source_tier) VALUES
  ('f9300000-0000-4000-8000-000000000001', 'pattern', 1, 'Suppliers are shared', 'Most rivals buy from a small set of suppliers (TEST DATA).',
   'A supplier outage hits several rivals at once, and Aurora if it uses the same source.', 5, 13, NULL, 'https://reports.example.org/field-read-suppliers', 'judgement'),
  ('f9300000-0000-4000-8000-000000000002', 'pattern', 2, 'Joint ventures follow tenders', 'Joint ventures are announced in the months before a large tender (TEST DATA).',
   'A new joint venture is an early signal that a bid is coming.', 3, 13, NULL, 'https://reports.example.org/field-read-ventures', 'judgement'),
  ('f9300000-0000-4000-8000-000000000003', 'pattern', 3, 'Indian MoUs link rivals', 'Two rivals have signed MoUs with the same Indian company (TEST DATA).',
   'The Indian company can pick which rival to back in a given bid.', 2, 13, NULL, 'https://reports.example.org/field-read-india', 'judgement'),
  ('f9300000-0000-4000-8000-000000000004', 'bottom_line', 99, NULL, NULL, NULL, NULL, NULL,
   'Rivals are building chains of suppliers and local partners; Aurora competes against chains, not single companies (TEST DATA).', 'https://reports.example.org/field-read', 'judgement');

-- Past awards (MarketOverview "Past awards"). Values stay in their own currency.
INSERT INTO staging.market_award
  (award_id, segment, winner, brand, buyer, site, country_name, programme, title, title_local, tender_number, award_date, award_year,
   value_amount, value_currency, value_text, bids, source_url, source_tier) VALUES
  (70001, 'Artillery', 'L&T (TEST)', 'K9 Vajra-Test', 'وزارة الدفاع (TEST)', 'Hazira-Test', 'India', 'Self-propelled howitzer buy (TEST)',
   '100 self-propelled 155 mm howitzers (TEST)', 'توريد 100 مدفع هاوتزر ذاتي الحركة عيار 155 ملم (TEST)', 'IN-MOD-2025-0100', '2025-03-18', 2025,
   650000000, 'USD', 'USD 650 million', 4, 'https://awards.example.com/in-mod-2025-0100', 'primary'),
  (70002, 'Ammunition', 'Halcyon Land Systems (TEST)', 'K-Shell (TEST)', 'Ministry of National Defence (TEST)', 'Changwon-Test', 'Poland', '155 mm round buy (TEST)',
   '250,000 rounds of 155 mm HE (TEST)', 'Dostawa 250 000 sztuk amunicji 155 mm HE (TEST)', 'PL-MND-2025-0250', '2025-07-02', 2025,
   410000000, 'EUR', 'EUR 410 million', 6, 'https://awards.example.org/pl-mnd-2025-0250', 'primary'),
  (70003, 'Armoured Vehicles', 'Cobalt Dynamics (TEST)', 'Guardian APC (TEST)', 'Royal Land Forces (TEST)', 'Redstone Bay', 'Saudi Arabia', 'Gulf APC refresh (TEST)',
   '40 Guardian armoured personnel carriers (TEST)', 'توريد 40 ناقلة جنود مدرعة من طراز غارديان (TEST)', 'SA-RLF-2026-0040', '2026-01-26', 2026,
   NULL, NULL, 'Value not published', 3, 'https://awards.example.net/sa-rlf-2026-0040', 'independent'),
  (70004, 'Small Arms', 'Meridian Ordnance (TEST)', 'M-Rifle (TEST)', 'Federal Police (TEST)', 'Valmont-sur-Test', 'Germany', 'Police rifle buy (TEST)',
   '12,000 service rifles (TEST)', NULL, 'DE-FP-2026-0120', '2026-05-11', 2026,
   18500000, 'EUR', 'EUR 18.5 million', 2, 'https://awards.example.com/de-fp-2026-0120', 'primary'),
  (70005, 'Unmanned & Counter-UAS', 'Tessera Aerospace (TEST)', 'Drone Killer (TEST)', 'Ministry of Defence (TEST)', 'Bengaluru-Test', 'India', 'Counter-drone fast track (TEST)',
   '60 counter-UAS interceptor batteries (TEST)', NULL, 'IN-MOD-2026-0060', '2026-08-04', 2026,
   9200000000, 'INR', 'INR 9.2 billion', NULL, 'https://awards.example.org/in-mod-2026-0060', 'independent'),
  -- no award_date, only the year: the backend sort must cope with a null date (task 4 fix round 1)
  (70006, 'Artillery', 'Meridian Ordnance (TEST)', NULL, 'Ministry of Defence (TEST)', NULL, 'France', 'Mortar refresh (TEST)',
   '300 mortars (TEST)', NULL, 'FR-MOD-2024-0300', NULL, 2024,
   NULL, NULL, NULL, NULL, 'https://awards.example.net/fr-mod-2024-0300', 'independent');

-- "What to do" per tender segment (segment = market_tender.category_text). A recommendation is a judgement.
INSERT INTO staging.market_segment_assessment (segment, recommendation, source_url, source_tier) VALUES
  ('Ammunition',        'Prioritise: two open tenders fit the Aurora 155 mm round (TEST DATA).',  'https://reports.example.org/segment-ammunition', 'judgement'),
  ('Artillery',         'Watch: open tenders exist but the incumbent wins most awards (TEST DATA).', 'https://reports.example.org/segment-artillery', 'judgement'),
  ('Armoured Vehicles', 'Steady: nothing open fits the current Aurora range (TEST DATA).',        'https://reports.example.org/segment-vehicles', 'judgement'),
  ('Small Arms',        'Watch: one police tender, low value (TEST DATA).',                       'https://reports.example.org/segment-small-arms', 'judgement');

-- Assessment per patent technology field (area_label = competitive_patent_filing.area_label, set below).
INSERT INTO staging.patent_field_assessment (area_label, crowding, client_position_note, source_url, source_tier) VALUES
  ('Gun systems',          'crowded',  'Aurora holds few filings here; gun mechanisms are well covered by rivals (TEST DATA).',      'https://reports.example.org/patents-guns', 'judgement'),
  ('Guided munitions',     'emerging', 'Aurora has room to file; two rivals have started guided shell families (TEST DATA).',        'https://reports.example.org/patents-guided', 'judgement'),
  ('Fuzes and initiation', 'locked',   'Core fuze claims are held by two rivals; Aurora would need a licence (TEST DATA).',          'https://reports.example.org/patents-fuzes', 'judgement'),
  ('Armour and protection','open',     'Few filings in the field; Aurora can claim modular attachment methods (TEST DATA).',         'https://reports.example.org/patents-armour', 'judgement'),
  ('Counter-UAS',          'emerging', 'Interceptor filings are rising; Aurora has none yet (TEST DATA).',                           'https://reports.example.org/patents-cuas', 'judgement'),
  ('Small arms',           'open',     'Low filing activity; Aurora position is neutral (TEST DATA).',                               'https://reports.example.org/patents-small-arms', 'judgement');

-- New columns on rows inserted by the earlier files ----------------------------------------------------------------------------------------

-- competitive_partnership.client_verdict (threat / watch / opportunity) and client_impact; the last four partnerships stay empty (no judgement yet).
UPDATE staging.competitive_partnership SET client_verdict = v.verdict, client_impact = v.impact
FROM (VALUES
  ('d2000000-0000-4000-8000-000000000001'::uuid, 'watch',       'Better optics lift the BH-155 against Aurora guns in NATO bids (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000002'::uuid, 'threat',      'Guided shells from two rivals could close the precision gap in India (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000003'::uuid, 'opportunity', 'A single barrel-steel source is a weak point; Aurora can offer shorter lead times (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000004'::uuid, 'threat',      'A joint counter-drone offer for India competes with the Aurora counter-UAS line (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000005'::uuid, 'watch',       'Armour supply stays tight; no direct effect on Aurora yet (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000006'::uuid, 'threat',      'Local assembly gives Cobalt a Gulf delivery edge over Aurora APC (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000007'::uuid, 'threat',      'EU final assembly shortens Halcyon delivery below the Aurora Gun 155 (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000008'::uuid, 'opportunity', 'Reliance on imported charges exposes Halcyon to a licence delay (TEST DATA).'),
  ('d2000000-0000-4000-8000-000000000009'::uuid, 'watch',       'Domestic fire control keeps Halcyon price low (TEST DATA).')
) AS v(rid, verdict, impact)
WHERE relationship_id = v.rid;

-- competitive_news_article.description: an excerpt on the first six stories; the rest stay empty.
UPDATE staging.competitive_news_article SET description = v.d
FROM (VALUES
  ('a5000000-0000-4000-8000-000000000001'::uuid, 'Borealis Arms (TEST) announced a NOK 2.1 billion order for towed 155 mm howitzers from a Polish customer (TEST DATA).'),
  ('a5000000-0000-4000-8000-000000000002'::uuid, 'The second barrel line in Poland doubles annual output of 155 mm barrels (TEST DATA).'),
  ('a5000000-0000-4000-8000-000000000003'::uuid, 'The Smart Shell reached 60 km in a range trial attended by two customers (TEST DATA).'),
  ('a5000000-0000-4000-8000-000000000004'::uuid, 'The first forty Guardian carriers were handed over in Riyadh-Test (TEST DATA).'),
  ('a5000000-0000-4000-8000-000000000005'::uuid, 'Quarterly revenue rose 11% on the vehicle order backlog (TEST DATA).'),
  ('a5000000-0000-4000-8000-000000000006'::uuid, 'Cobalt and Tessera will jointly offer counter-drone systems in India (TEST DATA).')
) AS v(aid, d)
WHERE article_id = v.aid;

-- competitive_patent_filing.area_label (technology field), threat_level (holder, threat / watch / fav), client_relevance (high / medium / low; empty for competitor 4).
UPDATE staging.competitive_patent_filing SET
  area_label = CASE classification_text
      WHEN 'Gun barrels and breech mechanisms' THEN 'Gun systems'
      WHEN 'Guided projectiles'                THEN 'Guided munitions'
      WHEN 'Ammunition fuzes'                  THEN 'Fuzes and initiation'
      WHEN 'Armour and vehicle protection'     THEN 'Armour and protection'
      WHEN 'Counter-UAS interceptors'          THEN 'Counter-UAS'
      WHEN 'Small arms mechanisms'             THEN 'Small arms'
  END,
  threat_level = CASE portfolio_id
      WHEN 'e1000000-0000-4000-8000-000000000001' THEN 'threat'
      WHEN 'e1000000-0000-4000-8000-000000000002' THEN 'watch'
      WHEN 'e1000000-0000-4000-8000-000000000003' THEN 'threat'
      WHEN 'e1000000-0000-4000-8000-000000000004' THEN 'fav'
      ELSE 'watch'
  END,
  client_relevance = CASE
      WHEN portfolio_id = 'e1000000-0000-4000-8000-000000000004' THEN NULL
      WHEN status = 'granted' THEN 'high'
      WHEN status = 'pending' THEN 'medium'
      ELSE 'low'
  END;

-- staging_ui.competitive_metric.metric_key: the three tiles the Overview draws by key.
UPDATE staging_ui.competitive_metric SET metric_key = CASE metric_label
    WHEN 'Competitors tracked'   THEN 'companies_tracked'
    WHEN 'Competitive threats'   THEN 'threats'
    WHEN 'Watch signals'         THEN 'watch'
END;

-- Sources for Trace ------------------------------------------------------------------------------------------------------------------------
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, document_id, retrieved_at) VALUES
  ('market_award', '70001', 'winner', 'https://awards.example.com/in-mod-2025-0100', 'primary', 'Ministry award notice (TEST)', 'Contract awarded to L&T (TEST) for 100 self-propelled howitzers (TEST DATA).', NULL, '2026-10-14 08:30:00+00'),
  ('market_award', '70001', 'value_amount', 'https://awards.example.com/in-mod-2025-0100', 'primary', 'Ministry award notice (TEST)', 'Contract value USD 650 million (TEST DATA).', NULL, '2026-10-14 08:30:00+00'),
  ('market_award', '70002', 'winner', 'https://awards.example.org/pl-mnd-2025-0250', 'primary', 'Polish procurement bulletin (TEST)', 'Winner: Halcyon Land Systems (TEST) (TEST DATA).', NULL, '2026-10-14 08:30:00+00'),
  ('competitive_synthesis', 'c0ffee00-0000-4000-8000-000000000001', 'thesis', 'https://borealis-arms.example.com/strategy', 'judgement', NULL, 'Thesis rests on the three partner ties of Borealis Arms (TEST) (TEST DATA).', NULL, '2026-10-14 08:30:00+00'),
  ('patent_field_assessment', 'Fuzes and initiation', 'crowding', 'https://reports.example.org/patents-fuzes', 'judgement', NULL, 'Locked: core fuze claims are held by two rivals (TEST DATA).', NULL, '2026-10-14 08:30:00+00'),
  ('competitive_partnership', 'd2000000-0000-4000-8000-000000000006', 'client_verdict', 'judgement', 'judgement', NULL, 'Threat: local assembly gives Cobalt a Gulf delivery edge (TEST DATA).', NULL, '2026-10-14 08:30:00+00');

COMMIT;
