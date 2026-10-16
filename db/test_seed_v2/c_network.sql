-- Test rows for area C (Partnerships, Projects, Geo Footprint, Patents). Fictional companies only.
-- Run after a_base.sql: db/make_test_db.sh kssl_v2_test_c db/test_seed_v2/a_base.sql db/test_seed_v2/c_network.sql
-- Competitors: 1111... Example Defence, 2222... Northwind Arms, 3333... Tarvo Systems; client_id 1 = KSSL.

-- ============================================================ Partnerships (rival side)
INSERT INTO staging.competitive_partnership
  (relationship_id, competitor_id, partner_id, partner_name, partner_type, region, relationship_confidence,
   relationship_scope, description, as_of_date, source_count, source_note, mapped_partner_count, view_relationship_action)
SELECT md5('rel-' || k)::uuid, c::uuid, md5('partner-' || pn)::uuid, pn, pt, rg, conf, scope, descr, asof::date, sc, snote, mc, true
FROM (VALUES
  ('eds-orion',  '11111111-1111-1111-1111-111111111111', 'Orion Dynamics',     'Joint venture',          'Exampleland', 'official',     'Turret drive co-development', 'Orion Dynamics and Example Defence run a 51/49 joint venture that builds turret drives for the EX-155 howitzer.', '2026-03-12', 2, 'Joint company announcement', 4),
  ('eds-helix',  '11111111-1111-1111-1111-111111111111', 'Helix Propulsion Ltd', 'Supply agreement',     'India',       'corroborated', 'Propellant charge supply',    'Helix Propulsion supplies modular propellant charges to Example Defence for export orders.', '2025-11-02', 2, 'Trade press, two outlets', 4),
  ('eds-marlow', '11111111-1111-1111-1111-111111111111', 'Marlow Optics',      'Technology / ToT',       'Northland',   'single_source','Fire-control optics transfer','Marlow Optics transfers its fire-control optics design to Example Defence.', '2024-06-20', 1, 'One trade article', 4),
  ('eds-sable',  '11111111-1111-1111-1111-111111111111', 'Sable Logistics',    'Distribution / reseller','UAE',         'single_source','Regional spares distribution','Sable Logistics holds the spares distribution contract for Example Defence in the Gulf.', '2026-01-15', 1, 'One regional report', 4),
  ('nwa-kestrel','22222222-2222-2222-2222-222222222222', 'Kestrel Systems',    'MoU',                    'Poland',      'official',     'Joint bid study',             'Northwind Arms and Kestrel Systems signed an MoU to study a joint bid for a self-propelled howitzer.', '2026-05-04', 1, 'Ministry press release', 4),
  ('nwa-vantor', '22222222-2222-2222-2222-222222222222', 'Vantor Metals',      'Supply agreement',       'Northland',   'official',     'Barrel steel supply',         'Vantor Metals supplies forged barrel steel under a five-year contract.', '2025-09-10', 1, 'Vantor annual report', 4),
  ('nwa-brindle','22222222-2222-2222-2222-222222222222', 'Brindle Fuzes',      'Licensing',              'Northland',   'corroborated', 'Fuze licence',                'Northwind Arms builds Brindle proximity fuzes under licence.', '2025-02-27', 2, 'Two trade outlets', 4),
  ('nwa-orion',  '22222222-2222-2222-2222-222222222222', 'Orion Dynamics',     'Technology / ToT',       'Exampleland', 'corroborated', 'Drive technology licence',    'Orion Dynamics licenses a drive technology to Northwind Arms.', '2025-12-01', 2, 'Two trade outlets', 4),
  ('tvo-lumen',  '33333333-3333-3333-3333-333333333333', 'Lumen Radar Oy',     'Technology / ToT',       'Tarvonia',    'official',     'Radar module integration',    'Lumen Radar integrates its fire-control radar module into Tarvo Systems battlefield networks.', '2026-02-18', 1, 'Tarvo investor note', 3),
  ('tvo-cobalt', '33333333-3333-3333-3333-333333333333', 'Cobalt Armour',      'Manufacturing',          'Tarvonia',    'corroborated', 'Hull manufacturing',          'Cobalt Armour manufactures protected hulls for Tarvo Systems vehicle kits.', '2025-07-30', 2, 'Two trade outlets', 3),
  ('tvo-kestrel','33333333-3333-3333-3333-333333333333', 'Kestrel Systems',    'Supply agreement',       'Poland',      'single_source','Communications kit supply',   'Kestrel Systems supplies communications kits to Tarvo Systems.', '2024-10-09', 1, 'One article', 3)
) AS v(k, c, pn, pt, rg, conf, scope, descr, asof, sc, snote, mc);

