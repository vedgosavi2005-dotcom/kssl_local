# Wording audit — summary (2026-10-18)

Scope: every stored display text in local staging: 159 columns, ~102,000 texts (titles, headlines, summaries,
assessments, timelines). The audit only reads. Rerun it with `scripts/audit_wording.py`. The detail below this summary
is the script's output.

## What needs fixing (prompt-written text; fix in the prompts, then re-run them)

| # | Problem | Where | How many | Example | Rule for the prompt |
|---|---|---|---:|---|---|
| 1 | Title ends on a preposition | `competitive_signal_detail.drawer_title` | 1 | "…in the programme KSSL and AM General **bid for**" | A title must read as a finished headline: never end on a preposition or conjunction. |
| 2 | Title ends on a number without its noun | `competitive_signal_detail.drawer_title` | 4 | "…with **option for 12**", "BEML **signs for 48**", "three **batches of 18**" | Keep the noun after a number ("option for 12 more", "48 fuselages"). |
| 3 | Stored codes inside sentences | tender competitor-fit rationale, tender fit rationale, innovation narrative, story steps | 51 | "sells_in_buyer_country is 'not on record'", "a **sniper_rifle**", "**sam_medium**", "Label changed to **need_stated**" | Never write a field name or code in prose; use the words ("does not record sales in the buyer's country", "sniper rifle", "medium-range surface-to-air missile"). |
| 4 | Title not in English | `story.title`, `competitive_project.project_title` | 1 | "dostawy seryjne Zdalnie Sterowanych Systemów Wieżowych 30 mm (ZSSW-30)" | Titles are English; a foreign programme name stays only as a name ("Serial deliveries of ZSSW-30 30 mm remote turrets"). |
| 5 | Sentence built around a messy tender title | `market_next_move.action_text` | 2 | "Prepare the bid for **. 22** RIM FIRE…", double space | Tidy the tender title (spacing, leading punctuation) before writing it into a sentence. |

Checked and fine: the matches were legitimate.
- years at the end ("by end of 2026"), "handed over"
- labels printed in front of a value ("Delivered to: …")
- model and company names ("Bagulnik-82 82 mm", "Item A", "Nammo AS", "xTerra", "armasuisse")
- doubled words that are names ("Dum Dum", "on on-board")

No cut-off text (… or open brackets), no HTML and no placeholder values were found in prompt-written text.

## Source text copied verbatim (publisher / portal wording)

Tender titles, news headlines, requirement extracts, datasheet labels and source labels are the source's own words and
are **not rewritten**. Their counts are in the detail below: spacing 132, dangling punctuation 72, cut-off 74,
lowercase starts 2,855 (mostly datasheet labels and website names). Only their display could be tidied, for example by
collapsing double spaces, and that would be a frontend option.

---

# Wording audit (staging)

160 display-text columns, 102070 stored texts scanned. Read-only (`scripts/audit_wording.py`). Code columns (impact_dimension, current_label, fit_label, ...) are left out: the UI shows them as words. One-line rules apply to title / headline / label / eyebrow / glance fields.

# Prompt-written text (fix in the prompts)

| Rule | Texts | Columns |
|---|---:|---:|
| ends on a preposition, conjunction or article (`ends-function-word`) | 2 | 2 |
| ends on 'for/of/to/with N' with no noun after the number (`ends-bare-count`) | 4 | 1 |
| ends on a comma, colon, semicolon, dash or slash (`ends-dangling-punct`) | 1 | 1 |
| ends in '…' / '...' or stops inside an open bracket or quote (`cut-off`) | 0 | 0 |
| the same word twice in a row (`doubled-word`) | 7 | 7 |
| a stored code instead of words (snake_case) (`raw-code`) | 51 | 5 |
| HTML tags or entities (`markup`) | 0 | 0 |
| a placeholder value (null, None, undefined, N/A, TBD, lorem) (`placeholder`) | 0 | 0 |
| double space, leading/trailing space or a space before punctuation (`spacing`) | 2 | 1 |
| a one-line field that starts lowercase (`lowercase-start`) | 14 | 8 |

