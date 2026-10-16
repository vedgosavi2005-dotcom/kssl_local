-- Group B test rows: Products (KSSL + competitor catalogues, specs, programmes, product news) and
-- Product Evaluation (competitive_matchup*). Fictional. References db/test_seed_v2/a_base.sql:
-- client 1 'KSSL'; competitors 1111.. Example Defence, 2222.. Northwind Arms, 3333.. Tarvo Systems.
-- edge_score / decision_level / better_side / gap_value follow the loader rules documented in
-- backend/areas/b_products.py (decision_level 1 = KSSL behind, 2 = near parity, 3 = KSSL ahead).

-- ===== KSSL (client) products =====
INSERT INTO staging.client_product
  (client_product_id, client_id, product_name, category, subcategory, product_family, model_code, status,
   technology, market_availability, created_at, updated_at)
VALUES
  (101, 1, 'Sample Howitzer 155/52', 'Artillery', 'Towed howitzer', 'Sample Gun Family', 'SH-155', 'In production',
   'Towed, 52-calibre barrel', 'Domestic and export', now(), now()),
  (102, 1, 'Sample HE Shell 155', 'Ammunition', 'Artillery shell', 'Sample Ammunition Family', 'SS-155-HE', 'In production',
   'High-explosive, base-bleed option', 'Domestic', now(), now()),
  (103, 1, 'Sample Armoured Carrier 6x6', 'Armoured Vehicles', 'Wheeled APC', 'Sample Carrier Family', 'SAC-6', 'Prototype',
   'Wheeled 6x6', NULL, now(), now());

INSERT INTO staging.client_product_specification
  (specification_id, client_product_id, spec_name, value_text, value_numeric, unit, spec_group, display_order)
VALUES
  (1001, 101, 'Max range', NULL, 40, 'km', 'Performance', 1),
  (1002, 101, 'Calibre', '155 mm / 52 cal', NULL, NULL, 'Gun', 2),
  (1003, 101, 'Weight', NULL, 13000, 'kg', 'Mobility', 3),
  (1004, 101, 'Rate of fire', NULL, 6, 'rpm', 'Performance', 4),
  (1005, 101, 'Crew', NULL, 5, NULL, 'Operation', 5),
  (1006, 101, 'Muzzle velocity', NULL, 900, 'm/s', 'Gun', 6),
  (1007, 101, 'Barrel life', NULL, 3000, 'rounds', 'Gun', 7),
  (1008, 101, 'Fire control', 'Digital fire-control computer', NULL, NULL, 'Electronics', 8),
  (1009, 102, 'Max range', NULL, 30, 'km', 'Performance', 1),
  (1010, 102, 'Shell weight', NULL, 43.5, 'kg', 'Physical', 2),
  (1011, 102, 'Filler mass', NULL, 11.3, 'kg', 'Physical', 3),
  (1012, 102, 'Dispersion (CEP)', NULL, 90, 'm', 'Performance', 4),
  (1013, 102, 'Fuze', 'Point-detonating / proximity', NULL, NULL, 'Fuze', 5),
  (1014, 102, 'Operating temperature', '-40 to +60 C', NULL, NULL, 'Environment', 6),
  (1015, 103, 'Crew', NULL, 2, 'persons', 'Operation', 1),
  (1016, 103, 'Troops carried', NULL, 8, 'persons', 'Operation', 2),
  (1017, 103, 'Combat weight', NULL, 18500, 'kg', 'Mobility', 3),
  (1018, 103, 'Max road speed', NULL, 100, 'km/h', 'Mobility', 4),
  (1019, 103, 'Armour protection', 'STANAG 4569 Level 2', NULL, NULL, 'Protection', 5),
  (1020, 103, 'Range', NULL, 700, 'km', 'Mobility', 6);

INSERT INTO staging.client_product_program
  (program_id, client_product_id, program_name, program_type, owner, start_date, end_date, status, description)
