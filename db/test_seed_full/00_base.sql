-- 00_base.sql  (part A)  Shared base rows every other file refers to. FICTIONAL, obviously test data.
-- ID contract (do not change): client 9001; technology_pillar 1; technology_category 1-6;
-- competitors c0ffee00-0000-4000-8000-00000000000N (N = 1..5); client products 9101-9106.
-- Tables: staging.client_account, staging.competitive_competitor, staging.technology_pillar,
--         staging.technology_category, staging.technology_category_ui_label,
--         staging_ui.technology_category, staging_ui.technology_category_ui_label.
-- staging.country_reference is filled by the database setup and is not touched here.
BEGIN;

DELETE FROM staging_ui.technology_category_ui_label;
DELETE FROM staging_ui.technology_category;
DELETE FROM staging.technology_category_ui_label;
DELETE FROM staging.technology_category;
DELETE FROM staging.technology_pillar;
DELETE FROM staging.competitive_competitor;
DELETE FROM staging.client_account;

-- The client (the company the dashboard is built for). Shown in the header, Products "client" side, Evaluation anchor.
INSERT INTO staging.client_account
  (client_id, client_name, brand_name, legal_name, headquarters, industry_sector, country, account_status, strategic_positioning, created_at, updated_at) VALUES
  (9001, 'Aurora Defence (TEST)', 'Aurora (TEST)', 'Aurora Defence Systems Ltd (TEST)', 'Pune, India', 'Defence', 'India', 'active',
   'Land-systems house building 155 mm artillery, ammunition, armoured vehicles and small arms for domestic and export customers (TEST DATA).',
   '2026-01-05 09:00:00+00', '2026-10-01 09:00:00+00');

-- The five competitors. Profile page (Competitors list, header chips, size/revenue), Products sidebar filters (country, revenue tier),
-- Overview threat dots. strategic_positioning and parallax_read are stored but hidden on the UI by design.
INSERT INTO staging.competitive_competitor
  (competitor_id, display_name, short_name, legal_name, headquarters, origin_country, industry_sector, employee_count, annual_revenue, revenue_currency, revenue_tier, starting_year, global_locations, strategic_positioning, parallax_read, threat_level) VALUES
  ('c0ffee00-0000-4000-8000-000000000001', 'Borealis Arms (TEST)',        'Borealis', 'Borealis Arms AS (TEST)',            'Fjordvik, Norway',           'Norway',        'Defence - land and naval systems',                  6200,  2850,  'USD', 'USD 1-5 bn',   1968, 'Norway; Sweden; Poland; India; United States',
     'Premium towed and mounted guns and precision munitions sold to NATO customers (TEST DATA).',
     'Borealis is expanding gun production capacity in Poland; direct overlap with Aurora artillery in export tenders (TEST DATA).', 'threat'),
  ('c0ffee00-0000-4000-8000-000000000002', 'Cobalt Dynamics (TEST)',      'Cobalt',   'Cobalt Dynamics Inc (TEST)',         'Redstone Bay, United States', 'United States', 'Defence - armoured vehicles and unmanned systems', 18500, 7400,  'USD', 'USD 5-10 bn',  1952, 'United States; Canada; United Kingdom; Saudi Arabia; Australia',
     'Large integrator of armoured vehicles and loitering munitions with a broad export footprint (TEST DATA).',
     'Cobalt competes mainly in vehicles and counter-UAS; indirect pressure on Aurora APC (TEST DATA).', 'watch'),
  ('c0ffee00-0000-4000-8000-000000000003', 'Halcyon Land Systems (TEST)', 'Halcyon',  'Halcyon Land Systems Co Ltd (TEST)', 'Changwon-Test, South Korea',  'South Korea',   'Defence - self-propelled artillery and ammunition', 9300,  4100,  'USD', 'USD 1-5 bn',   1977, 'South Korea; Poland; Romania; Egypt; India',
     'Fast-delivery self-propelled howitzers and 155 mm ammunition aimed at urgent buyers (TEST DATA).',
     'Halcyon is winning on delivery speed and price; strongest threat to Aurora Gun 155 in Eastern Europe (TEST DATA).', 'threat'),
  ('c0ffee00-0000-4000-8000-000000000004', 'Meridian Ordnance (TEST)',    'Meridian', 'Meridian Ordnance SA (TEST)',        'Valmont-sur-Test, France',   'France',        'Defence - ammunition and wheeled vehicles',         4800,  1650,  'EUR', 'EUR 1-5 bn',   1946, 'France; Belgium; United Arab Emirates; Morocco',
     'Ammunition and wheeled armoured vehicle maker focused on francophone and Gulf markets (TEST DATA).',
     'Meridian is strong in Gulf ammunition supply but weak in India; low pressure on Aurora (TEST DATA).', 'fav'),
  ('c0ffee00-0000-4000-8000-000000000005', 'Tessera Aerospace (TEST)',    'Tessera',  'Tessera Aerospace Pvt Ltd (TEST)',   'Bengaluru-Test, India',      'India',         'Defence - missiles, drones and air defence',        2700,  38000, 'INR', 'INR 25-50 bn', 1999, 'India; United Arab Emirates; Armenia',
     'Domestic missile and drone company scaling counter-UAS interceptors for the Indian forces (TEST DATA).',
     'Tessera is a domestic rival for drone and interceptor orders; watch for MoD fast-track approvals (TEST DATA).', 'watch');

