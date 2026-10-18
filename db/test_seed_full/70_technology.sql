-- 70_technology.sql  (part B)  Every staging.technology_* table except technology_pillar, technology_category and
-- technology_category_ui_label (those three are written by 00_base.sql). FICTIONAL, obviously test data.
-- Pages: Technology > Innovation (technology_innovation*, technology_company, technology_source),
--        Technology > Overview feed + drawer (technology_overview_*), the metric tiles (technology_metric).
-- Reads: technology_pillar 1, technology_category 1-6 (00_base.sql). Allowed values (prompts/FORMAT.md):
--   technology_innovation.client_position behind/parity/ahead; maturity lab/dev/prod/fielded (chip colour);
--   technology_overview_article.classification competitor_advance/adoptable, direction threat/watch/fav.
-- Id ranges: companies 70001-70010, sources 701xx, innovations 71001-71018 (71017, 71018 are 'candidate' rows), overview articles 72001-72010.
-- Innovation counts per category match technology_category.innovation_count in 00_base.sql: Artillery 3, Ammunition 3, Armoured 3, Small Arms 2, Unmanned 3, Missiles 2.
BEGIN;

-- ---------------------------------------------------------------------------------------------------------------- clean (fact_source first, children before parents)
DELETE FROM staging.fact_source WHERE table_name IN ('technology_innovation', 'technology_overview_article', 'technology_overview_fact', 'technology_overview_key_point')
  AND (row_id IN (SELECT innovation_id::text FROM staging.technology_innovation)
    OR row_id IN (SELECT overview_article_id::text FROM staging.technology_overview_article)
    OR row_id IN (SELECT overview_fact_id::text FROM staging.technology_overview_fact)
    OR row_id IN (SELECT key_point_id::text FROM staging.technology_overview_key_point));
DELETE FROM staging.technology_overview_source;
DELETE FROM staging.technology_overview_company;
DELETE FROM staging.technology_overview_key_point;
DELETE FROM staging.technology_overview_fact;
DELETE FROM staging.technology_overview_article;
DELETE FROM staging.technology_innovation_analysis;
DELETE FROM staging.technology_innovation_source;
DELETE FROM staging.technology_innovation_company;
DELETE FROM staging.technology_innovation_status;
DELETE FROM staging.technology_innovation;
DELETE FROM staging.technology_metric;
DELETE FROM staging.technology_source;
DELETE FROM staging.technology_company;

-- ---------------------------------------------------------------------------------------------------------------- technology_company
-- Companies and institutes named on innovations and overview articles ("Driver" chips, company filter). 10 rows.
INSERT INTO staging.technology_company (company_id, display_name, company_type, country_code, is_client) VALUES
  (70001, 'Aurora Defence (TEST)',              'client',     'IN', true),
  (70002, 'Borealis Arms (TEST)',               'competitor', 'NO', false),
  (70003, 'Cobalt Dynamics (TEST)',             'competitor', 'US', false),
  (70004, 'Halcyon Land Systems (TEST)',        'competitor', 'KR', false),
  (70005, 'Meridian Ordnance (TEST)',           'competitor', 'FR', false),
  (70006, 'Tessera Aerospace (TEST)',           'competitor', 'IN', false),
  (70007, 'Fjord Institute of Technology (TEST)', 'research', 'NO', false),
  (70008, 'Redstone University Labs (TEST)',    'research',   'US', false),
  (70009, 'Nova Propellants GmbH (TEST)',       'supplier',   'DE', false),
  (70010, 'Pinewood Optics Ltd (TEST)',         'supplier',   'GB', false);