INSERT INTO staging.competitive_partnership_evidence
  (evidence_card_id, relationship_id, card_number, evidence_type, relationship_label, evidence_text, scope, as_of_date, basis_for_type,
   confidence, source_publisher, source_article_title, source_article_url, source_url, source_type, source_note)
SELECT md5('ev-' || k || '-' || n)::uuid, md5('rel-' || k)::uuid, n::smallint, etype, rlabel, etxt, scope, asof::date, basis, conf, pub, atitle,
       'https://news.example.test/' || k || '/' || n, 'https://news.example.test/' || k, 'article', snote
FROM (VALUES
  ('eds-orion',  1, 'Announcement', 'Joint venture',   'Example Defence and Orion Dynamics have formed a joint venture, 51% Example Defence, to build turret drives in Rivertown.', 'Turret drives', '2026-03-12', 'The announcement uses the words joint venture.', 'official', 'Defence Weekly (fictional)', 'Orion and Example Defence form turret JV', 'Joint announcement'),
  ('eds-orion',  2, 'Analysis',     'Joint venture',   'The venture gives Example Defence a second source for drives and shortens delivery on export howitzers.', 'Turret drives', '2026-03-20', 'Analyst read of the announcement.', 'corroborated', 'Gun Journal (fictional)', 'What the Orion venture means for EX-155 deliveries', 'Trade analysis'),
  ('eds-helix',  1, 'Contract',     'Supply agreement','Helix Propulsion will supply modular propellant charges for Example Defence export orders through 2028.', 'Propellant charges', '2025-11-02', 'Contract summary names supply of charges.', 'corroborated', 'Munitions Monitor (fictional)', 'Helix wins charge supply deal', 'Trade press'),
  ('eds-marlow', 1, 'Report',       'Technology / ToT','Marlow Optics confirmed it is transferring fire-control optics know-how to Example Defence.', 'Optics design', '2024-06-20', 'The article says transfer of technology.', 'single_source', 'Optics Digest (fictional)', 'Marlow transfers optics design', 'One trade article'),
  ('eds-sable',  1, 'Report',       'Distribution',    'Sable Logistics was named spares distributor for Example Defence in the Gulf.', 'Spares distribution', '2026-01-15', 'The report names a distribution role.', 'single_source', 'Gulf Defence Wire (fictional)', 'Sable named Gulf spares distributor', 'One regional report'),
  ('nwa-kestrel',1, 'Press release','MoU',            'Northwind Arms and Kestrel Systems signed a memorandum to study a joint bid for a self-propelled howitzer.', 'Joint bid study', '2026-05-04', 'The release says memorandum of understanding.', 'official', 'Ministry of Defence (fictional)', 'MoU signed for howitzer study', 'Ministry press release'),
  ('nwa-vantor', 1, 'Annual report','Supply agreement','Vantor Metals reports a five-year barrel steel contract with Northwind Arms.', 'Barrel steel', '2025-09-10', 'Annual report line item.', 'official', 'Vantor Metals (fictional)', 'Vantor Metals annual report', 'Vantor annual report'),
  ('nwa-brindle',1, 'Report',       'Licensing',       'Northwind Arms manufactures Brindle proximity fuzes under licence.', 'Fuze production', '2025-02-27', 'The report says produced under licence.', 'corroborated', 'Fuze Review (fictional)', 'Brindle licenses proximity fuze', 'Trade press'),
  ('nwa-brindle',2, 'Report',       'Licensing',       'A second outlet confirms the fuze licence covers 120 mm rounds.', '120 mm fuzes', '2025-03-05', 'Second report repeats licence.', 'corroborated', 'Ammo Quarterly (fictional)', 'Licence covers 120 mm fuzes', 'Second outlet'),
  ('nwa-orion',  1, 'Report',       'Technology / ToT','Orion Dynamics licenses a drive technology to Northwind Arms.', 'Drive technology', '2025-12-01', 'Article reports a licence.', 'corroborated', 'Gun Journal (fictional)', 'Orion licenses drive technology', 'Trade press'),
  ('tvo-lumen',  1, 'Investor note','Technology / ToT','Tarvo Systems integrates the Lumen Radar fire-control module across its battlefield network.', 'Radar module', '2026-02-18', 'Investor note names integration.', 'official', 'Tarvo Systems (fictional)', 'Tarvo investor note Q1', 'Tarvo investor note'),
  ('tvo-cobalt', 1, 'Report',       'Manufacturing',   'Cobalt Armour builds protected hulls for Tarvo vehicle kits.', 'Hull manufacture', '2025-07-30', 'Report names contract manufacturing.', 'corroborated', 'Armour Today (fictional)', 'Cobalt builds Tarvo hulls', 'Trade press'),
  ('tvo-kestrel',1, 'Report',       'Supply agreement','Kestrel Systems supplies communications kits to Tarvo Systems.', 'Comms kits', '2024-10-09', 'Report names supply.', 'single_source', 'Signal Notes (fictional)', 'Kestrel kits for Tarvo', 'One article')
) AS v(k, n, etype, rlabel, etxt, scope, asof, basis, conf, pub, atitle, snote);

