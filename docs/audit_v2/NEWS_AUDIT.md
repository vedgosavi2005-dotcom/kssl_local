# News pipeline audit

Auditor: independent, read-only. Date of audit: 2026-10-16.
Scope: backend/news.py, backend/sources.py, prompts/news.yml (v3), prompts/news_merge.py, prompts/signal.yml,
staging tables (81 company rows, 6 product rows, 122 candidates, 10 `news` prompt runs), fetch logs for 2026-06 and
2026-08, and live probes of Google News RSS.
IDs below are the first 8 characters of `article_id` (or `candidate_id`).

## 1. Verdict

The plumbing works: no candidate is stuck as `new`, no duplicate URL per owner, every product row has a company row
with the same URL, every stored image file exists and decodes, 78 of 81 article pages load, and 67 of the 70 pages
that carry a date agree with the stored date to within one day. Merging inside a batch is mostly good: I checked every
`also_reported_by` headline against its main headline and found no certain wrong merge (one doubtful, see M5).

The weak part is **coverage and selection, not storage**. Measured against what Google can return, the fetch loses a
large share of relevant news before the model ever sees it: the month-wide query returns 2.3x to 3.5x fewer items than
daily queries; the relevance check drops real company news because it needs the full legal name ("Hanwha" and "L&T" fail);
the `--limit 20` cut drops about 50 allowlisted items in just two logged runs; and the DB holds nothing for Hanwha or
L&T after 2026-09-30 although a probe finds 14 and 20 kept items for 1-16 Oct. On the data itself: 4 missed merges
(3 of them caused by the 45-day stored-story window, 1 by the model), 18 of 81 categories I would change (7 are a
definition problem: accidents), 12 stories that are not really about the company (4 clearly not), 22 stories
(27%) that are stock tips or non-defence business, and a main-article rule that cannot rank 77 of 81 stories because
they are all tier `independent`.

## 2. Findings, ranked

### HIGH

**H1. Relevance check drops real news because it needs the full name. (Fetch, backend/news.py `mentions`, `_load_subjects`)**
- `staging.competitive_competitor` has `short_name` empty for all three companies and `legal_name` equal to the
  display name for L&T and Hanwha (name_key strips "Limited" / "Co., Ltd."). So `names` = one name. A headline that says
  "Hanwha" or "L&T" fails unless the page title or description also has the long name.
- In the two fetch logs plus my Oct probe there are 159 "not about" drops (25% of 644 drops). In 69 of the 159 the headline
  carries the short form (Hanwha 41 of 58, L&T 28 of 77, K9 Thunder 10 of 11, K9 Vajra-T 4 of 8).
- Sample of 15 "not about" drops, judged by me: **9 wrong, 3 right, 3 borderline.** Wrong drops:
  Breaking Defense "Army picks Hanwha's wheeled K9 for self-propelled howitzer prototypes";
  Breaking Defense "Hanwha Defense USA seeks to acquire Austal USA in $1.2B potential deal";
  euro-sd "Hanwha Wins U.S. Army MTC Contract";
  KED "S.Korea antitrust regulator clears Hanwha's acquisition of KAI stake";
  Chosun "Hanwha's KAI Review Bid Sparks Union Protest";
  Reuters "India's L&T to invest nearly $2 billion in Tamil Nadu";
  larsentoubro.com (own newsroom) "Sustainable Infrastructure Company";
  moneycontrol and TOI "300 more K9 Vajra" (product name "K9 Vajra-T" does not match "K9 Vajra").
  Right drops: BEML/HAL order, Jefferies picks list, NDTV Profit stocks-to-watch.
  Borderline: TOI "PM reviews ... facility in Hazira", Korea Times "Private sector's role in 5th Nuri launch",
  Bharatshakti "Navy to commission Samarthak".
- In my Oct probe the Hanwha run dropped 21 "not about" items, most of them about the XM1776 designation, KAI stake and
  KF-21 work; hanwha.com's own press release "U.S. Army, Hanwha unveil XM1776 Mobile Tactical Cannon" was dropped.