-- ---------------------------------------------------------------------------------------------------------------- technology_source
-- Documents behind innovations and articles (Sources list of the innovation panel and the article drawer). 34 rows:
-- 70101-70116 one per active innovation, 70117-70118 per candidate, 70119-70128 one per article, 70129-70134 second sources.
INSERT INTO staging.technology_source
  (source_id, label, url, source_url, publisher, source_type, source_kind, access_status, retrieved_at) VALUES
  (70101, 'Borealis loader trial report (TEST)',        'https://news.example.com/borealis-loader-trial',     'https://news.example.com/borealis-loader-trial',     'Borealis Arms (TEST)',       'press release', 'company',  'open',   '2026-10-12 08:00:00+00'),
  (70102, 'Barrel wear sensing white paper (TEST)',     'https://papers.example.org/barrel-wear-sensing',     'https://papers.example.org/barrel-wear-sensing',     'Fjord Institute of Technology (TEST)', 'paper', 'research', 'open', '2026-10-12 08:00:00+00'),
  (70103, '58-calibre barrel announcement (TEST)',      'https://news.example.com/halcyon-58-cal',            'https://news.example.com/halcyon-58-cal',            'Halcyon Land Systems (TEST)', 'press release', 'company', 'open',  '2026-10-12 08:00:00+00'),
  (70104, 'Low-erosion propellant patent note (TEST)',  'https://patents.example.org/low-erosion-propellant', 'https://patents.example.org/low-erosion-propellant', 'Nova Propellants GmbH (TEST)', 'patent', 'patent',   'open',   '2026-10-12 08:00:00+00'),
  (70105, 'IM shell qualification news (TEST)',         'https://news.example.com/meridian-im-shell',         'https://news.example.com/meridian-im-shell',         'Defence Weekly (TEST)',      'news',          'news',     'open',   '2026-10-12 08:00:00+00'),
  (70106, 'Guided kit trial video (TEST)',              'https://news.example.net/guided-155-kit',            'https://news.example.net/guided-155-kit',            'Munitions Quarterly (TEST)', 'news',          'news',     'open',   '2026-10-12 08:00:00+00'),
  (70107, 'Compact APS export order (TEST)',            'https://news.example.com/cobalt-aps-order',          'https://news.example.com/cobalt-aps-order',          'Cobalt Dynamics (TEST)',     'press release', 'company',  'open',   '2026-10-12 08:00:00+00'),
  (70108, 'Composite hull armour data sheet (TEST)',    'https://papers.example.org/composite-hull',          'https://papers.example.org/composite-hull',          'Redstone University Labs (TEST)', 'paper', 'research',  'open',   '2026-10-12 08:00:00+00'),
  (70109, 'Hybrid-electric drive study (TEST)',         'https://papers.example.org/hybrid-drive-study',      'https://papers.example.org/hybrid-drive-study',      'Fjord Institute of Technology (TEST)', 'paper', 'research', 'open', '2026-10-12 08:00:00+00'),
  (70110, 'Smart sight product page (TEST)',            'https://news.example.com/pinewood-smart-sight',      'https://news.example.com/pinewood-smart-sight',      'Pinewood Optics Ltd (TEST)', 'product page',  'company',  'open',   '2026-10-12 08:00:00+00'),
  (70111, 'Polymer-cased 5.56 mm tests (TEST)',         'https://news.example.net/polymer-case-556',          'https://news.example.net/polymer-case-556',          'Small Arms Review (TEST)',   'news',          'news',     'open',   '2026-10-12 08:00:00+00'),
  (70112, 'Interceptor drone demonstration (TEST)',     'https://news.example.com/tessera-interceptor-demo',  'https://news.example.com/tessera-interceptor-demo',  'Tessera Aerospace (TEST)',   'press release', 'company',  'open',   '2026-10-12 08:00:00+00'),
  (70113, 'Fibre-optic FPV drones in the field (TEST)', 'https://news.example.net/fibre-optic-fpv',           'https://news.example.net/fibre-optic-fpv',           'Counter-UAS Journal (TEST)', 'news',          'news',     'open',   '2026-10-12 08:00:00+00'),
  (70114, 'Jammer array trial note (TEST)',             'https://news.example.org/jammer-array-trial',        'https://news.example.org/jammer-array-trial',        'Cobalt Dynamics (TEST)',     'press release', 'company',  'open',   '2026-10-12 08:00:00+00'),
  (70115, 'Imaging IR seeker test report (TEST)',       'https://news.example.com/tessera-iir-seeker',        'https://news.example.com/tessera-iir-seeker',        'Tessera Aerospace (TEST)',   'press release', 'company',  'open',   '2026-10-12 08:00:00+00'),
  (70116, 'Programmable airburst licence (TEST)',       'https://news.example.org/airburst-licence',          'https://news.example.org/airburst-licence',          'Pinewood Optics Ltd (TEST)', 'press release', 'company',  'open',   '2026-10-12 08:00:00+00'),
  (70117, 'Laser counter-drone concept (TEST)',         'https://news.example.net/laser-counter-drone',       'https://news.example.net/laser-counter-drone',       'Counter-UAS Journal (TEST)', 'news',          'news',     'open',   '2026-10-14 08:00:00+00'),
  (70118, 'Additive barrel liner concept (TEST)',       'https://news.example.net/additive-barrel-liner',     'https://news.example.net/additive-barrel-liner',     'Gun Journal (TEST)',         'news',          'news',     'open',   '2026-10-14 08:00:00+00'),
  (70119, 'Halcyon 58-cal SP howitzer fielded (TEST)',  'https://news.example.com/halcyon-sp-58-fielded',     'https://news.example.com/halcyon-sp-58-fielded',     'Defence Weekly (TEST)',      'news',          'news',     'open',   '2026-10-10 08:00:00+00'),
  (70120, 'Meridian qualifies IM 155 mm shell (TEST)',  'https://news.example.com/meridian-im-qualified',     'https://news.example.com/meridian-im-qualified',     'Munitions Quarterly (TEST)', 'news',          'news',     'open',   '2026-10-09 08:00:00+00'),
  (70121, 'Open radar-cueing software released (TEST)', 'https://code.example.org/radar-cueing',              'https://code.example.org/radar-cueing',              'Redstone University Labs (TEST)', 'repository', 'research', 'open', '2026-10-08 08:00:00+00'),
  (70122, 'Cobalt unveils compact APS for 8x8 (TEST)',  'https://news.example.com/cobalt-compact-aps',        'https://news.example.com/cobalt-compact-aps',        'Armour Today (TEST)',        'news',          'news',     'open',   '2026-10-07 08:00:00+00'),
  (70123, 'Polymer-cased ammunition production-ready (TEST)', 'https://news.example.net/polymer-case-ready', 'https://news.example.net/polymer-case-ready',     'Small Arms Review (TEST)',   'news',          'news',     'open',   '2026-10-06 08:00:00+00'),
  (70124, 'Tessera tests 5 km interceptor (TEST)',      'https://news.example.com/tessera-5km-interceptor',   'https://news.example.com/tessera-5km-interceptor',   'Counter-UAS Journal (TEST)', 'news',          'news',     'open',   '2026-10-05 08:00:00+00'),
  (70125, 'Borealis integrates loader on towed gun (TEST)', 'https://news.example.com/borealis-loader-integrated', 'https://news.example.com/borealis-loader-integrated', 'Gun Journal (TEST)',     'news',          'news',     'open',   '2026-10-04 08:00:00+00'),
  (70126, 'Airburst fuze licence offered to Aurora (TEST)', 'https://news.example.org/airburst-offer',        'https://news.example.org/airburst-offer',            'Pinewood Optics Ltd (TEST)', 'press release', 'company',  'open',   '2026-10-03 08:00:00+00'),
  (70127, 'Tessera IIR seeker trial (TEST)',            'https://news.example.com/tessera-seeker-trial',      'https://news.example.com/tessera-seeker-trial',      'Tessera Aerospace (TEST)',   'press release', 'company',  'open',   '2026-10-02 08:00:00+00'),
  (70128, 'Nova offers propellant licence (TEST)',      'https://news.example.org/nova-propellant-licence',   'https://news.example.org/nova-propellant-licence',   'Nova Propellants GmbH (TEST)', 'press release', 'company', 'open',   '2026-10-01 08:00:00+00'),
  (70129, 'Halcyon investor briefing (TEST)',           'https://ir.example.com/halcyon-briefing',            'https://ir.example.com/halcyon-briefing',            'Halcyon Land Systems (TEST)', 'investor note', 'company', 'open',   '2026-10-10 08:00:00+00'),
  (70130, 'Meridian technical brochure (TEST)',         'https://ir.example.com/meridian-brochure',           'https://ir.example.com/meridian-brochure',           'Meridian Ordnance (TEST)',   'brochure',      'company',  'open',   '2026-10-09 08:00:00+00'),
  (70131, 'Cobalt trade-show note (TEST)',              'https://news.example.org/cobalt-show-note',          'https://news.example.org/cobalt-show-note',          'Armour Today (TEST)',        'news',          'news',     'open',   '2026-10-07 08:00:00+00'),
  (70132, 'Tessera trial footage (TEST)',               'https://news.example.net/tessera-trial-footage',     'https://news.example.net/tessera-trial-footage',     'Counter-UAS Journal (TEST)', 'news',          'news',     'login needed', '2026-10-05 08:00:00+00'),
  (70133, 'Borealis annual report (TEST)',              'https://ir.example.com/borealis-annual',             'https://ir.example.com/borealis-annual',             'Borealis Arms (TEST)',       'annual report', 'company',  'open',   '2026-10-04 08:00:00+00'),
  (70134, 'Nova patent family (TEST)',                  'https://patents.example.org/nova-family',            'https://patents.example.org/nova-family',            'Nova Propellants GmbH (TEST)', 'patent',      'patent',   'open',   '2026-10-01 08:00:00+00');