INSERT INTO staging.competitive_partnership_relationship_detail
  (detail_id, relationship_id, relationship_title, detail_label, type, confidence, scope, basis_for_type, stated_as_of,
   source_note, source_publisher_label, source_article_url, image_state, back_action, selected_card_id)
SELECT md5('det-' || k)::uuid, md5('rel-' || k)::uuid, rt, 'Relationship detail', ty, conf, scope, basis, asof::date,
       snote, pub, 'https://news.example.test/' || k || '/1', 'none', true, md5('ev-' || k || '-1')::uuid
FROM (VALUES
  ('eds-orion',  'Example Defence and Orion Dynamics turret drive venture', 'Joint venture', 'official', 'Turret drives', 'The announcement uses the words joint venture.', '2026-03-12', 'Joint company announcement', 'Defence Weekly (fictional)'),
  ('eds-helix',  'Example Defence and Helix Propulsion charge supply', 'Supply agreement', 'corroborated', 'Propellant charges', 'Contract summary names supply.', '2025-11-02', 'Trade press, two outlets', 'Munitions Monitor (fictional)'),
  ('eds-marlow', 'Example Defence and Marlow Optics optics transfer', 'Technology / ToT', 'single_source', 'Optics design', 'The article says transfer of technology.', '2024-06-20', 'One trade article', 'Optics Digest (fictional)'),
  ('eds-sable',  'Example Defence and Sable Logistics spares distribution', 'Distribution / reseller', 'single_source', 'Spares', 'The report names a distribution role.', '2026-01-15', 'One regional report', 'Gulf Defence Wire (fictional)'),
  ('nwa-kestrel','Northwind Arms and Kestrel Systems joint bid MoU', 'MoU', 'official', 'Joint bid study', 'The release says memorandum of understanding.', '2026-05-04', 'Ministry press release', 'Ministry of Defence (fictional)'),
  ('nwa-vantor', 'Northwind Arms and Vantor Metals steel supply', 'Supply agreement', 'official', 'Barrel steel', 'Annual report line item.', '2025-09-10', 'Vantor annual report', 'Vantor Metals (fictional)'),
  ('nwa-brindle','Northwind Arms and Brindle Fuzes licence', 'Licensing', 'corroborated', 'Fuze production', 'The report says produced under licence.', '2025-02-27', 'Two trade outlets', 'Fuze Review (fictional)'),
  ('nwa-orion',  'Northwind Arms and Orion Dynamics drive licence', 'Technology / ToT', 'corroborated', 'Drive technology', 'Article reports a licence.', '2025-12-01', 'Two trade outlets', 'Gun Journal (fictional)'),
  ('tvo-lumen',  'Tarvo Systems and Lumen Radar integration', 'Technology / ToT', 'official', 'Radar module', 'Investor note names integration.', '2026-02-18', 'Tarvo investor note', 'Tarvo Systems (fictional)'),
  ('tvo-cobalt', 'Tarvo Systems and Cobalt Armour hull manufacture', 'Manufacturing', 'corroborated', 'Hull manufacture', 'Report names contract manufacturing.', '2025-07-30', 'Two trade outlets', 'Armour Today (fictional)'),
  ('tvo-kestrel','Tarvo Systems and Kestrel Systems comms supply', 'Supply agreement', 'single_source', 'Comms kits', 'Report names supply.', '2024-10-09', 'One article', 'Signal Notes (fictional)')
) AS v(k, rt, ty, conf, scope, basis, asof, snote, pub);