- Note the probe with `--alias L&T` keeps more L&T items than the DB run would, because the DB run has no alias.
- Fix: fill `short_name` ("Hanwha", "L&T", "Adani Defence") or add an `aliases` list; use aliases in `names`, in the query
  and in the cheap pre-filter; accept a match on the URL slug; match product names loosely ("K9 Vajra" for "K9 Vajra-T",
  "K9" + "Hanwha"); add a `--domain` default per company (hanwha.com, larsentoubro.com, adanidefence.com) so own-site
  pages are never "not about".

**H2. Month-wide Google queries under-fetch. (Fetch)**
- Google RSS returns at most 100 items per query. Hanwha hits it in a month window on both queries (100 and 100).
- Below the cap the month window still returns far fewer items than short windows (unique links, Aug 2026):

| Query | month | 7-day windows | 1-day windows |
|---|---|---|---|
| "Larsen & Toubro" defence OR defense | 54 | 79 | 157 |
| "Hanwha Aerospace" | 100 | 160 | 229 |
| "Adani Defence & Aerospace" defence OR defense | 14 | 33 | 46 |
| "Adani Defence" | 44 | 66 | 154 |

- So the loss is 2.3x to 3.5x, before any filter.
- Fix: in `collect`, split the range into 1-3 day windows (cap 100 per window is then never reached), merge by link.
  Run them in parallel; 12 rapid RSS calls all returned 200 in 3.2 s, so rate limits are not a worry at this size.

**H3. The 45-day stored-story window is anchored on `current_date`, so backfills split events. (news.yml + news_merge._load)**
- Both `news.yml` (2nd block) and `news_merge._load` use `published_date >= current_date - 45`. Today (2026-10-16) that is
  2026-09-01. A batch of June or August candidates never sees stories already stored for June or August.
- Evidence: the data went in two stages (candidates found 08:56 and decided 09:14; then found 09:16-09:17 and decided
  09:19). Run `90d773a1` (Hanwha, 37 candidates) shows `stored_in_view: 9`, all September. Stage-1 stories from June to
  August were invisible.
- Missed merges caused by this (company table):
  1. `04ddc306` Chosunbiz "Hanwha Aerospace wins US Army deal for K9 wheeled howitzer prototypes" (08-19) and
     `74283a00` Korea Times "Hanwha Aerospace selected to build prototypes for US Army mobile artillery program" (08-19).
     Same award. `74283a00` was decided in run `5522dd37`; `04ddc306` in `90d773a1`, whose prompt does not contain `S74283a00`.
     (This is the pair the brief suspected. Cause confirmed.)
  2. `0764eda4` TOI "PM Modi inspects indigenous defence systems at Surat facility ... Zorawar" (06-06) and `08ad864f`
     The Week "What makes India's Zorawar tanks formidable ... PM Modi briefed" (06-05). Same Hazira visit. A third,
     `5ee86fde`, is the same visit mentioned in one sentence.
  3. `305bfe85` KED "Deadly Hanwha Aerospace blast disrupts output" (06-02) and `5129cca4` Korea Times "partially suspends
     Daejeon factory" (06-02). Probable same event (production suspension after the blast); lower confidence.
- Missed merge caused by the model (same batch, both visible):
  4. `67ef6459` Korea Times "partners with UAE defense firm for expansion into Middle East" (06-24) and `bc6dd49c` Korea
     Herald "to produce K9 Howitzers in UAE" (06-25). I read both pages: one teaming agreement with Generation 5 Holding,
     signed at Eurosatory. The Herald page says "Published June 24", so the stored 06-25 is also off by a day. The model
     gave them different reasons ("partnership" vs "local production") and never compared them.