-- ---------------------------------------------------------------------------------------------------------------- technology_innovation
-- The innovation card (Technology > Innovation: list per category tab and the detail panel). 16 active rows (3/3/3/2/3/2 per category) and
-- 2 'candidate' rows (thin discovery rows; the page hides them until innovation_detail fills them).
INSERT INTO staging.technology_innovation
  (innovation_id, pillar_id, category_id, sequence_no, external_id, title, list_description, list_secondary_value, list_status_label, summary,
   background_what_it_is, whats_new, why_matters_to_kssl, competitive_note, action_note, maturity, client_position, assessment_outcome,
   horizon_year, status, created_at, updated_at) VALUES
  (71001, 1, 1, 1, 'test-innovation-71001', 'Automatic loader for towed howitzers (TEST)', 'A powered loader that raises the sustained rate of fire of a towed gun.', 'Rate of fire 8 rpm', 'Emerging',
   'Borealis integrated a powered loader on its towed 155 mm gun.', 'An electric rammer and magazine arm lift and ram the shell so the crew does not.', 'First live-fire trial completed this quarter at 8 rounds per minute.',
   'Aurora towed guns load by hand; a loader would close the sustained rate-of-fire gap in export tenders.', 'Borealis Arms (TEST) fields a loader on its latest towed gun.', 'Internal note: evaluate a loader module with a Pune supplier.',
   'dev', 'behind', 'develop', 2028, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71002, 1, 1, 2, 'test-innovation-71002', 'Barrel wear sensing and life prediction (TEST)', 'Embedded sensors track bore erosion and predict remaining barrel life.', 'Life prediction within 5%', 'Fielded',
   'Barrel sensors report remaining life to the fire-control system.', 'Fibre-optic and acoustic sensors measure bore erosion round by round.', 'Fielded on two export customers; reduces unplanned barrel changes.',
   'Aurora already ships a barrel-life monitor, a selling point against rivals in life-cycle cost.', 'Fjord Institute of Technology (TEST) published the method; no rival fields it yet.', 'Internal note: promote in tenders.',
   'fielded', 'ahead', 'adopt', NULL, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71003, 1, 1, 3, 'test-innovation-71003', 'Extended-range 58-calibre barrel (TEST)', 'A longer barrel that adds range on standard charges.', 'Range +25% at same charge', 'Research',
   'Halcyon announced a 58-calibre barrel for its self-propelled howitzer.', 'A longer, forged barrel with a new chamber raises muzzle velocity for the same charge.', 'Firing trials reached 70 km with base-bleed rounds.',
   'Aurora 52-calibre guns would lose the long-range category in tenders if 58 calibre becomes the norm.', 'Halcyon Land Systems (TEST) leads; Borealis is rumoured to follow.', NULL,
   'lab', 'parity', 'monitor', 2029, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71004, 1, 2, 1, 'test-innovation-71004', 'Low-erosion modular propellant charge (TEST)', 'A propellant that cuts barrel erosion at high charge zones.', 'Erosion -35%', 'Research',
   'Nova Propellants developed a low-flame-temperature modular charge.', 'A new formulation lowers flame temperature and bore erosion at zone 8.', 'Licence offered to selected artillery makers.',
   'Longer barrel life helps Aurora guns and ammunition together.', 'Nova Propellants GmbH (TEST) holds the lead patents.', NULL,
   'lab', 'parity', 'monitor', 2030, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71005, 1, 2, 2, 'test-innovation-71005', 'Insensitive-munition 155 mm fill (TEST)', 'Explosive fills that survive fire and impact without detonating.', 'IM compliance STANAG 4439', 'Qualified',
   'Meridian qualified an insensitive-munition 155 mm shell.', 'A polymer-bonded explosive resists fast and slow cook-off and bullet impact.', 'Qualification completed; first orders from two European buyers.',
   'IM compliance is becoming a tender requirement in Europe; Aurora Shell 155 is not yet qualified.', 'Meridian Ordnance (TEST) is first to qualify; Halcyon follows.', 'Internal note: start IM qualification.',
   'prod', 'behind', 'develop', 2027, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71006, 1, 2, 3, 'test-innovation-71006', 'Guided 155 mm precision kit (TEST)', 'A fuze-replacement kit that adds GPS guidance to unguided shells.', 'CEP under 10 m', 'In development',
   'A guidance kit turns standard 155 mm rounds into precision munitions.', 'Fins and a GPS-inertial unit fit in the fuze well.', 'Test firing hit within 8 m at 35 km.',
   'Precision kits are asked for in new 155 mm frameworks; Aurora has no kit.', 'Borealis Arms (TEST) sells a kit; Halcyon is developing one.', NULL,
   'dev', 'behind', 'develop', 2028, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71007, 1, 3, 1, 'test-innovation-71007', 'Compact active protection system (TEST)', 'Hard-kill protection sized for light and medium armoured vehicles.', 'Defeats RPG and ATGM threats', 'Fielded soon',
   'Cobalt won the first export order for a compact active protection system.', 'Radar-cued countermeasures defeat incoming rockets within milliseconds.', 'First export order announced for an 8x8 fleet.',
   'Light vehicles are a growth line for Aurora; protection is a buying criterion in Brazil and India.', 'Cobalt Dynamics (TEST) leads in compact radar.', NULL,
   'prod', 'behind', 'develop', 2027, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71008, 1, 3, 2, 'test-innovation-71008', 'Composite hull armour (TEST)', 'Lightweight ceramic-composite panels for vehicle hulls.', 'Weight -18%', 'Fielded',
   'Layered ceramic-composite panels cut hull weight.', 'Ceramic tiles bonded to aramid backing stop armour-piercing rounds at lower weight.', 'Data sheet released with ballistic results.',
   'Weight savings allow more payload on the Aurora APC.', 'Redstone University Labs (TEST) published the data; vendors are licensing it.', NULL,
   'fielded', 'parity', 'monitor', NULL, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71009, 1, 3, 3, 'test-innovation-71009', 'Hybrid-electric silent drive (TEST)', 'A diesel-electric drive enabling silent watch and lower fuel use.', 'Silent watch 8 h', 'Research',
   'A study shows hybrid drives for 8x8 vehicles are feasible.', 'Batteries and an electric motor drive the vehicle in silent mode.', 'Prototype demonstrated 8 hours of silent watch.',
   'Silent watch and fuel saving are asked for in new vehicle requirements.', 'Fjord Institute of Technology (TEST) leads research; no vendor fields it.', NULL,
   'lab', 'behind', 'monitor', 2031, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71010, 1, 4, 1, 'test-innovation-71010', 'Smart sight with ballistic computer (TEST)', 'A sight that computes the aim point from range and wind.', 'First-round hit probability +40%', 'Fielded',
   'Pinewood Optics fields a smart sight for carbines.', 'A laser rangefinder and ballistic computer display the aim point in the reticle.', 'New model halves the weight.',
   'Smart sights are standard on new carbine tenders.', 'Pinewood Optics Ltd (TEST) supplies several rivals.', NULL,
   'fielded', 'parity', 'monitor', NULL, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71011, 1, 4, 2, 'test-innovation-71011', 'Polymer-cased 5.56 mm ammunition (TEST)', 'Cartridges with a polymer case that cut ammunition weight by a third.', 'Weight -33%', 'In development',
   'Polymer-cased 5.56 mm ammunition reached production readiness.', 'A polymer case replaces brass, reducing weight and heat transfer.', 'Production line qualified by a supplier.',
   'Aurora Carbine can fire polymer-cased ammunition with a barrel change.', 'Small Arms Review (TEST) reports interest from two buyers.', NULL,
   'dev', 'ahead', 'adopt', 2028, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71012, 1, 5, 1, 'test-innovation-71012', 'Interceptor drones for counter-UAS (TEST)', 'Small drones that hunt and ram or explode near enemy drones.', 'Engagement radius 5 km', 'In development',
   'Tessera demonstrated an interceptor drone with a 5 km radius.', 'A radar-cued drone with electro-optical seeker closes on the target.', 'Demonstration against Group 2 drones succeeded.',
   'Counter-UAS is a priority line; Aurora Interceptor Drone is in trials.', 'Tessera Aerospace (TEST) is the domestic rival in India.', 'Internal note: speed up trials.',
   'dev', 'parity', 'develop', 2027, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71013, 1, 5, 2, 'test-innovation-71013', 'Fibre-optic controlled FPV strike drones (TEST)', 'Drones controlled over a fibre cable, immune to jamming.', 'Range 20 km', 'Fielded',
   'Fibre-optic FPV drones are in the field.', 'A spool of fibre carries the video and control signal.', 'Used at scale by one side in a current conflict.',
   'Jammers do not stop fibre-controlled drones; protection needs hard-kill.', 'Cobalt Dynamics (TEST) sells a counter to them.', NULL,
   'fielded', 'behind', 'monitor', NULL, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71014, 1, 5, 3, 'test-innovation-71014', 'Swarm-resistant jammer array (TEST)', 'A phased jammer array that defeats swarms with directional nulls.', 'Defeats 20-drone swarms', 'Fielded soon',
   'Cobalt tested a jammer array against drone swarms.', 'A phased array steers jamming energy to each drone.', 'Trial defeated a 20-drone swarm.',
   'Swarm defence is a requirement in Freedonia and Gulf counter-UAS tenders.', 'Cobalt Dynamics (TEST) leads; Tessera follows.', NULL,
   'prod', 'behind', 'develop', 2027, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71015, 1, 6, 1, 'test-innovation-71015', 'Imaging infrared seeker for short-range missiles (TEST)', 'A seeker that recognises targets by shape, hard to decoy.', 'Hit probability +25%', 'In development',
   'Tessera trialled an imaging infrared seeker.', 'A focal-plane array and onboard processor classify targets in flight.', 'Seeker trial against decoy flares succeeded.',
   'Aurora has no missile product; the technology affects only partner decisions.', 'Tessera Aerospace (TEST) leads in India.', NULL,
   'dev', 'behind', 'monitor', 2029, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71016, 1, 6, 2, 'test-innovation-71016', 'Programmable airburst for air-defence guns (TEST)', 'A fuze that bursts a shell at a computed point near the target.', 'Burst point accuracy 2 m', 'Fielded soon',
   'Pinewood offered a programmable airburst fuze licence.', 'An inductively set fuze receives the burst time from the fire-control unit.', 'Licence offered to Aurora for its air-defence ammunition.',
   'Allows Aurora ammunition to address low drones.', 'Pinewood Optics Ltd (TEST) offers the licence to several makers.', 'Internal note: respond to licence offer.',
   'prod', 'parity', 'adopt', 2027, 'active', '2026-10-12 08:00:00+00', '2026-10-16 08:00:00+00'),
  (71017, 1, 5, 4, 'test-innovation-71017', 'Directed-energy counter-drone laser (TEST)', NULL, NULL, NULL,
   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'candidate', '2026-10-14 08:00:00+00', '2026-10-14 08:00:00+00'),
  (71018, 1, 1, 4, 'test-innovation-71018', 'Additive-manufactured barrel liner (TEST)', 'Candidate found in news: 3D-printed barrel liner.', NULL, NULL,
   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'candidate', '2026-10-14 08:00:00+00', '2026-10-14 08:00:00+00');