-- ============================================================ Partnerships (KSSL side)
INSERT INTO staging.client_partner
  (client_partner_id, client_id, partner_name, legal_name, partner_type, country, region, relationship_confidence, relationship_scope,
   relationship_start_date, relationship_status, strategic_role, created_at, updated_at)
VALUES
  (1, 1, 'Helix Propulsion', 'Helix Propulsion Limited', 'Supply agreement', 'India', 'India', 'official', 'Propellant charges', '2022-04-01', 'active', 'Charge supplier for KSSL 155 mm ammunition', now(), now()),
  (2, 1, 'Zenith Forgings', 'Zenith Forgings Pvt Ltd', 'Manufacturing', 'India', 'India', 'official', 'Barrel forgings', '2020-09-15', 'active', 'Forged barrel blanks', now(), now()),
  (3, 1, 'Alder Fuze Works', 'Alder Fuze Works GmbH', 'Licensing', 'Northland', 'Northland', 'corroborated', 'Fuze licence', '2023-01-10', 'active', 'Fuze licensor', now(), now());

INSERT INTO staging.client_partner_relationship
  (relationship_id, client_partner_id, relationship_type, category, description, territory, start_date, status, kssl_read, competitor_overlap)
VALUES
  (1, 1, 'Supply agreement', 'Ammunition', 'Helix supplies modular charges to KSSL.', 'India', '2022-04-01', 'active', 'KSSL depends on Helix for charge supply, so a rival drawing on the same plant competes for the same capacity.', true),
  (2, 2, 'Manufacturing', 'Artillery', 'Zenith forges barrel blanks for KSSL guns.', 'India', '2020-09-15', 'active', 'Domestic forging source for KSSL gun barrels.', false),
  (3, 3, 'Licensing', 'Ammunition', 'Alder licenses fuze designs to KSSL.', 'Worldwide', '2023-01-10', 'active', 'KSSL fuzes are built under the Alder licence.', false);

INSERT INTO staging.client_partner_source
  (client_partner_id, source_id, relationship_id, source_label, source_url, source_type, source_note, as_of_date, confidence)
VALUES
  (1, 1, 1, 'KSSL supplier register', 'https://kssl.example.test/suppliers/helix', 'company', 'Supplier register entry', '2026-01-01', 'official'),
  (2, 2, 2, 'KSSL supplier register', 'https://kssl.example.test/suppliers/zenith', 'company', 'Supplier register entry', '2026-01-01', 'official'),
  (3, 3, 3, 'KSSL licence list', 'https://kssl.example.test/licences/alder', 'company', 'Licence list entry', '2026-01-01', 'corroborated');

-- ============================================================ Projects
INSERT INTO staging_ui.ui_project_filter (filter_id, filter_code, filter_label, display_order, is_default) VALUES
  (1, 'Domestic', 'Domestic', 1, false), (2, 'Export', 'Export', 2, false);