- Fix: select stored stories for the prompt by the candidates' own dates (for example `published_date BETWEEN min(cand)-21d
  AND max(cand)+21d`), and apply the same filter in `_load`. For backfills, run months oldest-first in one batch or
  widen the window to 400 days. Add a post-check in code: two stories of one owner within 3 days whose headlines share a
  named entity and a number or product term are listed for review.

**H4. The DB has nothing for Hanwha or L&T after 2026-09-30. (Data load)**
- Latest candidate dates: Hanwha 2026-09-28, L&T 2026-09-30, Adani 2026-10-10. For 2026-09-17..09-30 the DB has 2 Hanwha and
  7 L&T candidates; for 1-16 Oct, 0 and 0.
- A dry-run probe (limit 20, no alias) for 1-16 Oct keeps 14 Hanwha items (Nuri launch, 473 safety violations and
  prosecution, XM1776 designation, Innocean/Hanwha, Janes Milrem UGV) and 20 L&T items (power T&D orders of Rs 10-15k crore,
  Samarthak commissioning, Q2 inflows, hyperloop partnership, and about 10 stock-tip items).
- I was not given a fetch log for 09-17..10-16, so I cannot tell whether the run was skipped, truncated, or not yet
  loaded. Check this before relying on the dashboard for October.

**H5. `--limit 20` cuts month backfills, and the cut is not ranked by importance. (Fetch)**
- Hanwha June: 91 seen, kept 20 (= limit), 6 "over limit" (pages fetched, images downloaded, then discarded), 25 "over
  limit (not processed)". The second query never ran. L&T Aug: kept 20, 19 not processed.
- That is about 50 allowlisted items unexamined in two runs. Order inside the cut is "headline names the company first, then
  Google's order", not date or importance, so stock tips compete with contracts for the 20 slots (L&T Oct probe: about 10 of
  20 kept items are stock tips).
- Fix: raise the limit once H2 gives short windows (limit per window, not per month), process the whole list, drop noise by
  headline pattern before the limit, and do not download images for items that will be dropped as "over limit".

### MEDIUM

**M1. Category definitions have gaps (see section 3).** Accidents sit in "Leadership & corporate" by definition, so the
Hanwha blast thread (5 rows) is filed with management changes; two follow-ups of the same thread went to "Other" (inconsistent).
"Contract & order" and "Export" overlap with no tie-break (the US Army award is a foreign customer). Credit ratings, state
MoUs for civil projects and civil partnerships have no home. "Other" is the largest bucket (18 of 81, 22%).

**M2. About 27% of stored stories are noise for a defence dashboard.** Stock & market 9 (8 L&T), Non-defence business 13,
and the stories listed under H6 below. The Profile news list shows them unless the UI filters by category.
Fix: drop them at fetch time (headline patterns: "stocks to watch", "target price", "breakout", "holdings", "volumes spurt",
"share price", "dividend", "Researchscope") or hide the categories in the UI. Do not spend model calls on them.

**M3. Relevance of stored stories (H6 list).** 12 of 81:
- Not about the company (4): `4dc81247` NDTV Lockheed transport-aircraft bid (Adani named once in a list of five bidders);
  `be1404c7` Business Today "This AI stock might be showing nearly 90% fall" (E2E Networks, "L&T-backed" in one sentence);
  `cbd8fdff` ET "Researchscope: Larsen & Toubro" (evergreen page dated 2004-08-09, stored as 2026-09-25);
  `5ee86fde` NIE "PM Modi launches Rs 23,000 crore projects in Gujarat" (one sentence: the day began at the L&T Hazira facility).
- Weak or passing (8): `496d6c17`, `471ca703`, `7a80ab7a`, `167b50fc` (ET slideshow stock lists, L&T is one of 6-10 names);
  `68449b05` Firstpost and `a3414b46` ET Government (India-Korea cooperation pieces, L&T is one party); `ef859392` L&T
  Technology Services deal (a separate listed company); `f76d7a3b` law-firm advisory note.
- Borderline but relevant: `686104bd` (Adani Defence & Aerospace named in the airline-waiver letter; belongs in
  Non-defence business) and `0e84fbd9` (Adani Kanpur capacity; correct subject, wrong category).

**M4. Main-article choice is arbitrary inside a tier.** 77 of 81 mains and all 41 merged are tier `independent`, so the rule
collapses to "earliest date, then has a saved image, then earliest found". Odd picks:
- `0be0e558` main The Indian Express over Reuters, Nikkei, Korea Times, Aviation Week (same day; Reuters lost because its page
  returns 401 and has no image).
- `59eefa67` main Chosun (09-01) while Yonhap, KED and JoongAng ran on 08-31. A story that is extended with `same_as` keeps the
  stored main and never re-ranks. The row date (09-01) is therefore a day after the first reports.
- `04ddc306` main Chosunbiz (headline ends " - CHOSUNBIZ") over Yonhap wire, same day.
- `0206e0a2` AK-203 ammunition deal: main The Week, whose headline does not state the deal. ANI, ET, ToI, Fortune India and
  Livemint (eight outlets, all 09-05) have descriptive headlines.
- `1c7c67aa`: "also reported by" is another NDTV URL of the same article (two URLs of one article, not a second publisher).
- Good picks: `9306fa4a` (PIB, primary) and the three larsentoubro.com primaries.
- Fix: rank within `independent` by a small publisher table (wire/agency > national daily > trade > portal), prefer the
  headline that names the company and the event, and let a later `same_as` merge re-pick the main if a better-ranked
  source arrives (keep the row id stable).

**M5. Stored dates.** Of 70 pages with a date: 67 agree within one day (allowing time zone). Errors:
`cbd8fdff` 2004-08-09 vs stored 2026-09-25 (22 years, RSS gave today's date for an evergreen page);
`bc6dd49c` 06-24 vs 06-25; `8087a60f` KED page says 06-02, stored 06-04 (KED's own page dates are unreliable:
`305bfe85` says 2026-05-12, before the blast, and the URL says 0602).
Also `0be0e558` holds a Chosun item `Sudden Explosion at Hanwha Aerospace Site Kills 5` dated 06-24 (URL date 06/24); the
page is an empty shell (51 characters of text), so I could not verify it. The model merged it into the 06-01 event on
headline similarity alone. Treat as doubtful; it is the only questionable merge I found.
Fix: when the page has `article:published_time` and it differs from the RSS date by more than 3 days, drop the item or use
the page date.

**M6. Images.** The UI reads `competitive_news_article.image_url` (remote publisher URL; `backend/areas/a_competitive.py`).
The downloaded files in `media/news` and the `image_local_path` fact_source rows are not read by any code I found. Today all
72 remote URLs answer 200 (tested with a foreign Referer), so it works now but will rot.
- 9 rows have no `image_url`; 4 of them also have no local file (`8da0e4ca`, `e943daa8`, `9caa9fde`, `ed60139b`; pages
  blocked 403/401 or no image). 5 rows have a local file but a NULL `image_url` (`15149764`, `7e98dbb7`, `5eb27b26`,
  `a3414b46`, `68449b05`): their product candidates stored no `image_url`, so the UI shows no image though one is on disk.
- Generic site art stored as the story image: `1741b74a`, `fe337730`, `f0152935` all use the same Business Standard logo
  banner (same file, same URL); `0e84fbd9` uses thehindu.com `theme/images/og-image.png`. The `BAD_IMG` regex misses
  "og-image" and "Business_Standard_1_685x385".
- One tiny image: `94be3c3d` is 240x180 (ANI thumbnail). All 77 local files decode.
- 37 of 144 files in `media/news` are referenced by no candidate (orphans from over-limit and earlier runs).
- Fix: point `image_url` at the served local copy (or serve `media/`), reject images seen on 2 or more stories, add "og-image"
  and "_685x385" style names to `BAD_IMG`, require 400 px width, clean orphans.

**M7. Product news is thin and depends on the product query.** Product rows: K9 Thunder 3, K9 Vajra-T 3. Five Hanwha company
stories are about the K9 but have no product row because the product query never returned them: `59eefa67`, `04ddc306`,
`81dfa327`, `590d7a7c`, `bc6dd49c`. Adani has no row in `competitive_product`, so `--products` fetches nothing for it.
The product relevance test accepts only the exact product name. In the logs the product queries kept 0 (Thunder, both months),
2 (Vajra, June) and 0 (Vajra, Aug). Fix: assign products to company stories by name match after merging (a story whose
headline or page names a product gets a product row), instead of relying on a second search.

**M8. Signal feed (section 5 below).**

### LOW

- **L1.** 4 headlines end with " - CHOSUNBIZ" (`590d7a7c`, `04ddc306`, `1193cdec`, `4cadb405`). `parse_rss` strips the
  suffix only on an exact case match ("Chosunbiz" vs "CHOSUNBIZ"). Make it case-insensitive.
- **L2.** Publisher names are inconsistent: "조선일보" x3 next to "Chosunbiz" x4 (same group), "upi", "Bloomberg.com",
  "ETLegalWorld.com", "ET Infra" / "ET Datacenters" / "ET Manufacturing" / "The Economic Times". Add a display-name map.
- **L3.** URLs: 11 stored article URLs are on the mobile host `m.economictimes.com` (the site redirects to
  economictimes.indiatimes.com) and 2 are `http://`. Normalise the host and scheme in `clean_url`.
