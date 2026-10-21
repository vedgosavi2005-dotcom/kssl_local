# Prompt logic for all three pillars (draft v1, 2026-10-17)

The user's brief for the competitive pillar is in `PROMPT_LOGIC_COMPETITIVE.md` (the starting point). This
document thinks it through further and does the same for the Market and Technology pillars. Fable 5.1 reviews
it (`PROMPT_LOGIC_FABLE_REVIEW.md`), then the prompts are rewritten and tested on a few real cases before the
data flood.

---

## 0. Foundations shared by every prompt

### 0.1 The KSSL lens, given to every prompt as context (from the DB, never typed into a prompt)
Every judgement is "what does this mean for KSSL", so every prompt gets:

| Block | Holds | Source |
|---|---|---|
| `client_portfolio` | KSSL products with category, sub-type, calibre, weight class and 3–5 key specs | client_product (+ product_class) |
| `client_markets` | countries where KSSL sells, has delivered, has a partner or a local presence, plus its key customers | competitive_geo_company_presence (role client) + client_partner* |
| `client_partners` | KSSL's partners and suppliers, and what each supplies | client_partner, client_partner_relationship, client_partner_product |
| `competitors` | each rival with its sub-types and markets | competitive_competitor + product_class |

Without `client_markets` and `client_partners`, "in KSSL's markets" and "supplier overlap" cannot be judged.
Those two blocks are a **data dependency** (client Excel or a research prompt). Until they exist, the prompt
must say "unknown", not guess.

### 0.2 Facts vs judgements
- **Facts** (who, what, quantity, value, date, place) need a quote from a source.
- **Judgements** (threat/watch, probability, impact, fit, why it matters) need a one-sentence reason that names
  the facts they rest on.
- "Unknown" is always allowed. A judgement with no supporting fact is "unknown", not a guess.

### 0.3 Plain English: one style for every card
- Sentences ≤ 20 words. Active voice. Name the company and the thing.
- No unexplained jargon or acronyms. Say "self-propelled gun (a gun on its own tracked vehicle)" the first
  time. Keep official names (ATAGS, K9 Vajra-T) as names.
- No hype adjectives ("game-changing", "unprecedented") unless quoted.
- Numbers with units, and the date they refer to.

### 0.4 Card anatomy: the same skeleton in every pillar, so users learn it once
1. **Title**: what happened, ≤ 12 words.
2. **At a glance**: 4–6 fixed fields, each one word or ≤ 8 words. Never a summary.
3. **What happened**: 2–4 plain sentences, the event only.
4. **Why it matters to KSSL**: 2–4 sentences, naming the KSSL product, market, partner or supplier touched.
5. **Key points**: 3–6 bullets, each ≤ 20 words. Each carries a fact worth remembering (a number, a name, a
   date, a condition), with no repeats of the summary.
6. **Timeline**: when the item is part of a story.
7. **Sources**.

### 0.5 Stories and timelines: one mechanism for every pillar
Signals, product news, partnerships, projects, opportunities, tenders and innovations all evolve over time.
Use one model:
- a **story** has a stable key (for example competitor + product + customer country + event family: "K9 –
  Poland – order");
- each news item, notice or document is a **step** on a story: date, step type, one line, source;
- the card shows the latest state plus the timeline.

The news merge (`news.yml`) already groups articles into stories. Extend that grouping to link a new story to an
**existing** story (same key) instead of creating a new card.

### 0.6 Scoring: anchored scales, not free numbers
Every score is 1–5 with written anchors, plus a reason. The model never outputs a bare percentage. Labels
(threat/watch, strong/partial/weak, behind/parity/ahead) are **derived from the scores by code** (like
`derive.py` does for matchups), so the same scores always give the same label.

### 0.7 Filters and tags come from the tables too (user, 2026-10-17)
Every filter value and tag on a page (threat / watch, country, category, sub-type, stage, news type, partnership
type, fit grade, maturity, ...) is stored in a table:
- the **value** on each row is written by the prompt, or derived by code from the prompt's scores;
- each filter's **option list** is built from the distinct values present in the data (a SQL roll-up into the
  ui filter tables, e.g. market_filter_option, competitive_geo_filter), never typed into the frontend.

A filter never offers an option with no data behind it. Allowed values are fixed in the prompt output rules
(FORMAT.md), so the stored tags stay consistent. Includes an audit of the frontend for hard-coded filter lists.

### 0.8 Cross-pillar consistency
One event can matter in several pillars, for example a rival's contract (competitive signal), the buyer's next
purchase (market opportunity) and a new capability (technology article). Each pillar writes its own card, and
the cards cite the same source and story key, so the UI can link them.

---

## 1. Competitive pillar

### 1.1 Signals (Overview): threat / watch by risk matrix
**Probability (Y), 1–5:** how likely the move is to materialise, and how soon.
- 5 = done or contract signed, effects within 12 months;
- 4 = selected / approved / funded, award expected within 12 months;
- 3 = shortlisted / in trials / RFP issued;
- 2 = announced intent, MoU, early talks;
- 1 = speculation, report of interest.