-- ---------------------------------------------------------------------------------------------------------------- technology_innovation_status
-- The status chips of an innovation (maturity, Aurora position, badge, horizon). One per active innovation: 16 rows.
INSERT INTO staging.technology_innovation_status
  (status_id, innovation_id, maturity_label, position_label, assessment_badge, horizon_text, effective_date) VALUES
  (71101, 71001, 'In development', 'Aurora behind',    'GAP',   '2028 first fielding', '2026-10-16'),
  (71102, 71002, 'Fielded',        'Aurora ahead',     'AHEAD', 'Fielded today',       '2026-10-16'),
  (71103, 71003, 'Lab / research', 'Aurora at parity', 'WATCH', 'by 2029',             '2026-10-16'),
  (71104, 71004, 'Lab / research', 'Aurora at parity', 'WATCH', 'by 2030',             '2026-10-16'),
  (71105, 71005, 'In production',  'Aurora behind',    'GAP',   'orders from 2027',    '2026-10-16'),
  (71106, 71006, 'In development', 'Aurora behind',    'GAP',   '2028',                '2026-10-16'),
  (71107, 71007, 'In production',  'Aurora behind',    'GAP',   'orders from 2027',    '2026-10-16'),
  (71108, 71008, 'Fielded',        'Aurora at parity', 'WATCH', 'Fielded today',       '2026-10-16'),
  (71109, 71009, 'Lab / research', 'Aurora behind',    'GAP',   'after 2031',          '2026-10-16'),
  (71110, 71010, 'Fielded',        'Aurora at parity', 'WATCH', 'Fielded today',       '2026-10-16'),
  (71111, 71011, 'In development', 'Aurora ahead',     'AHEAD', '2028',                '2026-10-16'),
  (71112, 71012, 'In development', 'Aurora at parity', 'WATCH', '2027 trials',         '2026-10-16'),
  (71113, 71013, 'Fielded',        'Aurora behind',    'GAP',   'Fielded today',       '2026-10-16'),
  (71114, 71014, 'In production',  'Aurora behind',    'GAP',   'orders from 2027',    '2026-10-16'),
  (71115, 71015, 'In development', 'Aurora behind',    'GAP',   'by 2029',             '2026-10-16'),
  (71116, 71016, 'In production',  'Aurora at parity', 'WATCH', 'licence in 2027',     '2026-10-16');

-- ---------------------------------------------------------------------------------------------------------------- technology_innovation_company
-- Who drives an innovation (the "Driver" line and company chips of the panel). relationship_type: driver / competitor / partner. 32 rows.
INSERT INTO staging.technology_innovation_company
  (innovation_company_id, innovation_id, company_id, display_name, display_order, relationship, relationship_type) VALUES
  (71201, 71001, 70002, 'Borealis Arms (TEST)',               1, 'Developer of the loader',                    'driver'),
  (71202, 71001, 70001, 'Aurora Defence (TEST)',              2, 'Evaluating a loader module',                  'partner'),
  (71203, 71002, 70007, 'Fjord Institute of Technology (TEST)', 1, 'Published the sensing method',              'driver'),
  (71204, 71002, 70001, 'Aurora Defence (TEST)',              2, 'Ships the barrel-life monitor',              'partner'),
  (71205, 71003, 70004, 'Halcyon Land Systems (TEST)',        1, 'Developer of the 58-calibre barrel',         'driver'),
  (71206, 71003, 70002, 'Borealis Arms (TEST)',               2, 'Rumoured follower',                          'competitor'),
  (71207, 71004, 70009, 'Nova Propellants GmbH (TEST)',       1, 'Patent holder',                              'driver'),
  (71208, 71004, 70005, 'Meridian Ordnance (TEST)',           2, 'Possible licensee',                          'competitor'),
  (71209, 71005, 70005, 'Meridian Ordnance (TEST)',           1, 'First to qualify',                           'driver'),
  (71210, 71005, 70004, 'Halcyon Land Systems (TEST)',        2, 'Following with its own IM fill',             'competitor'),
  (71211, 71006, 70002, 'Borealis Arms (TEST)',               1, 'Sells a guidance kit',                       'driver'),
  (71212, 71006, 70004, 'Halcyon Land Systems (TEST)',        2, 'Developing a kit',                           'competitor'),
  (71213, 71007, 70003, 'Cobalt Dynamics (TEST)',             1, 'Developer, first export order',              'driver'),
  (71214, 71007, 70008, 'Redstone University Labs (TEST)',    2, 'Radar research partner',                     'partner'),
  (71215, 71008, 70008, 'Redstone University Labs (TEST)',    1, 'Published ballistic data',                   'driver'),
  (71216, 71008, 70003, 'Cobalt Dynamics (TEST)',             2, 'Licensing the panels',                       'competitor'),
  (71217, 71009, 70007, 'Fjord Institute of Technology (TEST)', 1, 'Leads the research',                      'driver'),
  (71218, 71009, 70003, 'Cobalt Dynamics (TEST)',             2, 'Interested vendor',                          'competitor'),
  (71219, 71010, 70010, 'Pinewood Optics Ltd (TEST)',         1, 'Supplier of the sight',                      'driver'),
  (71220, 71010, 70002, 'Borealis Arms (TEST)',               2, 'Customer of the sight',                      'competitor'),
  (71221, 71011, 70009, 'Nova Propellants GmbH (TEST)',       1, 'Qualified the production line',              'driver'),
  (71222, 71011, 70001, 'Aurora Defence (TEST)',              2, 'Barrel change planned',                      'partner'),
  (71223, 71012, 70006, 'Tessera Aerospace (TEST)',           1, 'Demonstrated the interceptor',               'driver'),
  (71224, 71012, 70001, 'Aurora Defence (TEST)',              2, 'Own interceptor in trials',                  'partner'),
  (71225, 71013, 70003, 'Cobalt Dynamics (TEST)',             1, 'Sells a counter system',                     'driver'),
  (71226, 71013, 70008, 'Redstone University Labs (TEST)',    2, 'Research on fibre links',                    'partner'),
  (71227, 71014, 70003, 'Cobalt Dynamics (TEST)',             1, 'Developer of the jammer array',              'driver'),
  (71228, 71014, 70006, 'Tessera Aerospace (TEST)',           2, 'Following',                                  'competitor'),
  (71229, 71015, 70006, 'Tessera Aerospace (TEST)',           1, 'Developer of the seeker',                    'driver'),
  (71230, 71015, 70008, 'Redstone University Labs (TEST)',    2, 'Seeker algorithm research',                  'partner'),
  (71231, 71016, 70010, 'Pinewood Optics Ltd (TEST)',         1, 'Licensor of the fuze',                       'driver'),
  (71232, 71016, 70001, 'Aurora Defence (TEST)',              2, 'Licence offered',                            'partner');

-- ---------------------------------------------------------------------------------------------------------------- technology_innovation_source
-- Links innovation -> technology_source (primary first). 22 rows. provenance_status: verified / single_source / unverified.
INSERT INTO staging.technology_innovation_source
  (innovation_source_id, innovation_id, source_id, is_primary, provenance_status) VALUES
  (71301, 71001, 70101, true,  'verified'),
  (71302, 71002, 70102, true,  'verified'),
  (71303, 71003, 70103, true,  'verified'),
  (71304, 71003, 70129, false, 'single_source'),
  (71305, 71004, 70104, true,  'verified'),
  (71306, 71004, 70134, false, 'verified'),
  (71307, 71005, 70105, true,  'verified'),
  (71308, 71005, 70130, false, 'verified'),
  (71309, 71006, 70106, true,  'single_source'),
  (71310, 71007, 70107, true,  'verified'),
  (71311, 71007, 70131, false, 'verified'),
  (71312, 71008, 70108, true,  'verified'),
  (71313, 71009, 70109, true,  'verified'),
  (71314, 71010, 70110, true,  'verified'),
  (71315, 71011, 70111, true,  'single_source'),
  (71316, 71012, 70112, true,  'verified'),
  (71317, 71012, 70132, false, 'unverified'),
  (71318, 71013, 70113, true,  'verified'),
  (71319, 71014, 70114, true,  'verified'),
  (71320, 71015, 70115, true,  'verified'),
  (71321, 71016, 70116, true,  'verified'),
  (71322, 71001, 70133, false, 'verified');