- **L4.** Three pages cannot be fetched by a plain client: Reuters 401 (`9caa9fde`), UPI 403 (`ed60139b`), Bloomberg 403
  (`e943daa8`). `9caa9fde` is in the signal feed (Leadership & corporate); the signal runner's `from: url` fetch will fail on it.
- **L5.** Candidate to company-story link: six company rows (`8da0e4ca`, `7e98dbb7`, `15149764`, `68449b05`, `5eb27b26`,
  `a3414b46`) have no company-owned candidate; only the product candidate points at the product row. Works as designed, but
  a trace from the company row to a candidate is empty.
- **L6.** Source tier has no gradation: Reuters, Bharatshakti and Army Recognition are all `independent`.

## 3. Category corrections

Definitions are from `prompts/news.yml`. 18 of 81 rows (22%) I would change; 7 of them are the accident definition.

| id | headline (short) | now | suggested | reason |
|---|---|---|---|---|
| 0be0e558 | 5 killed ... explosion at Hanwha facility | Leadership & corporate | new "Incident, legal & regulatory" (else Other) | accident is not management or strategy |
| 305bfe85 | Deadly blast disrupts output | Leadership & corporate | same | same |
| 5129cca4 | partially suspends Daejeon factory | Leadership & corporate | same | same |
| 8087a60f | halts company-wide production | Leadership & corporate | same | same |
| 9caa9fde | CEO banned from foreign travel | Leadership & corporate | same | a criminal probe, not a management change |
| ea796f5b | labor ministry crackdown | Other | same | keep the thread in one category |
| c695ef7b | Tears and tributes for victims | Other | same | same |
| 04ddc306 | wins US Army deal for K9 prototypes | Contract & order | Export | a contract with a foreign customer; the definitions overlap, add a tie-break "foreign customer = Export" |
| 74283a00 | selected to build prototypes for US Army | Contract & order | Export | same event as 04ddc306 (should be one story) |
| 70d2b4d0 | ends $320m eVTOL supply deal | Other | Non-defence business | civil aerospace, no defence angle |
| 0e84fbd9 | Uttar Pradesh strengthens defence sector (Adani Kanpur) | Other | Facility & capacity | article is about Adani ammunition plant expansion, 2,000 staff, new jobs; as "Other" it is hidden from signals |
| 686104bd | Adani Group "lying brazenly" ... airline plans | Other | Non-defence business | airline ambition, no defence angle |
| 954995a0 | Tamil Nadu MoU Rs 18,600 cr with L&T | Partnership / JV | Non-defence business | data centre and civil projects (low confidence) |
| d9369d21 | L&T partners FAYAT for BOMAG road equipment | Partnership / JV | Non-defence business | civil equipment distribution |
| ed60139b | first S&P rating | Other | Financial results | credit rating is a financial disclosure; add it to the definition |
| 60cafbcc | sets up Saudi unit | Leadership & corporate | Facility & capacity | new local entity for the Middle East push (low confidence) |
| 1c7c67aa | Defence Secretary on fast-tracking Zorawar | Other | Contract & order | procurement of L&T's light tank (low confidence) |
| 7e98dbb7 | Canada eyes Hanwha K9 | Other | Export | prospective foreign sale (low confidence) |

