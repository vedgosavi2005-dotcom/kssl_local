# Prompt logic review (Fable 5.1, 2026-10-17)

Reviewed: `PROMPT_LOGIC_COMPETITIVE.md` (the user's brief) and `PROMPT_LOGIC.md` (the planner's draft for all three
pillars); `prompts/_shared.yml`, `FORMAT.md`, all 15 prompt files, `prompts/derive.py`, `loader.py` (key / update_only /
subject tokens), `news_merge.py`, `matchup_code.py`, `matchup_class.py`, `render.py` (context blocks); the schema list
`schema_v2_columns.txt`; `backend/areas/a_competitive.py`, `b_products.py`, `c_network.py`, `d_market_tech.py`,
`backend/review.py` (GRAPH); the pages `src/pages/competitive/*.jsx`, `src/pages/market/*.jsx`,
`src/pages/technology/Innovation.jsx`, `src/components/detailPanel/DetailPanel.jsx`, `src/lib/overview.js`,
`src/lib/geoBadge.js`. Read-only on `kssl_staging`: the latest loaded outputs of `signal`, `tech_article`,
`tender_assessment`, `global_requirement`, `top_opportunity`; the skip / reject reasons of every prompt; row counts.

Facts from the database that shape this review (2026-10-17):
- `client_product`: 83 rows in 11 categories (Excel). `technology_category` (the CATEGORIES block every prompt gets): 6
  names, in a different vocabulary ("Armoured Vehicles" vs the Excel's "Protected & Armoured Vehicles"; "Unmanned &
  Counter-UAS" vs "UAVs & Drones"; no row at all for Marine / Naval, Precision Components & Forgings, Armoured Vehicle
  MRO). The signal run that was examined said "KSSL has no ammunition product" because, when it ran, `client_product`
  had 4 rows; today it has 6 ammunition rows. The loaded signal is right by its inputs and wrong by the facts.
- `client_partner`: 0 rows. `competitive_geo_company_presence` with role client: 4 rows (from the `geo` prompt's web
  search, not from the client). So "in KSSL's market" and "supplier overlap" cannot be judged by any prompt today.
- `product_class` (the like-for-like gate): 16 client + 311 competitor rows of 83 + 4,520. `spec_dictionary`: 5,836 labels.
- Signals: 7 (6 watch, 1 threat); evidence 36 facts, 10 key points (1.4 per signal; the complaint is confirmed).
- `source_document` (raw layer): 7,643 rows (6,271 attributed). `tender_raw`: 36,402 (946 staged into `market_tender`:
  742 awarded, 104 closing, 102 open). Two `signal` runs failed on pages with no readable text; one output was invalid
  JSON; `innovation_detail` was rejected twice for writing `title`; `top_opportunity` skipped (nothing strong/partial).
- Innovations: "ATAGS 155mm towed howitzer order" is an active innovation at "parity"; "KSSL MArG 155mm" is a candidate.
- Global requirements: the US Mobile Tactical Cannon appears three times under three titles; "Canada Indirect Fires
  Modernization" twice; the Canada RFI is "open" with deadline "April (2025)".

Verdict in one paragraph. The draft is right in direction: scores with anchors, labels by code, one story mechanism, fixed
at-a-glance fields, plain English. It is not yet buildable, for four reasons that must be settled before any prompt is
rewritten: (1) the category vocabulary is split in two and the KSSL lens (markets, partners, sub-types) does not exist as
data; (2) several scales mix two things (probability and time; attractiveness and ability inputs) and have no anchors a
model can apply the same way twice; (3) story keys are left to the model, which is where duplicates come from today; (4)
a few proposals are more than the pages can show or than the data can support (a universal story table for seven
kinds of card at once; "likely reasons" a rival won; a relationship score). Sections A to G below: opinion and refinements,
schema mapping and gaps, prompt-by-prompt changes, invention risks, build order, example cards, and (G) the rule that
every filter and tag lives in a table: an inventory of the hard-coded lists in the frontend and the storage / option
source of every new tag and score.

---

## A. Opinion and refinements

### A.0 Foundations shared by every prompt

#### A.0.1 The KSSL lens: what the prompt must be given, and from where

Today `prompts/render.py:106` renders `client_products` as 83 lines of "product_name (category)". That list carries
ventures and capabilities as if they were products ("KSSL - FN Herstal MoU: small arms...", "Defence forging and precision
machining capability"), and its categories do not match CATEGORIES. A model asked "does KSSL have a product in this
category" has to translate vocabularies, and a signal in forgings, naval guns or MRO is skipped by test (c) of
`signal.yml` because no CATEGORIES name exists for it, although the supply-chain dimension of the brief is about exactly
those lines.

Decisions needed (user):
1. **One category vocabulary.** Make `technology_category` carry the Excel categories (11 rows; "Other" inactive), keep the
   old names in `canonical_name` for the technology tabs. Every prompt's CATEGORIES block, `client_product.category`,
   `competitive_product.category`, `spec_dictionary.category`, `product_class.category` then agree, and matchup,
   signal, tender assessment and global requirements can join on one string.
2. **`client_product.product_kind`** (new, text: product | variant | capability | venture), filled by the Excel loader from a
   column the client adds. The portfolio block lists products and variants; capabilities and ventures go in a separate
   short block (they matter for supply-chain and partnership impact, not for matchups).
3. **`client_product.subcategory`** (exists, empty) filled from the Excel with the `matchup_class.VOCAB` sub-type, plus
   calibre and weight class where the client knows them. 83 rows is a 30-minute job for the client and removes the model
   from classifying KSSL's own catalogue (16 of 83 done by the model today).

Context blocks to add to `_shared.yml` (rendered by `render.context_blocks`, "none on record" when empty):

| Block | Content per line | Source |
|---|---|---|
| `client_portfolio` | `category > sub_type: product (calibre; weight class; up to 3 key specs with units)` | client_product (product_kind product/variant) + product_class + client_product_specification (346 rows / 66 products) |
| `client_capabilities` | `category: name (kind)` | client_product where product_kind in (capability, venture) |
| `client_markets` | `country: sells/manufactures/sources — to whom — since — source tier` | competitive_geo_company_presence + competitive_geo_product where company_role = client |
| `client_partners` | `partner — type — what it supplies or does with KSSL — since` | client_partner + client_partner_relationship + client_partner_product |
| `competitors` (extend) | `display_name (short; country) — sub-types: ... — sells in: ...` | competitive_competitor + product_class + competitive_geo_company_presence |

`client_markets` and `client_partners` are empty today. Two ways to fill them, both needed:
- **Excel first** (client data, like products and leadership): a "KSSL markets" sheet (country, activity, customer, product,
  since, source) and a "KSSL partners" sheet (partner, type, scope, what it supplies, since, status, source), loaded by
  `backend/excel_load.py` into the presence / client_partner tables with `source_tier = 'client'`.
- **A one-off research prompt `client_partner_research`** (web search, subject = the client) as a stop-gap that the user
  reviews once, then the Excel takes over. The portfolio names already hand it ~13 partners to confirm: Elbit (BF Elbit
  Advanced Systems), IAI, Rafael (KRAS), Thales Belgium, AM General / Mandus, Arsenal JSCo, FN Herstal, BAE Systems
  (air-defence ToT), Junghans Defence, Zorya Mashproekt, Duma Engineering (Aegis), BEML, Analogic Controls. Each needs a
  quote; what each supplies is the field the overlap check will use.

Rule for every prompt until those blocks have rows: the modifiers `in_client_market` and `overlap_kind` are output as
`unknown`, never guessed from general knowledge. The loader rejects `yes`/`no` when the block was "none on record".

#### A.0.2 Facts vs judgements: one addition
Keep the draft's rule. Add an **evidence pointer**: a judgement's `_reason` must name at least one fact that is itself in
`_sources` of the same record (loader check: the reason mentions a value, label or quoted phrase of a sourced field; warn
if not). This is what stops "watch, because it is indirect" with nothing behind it. "Unknown" is a legal value of every
judgement and every modifier; a score may be null; a null never counts towards threat / pursue / threat-direction.

#### A.0.3 Plain English: make it testable, then enforce it in the loader
The brief's complaint ("language too difficult") will recur unless the rules are checkable. Proposed rules for every
text column of every pillar (`prompts/vocab.py` holds the lists; `loader.py` warns, and rejects only on the hard limits):
- Sentence length: ≤ 20 words (warn), ≤ 32 (reject). One idea per sentence. Active voice as guidance, not code.
- Banned phrases (reject): "leverage", "synergy", "ecosystem", "robust", "cutting-edge", "state-of-the-art",
  "game-changer", "going forward", "strategic imperative", "capability enhancement", "end-to-end", "strengthens its
  position", "extends its footprint", "poses a threat to", "positions itself", "KSSL should" (recommendations live only
  in Next moves and in `kssl_option` / `stance` fields that are built for them).
- Acronyms: an ALL-CAPS token of 3+ letters outside a whitelist (ATAGS, MArG, DRDO, MoD, PIB, DAC, AoN, JV, MoU, RFI, RFP,
  RFQ, UAV, UAS, UGV, MRAP, APC, IFV, MBT, SAM, ATGM, MRL, HE, USD, INR, EUR, GBP, NATO, STANAG, ToT, MRO) must be followed by
  "(...)" the first time it appears in the record (warn).
- Numbers keep their unit and their date; no conversion, no rounding (rule 1 already); "about" only when the source says so.
- No statement of absence as analysis ("KSSL has no stated route to adopt...", "no direct overlap exists") unless the field
  asks for it: `why_it_matters` names what IS touched, or says in one sentence "No KSSL product line is touched; kept
  because <dimension>".
- Reading-level proxy (warn only): average sentence ≤ 17 words and average word ≤ 5.3 letters over the record's prose.
- Three before/after pairs in the system prompt (see F for the register).

#### A.0.4 Card anatomy: fixed at-a-glance fields, and what makes a key point
Agree with the skeleton. Two corrections:
1. **At a glance = fixed fields stored as columns**, rendered first; the free `fact` rows of `competitive_signal_evidence`
   keep existing but move below the fixed fields and are capped (≤ 4 rows, value ≤ 60 characters). The UI needs no change
   for the fixed fields: `DetailPanel.jsx` renders `detail.facts` as `[label, value, quote]`, so
   `a_competitive.build_signals` can emit the six glance columns as the first six fact rows (same for
   `technology_overview_fact`, which already is a label/value table).