**Impact on KSSL (X), 1–5:** the maximum over these dimensions, each scored with a reason:
- **orders & revenue**: a contested tender, a customer KSSL sells to, price pressure;
- **market standing**: incumbency, preferred-supplier status, reference customer, reputation;
- **supply chain**: a shared supplier or raw material, capacity booked, licences or export controls;
- **technology / capability gap**: the rival leaps ahead on a spec KSSL competes on;
- **partnerships**: a KSSL partner or prospect teaming with a rival;
- **policy**: export approval, offset rules, an indigenisation list that favours or blocks KSSL.

**Directness modifiers** (stored, used by the label rule):
- same sub-type as a KSSL product? (yes / adjacent / no)
- in a KSSL market? (yes / no / unknown)
- time to effect (< 1 y, 1–3 y, > 3 y)

**Label (code):**
- **threat** = probability ≥ 4 AND impact ≥ 4 AND (same or adjacent sub-type, or the supply-chain /
  partnership dimension) AND in a KSSL market (or a global-supply effect);
- **watch** = everything else that passes relevance.

The UI can plot the 5×5 matrix.

**Escalation:** a watch signal is a story. Each new step re-scores probability and impact. When the label rule
flips, the card becomes a threat and the timeline records "escalated on <date> because <step>".

**At a glance:**
- **Who**: the company.
- **Move**: one word, e.g. Order / JV / Trial / Delivery / Capacity / Approval.
- **Where**: country or customer.
- **Impact on KSSL**: dimension + level, e.g. "Orders – high".
- **Third party**: the customer or partner.
- **When**: the event date, plus the next expected step if stated.

### 1.2 Competitor Moment
The moves of one competitor over the last 90 days, as a timeline. Each move is graded (high / watch /
opportunity-for-KSSL) and shows what changed since the previous move. It reuses signals and stories rather than
re-reading articles.

### 1.3 Products: facts from Excel, plus product news and the product timeline
**Product news types:**
- programme / order;
- delivery / induction;
- deployment / combat use;
- trial / test / demonstration;
- export / new customer;
- upgrade / variant / component R&D;
- production / localisation / licence;
- incident / failure.

Each step is attached to the product (and variant) it concerns. The timeline shows the product's life,
e.g. Poland: ordered → delivered → in service → combat use. **Why it matters to KSSL** is shown when the step
touches a KSSL product's sub-type or market.

### 1.4 Product Evaluation: like-for-like matchups
**Gate** (code, from `product_class`): same category → same sub-type → same calibre where it applies → same or
adjacent weight / size class. A pair that fails the gate is never shown.

**Within a pair:**
- only specs measured the same way are compared;
- "better" is decided per spec by the dictionary;
- the verdict text is written only for top pairs. It is plain English: where KSSL is ahead, where it is
  behind, and what matters for a buyer in that sub-type.

### 1.5 Partnerships
**Types:**
- JV;
- MoU / teaming;
- contract (customer);
- supplier / sub-supplier;
- licence / ToT;
- co-development;
- investment / acquisition.

**Value analysis** (each a short line with a reason):
- what each side gets: market access, technology, capacity, financing, credibility;
- what it means for KSSL: competes with, opens a door for, or threatens a KSSL partnership.

**Overlap check:** is the partner also a KSSL partner or supplier (client_partner*), or in a KSSL market?
- If it is the same supplier: does it supply the **same component or service** to the rival? Then that is a
  supply-chain dependency. Say what, and the risk (capacity, priority, IP) or the advantage (shared
  qualification).

**Status timeline:** MoU → definitive agreement → JV formed → first product → orders.

### 1.6 Geo footprint
**Layer 1, presence** (facts): for each company and each country, what it **sells** and to whom, where it
**manufactures / assembles** (incl. local partner), and where it **sources** from. Each item is dated and
sourced.

**Layer 2, analysis** (judgement, evidence-gated):
- **overlap**: same sub-type sold by KSSL and a rival in the same country;
- **anomaly**: the rival wins where KSSL's matchup says KSSL is ahead (better specs or price). Possible reasons
  are listed **only when a source states them**: incumbency, offsets/local content, financing or
  government-to-government deal, delivery time, a local partner, after-sales network, politics. Otherwise the
  card says "reason not stated in sources" and suggests what to find out.
- **whitespace**: countries buying the sub-type where KSSL is absent, but a comparable rival sells.

### 1.7 Projects
Each programme is a story: concept → trials → contract → production → deliveries → service. Every step is
dated and sourced. The card shows the current stage, what changed last, and what KSSL can do (compete, partner,
supply).

---

## 2. Market pillar

### 2.1 Top opportunity (overview): attractiveness × ability to win
Each candidate (an open tender, or a pre-tender requirement / opportunity) is scored on two axes.

**Attractiveness (Y), 1–5:**
- value (stated, or a quantity × unit-price range only if sourced);
- strategic value: new country, reference customer, follow-on potential;
- time to award.