Not changed but note: the model gave the right category for the other 63; its reasons are one sentence each and are stored.

Definition problems to fix in `news.yml`:
1. Add a category for accidents, safety, prosecutions and regulatory action (Hanwha has 473 safety violations, prosecution and a
   court penalty in October alone, which will all land in "Other" or "Leadership & corporate").
2. Say which wins when an item is both a contract and an export (suggest: foreign customer = Export).
3. Say that a civil partnership or civil MoU is Non-defence business (the text covers only "a civil contract").
4. Put credit ratings under Financial results.
5. Make the model assign "Other" only when no category fits; today it is 22% of the data.

## 4. API limitations (measured 2026-10-16)

| Item | Measurement |
|---|---|
| Items per RSS query | Hard cap 100. Hanwha month queries return exactly 100 (both queries). L&T 54 and 100. |
| Month window vs short windows | See H2: month returns 1/2.3 to 1/3.5 of what daily windows return (unique links). Even far below the cap. |
| Date operators, depth | Work back to 2015. Items per month for "Hanwha Aerospace" / "L&T defence": 2025-06 24 / 20, 2024-06 24 / 15, 2023-06 9 / 20, 2022-06 10 / 7, 2020-06 2 / 2, 2018-06 0 / 3, 2015-06 0 / 1. Thin before 2023. |
| Date operator accuracy | 100% of returned items fell inside the requested range in every probe (about 190 items). RSS pubDate vs page date: 67 of 70 within one day (3 errors, section M5). |
| Alias effect on volume | "Adani Defence" returns 44 items (month) vs 14 for "Adani Defence & Aerospace". The pipeline queries only the long name, and the relevance test needs it too. |
| Edition `hl=en-IN` | Identical results with `en-US` and `en-GB` on three queries (0 items differ). No loss from the edition. A non-English edition (Korean) was not tested. |
| Allowlist drops | Of 644 logged drops (two fetch logs + Oct probe): 375 unknown domain (58%, 179 domains), 159 not about subject (25%), 51 over limit, 21 outside range, 31 blocked list (15 defence.in, 12 data/market sites, 3 social, 1 blog). |
| Resolve failures | 0 "unresolved" among processed items in both logs. Wrapper resolution uses an undocumented `batchexecute` call plus a disk cache; it works today and is the most likely thing to break silently. |
| Page blocked | 5 of 72 kept items (7%): Hanwha June 2x http 401, 2x http 403; Hanwha Aug 1x 403. They are stored with no image. |
| Images | 66 of 72 kept items got an image (92%); 5 blocked pages, 1 "no image declared". |
| Time per competitor | Hanwha 34 s (June), 57 s (Aug); L&T 25 s, 32 s; Adani 1 s, 4 s. Product queries add 4-7 s. 12 rapid RSS calls: all 200 in 3.2 s. No 429 seen. |
| `--limit` | Counts per query run (company, or one product), not per window. Hanwha June hit it exactly (20); L&T Aug hit it (20). Second query is skipped once the limit is reached. |
| Product queries | Kept 0 / 2 / 0 items in three of four logged runs; Adani has no product rows. |

