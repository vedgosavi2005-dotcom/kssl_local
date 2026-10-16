-- Group D test rows: Market (tenders, top opportunity, opportunities, global requirements) and
-- Technology innovations. Fictional data only; example.test URLs. Needs a_base.sql (client 1,
-- technology_category 1-3, technology_pillar 1). Dates are relative to the day the DB is built.

-- ------------------------------------------------------------------ tenders
-- 101 open (closes in 12 days) | 102 closing (4 days) | 103 awarded | 104 closed | 105 open, no category/date | 106 open, no fit
INSERT INTO staging.market_tender
 (tender_id, title, title_localized, tender_number, notice_reference, issuer_display, buyer_name, buyer_organization_id,
  country_code, country_name, category_id, category_text, description, published_date, closing_date, deadline_text,
  days_remaining, is_live, value_text, value_amount, value_currency, expected_revenue_text, quantity, quantity_unit,
  lean_code, lean_text, kssl_fit, kssl_model, rank_position, source_url, url_kind, status,
  submission_method, registration_requirement, local_presence_requirement, frequency, latest_milestone, created_at, updated_at)
VALUES
 (101, '155 mm towed howitzer, 40 guns', NULL, 'EXD-2026-0101', 'NR-0101', 'Ministry of Defence, Exampleland', 'Ministry of Defence, Exampleland', 9001,
  'EX', 'Exampleland', 1, 'Artillery', 'Supply of forty 155 mm / 39 cal towed howitzers with 5 years of spares and training.',
  current_date - 20, current_date + 12, 'Closes in 12 days', 12, true, 'USD 180 M', 180000000, 'USD', 'INR 640 cr over 5 years', 40, 'guns',
  'go', 'Strong match to the KSSL towed howitzer line; offsets welcome.', 'strong', 'KSSL Towed 155', 1,
  'https://tenders.example.test/notice/101', 'notice', 'open',
  'e-bid via portal', 'Vendor registration required', 'Local office needed', 'one-off', 'Pre-bid meeting held', now(), now()),
 (102, 'Artillery fuzes, multi-option, 120 000 units', NULL, 'NWA-2026-0102', 'NR-0102', 'Northwind Armed Forces Procurement', 'Northwind Armed Forces Procurement', 9002,
  'NW', 'Northland', 2, 'Ammunition', 'Annual framework for multi-option fuzes compatible with 155 mm rounds.',
  current_date - 40, current_date + 4, 'Closes in 4 days', 4, true, 'EUR 22 M', 22000000, 'EUR', 'INR 90 cr', 120000, 'units',
  'maybe', 'Worth qualifying; local presence is a gap.', 'partial', 'KSSL Fuze Family', 2,
  'https://portal.example.test/northwind/102', 'portal', 'closing',
  'sealed bid', NULL, NULL, 'annual', NULL, now(), now()),
 (103, 'Armoured personnel carriers, 60 units', NULL, 'TRV-2026-0103', 'NR-0103', 'Tarvonia Defence Agency', 'Tarvonia Defence Agency', 9003,
  'TV', 'Tarvonia', 3, 'Armoured Vehicles', 'Contract for sixty 8x8 armoured personnel carriers; awarded to a domestic prime.',
  current_date - 120, current_date - 60, 'Awarded', NULL, false, 'EUR 95 M', 95000000, 'EUR', NULL, 60, 'vehicles',
  'pass', 'Concluded; no bid possible.', 'weak', NULL, 3,
  'https://awards.example.test/tarvonia/103', 'award', 'awarded',
  NULL, NULL, NULL, 'one-off', 'Contract signed', now(), now()),
 (104, 'Training ammunition, 30 mm', NULL, 'EXD-2026-0104', 'NR-0104', 'Ministry of Defence, Exampleland', 'Ministry of Defence, Exampleland', 9001,
  'EX', 'Exampleland', 2, 'Ammunition', '30 mm training rounds, 2 million units.',
  current_date - 90, current_date - 30, 'Closed', NULL, false, 'USD 12 M', 12000000, 'USD', NULL, 2000000, 'rounds',
  'closed', 'Deadline passed.', NULL, NULL, 4,
  'https://tenders.example.test/notice/104', 'notice', 'closed',
  NULL, NULL, NULL, 'one-off', NULL, now(), now()),
 (105, 'Mine-protected utility vehicles', NULL, NULL, NULL, 'Example Border Force', 'Example Border Force', NULL,
  'EX', 'Exampleland', NULL, NULL, 'Notice published without a category or closing date.',
  current_date - 5, NULL, NULL, NULL, true, NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL,
  'https://tenders.example.test/notice/105', 'notice', 'open',
  NULL, NULL, NULL, NULL, NULL, now(), now()),
 (106, 'Self-propelled gun upgrade kits', NULL, 'NWA-2026-0106', 'NR-0106', 'Northwind Armed Forces Procurement', 'Northwind Armed Forces Procurement', 9002,
  'NW', 'Northland', 1, 'Artillery', 'Upgrade kits for fielded self-propelled guns.',
  current_date - 10, current_date + 45, 'Closes in 45 days', 45, true, 'EUR 40 M', 40000000, 'EUR', NULL, 24, 'kits',
  NULL, NULL, NULL, NULL, NULL,
  'https://portal.example.test/northwind/106', 'portal', 'open',
  NULL, NULL, NULL, NULL, NULL, now(), now());