INSERT INTO staging_ui.ui_project_sequence_option (sequence_option_id, sequence_code, sequence_label, display_order, is_default) VALUES
  (1, 'recent', 'Most recent', 1, true), (2, 'stage', 'Furthest along', 2, false), (3, 'size', 'Largest', 3, false);
INSERT INTO staging_ui.ui_project_stage_step (stage_step_id, stage_name, stage_order) VALUES
  (1, 'Concept', 1), (2, 'Trials', 2), (3, 'Contract', 3), (4, 'Production', 4);

INSERT INTO staging.competitive_project
  (project_id, competitor_id, company_display, project_title, customer, location, kind, region, stage, stage_note, card_summary,
   estimated_value, grade, latest_milestone, latest_milestone_date, assessment_stance, assessment_read, strategic_assessment,
   kssl_platform, kssl_advantage, what_the_project_is, researched_as_of, display_order)
VALUES
  (1, '11111111-1111-1111-1111-111111111111', 'Example Defence', 'Aurora Howitzer Upgrade', 'Exampleland Army', 'Rivertown, Exampleland',
   'Modernisation', 'Domestic', 'Contract', 'Upgrade contract signed for 48 guns.', 'Upgrade of a towed howitzer fleet.',
   48, 'A', 'First upgraded gun handed over', '2026-08-14', 'threat',
   'The upgrade keeps Example Defence ahead on range and fire rate, which pressures KSSL in export tenders that cite the same fleet.',
   'Strategic read: strengthens the EX-155 reference base.', 'KSSL-155 Towed Gun', 'Lower unit cost',
   'A programme to upgrade 48 towed howitzers with new barrels, a digital fire-control suite and the Orion turret drive.', '2026-10-01', 1),
  (2, '22222222-2222-2222-2222-222222222222', 'Northwind Arms', 'Northstar Ammunition Plant', 'Poland Ministry of Defence', 'Gdansk, Poland',
   'Capacity expansion', 'Export', 'Trials', 'Line qualification trials under way.', 'New 120 mm ammunition line.',
   120, 'B', 'Qualification trials started', '2026-09-02', 'watch',
   'A second 120 mm line raises Northwind capacity but is not yet qualified.',
   NULL, 'KSSL-120 Mortar', 'Established export customers',
   'A new plant that fills 120 mm mortar rounds for the Polish armed forces.', '2026-10-01', 2);

INSERT INTO staging.competitive_project_stage (project_stage_id, project_id, stage_name, stage_order, is_current) VALUES
  (1, 1, 'Concept', 1, false), (2, 1, 'Trials', 2, false), (3, 1, 'Contract', 3, true), (4, 1, 'Production', 4, false),
  (5, 2, 'Concept', 1, false), (6, 2, 'Trials', 2, true), (7, 2, 'Contract', 3, false), (8, 2, 'Production', 4, false);

INSERT INTO staging.competitive_project_specification (project_spec_id, project_id, spec_label, spec_value, unit, display_order) VALUES
  (1, 1, 'Calibre', '155', 'mm', 1), (2, 1, 'Guns in scope', '48', NULL, 2), (3, 1, 'Maximum range', '40', 'km', 3),
  (4, 2, 'Calibre', '120', 'mm', 1), (5, 2, 'Annual capacity', '90000', 'rounds', 2);

INSERT INTO staging.competitive_project_timeline (timeline_id, project_id, event_date, event_title, event_description, is_expected, display_order) VALUES
  (1, 1, '2026-02-10', 'Upgrade contract signed', 'Signed with Exampleland Army.', false, 1),
  (2, 1, '2026-08-14', 'First upgraded gun handed over', NULL, false, 2),
  (3, 1, '2027-06-30', 'Final delivery', NULL, true, 3),
  (4, 2, '2026-09-02', 'Qualification trials started', NULL, false, 1),
  (5, 2, '2027-03-31', 'Line acceptance', NULL, true, 2);