### Allowlist recommendations (from drop counts)

Add as `independent` (established editorial or trade outlets that carried relevant stories):
- Korea business and defence press: `mk.co.kr` and `pulse.mk.co.kr` (17+4 drops), `businesskorea.co.kr` (10), `en.sedaily.com` (7),
  `asiae.co.kr` (9), `mbiz.heraldcorp.com` (3, Herald group), `mt.co.kr` (3), `ajupress.com` (4), `donga.com`, `fntimes.com`,
  `thelec.net` (15, electronics trade).
- Defence trade and wires: `defence-industry.eu` (5), `defencesecurityasia.com` (3), `asiapacificdefencereporter.com` (3),
  `canadiandefencereview.com`, `nationalinterest.org` (3), `joint-forces.com` (2), `zona-militar.com` (2), `euro-sd.com` is already listed.
  Spot check each for a named editor before adding; `defence-blog.com` (6) is mixed quality, add only with that check.
- India business and trade: `swarajyamag.com` (6), `manufacturingtodayindia.com` (3), `zeebiz.com` (2), `etnownews.com` (3),
  `freepressjournal.in`, `telanganatoday.com` (3), `constructionworld.in` (3), `oilandgasmiddleeast.com`, `rareearthexchanges.com`,
  `aa.com.tr` (Anadolu).
- Domain-learning fix: `hanwha.com`, `larsentoubro.com`, `adanidefence.com` as company domains from the competitor row so own newsroom
  pages are always primary.

Keep blocked (these would add noise or low-trust text):
- Market-data and tip sites: `finance.biggo.com` (17), `scanx.trade` (12), `ad-hoc-news.de` (12), `marketwatch.com` (8), `kalkine.co.in` (8),
  `tradebrains.in` (6), `upstox.com` (5), `tradingview.com` (4), `univest.in`, `cryptorank.io`, `simplywall.st`, `marketscreener.com`.
- Exam-prep and explainer sites: `ssbcrack.com` (6, plus `shop.ssbcrack.com`), `vajiramandravi.com` (4), `gktoday.in`,
  `indianmasterminds.com`, `envantermedya.com`.
- Opinion or partisan or sensational: `pgurus.com`, `opindia.com`, `eurasiantimes.com`, `republicworld.com` (borderline, review), `en.defence-ua.com`.
- Forums and social: `defence.in` (15), `instagram.com`.