-- ---------------------------------------------------------------------------------------------------------------- technology_innovation_analysis
-- Narrative sections of the innovation panel (section_code: background / whats_new / why_it_matters / competitive; the last is the Aurora read
-- when is_client_assessment = true). 36 rows.
INSERT INTO staging.technology_innovation_analysis
  (analysis_id, innovation_id, section_code, section_label, narrative, is_client_assessment, display_order) VALUES
  (71401, 71001, 'background',     'Background - what it is',        'An electric rammer and a magazine arm feed the breech of a towed gun at up to 8 rounds per minute.', false, 1),
  (71402, 71001, 'why_it_matters', 'Why this matters to Aurora',     'Hand-loaded Aurora guns cannot match the sustained rate of fire quoted in recent tenders.', true, 2),
  (71403, 71002, 'background',     'Background - what it is',        'Fibre-optic and acoustic sensors in the bore track erosion and send the data to the fire-control computer.', false, 1),
  (71404, 71002, 'why_it_matters', 'Why this matters to Aurora',     'Aurora already ships this; use it to argue lower life-cycle cost.', true, 2),
  (71405, 71003, 'background',     'Background - what it is',        'A 58-calibre forged barrel with a new chamber raises muzzle velocity.', false, 1),
  (71406, 71003, 'competitive',    'Competitive landscape',          'Halcyon leads and Borealis is expected to follow; no Aurora programme yet.', false, 2),
  (71407, 71004, 'background',     'Background - what it is',        'A new nitrocellulose-free formulation burns at a lower flame temperature.', false, 1),
  (71408, 71004, 'why_it_matters', 'Why this matters to Aurora',     'Barrel life is a cost driver for artillery customers; a licence would help both guns and ammunition.', true, 2),
  (71409, 71005, 'background',     'Background - what it is',        'Polymer-bonded explosive resists fast and slow cook-off and bullet impact.', false, 1),
  (71410, 71005, 'why_it_matters', 'Why this matters to Aurora',     'European tenders now ask for IM compliance; Aurora Shell 155 is not qualified.', true, 2),
  (71411, 71005, 'whats_new',      'What is new',                    'Meridian completed qualification and booked first orders from two European buyers.', false, 3),
  (71412, 71006, 'background',     'Background - what it is',        'A fuze-replacement guidance kit with fins and a GPS-inertial unit.', false, 1),
  (71413, 71006, 'why_it_matters', 'Why this matters to Aurora',     'Precision kits are written into new 155 mm frameworks.', true, 2),
  (71414, 71007, 'background',     'Background - what it is',        'Radar-cued countermeasures defeat incoming rockets and missiles.', false, 1),
  (71415, 71007, 'why_it_matters', 'Why this matters to Aurora',     'Protection is a buying criterion in the Brazil and India vehicle tenders.', true, 2),
  (71416, 71007, 'competitive',    'Competitive landscape',          'Cobalt has the first export order; Tessera is exploring a radar partnership.', false, 3),
  (71417, 71008, 'background',     'Background - what it is',        'Ceramic tiles on aramid backing stop armour-piercing rounds at lower weight.', false, 1),
  (71418, 71008, 'why_it_matters', 'Why this matters to Aurora',     'Lower hull weight gives the Aurora APC more payload.', true, 2),
  (71419, 71009, 'background',     'Background - what it is',        'Batteries and an electric motor drive the vehicle for silent watch.', false, 1),
  (71420, 71009, 'why_it_matters', 'Why this matters to Aurora',     'New vehicle requirements start asking for silent watch.', true, 2),
  (71421, 71010, 'background',     'Background - what it is',        'A rangefinder and ballistic computer place the aim point in the reticle.', false, 1),
  (71422, 71010, 'why_it_matters', 'Why this matters to Aurora',     'Aurora Carbine can be fitted with the sight; tenders increasingly ask for it.', true, 2),
  (71423, 71011, 'background',     'Background - what it is',        'A polymer case replaces brass, cutting a third of the ammunition weight.', false, 1),
  (71424, 71011, 'why_it_matters', 'Why this matters to Aurora',     'Aurora Carbine can use the round with a barrel change, a lead over rivals.', true, 2),
  (71425, 71012, 'background',     'Background - what it is',        'A radar-cued drone with electro-optical seeker closes on and destroys the target.', false, 1),
  (71426, 71012, 'why_it_matters', 'Why this matters to Aurora',     'Tessera is on par with the Aurora Interceptor Drone; trials decide the lead.', true, 2),
  (71427, 71013, 'background',     'Background - what it is',        'A fibre spool carries video and control to the drone, so jammers do not work.', false, 1),
  (71428, 71013, 'why_it_matters', 'Why this matters to Aurora',     'Counter-UAS offers must include hard-kill layers.', true, 2),
  (71429, 71014, 'background',     'Background - what it is',        'A phased array steers jamming energy to each drone separately.', false, 1),
  (71430, 71014, 'why_it_matters', 'Why this matters to Aurora',     'Swarm defence is a stated requirement in Freedonia and Gulf tenders.', true, 2),
  (71431, 71015, 'background',     'Background - what it is',        'A focal-plane array and onboard processor classify the target in flight.', false, 1),
  (71432, 71015, 'why_it_matters', 'Why this matters to Aurora',     'No Aurora missile line; relevant only for partner choices.', true, 2),
  (71433, 71016, 'background',     'Background - what it is',        'An inductively set fuze receives its burst time from the fire-control unit.', false, 1),
  (71434, 71016, 'why_it_matters', 'Why this matters to Aurora',     'The licence would let Aurora ammunition address low drones.', true, 2),
  (71435, 71016, 'competitive',    'Competitive landscape',          'Pinewood offers the same licence to several makers; first movers gain.', false, 3),
  (71436, 71012, 'competitive',    'Competitive landscape',          'Cobalt and Tessera both field cued interceptors; Aurora is in trials.', false, 3);