**Ability to win (X), 1–5:**
- **fit**: the like-for-like match of a KSSL product to the requirement lines;
- **eligibility**: registration, local presence, offset capacity, past performance, certifications. Each is
  met / not met / unknown;
- **competition**: incumbents and rivals with a comparable product in that country, from the geo layer;
- **relationship**: KSSL or partner presence with the buyer.

**Label (code):** pursue / position / monitor / pass. **Next move**: one concrete action with a due date tied
to the tender timeline, e.g. "Register on portal X by D-30", "Find a local partner", "Ask for clarification on
requirement 3".

**At a glance:**
- **Buyer**
- **What** (sub-type + quantity)
- **Value**
- **Deadline**
- **KSSL fit** (product + grade)
- **Rival to beat**

### 2.2 Tenders
**Extraction** (facts, from the notice):
- buyer, reference, lots;
- requirement lines (quantity, specs, standards);
- deadlines (clarification, submission, opening);
- eligibility conditions;
- evaluation criteria;
- value.

Each fact is quoted. Unlabelled dates stay unlabelled.

**Assessment** (judgement):
- per requirement line, which KSSL product meets it (like-for-like), with met / partly / not met per spec;
- eligibility checklist;
- likely rivals (from geo + products), and why.

**Tender timeline:** notice → amendments / extensions → clarifications → submission → award (winner, value).
Award notices are linked back to the tender. A won/lost tender feeds the competitive pillar: a signal, plus
the geo layer.

### 2.3 Global requirements (pre-tender demand)
Sources: budgets, procurement plans, acquisition-council approvals (e.g. DAC AoN), RFIs, statements by armed
forces.

**Stage:**
1. stated need;
2. approved / funded;
3. RFI;
4. RFP / tender;
5. award.

Each requirement shows its stage, quantity, value if stated, timeframe, KSSL fit, rivals positioned, and its
own timeline. **Stale rule:** a requirement whose latest step is older than N months, with no newer source,
is shown as "status unconfirmed since <date>", not "open". This fixes the stale "open" Canada RFI from the
test run.

### 2.4 Opportunities (from news)
A demand signal: a country or force announces or plans a purchase. Each one is classified by stage (as
above), linked to an existing requirement or tender when one matches, and assessed for fit as above. One story
per buyer + need.

### 2.5 Market intelligence (counts)
Counts by category and country: active tenders, strong fits, disclosed value, portals. These are SQL
roll-ups, never a prompt.

---

## 3. Technology pillar

### 3.1 Overview: technology articles, impact × maturity
For every technology development (from news, trade press, corpus documents with p_tech, or patents):

**Classification:**
- **competitor advance**: a rival gains a capability;
- **adoptable**: something KSSL could adopt, license or partner on;
- **threat to KSSL's technology position**;
- **enabling / industry trend**.

**Maturity (Y), 1–5:**
- 1 = concept / research;
- 2 = prototype;
- 3 = trials;
- 4 = production;
- 5 = fielded.

**Relevance to KSSL (X), 1–5:** how directly it touches a KSSL product line or capability: which sub-type, which
spec (range, accuracy, mobility, protection, cost).

**Horizon:** years to impact on KSSL.

**Direction (code, from the scores):** threat / watch / favourable.

**At a glance:**
- **What** (the technology in ≤ 8 words)
- **Who**
- **Maturity**
- **Horizon**
- **Touches** (the KSSL product line)
- **KSSL position**

### 3.2 Innovations (pipeline per category)
For each innovation:
- what it is, in plain English;
- who develops it;
- maturity and horizon;
- **KSSL position**: behind / parity / ahead, with evidence: KSSL's own product specs or programmes;
  "unknown" if none;
- **recommended stance**: watch / partner / license / develop / ignore, with a reason.

**Maturity timeline:** announced → prototype → trials → contract → production → fielded.

**Rules:**
- innovation_discovery proposes candidates; innovation_detail fills them;
- only "active" innovations are shown;
- a KSSL product, or a plain competitor product (not a new technology), is not an innovation;
- the test run listed ATAGS and XM1776 as innovations, and that must not repeat.

### 3.3 Patents
Classification of filings by technology area, plus trends: filings per competitor per area per year, as a
code roll-up. A spike in an area that touches a KSSL sub-type becomes a technology watch item, with the
patents as evidence.

---

## 4. What must be built besides prompt text (expected; Fable confirms or corrects)
- **`product_class`** (sub-type / calibre / weight class): being built for the matchup gate; reused
  everywhere as context.
- **Context blocks** for KSSL markets and partners, and the data behind them.
- **Story keys + timeline steps** across signals, product news, partnerships, projects, opportunities,
  tenders and innovations: one table or a story_key column, plus a link from each item to its story.
- **Score columns** (probability, impact + dimension, attractiveness, ability, maturity, relevance) and
  **code-derived labels**.
- **At-a-glance fields** stored as fields, not as a paragraph.
- **UI:**
  - the risk matrix on Overview;
  - timelines on signal, product, partnership, project and requirement cards;
  - the attractiveness × ability chart on Top opportunity;
  - the maturity × relevance chart on Technology.