INSERT INTO staging.competitive_project_source (source_id, project_id, source_label, source_url, source_domain, source_type) VALUES
  (1, 1, 'Exampleland Army notice', 'https://army.example.test/aurora', 'army.example.test', 'official'),
  (2, 1, 'Defence Weekly report', 'https://news.example.test/aurora', 'news.example.test', 'press'),
  (3, 2, 'Northwind press release', 'https://northwind.example.test/northstar', 'northwind.example.test', 'company');

-- ============================================================ Geo footprint
INSERT INTO staging.competitive_geo_location
  (location_id, country_name, map_label, region_name, latitude, longitude, presence_types, kssl_presence_summary) VALUES
  (1, 'India', 'India', 'Asia', 20.5937, 78.9629, 'Local production; Export', 'KSSL produces locally'),
  (2, 'United Arab Emirates', 'UAE', 'Middle East', 23.4241, 53.8478, 'Export; Sales and service', 'KSSL exports here'),
  (3, 'Poland', 'Poland', 'Europe', 51.9194, 19.1451, 'Local production; Export', NULL),
  (4, 'Exampleland', 'Exampleland', 'Europe', 47.0, 8.0, 'Local production', NULL),
  (5, 'Northland', 'Northland', 'Europe', 60.0, 10.0, 'Local production', NULL);

INSERT INTO staging.competitive_geo_source (source_id, location_id, source_label, source_url, source_type) VALUES
  (1, 1, 'Ministry trade statistics', 'https://trade.example.test/india', 'official');

INSERT INTO staging.competitive_geo_company_presence
  (presence_id, location_id, company_role, client_id, competitor_id, company_name, activity_type, presence_status, overlap_status,
   matched_ranges, product_count, products_summary, relationship_text, display_order) VALUES
  (1, 1, 'client', 1, NULL, 'KSSL', 'Local production', 'Active', NULL, NULL, 2, 'Towed guns and 155 mm ammunition', 'KSSL manufactures guns and ammunition at its own plants.', 1),
  (2, 2, 'client', 1, NULL, 'KSSL', 'Export', 'Active', NULL, NULL, 1, 'Towed guns', 'KSSL exports towed guns.', 2),
  (3, 1, 'competitor', NULL, '11111111-1111-1111-1111-111111111111', 'Example Defence', 'Licensed production', 'Active', 'confirmed', 'Artillery 155 mm', 2, 'EX-155 howitzer, EX-ammo charges', 'Licensed production through an Indian partner.', 3),
  (4, 2, 'competitor', NULL, '11111111-1111-1111-1111-111111111111', 'Example Defence', 'Export', 'Active', 'category', 'Artillery', 1, 'EX-155 howitzer', 'Direct export sales.', 4),
  (5, 3, 'competitor', NULL, '22222222-2222-2222-2222-222222222222', 'Northwind Arms', 'Local production', 'Active', 'confirmed', 'Mortars 120 mm', 2, 'NW-120 mortar, NW-fuze', 'Home market production.', 5),
  (6, 2, 'competitor', NULL, '22222222-2222-2222-2222-222222222222', 'Northwind Arms', 'Sales and service', 'Planned', 'none', NULL, 1, 'NW service kit', 'Service hub planned.', 6),
  (7, 3, 'competitor', NULL, '33333333-3333-3333-3333-333333333333', 'Tarvo Systems', 'Export', 'Active', 'none', NULL, 1, 'TS-Link radio', 'Export of tactical radios.', 7);

