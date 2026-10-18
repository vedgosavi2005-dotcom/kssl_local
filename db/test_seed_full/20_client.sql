-- 20_client.sql
-- (part A) All staging.client_* tables except client_account (in 00_base.sql): client products (+ specifications, programmes, sources) and client partners
-- (+ partner products, relationships, sources). Client = Aurora Defence (TEST), client_id 9001. Product ids 9101-9106, partner ids 9201-9206.
BEGIN;

-- own tables, children first
DELETE FROM staging.client_partner_source;
DELETE FROM staging.client_partner_product;
DELETE FROM staging.client_partner_relationship;
DELETE FROM staging.client_partner;
DELETE FROM staging.client_product_program;
DELETE FROM staging.client_product_specification;
DELETE FROM staging.client_product_source;
DELETE FROM staging.client_product;

-- Aurora's own catalogue (Products page > Aurora tab; client side of every Evaluation matchup). Power / fuel / frequency columns are filled only where they make sense for the product.
INSERT INTO staging.client_product
  (client_product_id, client_id, product_name, category, model_code, product_family, subcategory, technology, status, market_availability, prime_rating, standby_rating, fuel_type, rated_power_value, rated_power_unit, frequency_hz, image_url, source_id, created_at, updated_at) VALUES
  (9101, 9001, 'Aurora Gun 155 (TEST)', 'Artillery', 'AG-155/52', 'Aurora Guns', 'Towed howitzer', '155 mm / 52 calibre', 'In production', 'Domestic and export', NULL, NULL, NULL, NULL, NULL, NULL, 'https://img.example.com/client/9101.jpg', 9810, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9102, 9001, 'Aurora Mounted Gun (TEST)', 'Artillery', 'AMG-155T', 'Aurora Guns', 'Truck-mounted gun', '155 mm / 39 calibre on 8x8 truck', 'In production', 'Domestic; export on request', 'Auxiliary power 24 kW', 'Auxiliary power 24 kW (standby)', 'Diesel', 330, 'kW', NULL, 'https://img.example.com/client/9102.jpg', 9812, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9103, 9001, 'Aurora Shell 155 (TEST)', 'Ammunition', 'AS-155ER', 'Aurora Munitions', 'Extended-range shell', 'Base-bleed HE, modular charge', 'In production', 'Domestic and export', NULL, NULL, NULL, NULL, NULL, NULL, 'https://img.example.com/client/9103.jpg', 9814, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9104, 9001, 'Aurora APC (TEST)', 'Armoured Vehicles', 'AAPC-8x8', 'Aurora Vehicles', 'Armoured personnel carrier', '8x8 wheeled, STANAG 4569 Level 3', 'Series production', 'Domestic', 'Continuous 420 kW', 'Peak 460 kW', 'Diesel', 420, 'kW', NULL, 'https://img.example.com/client/9104.jpg', 9816, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9105, 9001, 'Aurora Carbine (TEST)', 'Small Arms', 'AC-556', 'Aurora Small Arms', 'Assault carbine', '5.56x45 mm gas-operated', 'In production', 'Domestic and export', NULL, NULL, NULL, NULL, NULL, NULL, 'https://img.example.com/client/9105.jpg', 9818, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9106, 9001, 'Aurora Interceptor Drone (TEST)', 'Unmanned & Counter-UAS', 'AID-1', 'Aurora Unmanned', 'Counter-UAS interceptor', 'Radar-cued electric interceptor', 'Pre-production', 'Domestic trials', 'Cruise 2.4 kW', 'Boost 6 kW', 'Electric (Li-ion)', 6, 'kW', 5800000000, 'https://img.example.com/client/9106.jpg', 9820, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00');

-- Where the Aurora product data comes from (Products > Aurora product > Sources).
INSERT INTO staging.client_product_source
  (source_id, client_product_id, source_label, source_type, source_url, published_date) VALUES
  (9810, 9101, 'Aurora Gun 155 (TEST) datasheet', 'company', 'https://aurora-defence.example.com/products/ag-155/52', '2026-03-15'),
  (9811, 9101, 'Aurora Gun 155 (TEST) test report', 'company', 'https://aurora-defence.example.com/reports/ag-155/52-test', '2026-08-20'),
  (9812, 9102, 'Aurora Mounted Gun (TEST) datasheet', 'company', 'https://aurora-defence.example.com/products/amg-155t', '2026-03-15'),
  (9813, 9102, 'Aurora Mounted Gun (TEST) test report', 'company', 'https://aurora-defence.example.com/reports/amg-155t-test', '2026-08-20'),
  (9814, 9103, 'Aurora Shell 155 (TEST) datasheet', 'company', 'https://aurora-defence.example.com/products/as-155er', '2026-03-15'),
  (9815, 9103, 'Aurora Shell 155 (TEST) test report', 'company', 'https://aurora-defence.example.com/reports/as-155er-test', '2026-08-20'),
  (9816, 9104, 'Aurora APC (TEST) datasheet', 'company', 'https://aurora-defence.example.com/products/aapc-8x8', '2026-03-15'),
  (9817, 9104, 'Aurora APC (TEST) test report', 'company', 'https://aurora-defence.example.com/reports/aapc-8x8-test', '2026-08-20'),
  (9818, 9105, 'Aurora Carbine (TEST) datasheet', 'company', 'https://aurora-defence.example.com/products/ac-556', '2026-03-15'),
  (9819, 9105, 'Aurora Carbine (TEST) test report', 'company', 'https://aurora-defence.example.com/reports/ac-556-test', '2026-08-20'),
  (9820, 9106, 'Aurora Interceptor Drone (TEST) datasheet', 'company', 'https://aurora-defence.example.com/products/aid-1', '2026-03-15'),
  (9821, 9106, 'Aurora Interceptor Drone (TEST) test report', 'company', 'https://aurora-defence.example.com/reports/aid-1-test', '2026-08-20');

-- Aurora product specifications (Products > Aurora product > Specs; the numbers also drive the Evaluation matchups).
INSERT INTO staging.client_product_specification
  (specification_id, client_product_id, display_order, spec_group, spec_name, unit, value_numeric, value_text, source_id) VALUES
  (9951, 9101, 1, 'Performance', 'Calibre', 'mm', 155, NULL, 9810),
  (9952, 9101, 2, 'Performance', 'Barrel length', 'calibres', 52, NULL, 9810),
  (9953, 9101, 3, 'Performance', 'Maximum range', 'km', 40, NULL, 9810),
  (9954, 9101, 4, 'Performance', 'Burst rate of fire', 'rds/min', 6, NULL, 9810),
  (9955, 9101, 5, 'Mobility', 'Weight in action', 't', 13.5, NULL, 9810),
  (9956, 9101, 6, 'Crew & logistics', 'Crew', 'persons', 6, NULL, 9810),
  (9957, 9101, 7, 'Mobility', 'Into-action time', 's', 90, NULL, 9810),
  (9958, 9101, 8, 'Crew & logistics', 'Ready-use ammunition', 'rounds', 30, NULL, 9810),
  (9959, 9102, 1, 'Performance', 'Calibre', 'mm', 155, NULL, 9812),
  (9960, 9102, 2, 'Performance', 'Maximum range', 'km', 40, NULL, 9812),
  (9961, 9102, 3, 'Performance', 'Burst rate of fire', 'rds/min', 6, NULL, 9812),
  (9962, 9102, 4, 'Mobility', 'Weight in action', 't', 28, NULL, 9812),
  (9963, 9102, 5, 'Crew & logistics', 'Crew', 'persons', 3, NULL, 9812),
  (9964, 9102, 6, 'Mobility', 'Into-action time', 's', 30, NULL, 9812),
  (9965, 9102, 7, 'Mobility', 'Road speed', 'km/h', 95, NULL, 9812),
  (9966, 9103, 1, 'Performance', 'Calibre', 'mm', 155, NULL, 9814),
  (9967, 9103, 2, 'Performance', 'Maximum range', 'km', 36, NULL, 9814),
  (9968, 9103, 3, 'Precision', 'Circular error probable', 'm', 38, NULL, 9814),
  (9969, 9103, 4, 'Performance', 'Shell weight', 'kg', 43.5, NULL, 9814),
  (9970, 9103, 5, 'Performance', 'Fuze type', NULL, NULL, 'Point-detonating / proximity', 9814),
  (9971, 9103, 6, 'Performance', 'Propellant', NULL, NULL, 'Modular charge, base bleed', 9814),
  (9972, 9103, 7, 'Crew & logistics', 'Shelf life', 'years', 20, NULL, 9814),
  (9973, 9104, 1, 'Crew & logistics', 'Troops carried', 'persons', 8, NULL, 9816),
  (9974, 9104, 2, 'Mobility', 'Combat weight', 't', 18.5, NULL, 9816),
  (9975, 9104, 3, 'Mobility', 'Top speed', 'km/h', 100, NULL, 9816),
  (9976, 9104, 4, 'Mobility', 'Operational range', 'km', 600, NULL, 9816),
  (9977, 9104, 5, 'Mobility', 'Engine power', 'kW', 420, NULL, 9816),
  (9978, 9104, 6, 'Protection', 'Protection level', NULL, NULL, 'STANAG 4569 Level 3', 9816),
  (9979, 9104, 7, 'Mobility', 'Amphibious', NULL, NULL, 'No', 9816),
  (9980, 9105, 1, 'Performance', 'Calibre', NULL, NULL, '5.56x45 mm NATO', 9818),
  (9981, 9105, 2, 'Performance', 'Weight (unloaded)', 'kg', 3.2, NULL, 9818),
  (9982, 9105, 3, 'Performance', 'Effective range', 'm', 450, NULL, 9818),
  (9983, 9105, 4, 'Performance', 'Cyclic rate of fire', 'rpm', 750, NULL, 9818),
  (9984, 9105, 5, 'Performance', 'Magazine capacity', 'rounds', 30, NULL, 9818),
  (9985, 9105, 6, 'Performance', 'Barrel length', 'mm', 368, NULL, 9818),
  (9986, 9106, 1, 'Performance', 'Interception range', 'km', 8, NULL, 9820),
  (9987, 9106, 2, 'Performance', 'Maximum speed', 'km/h', 160, NULL, 9820),
  (9988, 9106, 3, 'Performance', 'Endurance', 'min', 25, NULL, 9820),
  (9989, 9106, 4, 'Performance', 'Warhead mass', 'kg', 0.9, NULL, 9820),
  (9990, 9106, 5, 'Sensors & guidance', 'Radar detection cue range', 'km', 15, NULL, 9820),
  (9991, 9106, 6, 'Sensors & guidance', 'Guidance', NULL, NULL, 'Radar cue + electro-optical terminal', 9820);

-- Programmes an Aurora product takes part in (Products > Aurora product > Programmes).
INSERT INTO staging.client_product_program
  (program_id, client_product_id, program_name, program_type, owner, start_date, end_date, status, description) VALUES
  (9971, 9101, 'Indian Army Towed Gun System (TEST)', 'Tender', 'Indian MoD (TEST)', '2025-09-01', '2027-12-31', 'Bid submitted', 'Aurora Gun 155 offered for 400 towed guns.'),
  (9972, 9101, 'Romanian Gun Trials (TEST)', 'Trials', 'Romanian MoD (TEST)', '2026-11-01', '2027-03-31', 'Planned', 'User trials at the Romanian test range.'),
  (9973, 9102, 'Mounted Gun Evaluation (TEST)', 'Evaluation', 'Indian MoD (TEST)', '2026-03-01', '2026-12-31', 'In progress', 'Field evaluation of Aurora Mounted Gun on the 8x8 truck.'),
  (9974, 9103, 'Shell Production Ramp-Up (TEST)', 'Production', 'Aurora Defence (TEST)', '2026-01-01', '2027-06-30', 'In progress', 'Doubling Aurora Shell 155 output at Pune-Test.'),
  (9975, 9104, 'APC Series Production Batch 1 (TEST)', 'Production', 'Indian MoD (TEST)', '2025-10-01', '2027-09-30', 'In progress', 'First 120 Aurora APC vehicles.'),
  (9976, 9105, 'Carbine Infantry Trials (TEST)', 'Trials', 'Indian MoD (TEST)', '2026-02-01', '2026-11-30', 'In progress', 'Infantry trials of Aurora Carbine.'),
  (9977, 9106, 'Interceptor Drone Pre-Series (TEST)', 'Development', 'Aurora Defence (TEST)', '2026-04-01', '2027-03-31', 'In progress', 'Pre-series build of 20 interceptor drones.');

-- Aurora's own partners (Partnerships page > Aurora partners list). relationship_confidence: official / corroborated / single_source.
INSERT INTO staging.client_partner
  (client_partner_id, client_id, partner_name, legal_name, partner_type, country, region, relationship_confidence, relationship_scope, relationship_start_date, relationship_status, strategic_role, source_id, created_at, updated_at) VALUES
  (9201, 9001, 'Nordic Optics (TEST)', 'Nordic Optics AS (TEST)', 'Technology partner', 'Norway', 'Europe', 'official', 'Fire-control optics and gun sights', '2024-03-01', 'Active', 'Second-source supplier of fire-control optics.', 9850, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9202, 9001, 'Vikram Forgings (TEST)', 'Vikram Forgings Pvt Ltd (TEST)', 'Supplier', 'India', 'South Asia', 'official', 'Forged barrel blanks', '2022-08-15', 'Active', 'Domestic source of barrel steel blanks.', 9852, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9203, 9001, 'Helios Propellants (TEST)', 'Helios Propellants Pvt Ltd (TEST)', 'Supplier', 'India', 'South Asia', 'corroborated', 'Modular propellant charges', '2023-05-01', 'Active', 'Primary source of 155 mm propellant charges.', 9853, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9204, 9001, 'Delta Armour Works (TEST)', 'Delta Armour Works Ltd (TEST)', 'Joint venture', 'India', 'South Asia', 'official', 'Armour plate and hull assemblies', '2024-11-01', 'Active', 'Joint venture for APC hulls.', 9855, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9205, 9001, 'Sagar Electronics (TEST)', 'Sagar Electronics Pvt Ltd (TEST)', 'Technology partner', 'India', 'South Asia', 'corroborated', 'Radar and fire-control electronics', '2025-04-01', 'Active', 'Co-developer of interceptor drone radar cue.', 9856, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00'),
  (9206, 9001, 'Orion Logistics Group (TEST)', 'Orion Logistics Group FZE (TEST)', 'Other', 'United Arab Emirates', 'Middle East', 'single_source', 'Export distribution and logistics', '2026-09-01', 'Negotiating', 'Prospective distribution partner for Gulf exports.', 9858, '2026-01-12 09:00:00+00', '2026-10-02 09:00:00+00');

-- The agreements behind each Aurora partner (Partnerships > Aurora partner > relationships). competitor_overlap = the partner also works with a competitor.
INSERT INTO staging.client_partner_relationship
  (relationship_id, client_partner_id, relationship_type, category, description, territory, start_date, end_date, status, competitor_overlap, kssl_read, source_id) VALUES
  (9231, 9201, 'Supply agreement', 'Procurement', 'Supply of fire-control optics for Aurora guns.', 'Worldwide', '2024-03-01', '2027-02-28', 'Active', true, 'Nordic Optics also supplies Borealis; protect delivery slots.', 9850),
  (9232, 9201, 'Technology licence', 'Technology', 'Licence for stabilised sight software.', 'India', '2024-06-01', NULL, 'Active', true, 'Licence is non-exclusive; Borealis could use the same software.', 9851),
  (9233, 9202, 'Supply agreement', 'Procurement', 'Barrel blank supply for Aurora Gun 155.', 'India', '2022-08-15', '2028-08-14', 'Active', false, 'Sole domestic source; keep a second source warm.', 9852),
  (9234, 9203, 'Supply agreement', 'Procurement', 'Modular charge supply for Aurora Shell 155.', 'India', '2023-05-01', '2027-04-30', 'Active', true, 'Helios also supplies Halcyon; capacity could be shared.', 9853),
  (9235, 9204, 'Joint venture', 'Industrial', 'Joint venture producing hull assemblies for Aurora APC.', 'India', '2024-11-01', NULL, 'Active', true, 'Delta also supplies Meridian W8 parts; confidentiality clause in place.', 9855),
  (9236, 9205, 'Co-development', 'Technology', 'Radar cue module for Aurora Interceptor Drone.', 'India', '2025-04-01', '2027-03-31', 'Active', true, 'Sagar also supplies Tessera; watch for exclusivity pressure.', 9856),
  (9237, 9205, 'Supply agreement', 'Procurement', 'Fire-control electronics for Aurora Mounted Gun.', 'India', '2025-09-01', '2028-08-31', 'Active', true, 'Same overlap risk as the radar module.', 9857),
  (9238, 9206, 'Distribution agreement', 'Commercial', 'Draft distribution agreement for Gulf exports.', 'Gulf states', '2026-09-01', NULL, 'Under negotiation', false, 'Opens Gulf access without a local office.', 9858);

-- Which Aurora products each partner supplies or co-develops (Partnerships > Aurora partner > products).
INSERT INTO staging.client_partner_product
  (partner_product_id, client_partner_id, client_product_id, activity_type, market, scope, status, source_id) VALUES
  (9240, 9201, 9101, 'Supplies', 'Worldwide', 'Fire-control optics for Aurora Gun 155', 'Active', 9850),
  (9241, 9201, 9102, 'Supplies', 'India', 'Sights for Aurora Mounted Gun', 'Active', 9851),
  (9242, 9202, 9101, 'Supplies', 'India', 'Barrel blanks for Aurora Gun 155', 'Active', 9852),
  (9243, 9203, 9103, 'Supplies', 'India', 'Modular charges for Aurora Shell 155', 'Active', 9853),
  (9244, 9204, 9104, 'Co-produces', 'India', 'Hull assemblies for Aurora APC', 'Active', 9855),
  (9245, 9205, 9106, 'Co-develops', 'India', 'Radar cue module for Aurora Interceptor Drone', 'Active', 9856),
  (9246, 9205, 9102, 'Supplies', 'India', 'Fire-control electronics for Aurora Mounted Gun', 'Active', 9857),
  (9247, 9206, 9105, 'Distributes', 'Gulf states', 'Gulf distribution of Aurora Carbine (draft)', 'Negotiating', 9858);

-- Documents behind each Aurora partner relationship (Partnerships > Aurora partner > sources).
INSERT INTO staging.client_partner_source
  (source_id, client_partner_id, relationship_id, source_label, source_type, source_url, source_note, confidence, as_of_date) VALUES
  (9850, 9201, 9231, 'Nordic Optics supply agreement summary (TEST)', 'company', 'https://aurora-defence.example.com/partners/nordic-optics/agreement', 'Aurora partner register entry', 'official', '2026-03-01'),
  (9851, 9201, 9232, 'Nordic Optics licence note (TEST)', 'company', 'https://aurora-defence.example.com/partners/nordic-optics/licence', 'Licence summary', 'official', '2026-03-01'),
  (9852, 9202, 9233, 'Vikram Forgings supplier profile (TEST)', 'company', 'https://aurora-defence.example.com/partners/vikram-forgings', 'Supplier profile', 'official', '2026-02-10'),
  (9853, 9203, 9234, 'Helios Propellants contract notice (TEST)', 'news', 'https://news.example.com/helios-aurora-contract', 'Trade press report', 'corroborated', '2026-05-01'),
  (9854, 9203, NULL, 'Helios Propellants plant visit note (TEST)', 'news', 'https://news.example.com/helios-plant-visit', 'Trade press report', 'corroborated', '2026-07-12'),
  (9855, 9204, 9235, 'Delta Armour joint venture announcement (TEST)', 'company', 'https://aurora-defence.example.com/partners/delta-armour-jv', 'Joint venture announcement', 'official', '2024-11-01'),
  (9856, 9205, 9236, 'Sagar Electronics co-development note (TEST)', 'news', 'https://news.example.com/sagar-aurora-radar', 'Trade press report', 'corroborated', '2025-04-10'),
  (9857, 9205, 9237, 'Sagar Electronics supply note (TEST)', 'company', 'https://aurora-defence.example.com/partners/sagar/supply', 'Aurora partner register entry', 'official', '2025-09-01'),
  (9858, 9206, 9238, 'Orion Logistics draft agreement note (TEST)', 'news', 'https://news.example.com/orion-aurora-gulf', 'Single trade report', 'single_source', '2026-09-01');

COMMIT;