## ends on a preposition, conjunction or article (`ends-function-word`)

- **competitive_project_timeline.event_title**: 1 of 258
  - First Rak company fire module handed over
- **competitive_signal_detail.drawer_title**: 1 of 463
  - U.S. Army receives first Hanwha Mobile Tactical Cannon prototype in the programme KSSL and AM General bid for

## ends on 'for/of/to/with N' with no noun after the number (`ends-bare-count`)

- **competitive_signal_detail.drawer_title**: 4 of 463
  - Hanwha Defense USA wins U.S. Army contract for six wheeled K9 howitzer prototypes, with option for 12
  - HAL signs Adani Defence for 42 Prachand light combat helicopter fuselage structures; BEML signs for 48
  - Germany delivers first KNDS RCH 155 howitzers to Ukraine; 54 contracted in three batches of 18

## ends on a comma, colon, semicolon, dash or slash (`ends-dangling-punct`)

- **market_next_move.tender_title**: 1 of 15
  - FUZE TIME & PERCUSSION DA NO 213 P MK5 (M-3) EMPTY TO DRG. ARDE 1967 PT NO IQX-67, GE DC (I) 35076-

## the same word twice in a row (`doubled-word`)

- **competitive_leader_record.headline**: 1 of 1313
  - Earlier postings included Ordnance Factories Dum Dum and Itarsi, Khamaria, and MIL corporate office in Pune.
- **market_tender_eligibility.note**: 1 of 219
  - The notice names brands such as TOYOTA, Bosch, Nissens and AND. The client rows do not say if KSSL can supply them.
- **market_tender_fit_assessment.assessment_rationale**: 1 of 685
  - The buyer wants 250 feeler gauges for the 9x19 mm machine pistol, drawing number 2101 05 08 00 00 000 00GA. The client rows list only carbines and sniper rifles, which are weapons, not gauges. The ten…
- **story.title**: 1 of 1133
  - Russia tests Bagulnik-82 82 mm robotic mortar on Courier unmanned ground vehicle
- **story_step.one_line**: 1 of 1709
  - Russia tests Bagulnik-82 82 mm robotic mortar on Courier unmanned ground vehicle
- **technology_overview_article.title**: 1 of 620
  - Russia tests Bagulnik-82 82 mm robotic mortar on Courier unmanned ground vehicle
- **technology_overview_key_point.point_text**: 1 of 3086
  - Landmarks are processed on on-board edge hardware, so the drone needs no remote communications link.

## a stored code instead of words (snake_case) (`raw-code`)

- **market_tender_competitor_fit.fit_rationale**: 31 of 409
  - The candidate row lists projectile bodies, rotating-band welding and phosphate and paint finishing. It lists no size 107, and sells_in_buyer_country is 'not on record'.
  - The row lists forging, heat treating and machining of steel parts, so the process is similar. It lists projectile bodies, not bushings, and sells_in_buyer_country is not on record.
  - The candidate row lists calibre 12.7 mm and cartridge 12.7 x 107 mm. It is a sniper_rifle, not a machine gun, and the row does not say it sells in the buyer country.
- **story_step.one_line**: 15 of 1709
  - Label changed to downselect_prototype
  - Label changed to need_stated
  - Label changed to need_stated
- **market_tender_fit_assessment.assessment_rationale**: 2 of 685
  - The buyer wants Saab RBS 70NG launch stands, training materials, spare parts and special tools. The closest KSSL product is the MRSAM / Barak-8 missile kit, which is listed as sam_medium, not a very-s…
  - The buyer wants a semi-automatic sniper rifle in Lot 1 and buys weapons for 3 years. KSSL lists six T-5000M variants in the sniper_rifle sub-type. The tender states no technical value, so no check can…