INSERT INTO staging.competitive_geo_product
  (geo_product_id, presence_id, product_name, activity_type, since_date, record_note, reported_value, quantity, product_range,
   rated_power_value, rated_power_unit, fuel_type, frequency_hz, display_order) VALUES
  (1, 1, 'KSSL-155 Towed Gun', 'Local production', '2015-01-01', 'Built at the main KSSL plant.', NULL, '120 guns delivered', 'Towed artillery', NULL, NULL, NULL, NULL, 1),
  (2, 1, 'KSSL 155 mm ammunition', 'Local production', '2016-06-01', NULL, NULL, NULL, 'Ammunition', NULL, NULL, NULL, NULL, 2),
  (3, 2, 'KSSL-155 Towed Gun', 'Export', '2021-03-01', 'Export customer is a Gulf ministry.', 'USD 60 million', '18 guns', 'Towed artillery', NULL, NULL, NULL, NULL, 1),
  (4, 3, 'EX-155 Howitzer', 'Licensed production', '2020-05-01', 'Assembled by a local licensee.', NULL, '36 guns', 'Towed artillery', NULL, NULL, NULL, NULL, 1),
  (5, 3, 'EX-155 charges', 'Licensed production', '2021-02-01', NULL, NULL, NULL, 'Ammunition', NULL, NULL, NULL, NULL, 2),
  (6, 4, 'EX-155 Howitzer', 'Export', '2022-09-01', 'Delivered to a Gulf customer.', 'USD 90 million', '24 guns', 'Towed artillery', NULL, NULL, NULL, NULL, 1),
  (7, 5, 'NW-120 Mortar', 'Local production', '2012-01-01', NULL, NULL, '400 units', 'Mortars', NULL, NULL, NULL, NULL, 1),
  (8, 5, 'NW-fuze', 'Local production', '2013-01-01', NULL, NULL, NULL, 'Ammunition', NULL, NULL, NULL, NULL, 2),
  (9, 6, 'NW service kit', 'Sales and service', NULL, 'Hub planned for 2027.', NULL, NULL, 'Support', NULL, NULL, NULL, NULL, 1),
  (10, 7, 'TS-Link radio', 'Export', '2023-04-01', NULL, NULL, '800 radios', 'Communications', NULL, NULL, NULL, 50, 1);

INSERT INTO staging.competitive_geo_product_match
  (match_id, geo_product_id, comparison_title, kssl_counter_label, evaluation_label, decision_level, kssl_score, competitor_score,
   rating_delta, match_basis, qualitative_summary, match_status) VALUES
  (1, 4, 'KSSL-155 vs EX-155', 'KSSL-155 Towed Gun', 'Rival ahead on range', 1, 46, 62, -16, 'Same 155 mm towed class', 'The EX-155 out-ranges the KSSL-155 but costs more per round.', 'matched'),
  (2, 7, 'KSSL-120 vs NW-120', 'KSSL-120 Mortar', 'Near parity', 2, 58, 57, 1, 'Same 120 mm mortar class', 'The two mortars are close on every measured dimension.', 'matched');

INSERT INTO staging.competitive_geo_product_specification
  (comparison_spec_id, match_id, spec_name, spec_group, kssl_value, competitor_value, unit, gap_value, better_side, display_order) VALUES
  (1, 1, 'Maximum range', 'Performance', '30', '40', 'km', '33%', 'competitor', 1),
  (2, 1, 'Rate of fire', 'Performance', '6', '6', 'rpm', '0%', 'level', 2),
  (3, 1, 'Weight', 'Mobility', '7.2', '8.0', 't', '10%', 'client', 3),
  (4, 2, 'Range', 'Performance', '7.2', '7.0', 'km', '3%', 'level', 1),
  (5, 2, 'Weight', 'Mobility', '150', '165', 'kg', '10%', 'client', 2);

INSERT INTO staging.competitive_geo_product_news (news_id, geo_product_id, headline, publisher, published_date, article_url, display_order) VALUES
  (1, 4, 'Indian licensee to double EX-155 output', 'Defence Weekly (fictional)', '2026-07-21', 'https://news.example.test/ex155-licensee', 1);

INSERT INTO staging.competitive_geo_source (source_id, geo_product_id, match_id, source_label, source_url, source_type) VALUES
  (2, 4, NULL, 'Licensee press note', 'https://licensee.example.test/ex155', 'company'),
  (3, NULL, 1, 'Comparison sheet', 'https://kssl.example.test/compare/155', 'company');

-- ============================================================ Patents
INSERT INTO staging.competitive_patent_portfolio
  (portfolio_id, competitor_id, lens, filing_count, granted_count, pending_count, grant_status_state, status_note, empty_message,
   data_source_note, competitor_search_query)