INSERT INTO staging.market_tender_closing_window
 (closing_window_id, tender_id, as_of_date, closing_date, published_date, days_remaining, status, is_extension_confirmed, extension_checked_at, milestone_text)
VALUES
 (1, 101, current_date, current_date + 12, current_date - 20, 12, 'open', false, now(), 'Clarification round ends before closing'),
 (2, 102, current_date, current_date + 4, current_date - 40, 4, 'closing', true, now(), 'Deadline extended once by the buyer');

INSERT INTO staging.market_tender_portal
 (portal_id, portal_name, portal_url, country_code, access_status, registration_required, submission_method)
VALUES
 (1, 'Example e-Procurement', 'https://tenders.example.test', 'EX', 'open access', true, 'e-bid'),
 (2, 'Northwind Defence Portal', 'https://portal.example.test', 'NW', 'login needed', true, 'sealed bid');

INSERT INTO staging.market_tender_source
 (source_id, tender_id, is_primary, portal_name, publisher, source_type, source_url, access_note, retrieved_at, status_check_url)
VALUES
 (1, 101, true, 'Example e-Procurement', 'Ministry of Defence, Exampleland', 'tender notice', 'https://tenders.example.test/notice/101', 'Documents downloadable after registration', now(), NULL),
 (2, 101, false, NULL, 'Example Defence Weekly', 'news', 'https://news.example.test/howitzer-tender', NULL, now(), NULL),
 (3, 102, true, 'Northwind Defence Portal', 'Northwind Armed Forces Procurement', 'portal listing', 'https://portal.example.test/northwind/102', NULL, now(), NULL),
 (4, 103, true, NULL, 'Tarvonia Defence Agency', 'award notice', 'https://awards.example.test/tarvonia/103', NULL, now(), NULL);

INSERT INTO staging.market_tender_requirement
 (requirement_id, tender_id, display_order, requirement_type, description, scope_text, requirement_note, equipment_scope, rating_band,
  use_case, quantity, quantity_unit, scope_bullet_label, scope_bullet_value, category_text, source_text)
VALUES
 (1, 101, 1, 'Platform', 'Towed 155 mm / 39 cal howitzer, air-transportable.', 'Forty guns with prime movers.', NULL, 'Gun, sighting, ammunition handling kit', '24-30 km range band',
  'Mountain and desert deployment', 40, 'guns', 'Mobility', 'Towed, 90 s into action', 'Artillery', 'Section 3.1 of the RFP'),
 (2, 101, 2, 'Support', NULL, 'Five years of spares, tools and operator training.', 'Training in country', NULL, NULL,
  NULL, NULL, NULL, 'Warranty', '5 years', NULL, 'Section 4'),
 (3, 102, 1, 'Fuze', 'Multi-option electronic fuze, point detonating and time modes.', NULL, NULL, NULL, NULL,
  NULL, 120000, 'units', NULL, NULL, 'Ammunition', 'Annex B');