- **product_class.reason**: 2 of 3128
  - 155 mm barrels in several lengths (52/39/45 cal), so no single barrel_cal applies.
  - 120 mm smoothbore tank gun in L44 and L55 variants, so no single barrel_cal.
- **technology_innovation_analysis.narrative**: 1 of 168
  - Raytheon's Coyote Block 2C+RM pushes a counter-drone interceptor toward the surface-to-air missile role. That role sits next to the MRSAM / Barak-8 missile kits (sam_medium, 150-1000 kg) in KSSL's Mis…

## double space, leading/trailing space or a space before punctuation (`spacing`)

- **market_next_move.action_text**: 2 of 15
  - Prepare the bid for . 22 RIM FIRE LONG AMMUNITION before 26 Oct 2026.
  - Prepare the bid for Munition calibre 12 de force intermédiaire de courte portée; Munition  before 01 Dec 2026.

## a one-line field that starts lowercase (`lowercase-start`)

- **competitive_product_program.program_title**: 5 of 219
  - heavy weapon carrier infantry (Schwerer Waffenträger Infanterie: sWaTrg Inf)
  - collaborative combat aircraft (CCA)
  - armasuisse (Swiss Armed Forces) Piranha IV carrier vehicle purchase
- **story.title**: 2 of 1133
  - dostawy seryjne Zdalnie Sterowanych Systemów Wieżowych 30 mm (ZSSW-30)
  - xTerra Robotics unveils DHAV, an indigenous quadruped robot for inspection, security and surveillance
- **technology_overview_company.display_label**: 2 of 1105
  - xTerra Robotics
  - ideaForge Technology
- **competitive_project.project_title**: 1 of 72
  - dostawy seryjne Zdalnie Sterowanych Systemów Wieżowych 30 mm (ZSSW-30)
- **competitive_signal_detail.glance_third_party**: 1 of 414
  - armasuisse; GDELS-Mowag (Piranha IV)
- **market_global_requirement.title**: 1 of 139
  - qNFMLG 30 x 173 mm automatic cannon
- **market_next_move.tender_title**: 1 of 15
  - naboji 7,62 x 39 mm, ostro navadba krogla; naboji 7,62 x 39 mm, manevrski
- **technology_overview_article.title**: 1 of 620
  - xTerra Robotics unveils DHAV, an indigenous quadruped robot for inspection, security and surveillance

# Source text copied verbatim (publisher / portal wording; not rewritten)

| Rule | Texts | Columns |
|---|---:|---:|
| ends on a preposition, conjunction or article (`ends-function-word`) | 266 | 6 |
| ends on 'for/of/to/with N' with no noun after the number (`ends-bare-count`) | 4 | 2 |
| ends on a comma, colon, semicolon, dash or slash (`ends-dangling-punct`) | 72 | 5 |
| ends in '…' / '...' or stops inside an open bracket or quote (`cut-off`) | 74 | 8 |
| the same word twice in a row (`doubled-word`) | 23 | 7 |
| a stored code instead of words (snake_case) (`raw-code`) | 75 | 3 |
| HTML tags or entities (`markup`) | 0 | 0 |
| a placeholder value (null, None, undefined, N/A, TBD, lorem) (`placeholder`) | 0 | 0 |
| double space, leading/trailing space or a space before punctuation (`spacing`) | 132 | 9 |
| a one-line field that starts lowercase (`lowercase-start`) | 2855 | 11 |

## ends on a preposition, conjunction or article (`ends-function-word`)

- **competitive_matchup_source.source_label**: 125 of 573
  - munitionsindia.in
  - munitionsindia.in
  - kssl.in
- **technology_source.label**: 84 of 638
  - theprint.in
  - newsonair.gov.in
  - theweek.in
- **competitive_product_specification.spec_label**: 47 of 25193
  - Design standards complied with
  - Weapons fired from
  - Network add-on
- **competitive_geo_source.source_label**: 4 of 715
  - EDR Magazine – Finland K9 follow-on
  - European Security & Defence – Finland K9 follow-on
  - EDR Magazine – Finland K9 follow-on