-- ---------------------------------------------------------------------------------------------------------------- technology_overview_article
-- The overview feed card and drawer (Technology > Overview: signal cards, "what the article says", "why it matters to Aurora").
-- 10 rows; article_id and overview_article_id hold the same id (children join on either). 6 competitor_advance, 4 adoptable.
INSERT INTO staging.technology_overview_article
  (overview_article_id, article_id, pillar_id, lens, sequence_no, status, title, summary, card_summary, article_says, client_narrative,
   classification, direction, category_id, category_text, country_code, article_date, published_on, published_label, image_url,
   primary_company_id, external_id, created_at, updated_at) VALUES
  (72001, 72001, 1, 'Technology', 1, 'active', 'Halcyon fields 58-calibre barrel on self-propelled howitzer (TEST)',
   'Halcyon fielded a 58-calibre barrel.', 'Halcyon fields a 58-calibre barrel with 25% more range than Aurora 52-calibre guns.',
   'Halcyon Land Systems (TEST) delivered the first self-propelled howitzers with a 58-calibre barrel to its home army. Firing trials reached 70 km with base-bleed rounds.',
   'The barrel puts Halcyon ahead of the Aurora Gun 155 on range in export tenders, so Aurora should assess a longer barrel.',
   'competitor_advance', 'threat', 1, 'Artillery', 'KR', '2026-10-10', '2026-10-10', '10 Oct 2026', 'https://images.example.com/halcyon-58-cal.jpg', 70004, 'test-article-72001', '2026-10-10 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72002, 72002, 1, 'Technology', 2, 'active', 'Meridian qualifies insensitive-munition 155 mm shell (TEST)',
   'Meridian qualified an IM shell.', 'Meridian completed IM qualification of a 155 mm shell, the first in its class.',
   'Meridian Ordnance (TEST) completed qualification of an insensitive-munition 155 mm shell and booked first orders from two European buyers.',
   'European buyers will ask Aurora for IM compliance; Aurora Shell 155 is not yet qualified.',
   'competitor_advance', 'watch', 2, 'Ammunition', 'FR', '2026-10-09', '2026-10-09', '9 Oct 2026', 'https://images.example.com/meridian-im.jpg', 70005, 'test-article-72002', '2026-10-09 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72003, 72003, 1, 'Technology', 3, 'active', 'Open radar-cueing software released for counter-UAS (TEST)',
   'Open software for counter-UAS cueing.', 'Redstone University Labs released open software that cues interceptors from commodity radars.',
   'Redstone University Labs (TEST) published open-source software that links commodity radars to interceptor drones.',
   'Aurora can adopt the software for its Interceptor Drone and save radar integration time.',
   'adoptable', 'fav', 5, 'Unmanned & Counter-UAS', 'US', '2026-10-08', '2026-10-08', '8 Oct 2026', 'https://images.example.com/radar-cueing.jpg', 70008, 'test-article-72003', '2026-10-08 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72004, 72004, 1, 'Technology', 4, 'active', 'Cobalt unveils compact active protection for 8x8 vehicles (TEST)',
   'Cobalt showed a compact APS.', 'Cobalt Dynamics launched an active protection system sized for 8x8 vehicles with a first export order.',
   'Cobalt Dynamics (TEST) unveiled a compact active protection system and announced the first export order.',
   'Brazilian and Indian vehicle tenders may require active protection, so the Aurora APC needs a partner.',
   'competitor_advance', 'threat', 3, 'Armoured Vehicles', 'US', '2026-10-07', '2026-10-07', '7 Oct 2026', 'https://images.example.com/cobalt-aps.jpg', 70003, 'test-article-72004', '2026-10-07 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72005, 72005, 1, 'Technology', 5, 'active', 'Polymer-cased 5.56 mm ammunition reaches production readiness (TEST)',
   'Polymer-cased ammunition is ready.', 'A supplier qualified a production line for polymer-cased 5.56 mm ammunition.',
   'Nova Propellants GmbH (TEST) qualified a production line for polymer-cased 5.56 mm ammunition.',
   'Aurora Carbine can use the round after a barrel change, a lead over rivals.',
   'adoptable', 'fav', 4, 'Small Arms', 'DE', '2026-10-06', '2026-10-06', '6 Oct 2026', 'https://images.example.com/polymer-case.jpg', 70009, 'test-article-72005', '2026-10-06 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72006, 72006, 1, 'Technology', 6, 'active', 'Tessera tests interceptor drone with 5 km reach (TEST)',
   'Tessera tested a 5 km interceptor.', 'Tessera Aerospace demonstrated an interceptor drone with a 5 km engagement radius.',
   'Tessera Aerospace (TEST) demonstrated a radar-cued interceptor drone against Group 2 targets.',
   'The domestic rival matches the Aurora Interceptor Drone; trials decide who leads.',
   'competitor_advance', 'watch', 5, 'Unmanned & Counter-UAS', 'IN', '2026-10-05', '2026-10-05', '5 Oct 2026', 'https://images.example.com/tessera-interceptor.jpg', 70006, 'test-article-72006', '2026-10-05 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72007, 72007, 1, 'Technology', 7, 'active', 'Borealis integrates automatic loader on towed gun (TEST)',
   'Borealis integrated a loader.', 'Borealis Arms fitted an automatic loader to its towed 155 mm gun.',
   'Borealis Arms (TEST) integrated a powered loader on its towed gun and reached 8 rounds per minute.',
   'Aurora hand-loaded guns lose on sustained rate of fire in recent tenders.',
   'competitor_advance', 'threat', 1, 'Artillery', 'NO', '2026-10-04', '2026-10-04', '4 Oct 2026', 'https://images.example.com/borealis-loader.jpg', 70002, 'test-article-72007', '2026-10-04 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72008, 72008, 1, 'Technology', 8, 'active', 'Programmable airburst fuze licence offered to Aurora (TEST)',
   'Airburst licence offered.', 'Pinewood Optics offers a licence for a programmable airburst fuze.',
   'Pinewood Optics Ltd (TEST) offered Aurora and other makers a licence for a programmable airburst fuze.',
   'The licence would allow Aurora ammunition to engage low drones.',
   'adoptable', 'watch', 6, 'Missiles & Air Defence', 'GB', '2026-10-03', '2026-10-03', '3 Oct 2026', 'https://images.example.com/airburst.jpg', 70010, 'test-article-72008', '2026-10-03 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72009, 72009, 1, 'Technology', 9, 'active', 'Tessera trials imaging infrared seeker (TEST)',
   'Tessera trialled a seeker.', 'Tessera Aerospace trialled an imaging infrared seeker against decoys.',
   'Tessera Aerospace (TEST) completed a seeker trial against decoy flares.',
   'Aurora has no missile line; relevant to partner decisions only.',
   'competitor_advance', 'watch', 6, 'Missiles & Air Defence', 'IN', '2026-10-02', '2026-10-02', '2 Oct 2026', 'https://images.example.com/tessera-seeker.jpg', 70006, 'test-article-72009', '2026-10-02 08:00:00+00', '2026-10-16 08:00:00+00'),
  (72010, 72010, 1, 'Technology', 10, 'active', 'Nova offers low-erosion propellant licence (TEST)',
   'Nova offers a propellant licence.', 'Nova Propellants offers a licence for a low-erosion modular propellant charge.',
   'Nova Propellants GmbH (TEST) offered licences for a low-erosion modular propellant charge to artillery makers.',
   'A licence would extend barrel life of Aurora guns and cut customer cost.',
   'adoptable', 'fav', 2, 'Ammunition', 'DE', '2026-10-01', '2026-10-01', '1 Oct 2026', 'https://images.example.com/nova-propellant.jpg', 70009, 'test-article-72010', '2026-10-01 08:00:00+00', '2026-10-16 08:00:00+00');

-- ---------------------------------------------------------------------------------------------------------------- technology_overview_fact
-- The "At a glance" facts of the article drawer (label, value, proof sentence). 30 rows. fact_id and overview_fact_id hold the same id.
INSERT INTO staging.technology_overview_fact
  (overview_fact_id, fact_id, overview_article_id, article_id, display_order, fact_key, fact_label, ui_label, fact_value, proof_text) VALUES
  (72101, 72101, 72001, 72001, 1, 'competitor', 'Competitor', 'Competitor', 'Halcyon Land Systems (TEST)', 'Halcyon delivered the first howitzers to its home army.'),
  (72102, 72102, 72001, 72001, 2, 'category',   'Category',   'Category',   'Artillery',                   'The barrel belongs to the artillery category.'),
  (72103, 72103, 72001, 72001, 3, 'company',    'Country',    'Country',    'South Korea',                 'Halcyon is headquartered in South Korea.'),
  (72104, 72104, 72002, 72002, 1, 'competitor', 'Competitor', 'Competitor', 'Meridian Ordnance (TEST)',    'Meridian completed the qualification.'),
  (72105, 72105, 72002, 72002, 2, 'category',   'Category',   'Category',   'Ammunition',                  'The shell is 155 mm artillery ammunition.'),
  (72106, 72106, 72002, 72002, 3, 'company',    'Country',    'Country',    'France',                      'Meridian is headquartered in France.'),
  (72107, 72107, 72003, 72003, 1, 'company',    'Source',     'Source',     'Redstone University Labs (TEST)', 'The lab published the software.'),
  (72108, 72108, 72003, 72003, 2, 'category',   'Category',   'Category',   'Unmanned & Counter-UAS',      'The software cues interceptor drones.'),
  (72109, 72109, 72003, 72003, 3, 'company',    'Country',    'Country',    'United States',               'The lab is in the United States.'),
  (72110, 72110, 72004, 72004, 1, 'competitor', 'Competitor', 'Competitor', 'Cobalt Dynamics (TEST)',      'Cobalt announced the system and the first order.'),
  (72111, 72111, 72004, 72004, 2, 'category',   'Category',   'Category',   'Armoured Vehicles',           'The system protects 8x8 vehicles.'),
  (72112, 72112, 72004, 72004, 3, 'company',    'Country',    'Country',    'United States',               'Cobalt is headquartered in the United States.'),
  (72113, 72113, 72005, 72005, 1, 'company',    'Source',     'Source',     'Nova Propellants GmbH (TEST)', 'Nova qualified the production line.'),
  (72114, 72114, 72005, 72005, 2, 'category',   'Category',   'Category',   'Small Arms',                  'The cartridge is 5.56 mm small-arms ammunition.'),
  (72115, 72115, 72005, 72005, 3, 'company',    'Country',    'Country',    'Germany',                     'Nova is headquartered in Germany.'),
  (72116, 72116, 72006, 72006, 1, 'competitor', 'Competitor', 'Competitor', 'Tessera Aerospace (TEST)',    'Tessera ran the demonstration.'),
  (72117, 72117, 72006, 72006, 2, 'category',   'Category',   'Category',   'Unmanned & Counter-UAS',      'The product is an interceptor drone.'),
  (72118, 72118, 72006, 72006, 3, 'company',    'Country',    'Country',    'India',                       'Tessera is headquartered in India.'),
  (72119, 72119, 72007, 72007, 1, 'competitor', 'Competitor', 'Competitor', 'Borealis Arms (TEST)',       'Borealis integrated the loader.'),
  (72120, 72120, 72007, 72007, 2, 'category',   'Category',   'Category',   'Artillery',                   'The loader fits a towed gun.'),
  (72121, 72121, 72007, 72007, 3, 'company',    'Country',    'Country',    'Norway',                      'Borealis is headquartered in Norway.'),
  (72122, 72122, 72008, 72008, 1, 'company',    'Source',     'Source',     'Pinewood Optics Ltd (TEST)',  'Pinewood announced the licence offer.'),
  (72123, 72123, 72008, 72008, 2, 'category',   'Category',   'Category',   'Missiles & Air Defence',      'The fuze serves air-defence guns.'),
  (72124, 72124, 72008, 72008, 3, 'company',    'Country',    'Country',    'United Kingdom',              'Pinewood is headquartered in the United Kingdom.'),
  (72125, 72125, 72009, 72009, 1, 'competitor', 'Competitor', 'Competitor', 'Tessera Aerospace (TEST)',    'Tessera ran the seeker trial.'),
  (72126, 72126, 72009, 72009, 2, 'category',   'Category',   'Category',   'Missiles & Air Defence',      'The seeker equips short-range missiles.'),
  (72127, 72127, 72009, 72009, 3, 'company',    'Country',    'Country',    'India',                       'Tessera is headquartered in India.'),
  (72128, 72128, 72010, 72010, 1, 'company',    'Source',     'Source',     'Nova Propellants GmbH (TEST)', 'Nova offered the licence.'),
  (72129, 72129, 72010, 72010, 2, 'category',   'Category',   'Category',   'Ammunition',                  'The charge is modular artillery propellant.'),
  (72130, 72130, 72010, 72010, 3, 'company',    'Country',    'Country',    'Germany',                     'Nova is headquartered in Germany.');