INSERT INTO staging.market_tender_fit_assessment
 (assessment_id, tender_id, assessed_at, client_product_id, fit_grade, fit_rank, fit_score, kssl_fit, kssl_fit_rank, kssl_fit_rationale,
  assessment_rationale, kssl_model, kssl_revenue_estimate, match_status, match_summary, revenue_currency, revenue_estimate_min,
  revenue_estimate_max, revenue_estimate_text, revenue_tier)
VALUES
 (1, 101, now(), NULL, 'strong', 1, 88.5, 'strong', 1, 'Calibre, range and mobility meet the RFP; offsets are open to local production.',
  NULL, 'KSSL Towed 155', 'INR 640 cr', 'matched', 'Two KSSL guns match the requirement.', 'INR', 500, 700, 'INR 500-700 cr', 'high'),
 (2, 102, now(), NULL, 'partial', 3, 61, 'partial', 3, 'Fuze family covers the modes; no local presence in Northland.',
  NULL, 'KSSL Fuze Family', 'INR 90 cr', 'partial', NULL, 'INR', 70, 100, 'INR 70-100 cr', 'medium');

INSERT INTO staging.market_tender_product_match (tender_match_id, tender_id, display_order, match_label, fit_grade, fit_percent) VALUES
 (1, 101, 1, 'KSSL Towed 155 Mk II', 'strong', 91),
 (2, 101, 2, 'KSSL Towed 155 Light', 'partial', 68),
 (3, 102, 1, 'KSSL Multi-Option Fuze', 'partial', 63);

INSERT INTO staging.market_tender_product_match_line (match_line_id, tender_match_id, display_order, line_label, line_value) VALUES
 (1, 1, 1, 'Range', '30 km vs 24-30 km required'),
 (2, 1, 2, 'Weight', '6.8 t vs 7.5 t ceiling'),
 (3, 2, 1, 'Range', '27 km, inside the required band'),
 (4, 3, 1, 'Modes', 'PD, delay and time covered');

INSERT INTO staging.market_tender_competitor_fit
 (competitor_fit_id, tender_id, competitor_name, fit_label, competitor_product_display, competitor_products_text, fit_rationale, rank_position, source_id)
VALUES
 (1, 101, 'Example Defence', 'strong', 'EDS Hawk 155', NULL, 'Incumbent supplier with fielded guns in Exampleland.', 1, NULL),
 (2, 101, 'Northwind Arms', 'partial', 'Northwind NW-155T', NULL, 'Competitive on price; longer lead time.', 2, NULL);

-- ------------------------------------------------------------------ opportunities (pre-tender projects)
INSERT INTO staging.market_opportunity
 (opportunity_id, opportunity_kind, title, description, scope_text, buyer_name, contractor_name, location_text, country_code,
  category_id, stage, current_status, latest_milestone, as_of_date, created_at, updated_at)
VALUES
 (201, 'programme', 'Coastal artillery modernisation', 'Programme to replace ageing coastal guns with a modern towed or truck-mounted system.',
  'About 30 guns over eight years.', 'Exampleland Coastal Command', NULL, 'Exampleland, southern coast', 'EX',
  1, 'requirements drafting', 'Armed forces are drafting the staff requirement', 'Staff requirement draft circulated', current_date - 3, now(), now()),
 (202, 'programme', 'Tracked carrier fleet renewal', 'Renewal of a tracked armoured carrier fleet.',
  'Roughly 150 vehicles.', 'Tarvonia Defence Agency', 'Tarvo Systems', 'Tarvonia', 'TV',
  3, 'market survey', NULL, 'Request for information issued', current_date - 8, now(), now());

INSERT INTO staging.market_opportunity_fit_assessment
 (assessment_id, opportunity_id, assessed_at, client_product_id, fit_grade, fit_score, rationale, revenue_currency, revenue_display,
  revenue_estimate_amount, rival_name, client_model_display, rival_product_display)
VALUES
 (1, 201, now(), NULL, 'strong', 82, 'Existing towed guns meet the coastal-defence profile.', 'INR', 'INR 400-500 cr', 450, 'Example Defence', 'KSSL Towed 155', 'EDS Hawk 155'),
 (2, 202, now(), NULL, 'partial', 55, 'KSSL has no tracked carrier; teaming would be needed.', 'INR', 'INR 120-180 cr', 150, 'Tarvo Systems', 'KSSL Armoured Carrier', NULL);