### Fetch-side recommendations (summary)
1. Query by 1-3 day windows, merge, and cap per window (H2, H5).
2. Query and match on aliases; store aliases in the competitor row (H1).
3. Drop stock-tip headlines before the limit (M2).
4. Compare the page date with the RSS date (M5).
5. Run the 09-17..10-16 window again after the fix and log it (H4).

## 5. Signal subjects (prompts/signal.yml)

The query takes company-news rows whose category is not Stock & market, Non-defence business or Other. That feeds **41** rows to
the model and leaves out **40**.
- Included but noise (about 14): the 7 accident rows (once the category is fixed they drop out); `2ed01180` (Jeet Adani statement,
  an opinion); `842a6e3f`, `f76d7a3b`, `c389333b`, `993f5d83` (L&T corporate items with no defence event); `4d799eea`;
  `a4665356`, `60cafbcc`. Step 1 of the signal prompt rejects most of these ("no concrete event"), so the cost is model calls,
  not wrong cards. `9caa9fde` will fail on the Reuters 401 page.
- Included, duplicated by missed merges: `04ddc306` + `74283a00` (same award), `67ef6459` + `bc6dd49c` (same UAE deal),
  `0be0e558` + `305bfe85` + `5129cca4` + `8087a60f` (blast thread). These will produce two or more signal cards for one event.
- Left out that should be signals (category too coarse): `0e84fbd9` (Adani Kanpur expansion, filed as Other),
  `1c7c67aa` / `08ad864f` / `0764eda4` (Zorawar light tank, a core L&T land-systems programme, filed as Other),
  `7e98dbb7` (Canada eyes K9, Other), `34e2afa9` (US Army acquisition chief at Hanwha, Other), `274ac0f5` (SIDM export award, Other).
  Excluding "Other" outright hides real events whenever the model is unsure.
- Left out correctly: Stock & market (9) and Non-defence business (13) apart from the above.
- Fix: fix categories first (section 3), merge duplicates (H3), then keep the exclusion list but add a short
  pre-filter "headline names an event verb" rather than excluding by category only; or allow "Other" through when the
  headline names a product or programme from `client_products` or the competitor product list.

## 6. What is fine

- Candidates: 122 rows, 0 `new`, 81 `story` + 41 `merged`; every `story_id` exists; each `story` candidate's id equals its row id;
  0 duplicate URLs per owner (also 0 across owners per competitor). The 6 company rows without an own candidate are by design.
- Product rows: all 6 have a company row with the same URL, headline, date and category.
- Company and product table consistency of `category` is perfect (0 mismatches).
- `fact_source`: every company row has `article_url` and `category` rows; `also_reported_by` rows exist for every merged
  candidate; reasons are stored.
- Publishers and URLs: 78 of 81 URLs return 200; no homepage, AMP or Google-wrapper links stored. Headlines match the page title
  in the 78 pages that load (I compared the first 70-90 characters; differences are only the site suffix and `&amp;`). Publisher names are the real outlet in every checked row.
- Dates: 67 of 70 within one day of the page date.
- Images: all 77 local files exist and decode; all 72 remote image URLs answer 200.
- Merges inside a batch are good: Spain K9 (4 outlets), US Army prototypes (6 outlets), AK-203 ammunition (8 outlets), Chunmoo
  Croatia (4 outlets, different dates and amounts but one order), LNG US unit, BESS order, Samarthak delivery (PIB + ET Infra).
- The model's category reasons are sensible and cite the definition; "do not drop an article" and handle validation worked
  (0 warnings, 0 left new). One run needed a JSON retry and recovered.
- `python -m backend.news --selftest` passes. The per-owner unique id and the source allowlist/blocklist behaved as documented
  on everything I saw. I did not test `pre_group` beyond the self-test.
- Cost is low: the 10 news runs cost about 0.6 USD in total.

## 7. Things I could not verify

- The 09-17..10-16 fetch log (H4).
- The content of Chosun item dated 06-24 in `0be0e558` (page returns an empty shell).
- Pages for Reuters, UPI and Bloomberg (blocked); headlines taken from the RSS only.
- Whether the UI hides Stock & market or Non-defence rows; I read only the data side (`a_competitive.build_news`).