- **competitive_news_article.headline**: 4 of 4274
  - CAVS rides a wave and prepares for surge requirements as orders roll in
  - US Marine Corps provides US$900 million for prototypes as vehicle refresh motors on
  - BSE, L&T, Bharat Forge, Navin Fluorine, Sundram Fasteners shares: Expert weighs in
- **competitive_project_specification.spec_label**: 2 of 358
  - Total Dhanush inventory after follow-on
  - Second contract: delivery to

## ends on 'for/of/to/with N' with no noun after the number (`ends-bare-count`)

- **competitive_news_article.headline**: 3 of 4274
  - Naval News Staff, Author at Naval News - Page 5 of 333
  - Military Africa, Author at Military Africa * Page 32 of 40
  - Patrick Kenyette, Author at Military Africa * Page 9 of 13
- **market_tender.title**: 1 of 1626
  - ALUMINIUM WIPER TRAY FOR DIA 400 MM BILLET AS PER DRG. NO. FDY-237/1.,ALUMINIUM WIPER TRAY FOR 400

## ends on a comma, colon, semicolon, dash or slash (`ends-dangling-punct`)

- **market_tender_requirement.source_text**: 40 of 2580
  - bd_category_name: Goods Transport Service – Per Trip based Service - Machinery & Equipment; Open Body Taurus;
  - Lot 1 : Ceinturon et accessoires - Poste 1 : Ceinturon de service; - Poste 2 : Ceinturon de confort; - Poste 3 : Porte-chargeur cal 9mm; - Poste 4 : Porte-chargeur cal .300 ;
  - služba spočívající poskytnutí servisních činností (provádění defektace, běžných oprav, dodávek náhradních dílů ND, technické údržby, zvláštního druhu údržby,
- **market_tender.title**: 13 of 1626
  - Portugal – Unmanned underwater vehicles – Aquisição de ROV, com capacidade para mergulhar até aos 1000m de profundidade e incluindo:
  - AMMUNITION CONTAINER (BOX) H 2 A/L, STEEL, DULY PAINTED AS PERDRG WITH PAINT OF SHADE OLIVE GREEN,
  - MACHINE GUN 12.7MM A/D RECTIFIED / 1005-007341/RD/48/SA/26/2727,MACHINE GUN 12.7MM A/D RECTIFIED /
- **technology_overview_key_point.evidence_text**: 13 of 3086
  - The company did not disclose the contract value, the official signing date, or the full delivery schedule,
  - We pre‑deployed Halo_Shield in parallel with a next‑generation ground radar, with clear objectives:
  - Anduril, working with Ultra Maritime’s Sea Spear deployable sonar system, demonstrated the latest iteration of this system during the Navy’s recent Lanternfish exercise,
- **competitive_news_article.headline**: 4 of 4274
  - Adani Enterprises Executes Business Transfer Agreement To Acquire Punj Lloyds Defence Unit On February 28,
  - War-Tested, In Demand: Inside Rafael’s Arsenal - Defense Update:
  - David’s Sling Air Defense System Validates Combat Lessons in a Recent Test Campaign - Defense Update:
- **market_award.title**: 2 of 503
  - Część I zamówienia – Sukcesywne dostawy części do KTO Rosomak; Część II zamówienia – Sukcesywne dostawy części do pojazdów gąsienicowych;
  - Suministro de UBS de chalecos antitrauma integral verde para uso en distintas Unidades de la Guardia Civil,

## ends in '…' / '...' or stops inside an open bracket or quote (`cut-off`)

- **market_tender_requirement.source_text**: 23 of 2580
  - tender.lots[1].options.description: Options include 2x12 months for a total of 2 years (until 2033
  - An outline of the supplier’s existing capability, detailing cruise speeds, sprint speed, intercept ceiling, operational ranges, manoeuvra...
  - služba spočívající poskytnutí servisních činností (provádění defektace, běžných oprav, dodávek náhradních dílů ND, technické údržby, zvláštního druhu údržby,
- **competitive_product_specification.spec_label**: 21 of 25193
  - Titan (dual-unit kit
  - Contract award 2021 (Hanwha brochure timeline
  - Radar (X-band, ELTA 3D AESA/FMCW
- **competitive_news_article.headline**: 16 of 4274
  - HAL shares hit 52-week high on partnering with Adani Defence, BEML for Light Combat Helicopter fuselage...
  - IIT Madras’ Tunga Aerospace pips Adani Defence, Asteria with Rs 21 crore bid for Home Ministry drone...
  - Trade Spotlight: How should you trade Anand Rathi Wealth, LTM, Pine Labs, TCS, Bharat Dynamics, and others...
- **market_tender.title**: 10 of 1626
  - OIL MICRONISED GRAPHITE SHELL FORGING LUBRICANT AS PER IS: 14384: 1996(FOR HEAVY DUTY APPLICATION U
  - CARTRIDGE FOR 122MM HE ARTILLERY AMRNN FOR D-30 HOWITZER"
  - RING FORGING TO DRG. NO. GCF/FH-257 (REF DRG. NO. 2025046) (IS: 5517-1993, DESIG 25Cr13Mo6 LRS150 (TS= 1000
- **client_partner_source.source_label**: 1 of 17
  - Kalyani Rafael Advanced Systems (KRAS), a Joint Venture ...
- **competitive_partnership_evidence.source_article_title**: 1 of 493
  - HAL shares hit 52-week high on partnering with Adani Defence, BEML for Light Combat Helicopter fuselage...
- **market_award.title**: 1 of 503
  - Послуги з ремонту та технічного обслуговування : (БпЛА DЛ МАVІС ЗT (S/n: 1581F5FJC244P00D6Z39); БпЛА DЛ МАVІС ЗT (S/n: 1581F5FJC243K00DY322); БпЛА Autel EVO MAX 4T (S/n: 1748FEV3HMA923171199); БпЛА DЛ…
- **technology_overview_key_point.evidence_text**: 1 of 3086
  - You can attach a fibre optic cable, or you can have it digital or analogue," Harsheim said.

## the same word twice in a row (`doubled-word`)

- **market_tender_requirement.source_text**: 13 of 2580
  - • 52 000 000 kusů nábojů se střelou „FMJ“, zápalková slož nekorozivní a neerozivní - určeny pouze pro výcvikové účely.
  - • 8 000 000 kusů nábojů se střelou „TFMJ“, zápalková slož netoxická, v provedení se sníženým obsahem škodlivých látek - určeny pouze pro výcvikové účely.
  - cca 8 000 000 kusů nábojů se střelou „FMJ“, zápalková slož nekorozivní a neerozivní
- **market_tender.description**: 2 of 1321
  - The Ministry of Defence, Department of Defence Production, wants to buy one ring forging. It is made to drawing number GCF/FH-257 (reference drawing 2025046). The standard is IS: 5517-1993, designatio…
  - The Ministry of Defence, Department of Defence Production, is buying feeler gauges for the 9x19 mm machine pistol. The quantity is 250. The drawing number is 2101 05 08 00 00 000 00GA. Bids are due on…
- **market_tender.title**: 2 of 1626
  - Provision of of Steering and Rudder System Overhaul Services for RRS James Cook
  - FEELER GAUGE FOR 9X19MM MACHINE PISTOL DRG. NO. 2101 05 08 00 00 000 00GA
- **market_tender.value_text**: 2 of 1088
  - 4 000 000 €
  - 4 000 000 €
- **technology_overview_key_point.evidence_text**: 2 of 3086
  - basically the unit changed almost everything that that UGV had, starting from electronics, the software, the waterproofing, the communications
  - Apache crews destroyed three MQM-170 Outlaw target drones after receiving tracking information generated by an AN/MPQ-64 Sentinel radar.
- **competitive_news_article.headline**: 1 of 4274
  - Elbit Integrates Odysight.ai AI System for Israel’s Ministry of Defense
- **market_tender.lean_text**: 1 of 685
  - The buyer wants 250 feeler gauges for the 9x19 mm machine pistol, drawing number 2101 05 08 00 00 000 00GA. The client rows list only carbines and sniper rifles, which are weapons, not gauges. The ten…

## a stored code instead of words (snake_case) (`raw-code`)

- **market_tender_requirement.source_text**: 66 of 2580
  - lieuexecution_code: FR
  - bd_category_name: Repair, Maintenance, and Installation of Plant/ Systems/Equipments (Version 2) - Industry Unit; REPAIRING OF CHECKING DESK (PK-2) STE OF BV-1 OF CLR T-90; Service Provider
  - ba_is_limited_tendering: 1
- **competitive_product_specification.spec_label**: 7 of 25193
  - shephard_report_(25_mar_2013)
  - new_nitrocellulose_facility
  - bae_page
- **market_tender.lean_text**: 2 of 685
  - The buyer wants Saab RBS 70NG launch stands, training materials, spare parts and special tools. The closest KSSL product is the MRSAM / Barak-8 missile kit, which is listed as sam_medium, not a very-s…
  - The buyer wants a semi-automatic sniper rifle in Lot 1 and buys weapons for 3 years. KSSL lists six T-5000M variants in the sniper_rifle sub-type. The tender states no technical value, so no check can…

## double space, leading/trailing space or a space before punctuation (`spacing`)

- **market_tender_requirement.source_text**: 51 of 2580
  - bd_category_name: NOSE FUZE TYPE A 670M (EMPTY) FOR 30MM BMP-II AMMN. TO CQA(A) DRG. NO. ? ? . 3.140. 039. C? /c, DC-34241 -A, DT
  - Wymogi , ilości oraz szczegółowy opis przedmiotu zamówienia wyszczególniono w załączniku nr 1 do Specyfikacji Warunków Zamówienia, którą Zamawiający przekaże zaproszonym do składania ofert Wykonawcom,…
  - Montant minimum : 10 000,00 Euros. - Montant maximum : 120 000,00 Euros. En valeur en Euros H.T.
- **competitive_news_article.headline**: 33 of 4274
  - ​Ізраїль та Індія випробували ЗРК MRSAM: як Делі кардинально вирішує питання протиповітряної оборони (відео)  / Defense Express
  - Defence, Army, Latest News, Interviews, Videos, Show Report for Army from India and Asia   - SP's Land Forces
  - Індія запустила ліцензійне виробництво САУ К9: армія країни отримає 100 нових самохідних гармат  / Defense Express
- **market_tender.title**: 25 of 1626
  - FOURNITURE ET LIVRAISON D’ÉQUIPEMENTS POUR LA SÛRETÉ PUBLIQUE - LOT 1 : ARMEMENT ET MUNITIONS
  - Запасні частини для транспортних засобів: Модифіковані броньовані автомобілі HMMWV серії   М1152 2-х дверний пікап (довгий) В6
  - LOT 1 - VETEMENTS. Montant maximum annuel des commandes : 40 000 € HT.; LOT 2 - CHAUSSURES Montant maximum annuel des commandes : 10 000 € HT.; LOT 3 - EQUIPEMENTS, ARMEMENT Montant maximum annuel des…
- **market_award.title**: 12 of 503
  - Lot n°1 : Cartouches de calibre "5,56 x 45" M193; Lot n°2 : Cartouches de calibre "5,56 x 45" SS109; Lot n°3 : Cartouches de calibre "5,56 x 45" à balle optimisée
  - Lot n° 1 : Lanceur mono-coup de calibre 40 mm; Lot n° 2 : Viseur électronique
  - 12,7 mm 4 PzB : 1 PzBL-Patr/üsMG M2/geg - ZUSCHLAG
- **competitive_product_news.headline**: 5 of 276
  - Thales and KNDS France unveil  RAPIDFire Land, a land-based variant  of the 40 mm RAPIDFire Naval defence system / KNDS Group
  - ​Ізраїль та Індія випробували ЗРК MRSAM: як Делі кардинально вирішує питання протиповітряної оборони (відео)  / Defense Express
  - Індія запустила ліцензійне виробництво САУ К9: армія країни отримає 100 нових самохідних гармат  / Defense Express
- **client_product_specification.value_text**: 2 of 346
  - 51:49 (Bharat Forge : Elbit Systems Land and C4I)
  - ISO 9001 : 2015 for Aerospace BU
- **competitive_partnership_evidence.source_article_title**: 2 of 493
  - France : les premières munitions téléopérées Damoclès (Delair-KNDS) livrées aux forces armées
  - EuroTrophy and KNDS Deutschland sign a multi-nation contract to supply the Trophy® APS to four new Leopard 2 A8 user nations : Lithuania, The Netherlands, Czech Republic and Croatia
- **competitive_geo_product_news.headline**: 1 of 285
  - Rozpoczęliśmy seryjne dostawy BWP BORSUK ! – Huta Stalowa Wola S.A.
- **competitive_project_source.source_label**: 1 of 209
  - Rozpoczęliśmy seryjne dostawy BWP BORSUK ! – Huta Stalowa Wola S.A.

## a one-line field that starts lowercase (`lowercase-start`)

- **competitive_product_specification.spec_label**: 1528 of 25193
  - type
  - energy
  - application
- **technology_source.label**: 626 of 638
  - thehindubusinessline.com
  - biz.chosun.com
  - biz.chosun.com
- **competitive_matchup_source.source_label**: 573 of 573
  - armyrecognition.com
  - gdots.com
  - armyrecognition.com
- **competitive_matchup_specification.spec_label**: 74 of 1996
  - rate of fire (Indian MoD DDP listing of the L&T 155mm/52 cal TGS)
  - rate of fire
  - crew
- **competitive_news_article.headline**: 15 of 4274
  - xTerra Robotics Unveils DHAV Quadruped Robot As Astra Advances Rocket 4.0 Engine Tests / Indian Defence News
  - ammunition production
  - caesar Coverage - Breaking Defense
- **client_product_source.source_label**: 12 of 183
  - amgeneral.com - partner
  - amgeneral.com - partner
  - amgeneral.com - partner
- **market_tender.title**: 12 of 1626
  - część 1 zamówienia - 100 sztuk fabrycznie nowych miękkich kamizelek kuloodpornych o niskim profilu; część 2 zamówienia - 16 sztuk fabrycznie nowych kamizelek kuloodpornych typu Plate Carrier wyposażon…
  - tenue de contact; armes factices; Tenue de protection intégrale pour frappe bâton d’entraînement et son sac de transport; bouclier de frappe portatif et bâtons d’entrainement; Tenue de protection pour…
  - część 1 zamówienia - 100 sztuk fabrycznie nowych miękkich kamizelek kuloodpornych o niskim profilu; część 2 zamówienia - 16 sztuk fabrycznie nowych kamizelek kuloodpornych typu Plate Carrier wyposażon…
- **competitive_partnership_relationship_detail.source_publisher_label**: 8 of 497
  - domain-b.com
  - domain-b.com
  - army-technology.com
- **competitive_geo_source.source_label**: 4 of 715
  - gCaptain
  - bharatshakti.in
  - hartpunkt
- **market_award.title**: 2 of 503
  - zadanie nr 1 Dostawa części zamiennych do pojazdów BWP-1; zadanie nr 2 Dostawa części zamiennych do pojazdów WZT - 2; zadanie nr 3 Dostawa części zamiennych do pojazdów TATRA; zadanie nr 4 Dostawa czę…
  - część 1- techniczne środki materiałowe do 122 mm shb 2S-1; część 2- techniczne środki materiałowe do 122 mm wyrzutni WR-40 Langusta
- **competitive_project_source.source_label**: 1 of 209
  - mortar - Defence Industry Europe