INSERT INTO staging.market_opportunity_source (opportunity_id, source_id, source_title, publisher, source_type, source_url, source_date, confidence) VALUES
 (201, 1, 'Coastal command outlines gun replacement', 'Example Defence Weekly', 'news', 'https://news.example.test/coastal-guns', current_date - 10, 'medium'),
 (202, 2, 'RFI for tracked carriers', 'Tarvonia Defence Agency', 'official notice', 'https://awards.example.test/tarvonia/rfi', current_date - 8, 'high');

INSERT INTO staging.market_opportunity_update (update_id, opportunity_id, update_date, update_type, headline, narrative, confidence, source_id) VALUES
 (1, 201, current_date - 3, 'milestone', 'Staff requirement draft circulated', 'The draft names a 155 mm calibre and a 25 km minimum range.', 'medium', 1),
 (2, 201, current_date - 30, 'news', 'Budget line approved', 'The coastal budget includes a modernisation line.', 'high', NULL);

-- ------------------------------------------------------------------ top opportunity
INSERT INTO staging.market_top_opportunity_tender
 (top_opportunity_tender_id, tender_id, rank_position, decides, kssl_fit, kssl_model, rival_to_beat, revenue_text, status)
VALUES
 (1, 101, 1, 'Award expected in 3 months', 'strong', 'KSSL Towed 155', 'Example Defence', 'INR 500-700 cr', 'evaluation'),
 (2, 102, 2, 'Technical evaluation in 6 weeks', 'partial', 'KSSL Fuze Family', 'Northwind Arms', 'INR 70-100 cr', 'open');

INSERT INTO staging.market_top_opportunity_project
 (top_opportunity_project_id, opportunity_id, rank_position, buyer_name, country_name, where_it_stands, kssl_fit, kssl_model, rival_to_beat, revenue_text)
VALUES
 (1, 201, 1, 'Exampleland Coastal Command', 'Exampleland', 'Staff requirement being drafted', 'strong', 'KSSL Towed 155', 'Example Defence', 'INR 400-500 cr'),
 (2, 202, 2, NULL, 'Tarvonia', NULL, NULL, NULL, NULL, NULL);

INSERT INTO staging.market_next_move
 (next_move_id, sequence, action_text, tender_id, tender_title, opportunity_id, due_date, due_text, days_remaining, priority, status)
VALUES
 (1, 1, 'Submit clarification questions on offsets', 101, '155 mm towed howitzer, 40 guns', NULL, current_date + 2, NULL, 2, 'high', 'open'),
 (2, 2, 'Confirm local fuze partner', 102, 'Artillery fuzes, multi-option, 120 000 units', NULL, NULL, 'before submission', NULL, 'medium', 'open'),
 (3, 3, 'Brief the coastal command on gun range options', NULL, NULL, 201, current_date + 20, NULL, 20, 'low', 'open');

INSERT INTO staging.market_top_opportunity_metric (metric_id, metric_key, metric_label, formatted_value, numeric_value, amount_value, currency_code, note, as_of_date) VALUES
 (1, 'latest_tenders', 'Latest tenders', '4', 4, NULL, NULL, NULL, current_date),
 (2, 'strong_fits', 'Strong fits', '1', 1, NULL, NULL, 'stored grade strong', current_date);

INSERT INTO staging_ui.market_top_opportunity_view
 (view_id, view_code, page_heading, top_tenders_section_label, projects_section_label, next_moves_section_label,
  latest_tenders_metric_label, strong_fits_metric_label, tender_value_metric_label, perceived_opportunities_metric_label,
  top_tenders_description, projects_description, next_moves_description, sort_logic_label)
VALUES
 (1, 'top-opportunity', 'Top opportunity', 'Top tenders', 'Projects to win before they tender', 'Next moves',
  'Latest tenders', 'Strong fits', 'Tender value', 'Perceived opportunities',
  'Tenders in rank order; revenue is the analyst estimate.', 'Programmes with no tender issued yet.', 'Actions in sequence order.', 'rank_position');

