-- Shared fictional base rows for the v2 test databases (db/make_test_db.sh). Every group's seed
-- references these ids. Fictional companies only; example.test / *.test URLs.
INSERT INTO staging.client_account
  (client_id, client_name, brand_name, legal_name, headquarters, industry_sector, country, account_status, created_at, updated_at)
VALUES (1, 'KSSL', 'KSSL', 'KSSL Limited', 'Sampleton, Maharashtra, India', 'Defence and Aerospace', 'India', 'active', now(), now());

INSERT INTO staging.competitive_competitor
  (competitor_id, display_name, short_name, legal_name, headquarters, origin_country, industry_sector,
   employee_count, annual_revenue, revenue_currency, revenue_tier, starting_year, global_locations, threat_level)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'Example Defence', 'EDS', 'Example Defence Systems Limited',
   'Rivertown, Exampleland', 'Exampleland', 'Defence', 5400, 2650, 'USD', 'USD 1-5 bn', 1974, 'Exampleland; India; UAE', 'threat'),
  ('22222222-2222-2222-2222-222222222222', 'Northwind Arms', 'Northwind', 'Northwind Arms GmbH',
   'Nordhafen, Northland', 'Northland', 'Defence', 3100, 1200, 'EUR', 'EUR 1-5 bn', 1988, 'Northland; Poland', 'watch'),
  ('33333333-3333-3333-3333-333333333333', 'Tarvo Systems', 'Tarvo', 'Tarvo Systems Oy',
   'Lakeport, Tarvonia', 'Tarvonia', 'Defence electronics', 900, 210, 'EUR', 'under EUR 1 bn', 2001, 'Tarvonia', 'watch');

INSERT INTO staging.technology_pillar (pillar_id, pillar_code, pillar_name, client_name, is_active, created_at, updated_at)
VALUES (1, 'technology', 'Technology', 'KSSL', true, now(), now());

INSERT INTO staging.technology_category
  (category_id, category_code, category_name, canonical_name, category_description, category_number,
   display_order, innovation_count, is_active, tab_number)
VALUES
  (1, 'artillery', 'Artillery', 'Artillery', 'Towed, mounted and self-propelled guns and howitzers.', 1, 1, NULL, true, 1),
  (2, 'ammunition', 'Ammunition', 'Ammunition', 'Shells, charges, fuzes and small- and medium-calibre rounds.', 2, 2, NULL, true, 2),
  (3, 'armoured-vehicles', 'Armoured Vehicles', 'Armoured Vehicles', 'Protected mobility and armoured vehicles.', 3, 3, NULL, true, 3);