VALUES
  (2001, 101, 'Towed Gun Trials Phase 2', 'Trials', 'Example Army Ordnance Board', '2025-03-01', '2026-12-31', 'Ongoing',
   'User trials of the sample howitzer at two test ranges.'),
  (2002, 102, 'Shell Qualification Lot 1', 'Qualification', 'Example Army Ordnance Board', '2025-06-15', NULL, 'Planned',
   'First production-lot qualification of the sample shell.'),
  (2003, 103, 'Carrier Prototype Evaluation', 'Evaluation', 'Example Army Mechanised Command', '2026-01-10', '2026-09-30', 'Completed',
   'Prototype mobility and protection evaluation.');

INSERT INTO staging.client_product_source (client_product_id, source_id, source_label, source_type, source_url, published_date)
VALUES
  (101, 3001, 'KSSL product brochure (sample)', 'brochure', 'https://kssl.example.test/brochure/sh-155.pdf', '2025-01-20'),
  (103, 3002, 'KSSL carrier datasheet (sample)', 'datasheet', 'https://kssl.example.test/datasheet/sac-6.pdf', '2026-02-02');

-- ===== competitor products =====
INSERT INTO staging.competitive_product
  (product_id, competitor_id, product_name, category, category_filter, country, is_collapsed)
VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Thunder 155', 'Artillery', 'artillery', 'Exampleland', false),
  ('aaaaaaaa-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Shell Mk4', 'Ammunition', 'ammunition', 'Exampleland', false),
  ('aaaaaaaa-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'Nordgun 52', 'Artillery', 'artillery', 'Northland', false),
  ('aaaaaaaa-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'Nord Wheeled Carrier', 'Armoured Vehicles', 'armoured-vehicles', 'Northland', false),
  ('aaaaaaaa-0000-0000-0000-000000000005', '33333333-3333-3333-3333-333333333333', 'Fuze T1', 'Ammunition', 'ammunition', 'Tarvonia', false),
  ('aaaaaaaa-0000-0000-0000-000000000006', '33333333-3333-3333-3333-333333333333', 'Tarvo Sensor Mast', 'Defence electronics', 'defence-electronics', NULL, false);

INSERT INTO staging.competitive_product_specification
  (spec_id, product_id, spec_label, spec_value, unit, source_count, source_url)
VALUES
  ('bbbbbbbb-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'Max range', '45', 'km', 2, 'https://eds.example.test/thunder-155'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'Calibre', '155 mm / 52 cal', NULL, 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000001', 'Weight', '12500', 'kg', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000004', 'aaaaaaaa-0000-0000-0000-000000000001', 'Rate of fire', '8', 'rpm', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000001', 'Crew', '5', NULL, 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000006', 'aaaaaaaa-0000-0000-0000-000000000001', 'Muzzle velocity', '890', 'm/s', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000007', 'aaaaaaaa-0000-0000-0000-000000000001', 'Barrel life', '2500', 'rounds', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000008', 'aaaaaaaa-0000-0000-0000-000000000002', 'Max range', '27', 'km', 1, 'https://eds.example.test/shell-mk4'),
  ('bbbbbbbb-0000-0000-0000-000000000009', 'aaaaaaaa-0000-0000-0000-000000000002', 'Shell weight', '43.2', 'kg', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-00000000000a', 'aaaaaaaa-0000-0000-0000-000000000002', 'Filler mass', '11.0', 'kg', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-00000000000b', 'aaaaaaaa-0000-0000-0000-000000000002', 'Dispersion (CEP)', '80', 'm', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-00000000000c', 'aaaaaaaa-0000-0000-0000-000000000003', 'Max range', '38', 'km', 1, 'https://northwind.example.test/nordgun-52'),
  ('bbbbbbbb-0000-0000-0000-00000000000d', 'aaaaaaaa-0000-0000-0000-000000000003', 'Calibre', '155 mm / 52 cal', NULL, 1, NULL),
  ('bbbbbbbb-0000-0000-0000-00000000000e', 'aaaaaaaa-0000-0000-0000-000000000003', 'Weight', '14500', 'kg', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-00000000000f', 'aaaaaaaa-0000-0000-0000-000000000003', 'Rate of fire', '6', 'rpm', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000010', 'aaaaaaaa-0000-0000-0000-000000000003', 'Crew', '6', NULL, 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000011', 'aaaaaaaa-0000-0000-0000-000000000003', 'Muzzle velocity', '870', 'm/s', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000012', 'aaaaaaaa-0000-0000-0000-000000000003', 'Barrel life', '3200', 'rounds', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000013', 'aaaaaaaa-0000-0000-0000-000000000003', 'Loading', 'Manual', NULL, 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000014', 'aaaaaaaa-0000-0000-0000-000000000004', 'Crew', '3', 'persons', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000015', 'aaaaaaaa-0000-0000-0000-000000000004', 'Combat weight', '17000', 'kg', 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000016', 'aaaaaaaa-0000-0000-0000-000000000005', 'Fuze type', 'Electronic time / proximity', NULL, 1, NULL),
  ('bbbbbbbb-0000-0000-0000-000000000017', 'aaaaaaaa-0000-0000-0000-000000000005', 'Operating temperature', '-40 to +55 C', NULL, 1, NULL);

INSERT INTO staging.competitive_product_program
  (program_id, product_id, program_title, authority, program_date, status, status_color, description)
VALUES
  ('cccccccc-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'Exampleland Field Artillery Renewal', 'Exampleland Ministry of Defence', '2025-09-01', 'Contract awarded', '#34d399',
   'Renewal of the field artillery park with the Thunder 155.'),
  ('cccccccc-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000001', 'Export Evaluation, Utopia', 'Utopia Army', '2026-04-12', 'Under trial', '#f59e0b',
   'Evaluation of the Thunder 155 by a third-country army.'),
  ('cccccccc-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000003', 'Northland Gun Modernisation', 'Northland Armed Forces', '2025-11-20', 'In service', '#38bdf8',
   'Fielding of the Nordgun 52.'),
  ('cccccccc-0000-0000-0000-000000000004', 'aaaaaaaa-0000-0000-0000-000000000004', 'Wheeled Carrier Tender', 'Northland Armed Forces', '2026-02-02', 'Bid submitted', NULL,
   'Competitive tender for a wheeled personnel carrier.'),
  ('cccccccc-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000005', 'Fuze Second Source', 'Tarvonia Defence Forces', '2026-05-05', 'Planning', '#a78bfa',
   'Second-source fuze supply for 155 mm ammunition.');

INSERT INTO staging.competitive_product_news
  (product_news_id, product_id, matchup_id, headline, article_url, published_date, publisher, category, comparison_reason,
   side_a_product_id, side_b_product_id)
VALUES
  ('dddddddd-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 1,
   'Example Defence completes Thunder 155 firing trials', 'https://news.example.test/thunder-155-trials', '2026-09-18', 'Example Defence Review',
   'Artillery', 'Same calibre and role as the KSSL Sample Howitzer 155/52.', 'aaaaaaaa-0000-0000-0000-000000000001', NULL),
  ('dddddddd-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000003', 2,
   'Northwind Arms lifts Nordgun 52 output', 'https://news.example.test/nordgun-52-output', '2026-10-02', 'Northland Industry Weekly',
   'Artillery', NULL, 'aaaaaaaa-0000-0000-0000-000000000003', NULL);

-- ===== matchups (KSSL product vs rival product) =====
INSERT INTO staging.competitive_matchup
  (matchup_id, category_code, client_product_id, client_product_name, competitor_id, competitor_name,
   competitor_product_id, competitor_product_name, competitor_country, match_basis, verdict_headline, verdict,
   edge_score, decision_level, comparable_spec_count, sourced_spec_count, created_at, updated_at)
VALUES
  (1, 'Artillery', 101, 'Sample Howitzer 155/52', '11111111-1111-1111-1111-111111111111', 'Example Defence',
   'aaaaaaaa-0000-0000-0000-000000000001', 'Thunder 155', 'Exampleland',
   '155 mm towed howitzers in the same class',
   'KSSL trails on range and rate of fire',
   'Thunder 155 leads on range, weight and rate of fire; the Sample Howitzer 155/52 leads on barrel life.',
   30, 1, 7, 8, now(), now()),
  (2, 'Artillery', 101, 'Sample Howitzer 155/52', '22222222-2222-2222-2222-222222222222', 'Northwind Arms',
   'aaaaaaaa-0000-0000-0000-000000000003', 'Nordgun 52', 'Northland',
   '155 mm / 52 cal towed howitzers',
   'KSSL ahead on range, weight and crew',
   'The Sample Howitzer 155/52 is lighter, longer-ranged and needs a smaller crew; Nordgun 52 has the longer barrel life.',
   75, 3, 6, 7, now(), now()),
  (3, 'Ammunition', 102, 'Sample HE Shell 155', '11111111-1111-1111-1111-111111111111', 'Example Defence',
   'aaaaaaaa-0000-0000-0000-000000000002', 'Shell Mk4', 'Exampleland',
   '155 mm high-explosive shells',
   'Near parity: range against dispersion',
   'The Sample HE Shell 155 reaches further; Shell Mk4 groups tighter. Weight and filler are level.',
   50, 2, 4, 6, now(), now());

INSERT INTO staging.competitive_matchup_specification
  (comparison_specification_id, matchup_id, spec_label, spec_group, unit, client_value_text, client_value_numeric,
   competitor_value_text, competitor_value_numeric, comparability_state, better_side, gap_value, display_order)
VALUES
  -- matchup 1: Thunder 155 (decided: range/weight/rate of fire -> competitor, barrel life -> client)
  (1, 1, 'Max range', 'Performance', 'km', NULL, 40, NULL, 45, 'comparable', 'competitor', 11.8, 1),
  (2, 1, 'Calibre', 'Gun', NULL, '155 mm / 52 cal', NULL, '155 mm / 52 cal', NULL, 'comparable', 'equal', 0, 2),
  (3, 1, 'Weight', 'Mobility', 'kg', NULL, 13000, NULL, 12500, 'comparable', 'competitor', 3.9, 3),
  (4, 1, 'Rate of fire', 'Performance', 'rpm', NULL, 6, NULL, 8, 'comparable', 'competitor', 28.6, 4),
  (5, 1, 'Crew', 'Operation', NULL, NULL, 5, NULL, 5, 'comparable', 'equal', 0, 5),
  (6, 1, 'Muzzle velocity', 'Gun', 'm/s', NULL, 900, NULL, 890, 'comparable', 'equal', 1.1, 6),
  (7, 1, 'Barrel life', 'Gun', 'rounds', NULL, 3000, NULL, 2500, 'comparable', 'client', 18.2, 7),
  (8, 1, 'Fire control', 'Electronics', NULL, 'Digital fire-control computer', NULL, NULL, NULL, 'one_sided', NULL, NULL, 8),
  -- matchup 2: Nordgun 52 (decided: range/weight/crew/velocity -> client, barrel life -> competitor)
  (9, 2, 'Max range', 'Performance', 'km', NULL, 40, NULL, 38, 'comparable', 'client', 5.1, 1),
  (10, 2, 'Weight', 'Mobility', 'kg', NULL, 13000, NULL, 14500, 'comparable', 'client', 10.9, 2),
  (11, 2, 'Rate of fire', 'Performance', 'rpm', NULL, 6, NULL, 6, 'comparable', 'equal', 0, 3),
  (12, 2, 'Crew', 'Operation', NULL, NULL, 5, NULL, 6, 'comparable', 'client', 18.2, 4),
  (13, 2, 'Muzzle velocity', 'Gun', 'm/s', NULL, 900, NULL, 870, 'comparable', 'client', 3.4, 5),
  (14, 2, 'Barrel life', 'Gun', 'rounds', NULL, 3000, NULL, 3200, 'comparable', 'competitor', 6.5, 6),
  (15, 2, 'Loading', 'Gun', NULL, 'Semi-automatic', NULL, 'Manual', NULL, 'not_comparable', NULL, NULL, 7),
  -- matchup 3: Shell Mk4 (decided: range -> client, dispersion -> competitor; weight/filler level)
  (16, 3, 'Max range', 'Performance', 'km', NULL, 30, NULL, 27, 'comparable', 'client', 10.5, 1),
  (17, 3, 'Shell weight', 'Physical', 'kg', NULL, 43.5, NULL, 43.2, 'comparable', 'equal', 0.7, 2),
  (18, 3, 'Filler mass', 'Physical', 'kg', NULL, 11.3, NULL, 11.0, 'comparable', 'equal', 2.7, 3),
  (19, 3, 'Dispersion (CEP)', 'Performance', 'm', NULL, 90, NULL, 80, 'comparable', 'competitor', 11.8, 4),
  (20, 3, 'Fuze', 'Fuze', NULL, 'Point-detonating / proximity', NULL, NULL, NULL, 'one_sided', NULL, NULL, 5),
  (21, 3, 'Operating temperature', 'Environment', NULL, '-40 to +60 C', NULL, NULL, NULL, 'one_sided', NULL, NULL, 6);

INSERT INTO staging.competitive_matchup_advantage (advantage_id, matchup_id, side, advantage_text, display_order, source_id)
VALUES
  (1, 1, 'competitor', 'Longer maximum range (45 km against 40 km).', 1, NULL),
  (2, 1, 'competitor', 'Higher rate of fire (8 rpm against 6 rpm).', 2, NULL),
  (3, 1, 'competitor', 'Lighter by 500 kg.', 3, NULL),
  (4, 1, 'client', 'Longer barrel life (3000 rounds against 2500).', 1, NULL),
  (5, 1, 'client', 'Digital fire-control computer published; the rival does not publish one.', 2, NULL),
  (6, 2, 'client', 'Lighter by 1500 kg and a crew of five against six.', 1, NULL),
  (7, 2, 'client', 'Longer range (40 km against 38 km).', 2, NULL),
  (8, 2, 'client', 'Semi-automatic loading against manual loading.', 3, NULL),
  (9, 2, 'competitor', 'Longer barrel life (3200 rounds against 3000).', 1, NULL),
  (10, 2, 'competitor', 'Local production and an existing support network in Northland.', 2, NULL),
  (11, 3, 'client', 'Longer range (30 km against 27 km).', 1, NULL),
  (12, 3, 'client', 'Point-detonating and proximity fuze options published.', 2, NULL),
  (13, 3, 'competitor', 'Tighter dispersion (80 m CEP against 90 m).', 1, NULL),
  (14, 3, 'competitor', 'Existing supply contracts with Exampleland forces.', 2, NULL);

INSERT INTO staging.competitive_matchup_source (matchup_id, source_id, source_label, source_type, source_url, published_date, source_note)
VALUES
  (1, 1, 'Example Defence Thunder 155 datasheet', 'datasheet', 'https://eds.example.test/thunder-155', '2026-01-15', 'Manufacturer figures'),
  (1, 2, 'KSSL Sample Howitzer brochure', 'brochure', 'https://kssl.example.test/brochure/sh-155.pdf', '2025-01-20', NULL),
  (2, 3, 'Northwind Nordgun 52 brochure', 'brochure', 'https://northwind.example.test/nordgun-52', '2025-12-01', NULL);