INSERT INTO staging.market_filter_option (option_id, filter_type, option_code, option_label, record_count, sort_order, is_active) VALUES
 (1, 'country', 'NW', 'Northland', 2, 1, true),
 (2, 'country', 'EX', 'Exampleland', 3, 2, true),
 (3, 'category', 'ART', 'Artillery', 2, 1, true);

-- ------------------------------------------------------------------ global requirements
INSERT INTO staging.market_global_requirement
 (requirement_id, title, buyer_name, country_name, region, category, value_text, deadline, days_remaining, status, description,
  kssl_fit, kssl_model, strategic_assessment, empty_state_message)
VALUES
 (301, 'Wheeled self-propelled howitzer requirement', 'Northwind Armed Forces', 'Northland', 'Northern Europe', 'Artillery', 'EUR 300 M', 'Request for proposals Q1 next year', 90, 'Requirement stage',
  'Northland seeks a wheeled 155 mm self-propelled howitzer to replace tracked guns.', 'partial', 'KSSL Mounted 155',
  'KSSL has a truck-mounted gun but lacks an on-site service base in Northland.', 'No requirements on record'),
 (302, 'Insensitive-munition shell requirement', 'Tarvonia Defence Agency', 'Tarvonia', 'Northern Europe', 'Ammunition', NULL, NULL, NULL, NULL,
  'Tarvonia plans to move its 155 mm stock to insensitive-munition shells.', NULL, NULL, NULL, 'No requirements on record'),
 (303, 'Light protected patrol vehicle requirement', 'Example Border Force', 'Exampleland', 'South Asia', 'Armoured Vehicles', 'USD 60 M', 'Draft stage', NULL, 'Draft',
  'Border force wants 200 light protected patrol vehicles.', 'strong', 'KSSL Light Patrol', 'The KSSL light patrol vehicle already meets the draft threat level.', 'No requirements on record');

INSERT INTO staging.market_global_requirement_specification (requirement_spec_id, requirement_id, display_order, spec_label, spec_value) VALUES
 (1, 301, 2, 'Mobility', 'Wheeled 8x8'),
 (2, 301, 1, 'Calibre', '155 mm / 52 cal'),
 (3, 302, 1, 'Shell type', 'Insensitive munition'),
 (4, 303, 1, 'Protection', 'STANAG level 2'),
 (5, 303, 2, 'Seats', '6');

INSERT INTO staging.market_global_requirement_source (requirement_source_id, requirement_id, display_order, source_label, source_type, source_url) VALUES
 (1, 301, 1, 'Northland MoD white paper', 'official', 'https://mod.example.test/northland/white-paper'),
 (2, 301, 2, 'Defence Journal article', 'news', 'https://news.example.test/northland-howitzer'),
 (3, 303, 1, 'Border Force draft RFI', 'official', 'https://tenders.example.test/border/rfi');

-- ------------------------------------------------------------------ technology innovations
INSERT INTO staging.technology_company (company_id, display_name, company_type, country_code, is_client) VALUES
 (501, 'Example Defence', 'competitor', 'EX', false),
 (502, 'Northwind Arms', 'competitor', 'NW', false),
 (503, 'Tarvo Labs', 'research', 'TV', false);

INSERT INTO staging.technology_source (source_id, label, url, source_url, publisher, source_type, source_kind, access_status, retrieved_at) VALUES
 (601, 'Example Defence press release', 'https://news.example.test/eds-autoloader', 'https://news.example.test/eds-autoloader', 'Example Defence', 'press release', 'company', 'open', now()),
 (602, 'Northwind technical paper', 'https://papers.example.test/nw-propellant', 'https://papers.example.test/nw-propellant', 'Northwind Arms', 'paper', 'company', 'open', now()),
 (603, 'Tarvo Labs blog', 'https://blog.example.test/tarvo-armour', 'https://blog.example.test/tarvo-armour', 'Tarvo Labs', 'blog', 'company', 'open', now());

INSERT INTO staging.technology_innovation
 (innovation_id, pillar_id, category_id, sequence_no, title, list_description, summary, background_what_it_is, whats_new,
  why_matters_to_kssl, competitive_note, action_note, maturity, client_position, horizon_year, list_status_label, status, created_at, updated_at)