-- ---------------------------------------------------------------------------------------------------------------- technology_overview_key_point
-- The "Key points" of the article drawer (each with a quoted evidence sentence). 24 rows, 2-3 per article.
INSERT INTO staging.technology_overview_key_point
  (key_point_id, overview_article_id, article_id, point_no, display_order, point_type, point_text, evidence_text) VALUES
  (72201, 72001, 72001, 1, 1, 'fact',    'The first howitzers with a 58-calibre barrel were delivered.', 'Halcyon delivered the first self-propelled howitzers with a 58-calibre barrel to its home army.'),
  (72202, 72001, 72001, 2, 2, 'fact',    'Firing trials reached 70 km with base-bleed rounds.',           'Firing trials reached 70 km with base-bleed rounds.'),
  (72203, 72002, 72002, 1, 1, 'fact',    'Qualification of the IM shell is complete.',                    'Meridian completed qualification of an insensitive-munition 155 mm shell.'),
  (72204, 72002, 72002, 2, 2, 'fact',    'Two European buyers placed first orders.',                      'The company booked first orders from two European buyers.'),
  (72205, 72003, 72003, 1, 1, 'fact',    'The software is open source.',                                  'The lab published the software under an open-source licence.'),
  (72206, 72003, 72003, 2, 2, 'fact',    'It works with commodity radars.',                               'It links commodity radars to interceptor drones.'),
  (72207, 72004, 72004, 1, 1, 'fact',    'The system is sized for 8x8 vehicles.',                         'Cobalt unveiled a compact system sized for 8x8 vehicles.'),
  (72208, 72004, 72004, 2, 2, 'fact',    'A first export order was announced.',                           'The company announced the first export order for the system.'),
  (72209, 72004, 72004, 3, 3, 'context', 'Protection is becoming a tender requirement.',                 'Recent vehicle tenders list active protection as desirable.'),
  (72210, 72005, 72005, 1, 1, 'fact',    'A production line for polymer-cased 5.56 mm ammunition is qualified.', 'Nova qualified a production line for polymer-cased 5.56 mm ammunition.'),
  (72211, 72005, 72005, 2, 2, 'fact',    'The case weighs a third less than brass.',                      'The polymer case cuts ammunition weight by a third.'),
  (72212, 72006, 72006, 1, 1, 'fact',    'The interceptor has a 5 km engagement radius.',                 'The drone has a 5 km engagement radius.'),
  (72213, 72006, 72006, 2, 2, 'fact',    'It was tested against Group 2 targets.',                        'The demonstration was run against Group 2 drones.'),
  (72214, 72007, 72007, 1, 1, 'fact',    'The loader reaches 8 rounds per minute.',                       'The loader reached 8 rounds per minute in live-fire trials.'),
  (72215, 72007, 72007, 2, 2, 'fact',    'It fits the existing towed gun.',                               'Borealis integrated the loader on its towed gun.'),
  (72216, 72008, 72008, 1, 1, 'fact',    'A licence for a programmable airburst fuze is offered.',        'Pinewood offered Aurora and other makers a licence.'),
  (72217, 72008, 72008, 2, 2, 'context', 'The fuze is set inductively by the fire-control unit.',        'The fuze receives its burst time from the fire-control unit.'),
  (72218, 72009, 72009, 1, 1, 'fact',    'The seeker defeated decoy flares in trials.',                   'The seeker trial ran against decoy flares.'),
  (72219, 72009, 72009, 2, 2, 'fact',    'It uses a focal-plane array.',                                  'A focal-plane array classifies the target in flight.'),
  (72220, 72010, 72010, 1, 1, 'fact',    'A licence for a low-erosion charge is offered.',                'Nova offered licences to artillery makers.'),
  (72221, 72010, 72010, 2, 2, 'fact',    'Bore erosion falls by about 35% at zone 8.',                    'The charge cuts erosion by about 35% at zone 8.'),
  (72222, 72001, 72001, 3, 3, 'context', 'Aurora 52-calibre guns would lose range in tenders.',            'Export tenders quote range bands that 52-calibre guns cannot reach.'),
  (72223, 72007, 72007, 3, 3, 'context', 'Rate of fire is now a scored tender criterion.',                'Recent artillery tenders score sustained rate of fire.'),
  (72224, 72004, 72004, 4, 4, 'context', 'Radar cueing is the enabling technology.',                      'The system relies on a compact radar.');

-- ---------------------------------------------------------------------------------------------------------------- technology_overview_company
-- Companies named in an article ("Companies" chips in the drawer; relationship developer/adopter/supplier). 16 rows.
INSERT INTO staging.technology_overview_company
  (overview_company_id, overview_article_id, article_id, company_id, display_order, display_label, relationship, relationship_type) VALUES
  (72301, 72001, 72001, 70004, 1, 'Halcyon Land Systems (TEST)',        'developer', 'competitor'),
  (72302, 72002, 72002, 70005, 1, 'Meridian Ordnance (TEST)',           'developer', 'competitor'),
  (72303, 72003, 72003, 70008, 1, 'Redstone University Labs (TEST)',    'developer', 'third_party'),
  (72304, 72004, 72004, 70003, 1, 'Cobalt Dynamics (TEST)',             'developer', 'competitor'),
  (72305, 72004, 72004, 70008, 2, 'Redstone University Labs (TEST)',    'research partner', 'third_party'),
  (72306, 72005, 72005, 70009, 1, 'Nova Propellants GmbH (TEST)',       'developer', 'third_party'),
  (72307, 72006, 72006, 70006, 1, 'Tessera Aerospace (TEST)',           'developer', 'competitor'),
  (72308, 72007, 72007, 70002, 1, 'Borealis Arms (TEST)',               'developer', 'competitor'),
  (72309, 72008, 72008, 70010, 1, 'Pinewood Optics Ltd (TEST)',         'licensor',  'third_party'),
  (72310, 72008, 72008, 70001, 2, 'Aurora Defence (TEST)',              'prospective licensee', 'client'),
  (72311, 72009, 72009, 70006, 1, 'Tessera Aerospace (TEST)',           'developer', 'competitor'),
  (72312, 72010, 72010, 70009, 1, 'Nova Propellants GmbH (TEST)',       'licensor',  'third_party'),
  (72313, 72010, 72010, 70001, 2, 'Aurora Defence (TEST)',              'prospective licensee', 'client'),
  (72314, 72005, 72005, 70001, 2, 'Aurora Defence (TEST)',              'prospective user', 'client'),
  (72315, 72003, 72003, 70001, 2, 'Aurora Defence (TEST)',              'prospective user', 'client'),
  (72316, 72002, 72002, 70004, 2, 'Halcyon Land Systems (TEST)',        'follower',  'competitor');