-- The Technology pillar (one row; the pillar title on the Technology page).
INSERT INTO staging.technology_pillar
  (pillar_id, pillar_code, pillar_name, client_name, is_active, created_at, updated_at) VALUES
  (1, 'technology', 'Technology', 'Aurora Defence (TEST)', true, '2026-01-05 09:00:00+00', '2026-10-01 09:00:00+00');

-- The six technology categories (tabs on Technology; category chips on Products / Evaluation / Tenders).
INSERT INTO staging.technology_category
  (category_id, category_code, category_name, canonical_name, category_description, category_number, display_order, innovation_count, is_active, tab_number) VALUES
  (1, 'artillery',            'Artillery',              'Artillery',              'Towed, mounted and self-propelled guns and howitzers (TEST DATA).',                 1, 1, 3, true, 1),
  (2, 'ammunition',           'Ammunition',             'Ammunition',             'Shells, charges, fuzes and guided munitions (TEST DATA).',                          2, 2, 3, true, 2),
  (3, 'armoured-vehicles',    'Armoured Vehicles',      'Armoured Vehicles',      'Protected mobility: APCs, infantry fighting vehicles and light tanks (TEST DATA).', 3, 3, 3, true, 3),
  (4, 'small-arms',           'Small Arms',             'Small Arms',             'Rifles, carbines, machine guns and sights (TEST DATA).',                            4, 4, 2, true, 4),
  (5, 'unmanned-counter-uas', 'Unmanned & Counter-UAS', 'Unmanned & Counter-UAS', 'Drones, loitering munitions and systems that defeat them (TEST DATA).',             5, 5, 3, true, 5),
  (6, 'missiles-air-defence', 'Missiles & Air Defence', 'Missiles & Air Defence', 'Short- and medium-range missiles and ground-based air defence (TEST DATA).',        6, 6, 2, true, 6);

-- Display labels of the categories (Technology tab names).
INSERT INTO staging.technology_category_ui_label
  (category_label_id, category_id, database_category_id, label_text, locale, short_label, sort_order, tab_number, ui_name) VALUES
  (1, 1, 'artillery',            'Artillery',              'en', 'Artillery',  1, 1, 'Artillery'),
  (2, 2, 'ammunition',           'Ammunition',             'en', 'Ammo',       2, 2, 'Ammunition'),
  (3, 3, 'armoured-vehicles',    'Armoured Vehicles',      'en', 'Armour',     3, 3, 'Armoured Vehicles'),
  (4, 4, 'small-arms',           'Small Arms',             'en', 'Small arms', 4, 4, 'Small Arms'),
  (5, 5, 'unmanned-counter-uas', 'Unmanned & Counter-UAS', 'en', 'Drones',     5, 5, 'Unmanned & Counter-UAS'),
  (6, 6, 'missiles-air-defence', 'Missiles & Air Defence', 'en', 'Missiles',   6, 6, 'Missiles & Air Defence');

-- UI mirror of the categories (what the Technology page tab bar reads; category_id is text here).
INSERT INTO staging_ui.technology_category
  (category_id, category_name, category_description, display_order, innovation_count, tab_number) VALUES
  ('1', 'Artillery',              'Towed, mounted and self-propelled guns and howitzers (TEST DATA).',                 1, 3, 1),
  ('2', 'Ammunition',             'Shells, charges, fuzes and guided munitions (TEST DATA).',                          2, 3, 2),
  ('3', 'Armoured Vehicles',      'Protected mobility: APCs, infantry fighting vehicles and light tanks (TEST DATA).', 3, 3, 3),
  ('4', 'Small Arms',             'Rifles, carbines, machine guns and sights (TEST DATA).',                            4, 2, 4),
  ('5', 'Unmanned & Counter-UAS', 'Drones, loitering munitions and systems that defeat them (TEST DATA).',             5, 3, 5),
  ('6', 'Missiles & Air Defence', 'Short- and medium-range missiles and ground-based air defence (TEST DATA).',        6, 2, 6);

INSERT INTO staging_ui.technology_category_ui_label
  (database_category_id, tab_number, ui_name) VALUES
  ('artillery',            1, 'Artillery'),
  ('ammunition',           2, 'Ammunition'),
  ('armoured-vehicles',    3, 'Armoured Vehicles'),
  ('small-arms',           4, 'Small Arms'),
  ('unmanned-counter-uas', 5, 'Unmanned & Counter-UAS'),
  ('missiles-air-defence', 6, 'Missiles & Air Defence');

COMMIT;