VALUES
 (401, 1, 1, 1, 'Automatic loader for towed howitzers', 'A powered loader that raises the sustained rate of fire of a towed gun.',
  'Short summary of the loader.', 'The loader lifts and rams the shell so the crew does not.', 'First live-fire trial completed this quarter.',
  'KSSL towed guns load by hand; a loader would close the rate-of-fire gap.', 'Example Defence fields a loader on its latest gun.', 'Do not show this action note',
  'dev', 'behind', 2028, 'Emerging', 'active', now(), now()),
 (402, 1, 1, 2, 'Barrel life monitoring sensors', 'Embedded sensors that track barrel wear in real time.',
  NULL, 'Sensors measure bore erosion and report remaining barrel life.', NULL,
  'Lowers life-cycle cost for customers.', NULL, NULL,
  'fielded', 'ahead', NULL, NULL, 'active', now(), now()),
 (403, 1, 2, 1, 'Low-erosion modular propellant', 'A propellant that cuts barrel erosion at high charge.',
  'Summary of the propellant.', 'A new nitrocellulose-free formulation with lower flame temperature.', NULL,
  'Longer barrel life helps KSSL guns and ammunition together.', 'Northwind Arms holds the lead patents.', NULL,
  'lab', 'parity', 2030, 'Research', 'active', now(), now()),
 (404, 1, 3, 1, 'Active protection for light armoured vehicles', 'Hard-kill protection sized for light vehicles.',
  'Summary of the active protection system.', 'Radar-cued countermeasures defeat incoming rounds.', 'First export order announced.',
  'Light vehicles are KSSL''s growth line; protection is a buying criterion.', 'Tarvo Labs leads in compact radar.', NULL,
  'prod', 'behind', 2027, 'Fielded soon', 'active', now(), now()),
 (405, 1, 3, 2, 'Composite hull armour', 'Lightweight composite armour for vehicle hulls.',
  NULL, 'Layered ceramic-composite panels cut hull weight.', NULL,
  NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, 'active', now(), now());

INSERT INTO staging.technology_innovation_status (status_id, innovation_id, maturity_label, position_label, assessment_badge, horizon_text, effective_date) VALUES
 (1, 401, 'In development', 'KSSL behind', 'GAP', '2028 first fielding', current_date),
 (2, 402, 'Fielded', 'KSSL ahead', 'AHEAD', NULL, current_date),
 (3, 403, 'Lab / research', 'KSSL at parity', 'WATCH', 'by 2030', current_date),
 (4, 404, 'In production', 'KSSL behind', 'GAP', 'orders from 2027', current_date);

INSERT INTO staging.technology_innovation_company (innovation_company_id, innovation_id, company_id, display_name, display_order, relationship, relationship_type) VALUES
 (1, 401, 501, NULL, 1, 'developer', 'competitor'),
 (2, 401, 503, 'Tarvo Labs', 2, 'research partner', 'research'),
 (3, 403, 502, NULL, 1, 'patent holder', 'competitor'),
 (4, 404, 503, NULL, 1, 'developer', 'research');

INSERT INTO staging.technology_innovation_source (innovation_source_id, innovation_id, source_id, is_primary, provenance_status) VALUES
 (1, 401, 601, true, 'verified'),
 (2, 403, 602, true, 'verified'),
 (3, 404, 603, true, 'verified');

INSERT INTO staging.technology_innovation_analysis (analysis_id, innovation_id, section_code, section_label, narrative, is_client_assessment, display_order) VALUES
 (1, 401, 'approach', 'Technical approach', 'An electric rammer and a magazine arm feed the breech.', false, 1),
 (2, 401, 'risk', 'Adoption risk for KSSL', 'Integration with the existing breech needs a redesign.', true, 2),
 (3, 404, 'approach', 'Technical approach', 'Radar cues a hard-kill countermeasure within milliseconds.', false, 1);

INSERT INTO staging.technology_category_ui_label (category_label_id, category_id, database_category_id, label_text, locale, short_label, sort_order, tab_number, ui_name) VALUES
 (1, 2, 'ammunition', 'Ammunition and fuzes', 'en', 'Ammo', 2, 2, 'Ammunition and fuzes');