2. **Key points: 3 minimum, 6 maximum**, each ≤ 20 words, each carrying at least one of: a number with unit, a proper
   name that is not in the title, a date, or a condition ("option for", "subject to", "if"). A point that repeats more
   than 60 % of the title's or summary's words is dropped by the loader with a warning (that is how "often one" happens:
   the model writes the summary again and calls it the key point). Every point keeps its verbatim quote (exists).
   Good: "Option for 12 more vehicles after the first six, decided after a four-year test period." Bad: "The deal
   strengthens the company's position in the artillery market."

What a KSSL strategist wants on a card, in this order: who did what, where, with whom, when; what it touches at KSSL
(product line, market, supplier, partner); how sure and how soon; the numbers worth remembering; the source. Nothing
about the company's general strategy, nothing about "the market".

#### A.0.5 Stories and timelines: one mechanism, introduced in three places first
Agree with one table for steps. Disagree with starting it everywhere at once: projects (`competitive_project_timeline`),
partnerships (dated evidence cards), opportunities (`market_opportunity_update`) already have dated step rows and pages
that render them. Start the story mechanism where there is no timeline today and the brief asks for one: **signals**
(escalation), **product news** (the product's life), **requirements/opportunities** (dedupe and staleness). Link the
existing step tables to it later with a `story_id` column, not by moving their rows.

Model (B lists the columns): `staging.story` (one per thread; a stable `story_key`, the current label and scores, first and
last step dates) and `staging.story_step` (one per dated step: step type, one line ≤ 120 chars, the source url and the
table/row the step came from, the scores and label after this step, and `changed`, ≤ 120 chars: what is different from
the previous step).

Who assigns the key: **code proposes, the model picks, code decides.**
- `news_merge.py` already groups same-event articles (`same_as` S-handles). A story is the next level: same thread, later
  event. The daily prompt that reads an article (`signal`) receives the open stories of the same competitor (and of the
  named product / buyer) from the last 365 days, ≤ 15 candidates, each as `T<8hex>: key — last step — date`, and returns
  `story_ref` (a handle) or `new`. The loader links; a `new` whose generated key equals an existing one is linked anyway
  (exact key wins over the model).
- Key format: `<pillar>:<competitor-or-buyer-slug>:<product-or-system-slug>:<country-iso>:<family>` with family in
  {programme, order, delivery, trial, partnership, capacity, policy, demand, technology}. Blank parts stay blank
  ("competitive:hanwha:k9:pl:order"). The slug for a product is the catalogue product_id when the model resolves a
  `ref_product`, else a slug of the name.
- Escalation is code (`derive.story_label`): after each step the label rule (A.1.1) runs on the step's scores; when it
  differs from the story's current label, the story is updated, `escalated_at` set, and a step of type `label_change`
  is written with `changed = "watch -> threat: probability 3 -> 5 (contract signed)"`. De-escalation works the same way.
- The card shows the latest state plus its steps. UI: one new "Timeline" block in `DetailPanel.jsx` reading
  `detail.timeline` (date, type, line, source), ~30 lines.

#### A.0.6 Scoring: anchored 1-5, labels by code, null allowed
Agree. Three refinements: (a) every score field is `judgement: true` and has a `_reason` that names the anchor it chose
("4: selected, award expected within 12 months"); (b) the label rules live in `derive.py` with a `rule_version` stored on
the row, so a rule change can be re-derived without re-running the model; (c) impact is the maximum over dimensions, but
the dimension of the maximum and a second dimension ≥ 4 are stored, because the UI's "Impact on KSSL" field shows the
dimension, and the reviewer needs to see which one the model meant.

#### A.0.7 Cross-pillar
Agree; the join is `source_url` + `story_id`. No further mechanism is needed now.

### A.1 Competitive pillar

#### A.1.1 Signals: the risk matrix, operationally

**Probability (1-5)** that the move becomes a competitive fact. The draft mixes "how soon" into it; split it off.
- 5 done: contract signed, delivery made, JV registered, plant opened, induction completed.
- 4 decided: selected / L1 / approved with funding (DAC AoN with budget line, prototype contract with production option),
  award or signature stated as expected within 12 months.
- 3 in competition: shortlisted, in trials, RFP response submitted, MoU tied to a named programme.
- 2 intent: MoU without a programme, "plans to", "in talks", capacity announced without a customer.
- 1 report of interest, unnamed sources, analyst speculation.

**Time to effect** (separate modifier): `lt_1y` / `1_3y` / `gt_3y` / `unknown`, from stated delivery, production or service
dates only. Threat needs ≤ 3 years.

**Impact on KSSL (1-5 per dimension; stored: the maximum, its dimension, a second dimension when ≥ 4).**
- `orders_revenue`: 5 a tender or customer where KSSL is bidding or incumbent is decided or shifted (rival selected in an
  Indian Army programme KSSL competes in; price undercut stated in a KSSL tender); 4 a KSSL customer buys a like-for-like
  product from the rival; 3 a like-for-like win in a market in `client_markets`; 2 a like-for-like win outside KSSL's
  markets; 1 no like-for-like product.
- `market_standing`: 5 rival becomes preferred or sole supplier, or wins a reference with KSSL's key customer; 4 first
  export reference in a KSSL market; 3 rival gains a qualification or certification KSSL lacks; 2 reputational only; 1 none.
- `supply_chain`: 5 a KSSL supplier or partner commits capacity or exclusivity to the rival, or the rival buys a KSSL
  supplier; 4 rival books scarce capacity (barrels, forgings, propellant, explosives, titanium) or wins the same component
  supply KSSL sells; 3 rival builds in-house what KSSL supplies to it; 2 raw-material or licence news that could reach
  KSSL; 1 none.
- `technology_gap`: 5 trial evidence of a spec KSSL's like-for-like product cannot meet by a margin a buyer notices
  (range +20 %, weight -20 %, reaction time halved); 4 same, claimed or prototype; 3 parity on a spec where KSSL led;
  2 incremental; 1 none.
- `partnerships`: 5 a KSSL partner (in `client_partners`) signs a JV or exclusive tie with the rival; 4 a KSSL partner teams
  with the rival on a bid KSSL is in; 3 a prospective partner (same kind of supplier) ties with the rival; 2 partnership
  outside KSSL's lines; 1 none.
- `policy_export`: 5 a rule or approval that blocks KSSL or favours the rival in a KSSL market (indigenisation list, export
  licence, offset credit); 4 rival gets export approval to a KSSL market; 3 policy change affecting the category; 2 general;
  1 none.

**Directness modifiers** (judgement, each with the context it rests on): `subtype_match` same / adjacent / none / unknown
(from `product_class` of the named rival product against `client_portfolio`); `in_client_market` yes / no / unknown (from
`client_markets`; the customer's country, or "global" for supply-chain and policy events); `time_to_effect` as above.

**Label rule (code, `derive.signal_label`):**
```
threat  = probability >= 4
      and impact >= 4
      and time_to_effect in (lt_1y, 1_3y)
      and (in_client_market = yes  or  dimension in (supply_chain, partnerships, policy_export))
      and (subtype_match in (same, adjacent)  or  dimension in (supply_chain, partnerships))
fav     = direction = favourable and probability >= 4          # a rival's cancellation, loss, failure, exit
watch   = everything else that passed relevance (including any unknown modifier)
```
This encodes the brief exactly: "outside KSSL's markets" (`in_client_market = no`) is watch however big; "indirect"
(`subtype_match = none` with a product dimension) is watch; "will take time" (`gt_3y`) is watch. The 5x5 plot uses
probability x impact; the dot colour is the label, so a (5,5) watch outside KSSL's markets is visible as what it is.
`fav` already exists in the UI vocabulary (`DIR_WORD`); giving it a rule costs nothing and keeps the feed honest when a
rival loses.

#### A.1.2 The signal drawer
At a glance, six fixed columns on `competitive_signal_detail` (lengths are hard limits):
- `glance_who` ≤ 40: the competitor's display name.
- `glance_move` enum: Order | Contract | Selection | Delivery | Induction | Trial | Launch | JV | MoU | Acquisition |
  Capacity | Export approval | Policy | Supply deal | Cancellation.
- `glance_where` ≤ 40: country, or "customer country / buyer".
- `glance_impact` ≤ 40, built by the loader from the scores: "Orders · high" (impact 4-5 = high, 3 = medium, 1-2 = low).
- `glance_third_party` ≤ 60: the customer or partner, as named.
- `glance_when` ≤ 60: event date, then the next stated step: "5 Sep 2026 · deliveries from 2027".
Then "What happened" (2-4 sentences, stated facts), "Why it matters to KSSL" (2-4 sentences; must name a product,
category, market, partner or supplier from the context blocks; the eyebrow is the impact dimension in words), Key points
(3-6), Timeline (story steps), Sources. Image: `competitive_signal.thumbnail_url` exists and is never filled; the loader
can fill it from the article (`subject.image_url`, like `tech_article.yml` does) with no model involvement.

#### A.1.3 Competitor Moment: a roll-up of signals, not a second reading of the articles
`moment.yml` fetches 60 headlines and 5 articles per competitor every week and writes cards that overlap the daily
signals (the Adani-IRRPL deal is both a signal and a moment today, with two different analyses). Make the moment prompt
read the competitor's **signals and story steps of the last 90 days** (stored rows, no fetch), and write per move:
`signal_id` (new column), `change_note` (what changed since the previous move of this competitor, ≤ 160), the grade by code
from the signal's label (threat -> `high`, watch -> `watch`, fav -> `opportunity`; `ui.competitive_competitor_moment_level`
already has these three codes) and the "deeper analysis by view" only for views that have stored rows for this competitor
(partners, projects, geo presence, matchups). The page already sorts by date; a vertical rail with `change_note` is a
small UI addition in `ThreatAnalysis.jsx`.

#### A.1.4 Products: product news types and the product timeline
Types (final list, enum `news_type` on `competitive_product_news`): programme_order | delivery_induction |
deployment_combat_use | trial_test_demo | export_new_customer | upgrade_variant_component | production_localisation_licence
| certification_qualification | incident_failure. The draft's eight plus certification, which decides tenders.

Classification needs the article text, which `news.yml` never sees (headlines only) and `signal.yml` already fetches. So:
the `signal` run also writes `update_only` rows for the `competitive_product_news` rows that share the article's url
(news_merge writes the same story to the company table and to each product's table): `news_type`, `event_date`,
`product_variant` (≤ 60), `kssl_relevance` (≤ 200, only when the product's sub-type matches a KSSL sub-type), `story_ref`.
"A news item goes to a product when that product is involved in any way": the signal run outputs `products_mentioned`
(names from the competitor's catalogue, exact) and the loader copies the story row to each named product's news (the
gap today: an article found through the company search is never attached to the product it names).

Timeline: `Products.jsx` renders product news as a grid and "Programs" (`competitive_product_program`, 0 rows) as cards.
Sort the product's news by `event_date` with `news_type` as the step label and the grid becomes the timeline (UI: one
list variant). `competitive_product_program` can stay for Excel-supplied programmes; no prompt should fill it.

#### A.1.5 Product Evaluation: the like-for-like gate (`prompts/matchup_class.py`)
The gate exists and is sound (category -> sub-type -> calibre -> weight band, same or adjacent). Corrections and edge
cases from the vocabulary as written:
- Artillery: add `mounted_light_gun_105` (Garuda 105, Hawkeye-type): a mounted 105 is not a towed L118 and not a 155
  truck gun. Split `mortar` into `mortar_towed_manportable` and `mortar_vehicle_mounted` (a 120 mm turreted mortar is a
  vehicle system). Keep 155/39 vs 155/52 as one calibre with the barrel noted (correct: they meet in the same tenders;
  the tender requirement, not the gate, decides). Rename `self_propelled_wheeled_truck_mounted` to `wheeled_sp` and record
  `mount: integrated | truck` in the reason; a buyer of a Caesar-class gun does look at RCH 155.
- Ammunition: split `artillery_ammo` into `artillery_round_conventional`, `artillery_round_guided` and
  `shell_body_component` (KSSL sells empties: comparing an empty 155 body with a filled Excalibur is meaningless).
  Rename `fuze_component` to `fuze` and add `propellant_charge`. Nature (HE / smoke / illuminating) is a spec, not a gate.
- Small arms: fine; the calibre gate separates 5.56 CQB carbines from 9 mm. Add `designated_marksman` out of `sniper_rifle`
  only if the client asks; .338 vs .308 are already separated by calibre.
- Vehicles: Kalyani M4 is `mrap`, LSV / ULSV `light_4x4`, Maverick ATC `apc_wheeled`. Adjacent weight bands (6-15 t vs
  15-30 t) are right for MRAPs. Keep `light_tank` apart from `ifv_tracked` (the Zorawar vs M4 case).
- UAVs: the sub-types already embed weight; keep both (the band catches a mis-typed sub-type). Loitering munitions: the
  band on MTOW separates a 10 kg from a 200 kg one, which is what the brief's quad-rotor example asks.
- Naval: add calibre to `naval_weapon` for guns (57 / 76 / 127 mm; KSSL's 57 and 127 are under development) and split
  `unmanned_vessel` into `usv` and `uuv_auv` (displacement bands do not separate them).
- Forgings and MRO: no matchups (like "Other"); they matter for signals and partnerships, not for spec tables.
- `unknown` -> no pair, plus a row in `db/excel_reports/unclassified_products.csv` so the client can fix the Excel.
- Client side: fill `subcategory` from the Excel (A.0.1) and let the model classify competitors only.
Within a pair the draft is right: dictionary decides "better", code computes gaps and the edge, the model writes the
verdict for top pairs only (already the design of `matchup_code.py`). Add to the verdict prompt: "state in one sentence
what a buyer in this sub-type weighs most" from the dictionary's `better` reasons, not from general knowledge.

#### A.1.6 Partnerships
Types: JV | MoU / teaming | Contract (customer-supplier) | Supplier / sub-supplier | Licence / ToT | Co-development |
Investment / acquisition. Map the existing `partner_type` enum onto this (UI shows the stored word).
Value analysis: two short fields with tags: `value_to_competitor` and `value_to_partner`, each "tag: one line ≤ 160" with
tag in {market_access, technology, capacity, financing, credibility, offsets, other}; `kssl_read` ≤ 300 (what it means for
KSSL: competes with / opens a door for / threatens a KSSL partnership, naming which).
Overlap: **code first**. `partner_name` (casefold, legal-form suffixes stripped, alias table) against
`client_partner.partner_name / legal_name` gives `overlap_client_partner_id`. Only then the model, given that KSSL
partner's `client_partner_product` rows, judges `overlap_kind` same_component | same_partner_other_scope | kssl_market |
none | unknown, `overlap_component` (what it supplies to whom, ≤ 160), `overlap_effect` risk | advantage | both | unknown
with a reason naming the two supply facts. With `client_partner` empty every overlap is `unknown` and the page says
"KSSL partner list not loaded" instead of nothing (one line in `Partnerships.jsx`).
Status and timeline: `status` announced | active | ended | unknown on the partnership; the evidence cards already carry
`as_of_date`; add `step_type` to them (mou | agreement | jv_formed | first_product | order | delivery | ended) and the
page sorts the cards by date as the tie's timeline.

#### A.1.7 Geo footprint
Layer 1 vocabulary: replace the four activity values with five that say what the brief asks: Sells | Manufactures |
Licensed production | Sources | Sales and service. The column stays `activity_type` (the pages show it as stored;
`geoBadge.activityClass` needs its four colour codes re-mapped). Add `customer_name` and `local_partner` (≤ 120 each) on
`competitive_geo_product`; `since_date` exists. KSSL's own footprint comes from the Excel sheet (A.0.1), with the `geo`
client run as a fallback only.
Layer 2, three findings, each evidence-gated and pre-computed by code where possible:
- **overlap**: same sub-type (product_class) sold by KSSL and a rival in the same country: `competitive_geo_product_match`
  already carries it; keep.
- **anomaly**: code lists candidates: a rival `Sells` row in country X with a `since_date` in the last 5 years, where a
  stored matchup between that product and a KSSL product has `decision_level = 3` (KSSL ahead), and KSSL has no `Sells`
  row in X for that sub-type (or has one dated earlier). Only for candidates does a prompt (web search on) look for **a
  source that states why the buyer chose the rival**; it outputs `stated_reasons` (multi-select: incumbency,
  offsets_local_content, financing_g2g, delivery_time, local_partner, after_sales, politics, price, performance, other) each
  with its quote, or `reason_state = not_stated` plus `to_find_out` (≤ 160: the question a KSSL salesperson should ask).
  A separate, clearly labelled `hypothesis` (≤ 200, judgement, shown greyed as "analyst hypothesis, no source") is the
  only place "likely reasons" may appear, and it must name the facts it rests on (e.g. "the rival has a plant in X since
  2019; KSSL has no presence row"). That honours the brief without letting a model invent incumbency.
- **whitespace**: code only: countries where a comparable rival sells sub-type S and KSSL has no row. No prompt.
New table `competitive_geo_analysis` (B); UI: an "Analysis" block in the country drawer of `Geo.jsx` (~40 lines).

#### A.1.8 Projects
A project is already a story with its own steps (`competitive_project_timeline`). Three changes: extend
`ui.ui_project_stage_step` (Concept, Trials, Contract, Production) with Deliveries and In service (the prompt reads the
table, nothing else changes); add `kssl_option` (compete | partner | supply | none | unknown) with a reason, which is the
"what KSSL can do" the draft asks for; and let the daily `signal` run propose `project_ref` (exact project title from a
KNOWN PROJECTS block of the same competitor) so a new article appends a timeline row and updates the stage without
waiting for the quarterly research run (the `ref_opportunity` extension pattern of `opportunity.yml` already does this
in the loader).

### A.2 Market pillar

#### A.2.1 Top opportunity: attractiveness x ability to win
The draft's axes are right; the inputs need separating so that code can rank. Proposed:
- **Attractiveness (1-5)** = round(mean(`value_score`, `strategic_score`)), each a judgement with anchors.
  `value_score`: 5 stated value ≥ USD 100 m (or ≥ 50 units of a KSSL-class system); 4 25-100 m; 3 5-25 m; 2 < 5 m or
  unknown with a small quantity; 1 service / spares only. `strategic_score`: 5 a KSSL target market (client_markets) with
  follow-on stated (framework, options, phases); 4 new reference customer in a KSSL category; 3 repeat market, one-off;
  2 outside KSSL's markets with no follow-on; 1 none. `time_to_award` (≤ 6 m / 6-18 m / > 18 m / unknown) orders ties.
- **Ability to win (1-5)** = code: start from fit (strong -> 5 if `fit_percent` ≥ 75 else 4; partial -> 3; weak -> 1);
  -1 per eligibility item `not_met` that is fixable (registration, local agent, bid security), -2 for a hard bar
  (domestic manufacturer only, nationality, security clearance KSSL cannot get), floor 1; -1 when ≥ 2 rivals have a
  strong fit and one is the incumbent (from geo `Sells` rows with the buyer); +1 when KSSL or a KSSL partner has a
  presence row with the buyer's country; clamp 1-5. Relationship is otherwise unknown and counts 0.
- **Eligibility is a checklist, not a score**: new table `market_tender_eligibility` (item, state met | not_met | unknown,
  fixable yes | no | unknown, note, quote). The assessment prompt fills it from the extracted eligibility requirement rows.
- **Label (code)**: pursue A ≥ 3 and W ≥ 4; position A ≥ 3 and W = 3, or A ≥ 4 and W = 2 with every `not_met` item fixable;
  monitor A ≤ 2 with fit strong/partial, or W ≤ 2 otherwise; pass fit weak or any hard bar. Stored as `pursue_label`;
  `lean_code` keeps its colour mapping (pursue -> go, position -> maybe, monitor -> new `watch`, pass -> pass).
- **Next move**: one action with a due date from the tender's dates, kind in {register, request_documents, clarify,
  find_partner, confirm_eligibility, prepare_bid, monitor}; the prompt writes it only for pursue / position rows.
The weekly `top_opportunity` prompt then copies nothing: ranking is SQL over the stored scores (a derive step), and the
model writes only `decides` and the next moves for the top 15. Today it skipped because nothing was strong or partial;
with the Ammunition and Small Arms products now in the catalogue the hand-smoke-grenade RFI and the 105 mm illumination
shells tender are assessable.

#### A.2.2 Tenders: extraction, assessment, timeline
Extraction (`tender.yml`) is good. Add rows of `requirement_type` "Eligibility: ..." and "Evaluation: ..." so the checklist
has sources; add `clarification_deadline` and `opening_date` to `market_tender_closing_window` (today they are text in
`milestone_text`). Before any assessment, code pre-filters `tender_raw` (36k rows, `cpv_codes`, `defence_tags`) so only
defence notices in a client category are staged; the assessment subject already requires `category_id`.
Assessment: per-line checks exist (transient `check`); add the eligibility table; rivals come from code candidates
(competitors with a same-sub-type product and a presence row in the buyer's country), which the prompt ranks and explains.
Award linking: `market_tender_source.url_kind = award` exists; add `awarded_to`, `award_date`, `award_value_text` on
`market_tender` (already in ANSWERS.md §5). A derive step `award_to_signal` creates a competitive signal by rule when the
awardee resolves to a competitor (probability 5; impact orders 4 if KSSL assessed the tender strong/partial, else 3;
`in_client_market` from the buyer's country) and a geo `Sells` row. No model call: the facts are all on the row.

#### A.2.3 Global requirements: stage, staleness, duplicates
Stage enum replacing `status` (open | monitored | closed): need_stated | approved_funded | rfi | rfp_tender |
downselect_prototype | production_award | delivered | cancelled, plus `stage_date` and `last_confirmed` (the newest source
date). The US Mobile Tactical Cannon shows why: the prototype award was recorded as "closed" although the production
decision is four years away; with the enum it is `downselect_prototype`. Staleness by code: `status_state` =
unconfirmed when `last_confirmed` is older than 9 months for stages ≤ rfi, 3 months for rfp_tender; the page prints
"status unconfirmed since <date>". Duplicates by code before the prompt: candidates with the same buyer country +
category + normalised system words ("mobile tactical cannon", "indirect fires") are shown to the model as KNOWN
REQUIREMENT with a handle, and the record must say `ref_requirement` or `new`; the loader links an exact key either way.
Rivals positioned: child table `market_global_requirement_rival` (competitor, product, basis selected | shortlisted |
offered | presence, quote). KSSL fit uses the same gate and check logic as the tender assessment (one shared task block
in `_shared.yml`, so the two prompts cannot drift).

#### A.2.4 Opportunities (from news)
Same stage enum; `market_opportunity_update` is already the timeline (its `update_type` becomes the stage vocabulary);
add `requirement_id` and `tender_id` so an opportunity is linked to the requirement or tender it belongs to (code
candidates by buyer + category, model picks). The relevance gate is good; keep it.

#### A.2.5 Market intelligence counts
Agree: SQL roll-ups into `market_category_summary`, never a prompt.

### A.3 Technology pillar

#### A.3.1 Articles: classification, maturity x relevance, direction by code
Classification: competitor_advance | adoptable | threat_to_position | industry_trend (the UI's two tiles map the first
two; the other two need a third tile "Trends and threats", `overview.js:TECH_KIND`). The binary forced the Zorawar
procurement story into `competitor_advance` and made the narrative explain what KSSL cannot adopt.
Maturity 1-5 as the draft (concept / prototype / trials / production / fielded), anchored on the article's stated event.
Relevance 1-5: 5 same sub-type as a KSSL product and a figure on a spec KSSL competes on (range, accuracy, weight,
protection, reaction time, cost); 4 same sub-type without a figure, or adjacent sub-type with a figure; 3 same category,
other sub-type, or an enabling technology KSSL's suppliers would need; 2 adjacent category; 1 general.
Horizon: `lt_2y` | `2_5y` | `gt_5y` | `unknown` from stated dates; when none, code derives it from maturity (5 -> lt_2y,
3-4 -> 2_5y, 1-2 -> gt_5y) and marks `horizon_source = rule`.
Direction (code): threat if classification in (competitor_advance, threat_to_position) and relevance ≥ 4 and maturity ≥ 3;
fav if adoptable and relevance ≥ 3; watch otherwise. Touches: `touches_client_product_id` + `spec_touched` (≤ 60).
KSSL position: behind | parity | ahead | unknown, allowed only when a CLIENT PRODUCT SPEC row exists for `spec_touched`.
At a glance: the six fields (What ≤ 60, Who, Maturity label, Horizon, Touches, KSSL position) written by the loader as
`technology_overview_fact` rows (the `rows:` loader_only pattern of `innovation_detail.yml`), so the drawer shows them
with no UI change. Key points 3-6 with quotes (exists as 3-5).

#### A.3.2 Innovations
Gate by code first: a candidate whose title contains a client product name or a competitor catalogue product name
(casefold, ≥ 2 shared tokens) is rejected as "a product, not a technology" (this removes ATAGS, MArG and XM1776 from the
pipeline without a prompt change). The discovery prompt gets `technology_kind` (material | energetics | propulsion |
guidance_fuze | autonomy_ai | sensor | protection | manufacturing_process | platform_architecture | c2_software) and must
write one sentence "what is new" that names the technology, not the system. Detail: `maturity_level` 1-5 beside the
text label; `client_position` with `unknown`; `stance` watch | partner | license | develop | ignore with a reason, gated:
develop only when behind and relevance ≥ 4; partner / license only when the developer is not a competitor. Timeline:
`technology_innovation_milestone` (date, step announced | prototype | trials | contract | production | fielded, note,
source url). Loader tolerance: ignore a `title` equal to the stored one instead of rejecting the record (two rejections
in the test run were exactly that).

#### A.3.3 Patents
`category_label` on `competitive_patent_filing` (today the label lives only in the run log); a code roll-up
`competitive_patent_trend` (portfolio, category, year, count); a spike rule (last 12 months ≥ 2x the prior 24-month
average and ≥ 5 filings) that writes a `technology_overview_article` row with classification industry_trend, direction
watch, the filings as sources, and a one-paragraph summary from a small prompt over the filing titles. Nothing else.

---

## B. Schema mapping and gaps

Legend: **reuse** = existing column the pages already render; **add** = new column/table (type; table). Ids follow the
table's style (bigint hash or uuid5, both deterministic in the loader). Every new table must be registered in
`backend/review.py` GRAPH (parent link) and in the DDL under `db/setup/` for staging and serving.

### B.1 Shared
| Need | Reuse | Add |
|---|---|---|
| Stories | - | `story` (story_id bigint pk, story_key text unique, pillar text, kind text, competitor_id uuid, product_id uuid, buyer_name text, country_code char(2), title text, current_label text, probability smallint, impact smallint, impact_dimension text, first_step_at date, last_step_at date, escalated_at date, rule_version text) |
| Story steps | - | `story_step` (step_id bigint pk, story_id, step_no int, step_date date, step_type text, one_line varchar(120), changed varchar(120), source_url text, source_table text, source_row_id text, probability smallint, impact smallint, label_after text, run_id uuid) |
| Link cards to stories | - | `story_id bigint` on competitive_signal, competitive_product_news, competitive_competitor_moment, competitive_project, market_opportunity, market_global_requirement, technology_overview_article |
| Plain-English checks | - | none (loader warnings in `prompt_run.details`) |
| Category vocabulary | technology_category.category_name, canonical_name | rows for the Excel categories; `client_product.product_kind` varchar(20); `client_product.subcategory` (exists) filled |
| KSSL lens | competitive_geo_company_presence (client rows), client_partner* | Excel sheets + loader; `client_partner_product.component text` if "what it supplies" needs more than `scope` |

### B.2 Competitive
| Requirement | Reuse (rendered by) | Gap (add) |
|---|---|---|
| Signal label | competitive_signal.classification (feed pill) | `direction` varchar(12) adverse/favourable |
| Risk matrix | - | on competitive_signal: `probability smallint`, `impact smallint`, `impact_dimension varchar(20)`, `impact_dimension_2 varchar(20)`, `time_to_effect varchar(10)`, `subtype_match varchar(10)`, `in_client_market varchar(10)`, `rule_version varchar(10)`; UI: matrix plot on Overview |
| At a glance | signal_evidence 'fact' rows (DetailPanel facts) | on competitive_signal_detail: `glance_who varchar(40)`, `glance_move varchar(20)`, `glance_where varchar(40)`, `glance_impact varchar(40)`, `glance_third_party varchar(60)`, `glance_when varchar(60)`; backend emits them as the first fact rows (no UI change) |
| Image | competitive_signal.thumbnail_url (DetailPanel image) | loader `thumbnail_url: subject.image_url` (subject query selects `n.image_url`) |
| What / why / key points / sources | detail.what_article_says, why_it_matters, impact_eyebrow; evidence key_point rows; source_name/url | loader rule: key_point count 3-6, dedupe against title/summary |
| Timeline / escalation | - | story + story_step; `escalated_at` on story; UI: Timeline block in DetailPanel |
| Moment as roll-up | competitive_competitor_moment.* (ThreatAnalysis) | `signal_id uuid`, `change_note varchar(160)`, `story_id` |
| Product news types + timeline | competitive_product_news.category, published_date (Products news grid) | `news_type varchar(40)`, `event_date date`, `product_variant varchar(60)`, `kssl_relevance varchar(200)`, `story_id`; UI: timeline sort/labels |
| Matchup gate | product_class (staging only), competitive_matchup.match_basis | vocabulary edits in matchup_class.py; `db/excel_reports/unclassified_products.csv` |
| Partnership types / value / overlap | competitive_partnership.partner_type, description, relationship_scope; relationship_detail | `status varchar(12)`, `value_to_competitor varchar(200)`, `value_to_partner varchar(200)`, `kssl_read varchar(300)`, `overlap_client_partner_id bigint`, `overlap_kind varchar(30)`, `overlap_component varchar(160)`, `overlap_effect varchar(12)`; on partnership_evidence `step_type varchar(20)`; UI: value/overlap block, evidence as timeline |
| Geo layer 1 | competitive_geo_company_presence.activity_type, relationship_text; competitive_geo_product.since_date, quantity, reported_value | new activity vocabulary; on competitive_geo_product `customer_name varchar(120)`, `local_partner varchar(120)`; Excel sheet for KSSL rows |
| Geo layer 2 | competitive_geo_product_match (overlap) | `competitive_geo_analysis` (analysis_id, location_id, competitor_id, geo_product_id, kssl_product_id, kind overlap/anomaly/whitespace, finding varchar(300), stated_reasons text[], reason_state varchar(12), hypothesis varchar(200), to_find_out varchar(160), source_url, matchup_id); UI: Analysis block in Geo country drawer |
| Projects as timelines | competitive_project_timeline, competitive_project_stage, latest_milestone | stage steps Deliveries / In service in ui.ui_project_stage_step; `kssl_option varchar(12)` + reason (fact_source); `story_id` |

### B.3 Market
| Requirement | Reuse | Gap (add) |
|---|---|---|
| Attractiveness x ability | market_tender_fit_assessment.fit_grade, fit_score, fit_rank; market_tender.lean_code, kssl_fit, rank_position | on market_tender_fit_assessment: `value_score smallint`, `strategic_score smallint`, `attractiveness smallint`, `ability smallint`, `pursue_label varchar(10)`, `time_to_award varchar(10)`, `rule_version`; same five on market_opportunity_fit_assessment; UI: chart on Top opportunity; lean_code gains `watch` |
| Eligibility checklist | market_tender_requirement rows (type Eligibility) | `market_tender_eligibility` (eligibility_id, tender_id, item varchar(120), state met/not_met/unknown, fixable yes/no/unknown, note varchar(200), requirement_id) |
| Rivals | market_tender_competitor_fit (exists, rendered) | `basis varchar(20)` selected/shortlisted/offered/presence |
| Next move | market_next_move (exists) | `move_kind varchar(20)` |
| Tender timeline / award | market_tender_closing_window; market_tender_source.url_kind | on market_tender: `awarded_to varchar(200)`, `award_date date`, `award_value_text varchar(120)`; on closing_window: `clarification_deadline date`, `opening_date date`; derive `award_to_signal` |
| Requirement stage / stale | market_global_requirement.status, deadline | `stage varchar(24)`, `stage_date date`, `last_confirmed date`, `status_state varchar(12)` (code), `story_id`; child `market_global_requirement_rival` (rival_id, requirement_id, competitor_id, product_id, basis, note) |
| Opportunity links | market_opportunity_update (timeline) | `requirement_id bigint`, `tender_id bigint` on market_opportunity; stage enum on `stage` |

### B.4 Technology
| Requirement | Reuse | Gap (add) |
|---|---|---|
| Article classes / scores | technology_overview_article.classification, direction | classification enum extended; `maturity smallint`, `relevance smallint`, `horizon varchar(10)`, `horizon_source varchar(6)`, `touches_client_product_id bigint`, `spec_touched varchar(60)`, `client_position varchar(10)`, `rule_version`; UI: third tile, maturity x relevance chart |
| Article at a glance | technology_overview_fact (fact_key/ui_label/fact_value) | fact_key enum + what/who/maturity/horizon/touches/position rows written by loader |
| Innovation scores / stance / timeline | technology_innovation.maturity, client_position, horizon_year; technology_innovation_status | `maturity_level smallint`, `technology_kind varchar(30)`, `stance varchar(10)` (+ reason via fact_source); `technology_innovation_milestone` (milestone_id, innovation_id, step_date, step_type, note varchar(160), source_url) |
| Patents | competitive_patent_filing, competitive_patent_classification | `category_label varchar(80)` on filing; `competitive_patent_trend` (portfolio_id, category_label, year, filing_count) |

---

## C. Prompt-by-prompt change list

Conventions for every rewrite: task text in the plain-English register with three example pairs; every score and modifier
is `judgement: true` with `_reason`; `unknown` allowed; the new context blocks of A.0.1; `source_document.body_text` as the
document when the article is in the raw layer (`{from: sql}`), the url fetch as fallback (two runs failed on unreadable
pages).

**_shared.yml**: add the plain-English rules and examples to the system prompt; add context blocks `client_portfolio`,
`client_capabilities`, `client_markets`, `client_partners`, the extended `competitors`; one shared task block
`FIT_CHECK` (per-line met / not_met / unknown rules) used by tender_assessment and global_requirement.

**news.yml** (v4): unchanged grouping; add `story_ref` per story from a STORIES block (open stories of the competitor,
handles T...), `new` otherwise; `news_merge.py` links or creates the story by key. No UI change.

**signal.yml** (v2): subject query selects `n.image_url` and the product-news rows sharing the url; documents: raw body
text first; context: new blocks + KNOWN PROJECTS of the competitor + STORIES candidates. Task: relevance as today (with
the unified categories); then `probability`, per-dimension impact (`impact_*` six judgements, loader keeps max and
dimension), `time_to_effect`, `subtype_match`, `in_client_market`, `direction`; the six glance fields; what / why; 3-6 key
points; `story_ref`; `project_ref`; `products_mentioned`; `product_news` child rows (update_only: news_type, event_date,
product_variant, kssl_relevance). Output rules: enums above, lengths above; `classification` becomes loader-derived
(`derive.signal_label`), `thumbnail_url: subject.image_url`. UI: matrix plot, Timeline block; glance via backend facts.

**moment.yml** (v3): subject per competitor; documents = its signals + story steps (90 days), no fetch; task: one row per
signal with `change_note`, deeper analysis only for views with rows; `grade` derived from the signal label. UI: rail.

**partnership.yml** (v3): types enum; `status`; value fields; overlap fields fed by the code match
(`overlap_client_partner_id` resolved by the loader before the call and shown in the prompt as KSSL PARTNER MATCH with its
products); evidence `step_type`. UI: value/overlap block; evidence as timeline; "partner list not loaded" line.

**geo.yml** (v3): activity vocabulary; `customer_name`, `local_partner`; client subject removed when the Excel sheet
exists. New **geo_analysis.yml**: subject = anomaly candidates computed by SQL (A.1.7); web search on; outputs
`competitive_geo_analysis` rows with stated reasons + quotes, or `not_stated` + `to_find_out`, and the labelled hypothesis.
UI: Analysis block.

**project.yml** (v2): stage steps from the extended ui table; `kssl_option` + reason; `story_id`. No UI change beyond the
two new stage names.

**matchup.yml**: unchanged except the "what a buyer weighs" sentence sourced from the dictionary; the gate changes are in
`matchup_class.py` (vocabulary) and the Excel (client sub-types).

**tender.yml** (v2): eligibility / evaluation requirement rows; `clarification_deadline`, `opening_date`; award notices
write `awarded_to`, `award_date`, `award_value_text`; derive `award_to_signal`.

**tender_assessment.yml** (v2): shared FIT_CHECK; eligibility table; `value_score`, `strategic_score`, `time_to_award`
judgements; rivals from code candidates with `basis`; loader derives ability, attractiveness, `pursue_label`
(`derive.pursue_label`). UI: checklist and scores on the tender drawer; chart on Top opportunity.

**top_opportunity.yml** (v2): ranking by SQL (derive step `top_opportunity_rank`); the prompt gets the top 15 rows and
writes `decides` and next moves (`move_kind`, due date from the row) only. `replace: all_rows` stays.

**opportunity.yml** (v3): stage enum; `requirement_id` / `tender_id` via candidate handles; `story_ref`.

**global_requirement.yml** (v3): stage enum + `stage_date` + `last_confirmed`; KNOWN REQUIREMENT handles with
`ref_requirement`; rivals child table; shared FIT_CHECK; loader derives `status_state`. UI: "unconfirmed since" line.

**tech_article.yml** (v2): four classes; `maturity`, `relevance`, `horizon`, `touches_client_product`, `spec_touched`,
`client_position`; direction derived (`derive.tech_direction`); glance rows by loader; key points 3-6; `story_ref`.
UI: third tile, chart.

**innovation_discovery.yml** (v2): code gate against product names before loading; `technology_kind`; "what is new"
sentence. **innovation_detail.yml** (v3): `maturity_level`, `stance` + reason, milestones child; loader ignores an
unchanged `title`.

**patent_classification.yml** (v2): writes `category_label` on the filing (update_only, already the pattern); new
derive `patent_trend` + optional **patent_trend_summary.yml** (one paragraph over titles).

New one-off **client_partner_research.yml** (A.0.1) until the Excel sheet exists.

---

## D. Where a model will invent, and the guard

| Invention | Where it shows | Guard |
|---|---|---|
| Reasons a rival won a tender ("incumbency", "offsets") | geo layer 2, project assessment | reasons only as a multi-select with a quote each; else `not_stated` + `to_find_out`; the hypothesis field is separate, labelled, greyed in the UI, and must name stored facts |
| Probability numbers from tone ("likely", "poised") | signals, opportunities | anchors keyed to procurement states; `_reason` must cite the anchor and the sourced fact (evidence pointer); null when the state is not stated |
| "In KSSL's market" / "KSSL partner" from general knowledge | signals, partnerships | modifiers may be yes/no only when the block had rows; loader rejects otherwise; `unknown` is the default |
| KSSL position (behind / parity / ahead) without specs | technology, innovations, geo matches | allowed only when a CLIENT PRODUCT SPEC row exists for the spec named; else `unknown` |
| Dates: month-only turned into a day; "soon" turned into a year | every timeline | `_precision` already exists; horizon from rules is marked `horizon_source = rule`; "soon" -> `unknown` |
| Products counted as innovations | innovation pipeline | code gate on catalogue names before load; `technology_kind` required |
| Key points that restate the summary | signal, tech drawers | loader dedupe (token overlap) + the "one fact per point" rule; minimum 3 |
| Revenue estimates | tenders, top opportunity | columns stay null (already decided); `value_score` uses the stated value or quantity only |
| Category by company, not by item | signals, patents, tenders | "do not guess from the company's business" already in patent_classification; copy it to signal and tender; one vocabulary |
| Duplicated requirements / stories under new titles | global requirements, stories | code candidates with handles; exact key wins over the model's "new" |
| Narrative about what is absent | tech_article `client_narrative`, signal `why_it_matters` | the plain-English rule: name what is touched, or one fixed sentence |
| Invalid or oversized JSON | any | shorter outputs (child-row caps), `max_tokens` headroom, and the loader's existing reject path; log the failure as a skip reason the reviewer sees |

---

## E. Build order (biggest quality gain first, so the flood can start)

1. **Vocabulary and lens data (no prompt change, unblocks every judgement):** align `technology_category` with the Excel
   categories; `product_kind` and `subcategory` from the client Excel; KSSL markets and partners sheets (or the one-off
   research prompt) into `competitive_geo_company_presence` / `client_partner*`; run `matchup_class` for all competitor
   products. Add the four context blocks in `_shared.yml` / `render.py`.
2. **Loader and derive foundations:** score / modifier / glance columns (B); `derive.signal_label`, `pursue_label`,
   `tech_direction`; plain-English checks; key-point dedupe; `story` + `story_step` with code-assigned keys and
   `derive.story_label`; `thumbnail_url` from the article; raw-layer documents (`source_document.body_text`).
3. **Rewrite `signal` (daily, the most visible card) with product-news classification and story linking; `news` v4.**
   Test on the 81 stored articles, then the raw layer (7,643 documents).
4. **`tech_article` v2** (same pattern, shares the story and glance mechanics).
5. **Market:** `tender` v2 + `tender_assessment` v2 + eligibility + scores; `top_opportunity` becomes ranking by code;
   `award_to_signal`. Then `global_requirement` v3 and `opportunity` v3 (stage, stale, dedupe).
6. **Roll-ups:** `moment` v3 from signals; `project` v2; `partnership` v3 with overlap; `geo` v3 + `geo_analysis`.
7. **Innovations gate + stance + milestones; patent trend.**
8. **UI, in the order the data arrives:** glance via backend facts (none), Timeline block, risk matrix, product timeline
   sort, partnership value/overlap block, Geo analysis block, tender checklist + scores, Top-opportunity chart, technology
   third tile + chart.

Steps 1-3 give the Overview a card that is right about KSSL's own portfolio, in plain English, with a matrix position and a
timeline; that is the visible gain the user asked for. Steps 5-7 depend on step 1's data, not on each other.

---

## F. Example cards (fictional companies, programmes and figures; KSSL products are real names)

### F.1 Competitive signal (as `signal` v2 should output it)
```json
{"prompt_id": "signal", "subject": "Nordvik Defence: Veland orders 24 NV-155 wheeled guns", "skip_reason": null,
 "records": [{"table": "competitive_signal", "values": {
   "ref_competitor": "Nordvik Defence",
   "title": "Veland orders 24 NV-155 wheeled guns from Nordvik Defence",
   "summary": "Veland's army signed for 24 NV-155 truck-mounted 155 mm guns, with deliveries from 2028. KSSL offered the MArG 155/52 in the same competition.",
   "event_date": "2026-10-09", "ref_category": "Artillery", "direction": "adverse",
   "probability": 5, "time_to_effect": "1_3y", "subtype_match": "same", "in_client_market": "yes",
   "impact_orders_revenue": 5, "impact_market_standing": 4, "impact_supply_chain": 1, "impact_technology_gap": 2,
   "impact_partnerships": 1, "impact_policy_export": 2,
   "story_ref": "T3f9a12c0", "project_ref": null, "products_mentioned": ["NV-155"],
   "_reason": {"probability": "5: the contract is signed (anchor: done).",
               "impact_orders_revenue": "5: KSSL bid the MArG 155/52 in this competition (client_markets: Veland, offered 2025) and the rival was chosen.",
               "subtype_match": "NV-155 is a truck-mounted 155 mm gun (wheeled_sp); MArG 155/52 is wheeled_sp, 155 mm.",
               "in_client_market": "Veland is in client_markets (offer 2025, no sale)."},
   "_sources": {"title": [{"url": "https://example-defence-news.test/veland-nv155", "quote": "Veland's Ministry of Defence signed a contract on 9 October for 24 NV-155 systems."}],
                "event_date": [{"url": "https://example-defence-news.test/veland-nv155", "quote": "signed a contract on 9 October"}]}},
  "children": {
   "competitive_signal_detail": [{
     "drawer_title": "Veland picks Nordvik's NV-155 over KSSL's MArG 155/52: 24 guns, deliveries from 2028",
     "glance_who": "Nordvik Defence", "glance_move": "Contract", "glance_where": "Veland",
     "glance_third_party": "Veland Ministry of Defence", "glance_when": "9 Oct 2026 · deliveries 2028-2030",
     "impact_eyebrow": "Orders and revenue · high",
     "what_article_says": "Veland's Ministry of Defence signed a contract on 9 October for 24 NV-155 truck-mounted 155 mm guns. The value is EUR 310 million. Deliveries run from 2028 to 2030. Nordvik will assemble the trucks at a local partner, Veland Motor Works.",
     "why_it_matters": "KSSL offered the MArG 155/52 in this competition in 2025. The buyer chose a gun of the same class with a shorter stated range (40 km against 48 km for MArG 155/52). The article gives no reason for the choice. Nordvik now has a reference customer in a market KSSL targets.",
     "source_name": "Example Defence News", "source_url": "https://example-defence-news.test/veland-nv155"}],
   "competitive_signal_evidence": [
     {"evidence_group": "key_point", "label": "Value", "value": "EUR 310 million for 24 guns, about EUR 13 million each including training and spares.", "quote": "The contract is worth EUR 310 million and covers training and an initial spares package."},
     {"evidence_group": "key_point", "label": "Local assembly", "value": "Final assembly at Veland Motor Works, a local company, which the ministry called a condition of the deal.", "quote": "Final assembly will take place at Veland Motor Works, a condition the ministry set for all bidders."},
     {"evidence_group": "key_point", "label": "Option", "value": "An option for 12 more guns can be taken until the end of 2029.", "quote": "The contract includes an option for 12 additional systems until the end of 2029."},
     {"evidence_group": "key_point", "label": "Range stated", "value": "The ministry quoted 40 km with base-bleed ammunition as the accepted range.", "quote": "The accepted range is 40 km with base-bleed ammunition."},
     {"evidence_group": "fact", "label": "Customer", "value": "Veland Ministry of Defence", "quote": "Veland's Ministry of Defence signed a contract"},
     {"evidence_group": "fact", "label": "Quantity", "value": "24 guns (+12 option)", "quote": "24 NV-155 systems"}],
   "competitive_product_news": [{"ref_product": "NV-155", "news_type": "programme_order", "event_date": "2026-10-09",
     "product_variant": null, "kssl_relevance": "Same class as MArG 155/52; chosen over it in Veland."}]}}],
 "not_found": ["competitive_signal_detail.glance_when.next_step"], "conflicts": []}
```
Rendered at a glance: Who Nordvik Defence · Move Contract · Where Veland · Impact on KSSL Orders · high · Third party
Veland Ministry of Defence · When 9 Oct 2026, deliveries 2028-2030. Label by code: probability 5, impact 5 (orders),
1-3 y, same sub-type, in KSSL's market -> **threat**. Timeline: 2025-06 "KSSL and Nordvik offer in Veland competition"
(earlier watch step, probability 3) -> 2026-10-09 "contract signed" -> label_change "watch -> threat".

### F.2 Tender / top opportunity (as `tender_assessment` v2 writes it; ranking by code)
```json
{"prompt_id": "tender_assessment", "subject": "Republic of Marendo MoD RFP MR-ART-2026-07: 36 mounted 155 mm/52 gun systems",
 "records": [{"table": "market_tender_fit_assessment", "values": {
   "fit_grade": "strong", "ref_client_product": "MArG 155 mm/52 cal Mounted Gun System (soft recoil, AM General partnership)",
   "match_summary": "MArG 155/52 meets the calibre, barrel length, range and crew lines. Weight is not stated for MArG, so that line is unknown.",
   "assessment_rationale": "Marendo wants 36 mounted 155 mm/52 guns with a 40 km range, delivered within 36 months, and 30 percent local content. MArG 155/52 meets every technical line that has a figure. Local content is not met today; the RFP allows a local partner. Bid security is 2 percent of the bid value.",
   "value_score": 4, "strategic_score": 4, "time_to_award": "6_18m",
   "_reason": {"fit_grade": "No not_met on a defining line (calibre 155, barrel 52 cal); 5 of 6 checks met.",
               "value_score": "4: the RFP states an indicative budget of USD 420 million (anchor 25-100 m per... no: anchor ≥ 100 m is 5; the budget covers 36 units plus a 10-year support package, so the equipment share is scored 4).",
               "strategic_score": "4: Marendo is a new reference customer in Artillery; no follow-on phase is stated.",
               "time_to_award": "RFP closes 2027-02-15; award stated for Q3 2027."}},
  "children": {
   "market_tender_product_match": [{"ref_client_product": "MArG 155 mm/52 cal Mounted Gun System (soft recoil, AM General partnership)", "fit_grade": "strong",
     "children": {"market_tender_product_match_line": [
       {"line_label": "Calibre", "line_value": "155 mm | required: 155 mm", "check": "met"},
       {"line_label": "Barrel length", "line_value": "52 cal | required: 52 cal", "check": "met"},
       {"line_label": "Maximum range", "line_value": "48 km (ERFB-BB) | required: 40 km", "check": "met"},
       {"line_label": "Crew", "line_value": "6 | required: not more than 6", "check": "met"},
       {"line_label": "Shoot-and-scoot", "line_value": "into action under 90 s | required: under 2 min", "check": "met"},
       {"line_label": "System weight", "line_value": "no spec on file | required: under 30 t", "check": "unknown"}]}}],
   "market_tender_eligibility": [
     {"item": "Local content 30 percent", "state": "not_met", "fixable": "yes", "note": "The RFP accepts a local assembly partner; KSSL has no presence row in Marendo.", "quote": "A minimum of 30 percent local content, which may be achieved through a local partner."},
     {"item": "Bid security 2 percent", "state": "unknown", "fixable": "yes", "note": "Standard bank guarantee.", "quote": "Bid security of 2 percent of the bid value."},
     {"item": "Registered on the Marendo procurement portal", "state": "not_met", "fixable": "yes", "note": "Registration takes up to 30 days per the notice.", "quote": "Bidders must be registered on the portal before submission."}],
   "market_tender_competitor_fit": [
     {"ref_competitor": "Nordvik Defence", "ref_product": "NV-155", "fit_label": "strong", "basis": "presence", "fit_rationale": "NV-155 states 155 mm/52 and 40 km, meeting the lines; Nordvik sells in Marendo since 2022 (geo)."},
     {"ref_competitor": "Hanwha Aerospace", "ref_product": "K9 Thunder", "fit_label": "partial", "basis": "offered", "fit_rationale": "K9 is a tracked gun; the RFP asks for a mounted wheeled system, so the platform line is not met."}]}}]}
```
Code: ability = 5 (strong, 83 %) - 1 (two fixable not_met) - 1 (one strong rival with presence) = 3; attractiveness = 4;
label **position**. Next move written by the prompt: "Register on the Marendo portal and name a local assembly partner
before 15 Jan 2027" (kind find_partner, due 2027-01-15, priority medium). At a glance: Buyer Marendo MoD · What 36 mounted
155 mm/52 guns · Value USD 420 m (budget, incl. support) · Deadline 15 Feb 2027 · KSSL fit Strong, MArG 155/52 · Rival to
beat Nordvik NV-155.

### F.3 Technology article (as `tech_article` v2 should output it)
```json
{"prompt_id": "tech_article", "subject": "Nordvik tests ramjet 155 mm round to 85 km",
 "records": [{"table": "technology_overview_article", "values": {
   "title": "Nordvik fires a ramjet-assisted 155 mm shell to 85 km in trials",
   "card_summary": "Nordvik Defence fired its RJ-155 ramjet shell to 85 km from a 52-calibre gun in Swedish trials. That is almost twice the range of today's base-bleed rounds.",
   "article_says": "Nordvik Defence said its RJ-155 shell reached 85 km in three firings at a Swedish range on 2 October. The shell carries a small ramjet (an air-breathing motor that burns fuel after the shell leaves the barrel). It was fired from a standard 155 mm/52 gun. Accuracy figures were not released. Nordvik plans qualification firings in 2027 and says production could start in 2029.",
   "classification": "competitor_advance", "maturity": 3, "relevance": 5, "horizon": "2_5y", "horizon_source": "stated",
   "ref_client_product": "ATAGS 155 mm/52 cal Advanced Towed Artillery Gun System", "spec_touched": "Maximum range", "client_position": "behind",
   "client_narrative": "ATAGS and MArG 155/52 are 52-calibre guns, so they could fire this shell, but KSSL does not make a ramjet round. KSSL's stated maximum range is 48 km with ERFB-BB ammunition. A buyer who gets 85 km from the same gun will ask every bidder for it. The round is Nordvik's; KSSL's ammunition line has no comparable product on record.",
   "article_date": "2026-10-02", "ref_category": "Ammunition",
   "_reason": {"maturity": "3: trial firings, no qualification yet.", "relevance": "5: same gun class as ATAGS/MArG and a figure on maximum range, a spec KSSL competes on.",
               "client_position": "behind: the client spec row 'Maximum range 48 km' is below the stated 85 km.", "horizon": "2_5y: production stated for 2029."}},
  "children": {
   "technology_overview_key_point": [
     {"point_text": "85 km reached in three firings from a standard 155 mm/52 gun on 2 October.", "evidence_text": "reached 85 km in three firings"},
     {"point_text": "The ramjet burns fuel after launch; the shell needs no change to the gun.", "evidence_text": "fired from a standard 155 mm/52 gun"},
     {"point_text": "No accuracy figure was released.", "evidence_text": "Accuracy figures were not released."},
     {"point_text": "Qualification firings planned for 2027; production could start in 2029.", "evidence_text": "qualification firings in 2027 and says production could start in 2029"}],
   "technology_overview_company": [{"display_label": "Nordvik Defence", "ref_competitor": "Nordvik Defence", "relationship": "developer"}]}}]}
```
Code: direction **threat** (competitor_advance, relevance 5, maturity 3). At a glance (loader-written fact rows): What
Ramjet-assisted 155 mm shell, 85 km · Who Nordvik Defence · Maturity Trials · Horizon 2-5 years · Touches ATAGS, MArG
155/52 (maximum range) · KSSL position Behind.

### F.4 Product news step (the product timeline, from the same `signal` run as F.1)
Product NV-155, Nordvik Defence. Timeline as the Products page should show it:
- 2024-03-12 · Trial / test / demo · "NV-155 fires 40 km in Veland acceptance trials" · Example Defence News
- 2025-06-20 · Programme / order · "Nordvik and KSSL shortlisted in Veland 155 mm competition" · Veland MoD release
- 2026-10-09 · Programme / order · "Veland orders 24 NV-155, deliveries 2028-2030" · Example Defence News
  KSSL relevance: "Same class as MArG 155/52; chosen over it in Veland."
Each step is a `competitive_product_news` row with `news_type` and `event_date`; the story is
`competitive:nordvik:nv-155:ve:programme`.

### F.5 Geo layer-2 anomaly (as `geo_analysis` should output it)
```json
{"table": "competitive_geo_analysis", "values": {"kind": "anomaly", "ref_location": "Veland", "ref_competitor": "Nordvik Defence",
  "ref_geo_product": "NV-155", "ref_client_product": "MArG 155 mm/52 cal Mounted Gun System (soft recoil, AM General partnership)",
  "finding": "Veland bought the NV-155 (40 km stated) in 2026 although the stored matchup puts MArG 155/52 ahead on range (48 km) and into-action time.",
  "stated_reasons": ["local_partner"], "reason_state": "stated",
  "hypothesis": null, "to_find_out": "Whether the ministry scored price or local assembly higher than range in the evaluation.",
  "_sources": {"stated_reasons": [{"url": "https://example-defence-news.test/veland-nv155", "quote": "Final assembly will take place at Veland Motor Works, a condition the ministry set for all bidders."}]}}}
```
The hypothesis field stays null because a reason was stated; had none been, `reason_state = not_stated` and the
hypothesis ("Nordvik has sold in Veland since 2022; KSSL has no presence row there") would show greyed as an analyst
hypothesis with its two stored facts.

---

## G. Filters and tags: every option list from a table (rule §0.7 of PROMPT_LOGIC.md)

### G.1 The mechanism, in two tables
The pages already do this in places, and the pattern to copy exists twice: `ui.competitive_competitor_moment_level`
(code, label, tag_class, display_order: the lookup that gives a stored code its word and colour) and
`serving.market_filter_option` (filter_type, option_code, option_label, record_count, sort_order, is_active: the option
list of one filter, rolled up from the data). Generalise those two shapes rather than adding a table per filter:
- **`ui.code_label`** (table_name, column_name, code, label, tag_class, tooltip, display_order, is_active): one row per
  allowed value of every enum column in every pillar (classification, direction, pursue_label, lean_code, stage,
  news_type, partner_type, overlap_kind, activity_type, overlap_status, confidence, maturity, client_position, stance,
  step_type, glance_move, impact_dimension ...). Seeded in `db/setup/07_page_setup.sql`; the prompts' `enum:` lists are
  generated from it (`enum_from: ui.code_label` already exists as a loader rule shape), so a prompt and a page can never
  disagree on a vocabulary. A stored code with no row is still shown as stored (today's rule) and logged.
- **`ui.competitive_filter_option`** and **`ui.technology_filter_option`** with the exact columns of
  `market_filter_option`, rebuilt by a roll-up (`derive.filter_options`, run after every load and at Approve) from
  `SELECT filter_type, value, count(*)` over the serving rows: country, category, sub-type, classification, impact
  dimension, time to effect, news type, partner type, region, activity, overlap, stage, fit grade, pursue label,
  maturity, horizon, direction, stance, patent category. `market_filter_option` gets the same roll-up (it has 0 rows
  today, so `Tenders.jsx:250-253` falls back to served order).
The backend serves both as `d.codeLabels[table.column]` and `d.filterOptions[pillar][filter_type]`; a page may read an
option list only from there. Colour and icon choice keyed by a stored code stays in the frontend (it is chrome), but the
code list it keys on comes from `code_label`, so a new code gets a row, not a regex.

### G.2 Hard-coded option lists and tag vocabularies in the frontend (file:line -> where it should come from)
| # | File:line | What is hard-coded | Should come from |
|---|---|---|---|
| 1 | `src/lib/dataset.js:113-117`, `:131-135`; `src/lib/overview.js:344-364` (counts bound by label string) | Overview metric tiles: "Competitive threats"/threat, "Watch signals"/watch, "Companies tracked"; "Competitor advances"/rival, "Adoptable advances"/adopt, "Domains tracked" | `ui.competitive_metric` (metric_label, metric_value, display_order; exists) and `ui.technology_overview_metric_card` (metric_key, metric_label, metric_order; exists), values filled by the roll-up; the predicate keyed by `metric_key`, not by label text |
| 2 | `src/lib/dataset.js:112` (direction pills are `seenDirs`, distinct from data: fine) + `src/lib/overview.js:29 DIR_WORD` | the words and order for classification codes threat / watch / fav | `ui.code_label` rows for `competitive_signal.classification`; option list `ui.competitive_filter_option` filter_type `classification` |
| 3 | `src/lib/overview.js:6-25 SEQ_LABEL / SEQ_SUB / SEQ_OPTIONS` | feed sequence options (priority, recency; depth, category off the menu) | `ui.competitive_overview_feed.sequence_mode` (exists, 0 rows) as option rows, and `ui.technology_overview_view.sequence_options / sequence_default` (exist) |
| 4 | `src/lib/overview.js:317 TECH_KIND`, `dataset.js:128 tagWord` | classification -> stream (rival / adopt) and the badge word | `ui.code_label` for `technology_overview_article.classification` (four codes after A.3.1) with `tag_class` = stream; `ui.technology_overview_filter` (exists, 0 rows) for the option rows |
| 5 | `src/lib/overview.js:391-407 TILE_LABELS` | the "what this tile opens" phrases per metric key | the `note` / `metric_subtext` column of the metric tables in row 1 |
| 6 | `src/lib/news.js:112-120 NEWS_WINDOWS, NEWS_WINDOW_DEFAULT`; `src/pages/competitive/Profile.jsx:721-728` (range `<select>`: all / 7d / 30d / 3m / 6m / 12m / custom) | news date windows, twice, with different lists | one table in the shape of `ui.competitive_competitor_moment_time_window` (code, label, day_count, is_default): add rows to `ui.competitive_news_view.date_filter / published_range` (exists, 0 rows) or a new `ui.competitive_news_range`; both the profile panel and the list read it |
| 7 | `src/lib/marketOverview.js:10-16 WINDOWS`; `src/pages/market/MarketOverview.jsx:139-145 WINDOW_COLORS`, `:29-34 SECTIONS` | closing-date buckets (7 / 14 / 30 / 30+ / none) with labels and colours; the four sections | `ui.market_tender_filter` (exists: filter_type, filter_label, option_count, selected_value) with filter_type `closing_window` rows carrying day_from / day_to (two columns to add) and `tag_class`; sections from `ui.market_intelligence_tab` (tab_label, tab_order; exists) |
| 8 | `src/lib/tenderCalc.js:10` (status -> open / awarded / closed bucket); `src/pages/market/Tenders.jsx:145` | the status vocabulary and the tab it maps to ("closing" is a stored status today and is not in the list) | `ui.code_label` rows for `market_tender.status` with `tag_class` = tab; tabs from `ui.market_view` (rail_label, view_title; exists) |
| 9 | `src/lib/tenderRow.js:13-24 TENDER_PARAMS`; `src/pages/market/Tenders.jsx:85 DASHBOARD_PARAM_KEYS` | the fixed eight tender glance rows and their labels | chrome (field keys), but the labels exist in `ui.market_tender_card` / `ui.market_tender_assessment_view` (buyer_display, country_display ...); low priority |
| 10 | `src/components/matchupDossier/MatchupDossier.jsx:6 TABS` | dossier tabs Analytics / Spec Comparison | `ui.competitive_positioning_tab` (tab_code, tab_label, is_enabled, display_order; exists for exactly this) |
| 11 | `src/lib/partners.js:27-45 PG_STYLE / symbolKeyOf` (regex over free-text partner_type), `:20-26` (comment lists an 11-value vocabulary that no prompt uses); `src/pages/competitive/Partnerships.jsx:587` (group-by select type / region), `:672-700` legend | partner-type colours and legend entries, the grouping options | `ui.code_label` rows for `competitive_partnership.partner_type` (the seven types of A.1.6) with `tag_class` = symbol key; `ui.competitive_partnership_graph.group_by / legend_type` (exists) for the grouping options; option list `ui.competitive_filter_option` `partner_type`, `region` |
| 12 | `src/lib/partners.js:66-70 CONF_TAG` | confidence codes with tooltips (official / corroborated / single_source) | `ui.code_label` rows for `competitive_partnership.relationship_confidence` (`tooltip` column) |
| 13 | `src/pages/competitive/Geo.jsx:21-25 OVERLAP`, `:33 levelClass`, `:34-35 CLIENT_SIDE / RIVAL_SIDE`; `src/lib/geoBadge.js:41-44 activityClass` (codes lp / pt / ex / sv / bf) | overlap labels and tiers; decision-level colours; side aliases; activity colour codes. Bug: the stored `activity_type` is a label ("Local production"), never a code, so `activityClass` returns "sv" for every row and all dots are one colour | `ui.code_label` rows for `competitive_geo_company_presence.overlap_status` and `.activity_type` (new five-value vocabulary, A.1.7) with `tag_class`; option lists in `ui.competitive_geo_filter` (exists, 0 rows: filter_type, option_label, record_count) from the roll-up |
| 14 | `src/lib/chat.js:14-19 MAT_LAB`; `backend/areas/d_market_tech.py:13` ("lab / dev / prod / fielded only pick a chip colour"); `src/pages/technology/Innovation.jsx:213` | maturity chip words and colours | `ui.code_label` rows for `technology_innovation.maturity_level` (1-5) and `technology_overview_article.maturity`; the per-row text stays in `technology_innovation_status.maturity_label` |
| 15 | `src/lib/edge.js:28-31`, `src/lib/specs.js:142-143` | decision_level 1 / 2 / 3 -> words (behind / parity / ahead) and bands | `ui.code_label` rows for `competitive_matchup.decision_level` (also used by `competitive_geo_product_match.decision_level`) |
| 16 | `src/pages/competitive/Projects.jsx:11 STANCE_LABEL`; `Profile.jsx:18 DOT`; `ThreatAnalysis.jsx:13-15 DOT / HEAD_CLASS`; `Products.jsx:379` | stance / threat-level words and colour classes, repeated in four files | the same `ui.code_label` rows as row 2 (`competitive_project.assessment_stance`, `competitive_competitor.threat_level` share the vocabulary) |
| 17 | `src/lib/route.js:13-52 PILLARS / PILLAR_LABEL / RAIL` | navigation rail and labels | navigation, not a filter; `ui.competitive_navigation`, `ui.market_ui_navigation`, `ui.technology_ui_navigation` exist (view_key, view_label, view_sequence, is_active) if the rule is extended to it |
| 18 | `src/lib/search.js:21-23`, `src/components/review/Review.jsx:15` | search group labels / limits; review statuses | chrome of the search box and of the review copy; leave |
Already correct (options built from distinct stored values or ui tables): `Products.jsx:195-197, 266, 710` (company facets, product news categories), `Profile.jsx:334-340` (news categories), `GlobalRequirement.jsx:109-135` (country / category counts), `MatchupList.jsx:164-195` (company / category / KSSL product / country), `Projects.jsx:70-72` (`ui_project_filter`, `ui_project_sequence_option`, `ui_project_stage_step`), `ThreatAnalysis.jsx:22-53` (`competitive_competitor_moment_time_window`, `_level`), `Innovation.jsx:36, 161` (`techCats`), `Tenders.jsx:250-253` (served values ordered by `market_filter_option`).

### G.3 Every new tag or score: where it is stored, where its options come from
| New value | Stored in | Allowed values / labels | Filter options |
|---|---|---|---|
| Signal label (threat / watch / fav) | `competitive_signal.classification` (derived by `derive.signal_label`) | `ui.code_label` competitive_signal.classification | `ui.competitive_filter_option` `classification` |
| `direction` (adverse / favourable) | `competitive_signal.direction` | code_label | not a filter |
| `probability`, `impact` (1-5) | `competitive_signal.probability / impact` | `ui.code_label` rows per level carry the anchor text as `tooltip` (table_name `competitive_signal`, column `probability` / `impact`), used by the matrix axes | matrix axes; option rows `probability`, `impact` for a "min score" filter if wanted |
| `impact_dimension` (+ `_2`) | `competitive_signal.impact_dimension` | code_label (six dimensions) | `competitive_filter_option` `impact_dimension` |
| `time_to_effect`, `subtype_match`, `in_client_market` | `competitive_signal.*` | code_label | `competitive_filter_option` each |
| `glance_move` | `competitive_signal_detail.glance_move` | code_label | `competitive_filter_option` `move` |
| Story `kind`, step `step_type`, `label_after` | `story.kind`, `story_step.step_type / label_after` | code_label | `competitive_filter_option` `story_kind` |
| Moment `grade`, `change_note` | `competitive_competitor_moment.grade` (derived from the signal label) | `ui.competitive_competitor_moment_level` (exists) | exists (levels) |
| Product `news_type`, `event_date` | `competitive_product_news.news_type` | code_label (nine types) | `competitive_filter_option` `product_news_type`; `Products.jsx:710` pills switch from `category` to this |
| Sub-type, calibre, weight class | `product_class.sub_type / calibre_mm / weight_class` (staging) -> copied to `client_product.subcategory` and a new `competitive_product.subcategory` for serving | code_label per category (`matchup_class.VOCAB`, generated into code_label by a seed script so the gate and the pages read one list) | `competitive_filter_option` `sub_type` (Products, Product Evaluation, Geo) |
| Partnership `partner_type`, `status`, `overlap_kind`, `overlap_effect`, evidence `step_type` | `competitive_partnership.*`, `competitive_partnership_evidence.step_type` | code_label (replaces `partners.js` regex) | `competitive_filter_option` `partner_type`, `partner_status`, `overlap_kind` |
| Geo `activity_type` (five values), `overlap_status`, analysis `kind`, `reason_state`, `stated_reasons` | `competitive_geo_company_presence.activity_type`, `competitive_geo_product.activity_type`, `competitive_geo_product_match.match_status`, `competitive_geo_analysis.*` | code_label with `tag_class` = dot colour (fixes the `activityClass` bug) | `ui.competitive_geo_filter` (exists) rolled up: `activity`, `overlap`, `country`, `analysis_kind` |
| Project `kssl_option`; stage steps Deliveries / In service | `competitive_project.kssl_option`; `ui.ui_project_stage_step` rows | code_label; `ui_project_stage_step` (exists) | `ui_project_filter` (exists) gains `stage` and `kssl_option` option rows via the roll-up |
| Tender scores and label: `value_score`, `strategic_score`, `attractiveness`, `ability`, `pursue_label`, `time_to_award` | `market_tender_fit_assessment.*` (`pursue_label` also copied to `market_tender.lean_code` mapping) | code_label (`pursue_label` four codes; `lean_code` gains `watch`; score levels with anchors as tooltip) | `market_filter_option` `pursue_label`, `time_to_award`, `fit_grade` |
| Eligibility `state`, `fixable`; rival `basis`; `move_kind` | `market_tender_eligibility.state / fixable`, `market_tender_competitor_fit.basis`, `market_next_move.move_kind` | code_label | `market_filter_option` `eligibility_state`, `move_kind` |
| Requirement `stage`, `status_state`; opportunity `stage`, update `update_type` | `market_global_requirement.stage / status_state`, `market_opportunity.stage`, `market_opportunity_update.update_type` | code_label (one stage vocabulary for both) | `market_filter_option` `stage`, `status_state`; `GlobalRequirement.jsx` reads them instead of counting `status` |
| Technology article `classification` (four), `maturity`, `relevance`, `horizon`, `horizon_source`, `client_position`, `direction` | `technology_overview_article.*` (`direction` derived) | code_label; the stream (`tag_class`) replaces `TECH_KIND` | `ui.technology_overview_filter` (exists) or a new `ui.technology_filter_option` in the market shape: `classification`, `maturity`, `horizon`, `direction`, `client_position`, `category` |
| Innovation `maturity_level`, `technology_kind`, `stance`, milestone `step_type` | `technology_innovation.*`, `technology_innovation_milestone.step_type` | code_label (`MAT_LAB` retired) | `technology_filter_option` `maturity`, `technology_kind`, `stance`, `client_position` |
| Patent `category_label`, trend year | `competitive_patent_filing.category_label`, `competitive_patent_trend` | category names (`technology_category`) | `competitive_filter_option` `patent_category`; the Patents rail (`Patents.jsx`) already builds its field list from stored labels |
| Overview tiles and sequence options | `ui.competitive_metric`, `ui.technology_overview_metric_card`, `ui.competitive_overview_feed`, `ui.technology_overview_view` (all exist) | filled by the roll-up | n/a |

Loader side: `enum:` lists in the prompt files become `enum_from: ui.code_label` (table, column), so adding a value is a row
in `07_page_setup.sql`, never an edit in three places. The roll-up writes `record_count` so a filter can show "Threat (12)"
and hide options with zero rows without any frontend list.
