-- TEST-ONLY input seed for kssl_staging, so the prompts matchup / tender / tender_assessment /
-- patent_classification have something to read until the client's Excel (product specs) and the
-- tender-portal / patent-office loads replace it. Every value below is stated on a public page that was
-- fetched on 2026-10-16; the page URL is stored with the value. Nothing is estimated. A value that no
-- fetched page states is left out (e.g. ATAGS crew size, Vajra-T elevation/traverse).
-- No Wikipedia / wiki source is used.
-- Run: docker exec -i kssl-pg psql -U kssl -d kssl_staging -v ON_ERROR_STOP=1 < db/test_inputs_seed.sql
-- Idempotent: re-running deletes the rows it owns (fixed ids) and inserts them again.
-- Writes only to staging.client_product_specification/_source, competitive_product(+_specification),
-- market_tender(+_source), competitive_patent_portfolio/_filing.
BEGIN;

-- ---------------------------------------------------------------- 0. competitor products' category
-- The two competitor products were created by the review-copy test fixture with category 'Test'. Both are
-- 155 mm/52-calibre self-propelled howitzers (L&T release 2024-12-23: "a 155 mm, 52-calibre tracked
-- self-propelled artillery platform"; Janes 2024-12-23 for K9 Thunder/Vajra-T), i.e. client category 'Artillery'.
UPDATE staging.competitive_product SET category = 'Artillery', category_filter = 'Artillery'
 WHERE product_name IN ('K9 Vajra-T', 'K9 Thunder') AND category = 'Test';

-- ---------------------------------------------------------------- 1a. client product: ATAGS (client_product_id 101)
DELETE FROM staging.client_product_specification WHERE client_product_id = 101;
DELETE FROM staging.client_product_source WHERE client_product_id = 101 AND source_id BETWEEN 910101 AND 910199;

INSERT INTO staging.client_product_source (source_id, client_product_id, source_label, source_type, source_url, published_date) VALUES
  (910101, 101, 'KSSL - Artillery business page (ATAGS)', 'manufacturer', 'https://www.kssl.in/our-business-artillery', NULL),
  (910102, 101, 'Ajai Shukla, Business Standard / broadcast.in: Indian artillery gun shines in trials', 'defence_press', 'https://www.ajaishukla.com/2016/12/indian-artillery-gun-shines-in-trials.html', '2016-12-28'),
  (910103, 101, 'WION: What is ATAGS and how this indigenous 155mm howitzer is transforming the Indian Army''s artillery', 'defence_press', 'https://www.wionews.com/photos/what-is-atags-and-how-this-155mm-howitzer-is-modernising-the-indian-armys-artillery-1752152396642', '2025-07-10');

INSERT INTO staging.client_product_specification (specification_id, client_product_id, display_order, spec_group, spec_name, value_text, value_numeric, unit, source_id) VALUES
  (910201, 101,  1, 'Gun',         'Gun calibre',                        '155',                      155,  'mm',   910101),  -- KSSL: "155mm/52 Caliber Gun System"
  (910202, 101,  2, 'Gun',         'Barrel length (calibres)',           '52',                       52,   'cal',  910101),  -- same line
  (910203, 101,  3, 'Performance', 'Maximum firing range (HE base-bleed)', '48',                     48,   'km',   910103),  -- WION: "about 48 km using HE-BB shells"
  (910204, 101,  4, 'Performance', 'Range with ERFB ammunition',         '45',                       45,   'km',   910102),  -- Shukla 2016: "range goes up to ... 45 kilometres" with ERFB
  (910205, 101,  5, 'Performance', 'Burst rate of fire',                 '6 rounds in 30 seconds',   NULL, NULL,   910102),  -- Shukla: "six-round burst in just 30 seconds"
  (910206, 101,  6, 'Performance', 'Sustained rate of fire',             '60 rounds in 60 minutes',  NULL, NULL,   910102),  -- Shukla: "60 rounds in 60 minutes in the sustained fire mode"
  (910207, 101,  7, 'Mobility',    'Combat weight',                      '16',                       16,   't',    910102),  -- Shukla 2016: "increased the weight of ATAGS to 16 tonnes" (2016 trial figure)
  (910208, 101,  8, 'Mobility',    'Maximum speed, towed',               '80',                       80,   'km/h', 910101),  -- KSSL: "Max Speed in towing mode 80 kmph"
  (910209, 101,  9, 'Mobility',    'Maximum speed, self-propelled',      '18',                       18,   'km/h', 910101),  -- KSSL: "self-propelled upto 18 kmph"
  (910210, 101, 10, 'Gun',         'Elevation',                          '-5 to 75 degrees',         NULL, NULL,   910101),  -- KSSL: "Elevation: -5 deg to 75 deg"
  (910211, 101, 11, 'Gun',         'Traverse',                           '30 degrees right and left', NULL, NULL,  910101),  -- KSSL: "Traverse: 30 deg Right and Left"
  (910212, 101, 12, 'Deployment',  'Coming into action time (day)',      '2.5',                      2.5,  'min',  910101);  -- KSSL: "2.5 minute in day and 3 minutes at night"

-- ---------------------------------------------------------------- 1a-2. client product: MArG 155 (client_product_id 102)
-- Variant: KSSL's own page lists "MaRG 155mm / 39 cal - BR" (155 mm/39-calibre gun on a 4x4 truck), the variant the
-- press describes in detail; the 45/52-calibre MArG variants have no per-variant spec sheet and are not used here.
-- Left out (no fetched page states it for the /39 variant): maximum road speed, operating range (km), crew count
-- (only "armoured cab for five people"), range with extended-range/base-bleed ammunition.
-- Sources disagree on burst rate (Shukla/armyrecognition/KSSL-quoting press: 3 rounds in 30 s; SPS MAI: 2 in 30 s); 3 is used.
DELETE FROM staging.client_product_specification WHERE client_product_id = 102;
DELETE FROM staging.client_product_source WHERE client_product_id = 102 AND source_id BETWEEN 910301 AND 910399;

INSERT INTO staging.client_product_source (source_id, client_product_id, source_label, source_type, source_url, published_date) VALUES
  (910301, 102, 'KSSL - Artillery business page (MaRG 155mm / 39 cal - BR)', 'manufacturer', 'https://www.kssl.in/our-business-artillery', NULL),
  (910302, 102, 'Ajai Shukla, Broadsword: Rajnath Singh unveils indigenous Multi-terrain Artillery Gun (MArG)', 'defence_press', 'https://www.ajaishukla.com/2021/12/rajnath-singh-unveils-indigenous-multi.html', NULL),
  (910303, 102, 'Army Recognition: Bharat Forge to deliver 155mm wheeled self-propelled howitzers to Armenia', 'defence_press', 'http://www.armyrecognition.com/archives/archives-land-defense/land-defense-2022/bharat-forge-from-india-to-deliver-armenia-155mm-wheeled-self-propelled-howitzers', NULL),
  (910304, 102, 'Frontier India: Armenia buys the 155-mm / 39 self-propelled howitzers, Kalyani MArG 155-BR, from India', 'defence_press', 'https://frontierindia.com/armenia-buys-the-155-mm-39-self-propelled-howitzers-kalyani-marg-155-br-from-india/', NULL);

INSERT INTO staging.client_product_specification (specification_id, client_product_id, display_order, spec_group, spec_name, value_text, value_numeric, unit, source_id) VALUES
  (910401, 102,  1, 'Gun',         'Gun calibre',                           '155',                      155,  'mm',   910301),  -- KSSL: "155mm 39 Caliber Gun System"
  (910402, 102,  2, 'Gun',         'Barrel length (calibres)',              '39',                       39,   'cal',  910301),  -- same line
  (910403, 102,  3, 'Performance', 'Maximum firing range (standard ammunition)', '24',                  24,   'km',   910303),  -- armyrecognition 2022: "maximum firing range of 24 km"
  (910404, 102,  4, 'Performance', 'Burst rate of fire',                    '3 rounds in 30 seconds',   NULL, NULL,   910302),  -- Shukla: "Burst Rate: 3 rounds in 30 sec"
  (910405, 102,  5, 'Performance', 'Intense rate of fire',                  '12 rounds in 3 minutes',   NULL, NULL,   910302),  -- Shukla: "Intense Rate: 12 rounds in 3 min"
  (910406, 102,  6, 'Performance', 'Sustained rate of fire',                '42 rounds in 60 minutes',  NULL, NULL,   910302),  -- Shukla: "Sustained Rate: 42 rounds in 60 min"
  (910407, 102,  7, 'Crew',        'Armoured cab capacity',                 '5',                        5,    'persons', 910304),  -- Frontier India: "armoured cab for five people"
  (910408, 102,  8, 'Mobility',    'Combat weight (all up)',                '18',                       18,   't',    910301),  -- KSSL: "All up weight: 18 Tons"
  (910409, 102,  9, 'Gun',         'Elevation',                             '-2 to 72 degrees',         NULL, NULL,   910301),  -- KSSL: "Elevation: -2 deg to +72 deg"
  (910410, 102, 10, 'Gun',         'Traverse',                              '25 degrees right and left', NULL, NULL,  910301),  -- KSSL: "Traverse: 25 deg to Right and Left"
  (910411, 102, 11, 'Deployment',  'Coming into action time (day)',         '1.5',                      1.5,  'min',  910301),  -- KSSL: "1.5 min in day, and 2 min in night"
  (910412, 102, 12, 'Deployment',  'On-board ammunition',                   '18',                       18,   'rounds', 910301);  -- KSSL: "18 rounds with Zone 5"

-- ---------------------------------------------------------------- 1b. competitor products: K9 Vajra-T and K9 Thunder
DELETE FROM staging.competitive_product_specification
 WHERE product_id IN (SELECT product_id FROM staging.competitive_product WHERE product_name IN ('K9 Vajra-T', 'K9 Thunder'));

-- K9 Vajra-T (Larsen & Toubro). Sources: L&T press release 2024-12-23, Janes 2024-12-23, SP's Land Forces (Lt Gen P.C. Katoch).
INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit, source_url, source_count)
SELECT md5('testseed-vajra-' || v.n)::uuid, p.product_id, v.label, v.val, v.unit, v.url, 1
FROM staging.competitive_product p
JOIN (VALUES
  (1,  'Gun calibre',                          '155',                     'mm',   'https://www.larsentoubro.com/pressreleases/2024-12-23-lt-precision-engineering-systems-wins-major-order-for-k9-vajra-t-artillery-platforms'),
  (2,  'Barrel length (calibres)',             '52',                      'cal',  'https://www.larsentoubro.com/pressreleases/2024-12-23-lt-precision-engineering-systems-wins-major-order-for-k9-vajra-t-artillery-platforms'),
  (3,  'Maximum firing range',                 '38',                      'km',   'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (4,  'Range across projectile types',        '18 to 42',                'km',   'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (5,  'Burst rate of fire',                   '3 rounds in 30 seconds',  NULL,   'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (6,  'Rate of fire over three minutes',      '15 rounds in 3 minutes',  NULL,   'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (7,  'Crew',                                 '5',                       'persons', 'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (8,  'Combat weight',                        '47',                      't',    'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (9,  'Engine power',                         '1000',                    'hp',   'https://www.janes.com/defence-intelligence-insights/defence-news/weapons/lt-signs-contract-to-supply-k9-sphs-for-indian-army'),
  (10, 'Maximum speed',                        'over 60',                 'km/h', 'https://www.spslandforces.com/experts-speak/?id=119'),
  (11, 'Self-propelled travel range',          '450',                     'km',   'https://www.spslandforces.com/experts-speak/?id=119')
) AS v(n, label, val, unit, url) ON true
WHERE p.product_name = 'K9 Vajra-T';

-- K9 Thunder (Hanwha Aerospace). Source: Army Technology project page (2021-08-09), spec table.
INSERT INTO staging.competitive_product_specification (spec_id, product_id, spec_label, spec_value, unit, source_url, source_count)
SELECT md5('testseed-thunder-' || v.n)::uuid, p.product_id, v.label, v.val, v.unit, 'https://www.army-technology.com/projects/thunderselfpropelled/', 1
FROM staging.competitive_product p
JOIN (VALUES
  (1,  'Gun calibre',                          '155',                      'mm'),
  (2,  'Barrel length (calibres)',             '52',                       'cal'),
  (3,  'Maximum firing range (M107 HE)',       '18',                       'km'),
  (4,  'Maximum firing range (rocket-assisted projectile)', '30',          'km'),
  (5,  'Maximum firing range (K307 modular charge)', 'over 40',            'km'),
  (6,  'Burst rate of fire',                   '3 rounds in 15 seconds',   NULL),
  (7,  'Maximum rate of fire',                 '6 to 8 rounds per minute for 3 minutes', NULL),
  (8,  'Sustained rate of fire',               '2 to 3 rounds per minute for 1 hour', NULL),
  (9,  'Crew',                                 '4',                        'persons'),
  (10, 'Combat weight',                        '46.3',                     't'),
  (11, 'Maximum speed',                        '67',                       'km/h'),
  (12, 'Cruising range',                       'over 360',                 'km'),
  (13, 'On-board ammunition',                  '48',                       'rounds'),
  (14, 'Engine power',                         '1000',                     'hp')
) AS v(n, label, val, unit) ON true
WHERE p.product_name = 'K9 Thunder';

-- ---------------------------------------------------------------- 2. tender notices (stubs; prompt `tender` replaces them)
-- Each URL was fetched as HTML text by the runner's own fetch_document. title = page title as on the notice.
DELETE FROM staging.market_tender_source WHERE tender_id IN (9201001, 9201002, 9201003);
DELETE FROM staging.market_tender WHERE tender_id IN (9201001, 9201002, 9201003);

INSERT INTO staging.market_tender (tender_id, title, status, url_kind, source_url, created_at, updated_at) VALUES
  (9201001, 'VR7 ARMOURED SPORTS UTILITY VEHICLES SUPPLY ARRANGEMENT', 'open', 'notice',
   'https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/ws5076037717-doc5474154676', now(), now()),
  (9201002, 'RFI W8703-270075_OPERATIONAL HAND SMOKE GRENADES', 'open', 'notice',
   'https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/ws5932273113-doc5932396100', now(), now()),
  (9201003, 'DGM/2062 105mm Illumination Artillery Shells', 'open', 'notice',
   'https://www.find-tender.service.gov.uk/Notice/012516-2026', now(), now());

INSERT INTO staging.market_tender_source (source_id, tender_id, source_url, is_primary, portal_name) VALUES
  (9202001, 9201001, 'https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/ws5076037717-doc5474154676', true, 'CanadaBuys'),
  (9202002, 9201002, 'https://canadabuys.canada.ca/en/tender-opportunities/tender-notice/ws5932273113-doc5932396100', true, 'CanadaBuys'),
  (9202003, 9201003, 'https://www.find-tender.service.gov.uk/Notice/012516-2026', true, 'Find a Tender');

-- ---------------------------------------------------------------- 3. patents: Hanwha Aerospace
-- 16 real filings whose assignee on the Google Patents page is Hanwha Aerospace Co., Ltd. (Korean name
-- 한화에어로스페이스 주식회사 on KR filings). Title, number, filing date, status and first CPC code are as shown on each
-- patent page https://patents.google.com/patent/<number>/en, fetched 2026-10-16. status: B-kind documents = granted,
-- A-kind documents (published applications) = pending. classification_text is left NULL: prompt patent_classification writes it.
DELETE FROM staging.competitive_patent_classification WHERE portfolio_id = md5('testseed-pf-hanwha-aerospace')::uuid;
DELETE FROM staging.competitive_patent_filing        WHERE portfolio_id = md5('testseed-pf-hanwha-aerospace')::uuid;
DELETE FROM staging.competitive_patent_portfolio     WHERE portfolio_id = md5('testseed-pf-hanwha-aerospace')::uuid;

INSERT INTO staging.competitive_patent_portfolio
  (portfolio_id, competitor_id, lens, filing_count, granted_count, pending_count, grant_status_state, status_note, empty_message, data_source_note, competitor_search_query)
SELECT md5('testseed-pf-hanwha-aerospace')::uuid, c.competitor_id, 'rival', 16, 3, 13, 'known',
       'Status from the document kind on Google Patents: B = granted, A = published application (pending).',
       NULL,
       'TEST sample, not the full portfolio: 16 filings listed on Google Patents (patents.google.com) with assignee Hanwha Aerospace Co., Ltd.; the counts are the real count of the 16 rows loaded.',
       'assignee: Hanwha Aerospace (Google Patents)'
FROM staging.competitive_competitor c WHERE c.display_name = 'Hanwha Aerospace';

INSERT INTO staging.competitive_patent_filing
  (filing_id, portfolio_id, title, publication_number, jurisdiction, filed_date, status, classification_code, classification_text, patent_url)
SELECT md5('testseed-pat-' || v.pn)::uuid, md5('testseed-pf-hanwha-aerospace')::uuid, v.title, v.pn, v.jur, v.filed::date, v.st, v.code, NULL,
       'https://patents.google.com/patent/' || v.pn || '/en'
FROM (VALUES
  ('US20260185810A1', 'Charge separating apparatus',                                                         'US', '2025-07-14', 'pending', 'F42B39/00'),
  ('US12650281B2',    'System and method for improving shooting accuracy and predicting shooting hit rate',  'US', '2024-03-01', 'granted', 'F41G3/00'),
  ('US12347206B2',    'Unmanned combat vehicle and target detection method thereof',                         'US', '2022-06-10', 'granted', 'F41G3/00'),
  ('US20230215185A1', 'Unmanned combat vehicle and target detection method thereof',                         'US', '2022-06-10', 'pending', 'F41G3/00'),
  ('US20250316257A1', 'Apparatus and method for cancelling vehicle noises',                                  'US', '2024-08-29', 'pending', 'G10K11/00'),
  ('US11932391B2',    'Wireless communication relay system using unmanned device and method therefor',       'US', '2020-06-17', 'granted', 'B64C39/00'),
  ('EP4632728A1',     'Apparatus and method for cancelling vehicle noises',                                  'EP', '2024-07-18', 'pending', 'G10K11/00'),
  ('AU2025202684A1',  'Track attachment/detachment apparatus',                                               'AU', '2025-04-16', 'pending', 'B62D55/00'),
  ('KR20250080566A',  'Self-propelled artillery device and method of controlling shooting motion of self-propelled artillery device', 'KR', '2023-11-28', 'pending', 'F41G3/00'),
  ('KR20240047187A',  'Apparatus for feeding charge',                                                        'KR', '2022-10-04', 'pending', 'F41A9/00'),
  ('KR20240111559A',  'Apparatus and method for loading shells',                                             'KR', '2023-01-10', 'pending', 'F41A9/00'),
  ('KR20250070964A',  'Ammunition providing apparatus',                                                      'KR', '2023-11-14', 'pending', 'F41A9/00'),
  ('KR20240127634A',  'Automatic classifying device for a charge and method thereof',                        'KR', '2023-02-16', 'pending', 'F41A9/00'),
  ('KR20250085507A',  'Bore sighting system and method',                                                     'KR', '2023-12-05', 'pending', 'F41G1/00'),
  ('KR20240134513A',  'Device proving shooting accuracy and method thereof',                                 'KR', '2023-03-02', 'pending', 'F41G3/00'),
  ('KR20250057388A',  'Object detection and fire control systems using unmanned aerial vehicles',            'KR', '2023-10-20', 'pending', 'F41H13/00')
) AS v(pn, title, jur, filed, st, code);

COMMIT;