SELECT md5('pf-' || c)::uuid, c::uuid, 'rival', fc, gc, pc, state, note, NULL, dsn, q
FROM (VALUES
  ('11111111-1111-1111-1111-111111111111', 4, 2, 2, 'known',   'Grant status read from the registry.', 'Records from the national patent registry.', 'Example Defence'),
  ('22222222-2222-2222-2222-222222222222', 3, NULL, NULL, 'unknown', 'Grant status was not captured for this portfolio.', 'Records from the national patent registry.', 'Northwind Arms'),
  ('33333333-3333-3333-3333-333333333333', 3, 1, 2, 'known',   NULL, 'Records from the national patent registry.', 'Tarvo Systems')
) AS v(c, fc, gc, pc, state, note, dsn, q);

INSERT INTO staging.competitive_patent_filing
  (filing_id, portfolio_id, title, publication_number, jurisdiction, filed_date, status, classification_code, classification_text, patent_url)
SELECT md5('pat-' || n)::uuid, md5('pf-' || c)::uuid, t, n, j, d::date, s, code, ctext, 'https://patents.example.test/' || n
FROM (VALUES
  ('11111111-1111-1111-1111-111111111111', 'EX-0001', 'Recoil damper for towed howitzer', 'XL', '2022-03-04', 'granted', 'F41A 25/12', 'Artillery'),
  ('11111111-1111-1111-1111-111111111111', 'EX-0002', 'Modular propellant charge case', 'XL', '2023-07-19', 'granted', 'F42B 5/18', 'Ammunition'),
  ('11111111-1111-1111-1111-111111111111', 'EX-0003', 'Digital fire-control interface', 'XL', '2024-11-02', 'pending', 'F41G 3/06', 'Artillery'),
  ('11111111-1111-1111-1111-111111111111', 'EX-0004', 'Turret drive gearbox', 'US', '2025-02-27', 'pending', 'F41A 27/06', 'Artillery'),
  ('22222222-2222-2222-2222-222222222222', 'NW-0001', 'Proximity fuze with tilt sensor', 'XN', '2021-05-11', NULL, 'F42C 13/04', 'Ammunition'),
  ('22222222-2222-2222-2222-222222222222', 'NW-0002', 'Mortar baseplate with quick-lock', 'XN', '2022-09-30', NULL, 'F41A 23/20', 'Artillery'),
  ('22222222-2222-2222-2222-222222222222', 'NW-0003', 'Lightweight mortar barrel liner', 'EP', '2024-01-15', NULL, 'F41A 21/02', 'Artillery'),
  ('33333333-3333-3333-3333-333333333333', 'TS-0001', 'Hull armour insert panel', 'XT', '2020-10-06', 'granted', 'F41H 5/04', 'Armoured Vehicles'),
  ('33333333-3333-3333-3333-333333333333', 'TS-0002', 'Radar module mount for vehicles', 'XT', '2023-12-12', 'pending', 'F41H 7/02', 'Armoured Vehicles'),
  ('33333333-3333-3333-3333-333333333333', 'TS-0003', 'Active protection sensor array', 'US', '2025-06-23', 'pending', 'F41H 11/02', 'Armoured Vehicles')
) AS v(c, n, t, j, d, s, code, ctext);

INSERT INTO staging.competitive_patent_classification (classification_id, portfolio_id, lens, category_label, filing_count)
SELECT md5('cl-' || c || '-' || lab)::uuid, md5('pf-' || c)::uuid, 'technology', lab, n
FROM (VALUES
  ('11111111-1111-1111-1111-111111111111', 'Artillery', 3),
  ('11111111-1111-1111-1111-111111111111', 'Ammunition', 1),
  ('22222222-2222-2222-2222-222222222222', 'Artillery', 2),
  ('22222222-2222-2222-2222-222222222222', 'Ammunition', 1),
  ('33333333-3333-3333-3333-333333333333', 'Armoured Vehicles', 3)
) AS v(c, lab, n);