-- ---------------------------------------------------------------------------------------------------------------- technology_overview_source
-- Links article -> technology_source (primary first; provenance_status is shown as the "provenance" line). 16 rows.
INSERT INTO staging.technology_overview_source
  (overview_source_id, overview_article_id, article_id, source_id, display_order, is_primary, source_role, provenance_status) VALUES
  (72401, 72001, 72001, 70119, 1, true,  'primary',       'verified'),
  (72402, 72001, 72001, 70129, 2, false, 'corroboration', 'verified'),
  (72403, 72002, 72002, 70120, 1, true,  'primary',       'verified'),
  (72404, 72002, 72002, 70130, 2, false, 'corroboration', 'verified'),
  (72405, 72003, 72003, 70121, 1, true,  'primary',       'verified'),
  (72406, 72004, 72004, 70122, 1, true,  'primary',       'verified'),
  (72407, 72004, 72004, 70131, 2, false, 'corroboration', 'single_source'),
  (72408, 72005, 72005, 70123, 1, true,  'primary',       'single_source'),
  (72409, 72006, 72006, 70124, 1, true,  'primary',       'verified'),
  (72410, 72006, 72006, 70132, 2, false, 'corroboration', 'unverified'),
  (72411, 72007, 72007, 70125, 1, true,  'primary',       'verified'),
  (72412, 72007, 72007, 70133, 2, false, 'corroboration', 'verified'),
  (72413, 72008, 72008, 70126, 1, true,  'primary',       'verified'),
  (72414, 72009, 72009, 70127, 1, true,  'primary',       'verified'),
  (72415, 72010, 72010, 70128, 1, true,  'primary',       'verified'),
  (72416, 72010, 72010, 70134, 2, false, 'corroboration', 'verified');

-- ---------------------------------------------------------------------------------------------------------------- technology_metric
-- The metric tiles on the Technology pages (counts; metric_action is the filter the tile opens). 8 rows.
INSERT INTO staging.technology_metric
  (metric_id, pillar_id, metric_key, metric_label, metric_value, metric_unit, metric_action, display_order, as_of_date) VALUES
  (72501, 1, 'innovations_tracked',  'Innovations tracked',    16, 'innovations', 'open-innovation-tab',          3, '2026-10-16'),
  (72502, 1, 'aurora_behind',        'Aurora behind',           8, 'innovations', 'filter-position-behind',       4, '2026-10-16'),
  (72503, 1, 'aurora_parity',        'Aurora at parity',        6, 'innovations', 'filter-position-parity',       5, '2026-10-16'),
  (72504, 1, 'aurora_ahead',         'Aurora ahead',            2, 'innovations', 'filter-position-ahead',        6, '2026-10-16'),
  (72505, 1, 'signals_total',        'Overview signals',       10, 'signals',     'open-overview',                7, '2026-10-16'),
  (72506, 1, 'competitor_advances',  'Competitor advances',     6, 'signals',     'filter-classification-competitor_advance', 1, '2026-10-16'),
  (72507, 1, 'adoptable',            'Adoptable technologies',  4, 'signals',     'filter-classification-adoptable', 2, '2026-10-16'),
  (72508, 1, 'candidates_pending',   'Candidates pending detail', 2, 'innovations', NULL,                         8, '2026-10-16');

-- ---------------------------------------------------------------------------------------------------------------- staging.fact_source (Trace panel)
-- Innovation cards: the primary source link of each active innovation ...
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'technology_innovation', i.innovation_id::text, 'summary', s.source_url,
       CASE WHEN s.source_kind = 'company' THEN 'primary' WHEN s.source_kind = 'patent' THEN 'primary' ELSE 'independent' END,
       s.publisher, i.summary, '2026-10-16 08:00:00+00'
FROM staging.technology_innovation i
JOIN staging.technology_innovation_source l ON l.innovation_id = i.innovation_id AND l.is_primary
JOIN staging.technology_source s ON s.source_id = l.source_id
WHERE i.status = 'active';
-- ... overview article cards: the primary source of each article ...
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at)
SELECT 'technology_overview_article', a.overview_article_id::text, 'article_says', s.source_url,
       CASE WHEN s.source_kind IN ('company', 'research') THEN 'primary' ELSE 'independent' END,
       s.publisher, a.article_says, '2026-10-16 08:00:00+00'
FROM staging.technology_overview_article a
JOIN staging.technology_overview_source l ON l.overview_article_id = a.overview_article_id AND l.is_primary
JOIN staging.technology_source s ON s.source_id = l.source_id;
-- ... and the judgement reasons behind the Aurora position, the classification and the direction.
INSERT INTO staging.fact_source (table_name, row_id, column_name, source_url, source_tier, publisher, quote, retrieved_at) VALUES
  ('technology_innovation', '71001', 'client_position', 'judgement', 'judgement', NULL, 'Behind: Aurora guns are hand-loaded and the stored specifications give no powered loader.', '2026-10-16 08:00:00+00'),
  ('technology_innovation', '71002', 'client_position', 'judgement', 'judgement', NULL, 'Ahead: Aurora already ships a barrel-life monitor and no rival does.', '2026-10-16 08:00:00+00'),
  ('technology_innovation', '71003', 'client_position', 'judgement', 'judgement', NULL, 'Parity: no fielded 58-calibre gun yet, Aurora 52-calibre guns remain competitive.', '2026-10-16 08:00:00+00'),
  ('technology_innovation', '71005', 'client_position', 'judgement', 'judgement', NULL, 'Behind: Aurora Shell 155 has no IM qualification in the stored specifications.', '2026-10-16 08:00:00+00'),
  ('technology_innovation', '71011', 'client_position', 'judgement', 'judgement', NULL, 'Ahead: the Aurora Carbine can fire the round with a barrel change; no rival says so.', '2026-10-16 08:00:00+00'),
  ('technology_innovation', '71012', 'maturity', 'judgement', 'judgement', NULL, 'In development: demonstrated against Group 2 drones, not yet fielded.', '2026-10-16 08:00:00+00'),
  ('technology_overview_article', '72001', 'classification', 'judgement', 'judgement', NULL, 'Competitor advance: Halcyon fielded a longer barrel that Aurora does not have.', '2026-10-16 08:00:00+00'),
  ('technology_overview_article', '72001', 'direction', 'judgement', 'judgement', NULL, 'Threat: the range advantage appears in current export tenders.', '2026-10-16 08:00:00+00'),
  ('technology_overview_article', '72003', 'classification', 'judgement', 'judgement', NULL, 'Adoptable: open-source software Aurora can use without a licence fee.', '2026-10-16 08:00:00+00'),
  ('technology_overview_article', '72003', 'direction', 'judgement', 'judgement', NULL, 'Favourable: it shortens Aurora Interceptor Drone integration.', '2026-10-16 08:00:00+00'),
  ('technology_overview_article', '72008', 'classification', 'judgement', 'judgement', NULL, 'Adoptable: the licence is offered to Aurora directly.', '2026-10-16 08:00:00+00'),
  ('technology_overview_fact', '72101', 'fact_value', 'https://news.example.com/halcyon-sp-58-fielded', 'independent', 'Defence Weekly (TEST)', 'Halcyon Land Systems delivered the first howitzers to its home army.', '2026-10-16 08:00:00+00'),
  ('technology_overview_key_point', '72201', 'point_text', 'https://news.example.com/halcyon-sp-58-fielded', 'independent', 'Defence Weekly (TEST)', 'The first self-propelled howitzers with a 58-calibre barrel were delivered.', '2026-10-16 08:00:00+00');

COMMIT;
