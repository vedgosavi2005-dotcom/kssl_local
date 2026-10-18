import { clientShort } from "./client.js";
import { globalRequirements } from "./globalRequirements.js";
import { momentsOf } from "./moments.js";
/* Overview feed: the sequence logic, the group split, and the per-pillar metric
   strip. Pure — it returns data, and the React components render it. */
import { isVisible, viewVisible } from "./visibility.js";
import { navTitle } from "./route.js";
import { COMPETITIVE_TITLE } from "./chrome.js";

export const SEQ_LABEL = {
  recency: "Most Recent First",
  category: "Grouped by Domain",
};
export const SEQ_SUB = {
  recency: "newest signals at top",
  category: "ordered by category",
};

/* WHAT THE DROPDOWN OFFERS, not what the engine can do. `category` is off the menu at the operator's
   request; its comparator below is untouched, but readFeedSeq() accepts only the menu options, so a
   saved session carrying category falls back to priority. Re-listing it here (and in SEQ_MODES) is the whole of putting it back. */
export const SEQ_OPTIONS = [
  ["priority", "Priority (threats first)"],
  ["recency", "Most recent"],
];

const MONTHS = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

/* A sortable number for a displayed date; newer = higher.
   'DD Mon YYYY' -> 20260830, 'Mon YYYY' -> 20260900, 'Nd ago' -> most recent.

   Replaces a month-precision predecessor that returned year*12+month, under which
   '11 Aug 2026' and '30 Aug 2026' were the SAME number. Both date shapes are real:
   serving.signal_detail states the day ('30 Aug 2026') while signal_card.ago is often
   month-only ('Sep 2026'), so a comparator has to order across the two. A month-only
   value takes day 0, which puts it after every dated day of that month when sorting
   newest-first, and still ahead of the whole previous month. */
export function dateVal(s) {
  if (!s) return 0;
  const t = String(s).toLowerCase().trim();
  if (/ago\b/.test(t)) return 99999999; // '1d ago' is newer than any printed date
  let m = t.match(/(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})/);
  if (m) {
    return parseInt(m[3], 10) * 10000 + (MONTHS[m[2]] || 0) * 100 + parseInt(m[1], 10);
  }
  m = t.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (m) {
    return parseInt(m[1], 10) * 10000 + parseInt(m[2], 10) * 100 + parseInt(m[3], 10);
  }
  m = t.match(/([a-z]{3})[a-z]*\.?\s+(\d{4})/);
  if (m) return parseInt(m[2], 10) * 10000 + (MONTHS[m[1]] || 0) * 100;
  m = t.match(/(\d{4})/);
  if (m) return parseInt(m[1], 10) * 10000;
  return 0;
}

/* Stamp `dirs` onto a pillar's priority groups so buildFeed cuts them by CONTENT.

   The first group claims the threat direction; the last takes everything else (the
   `last` rule inside buildFeed). Groups that already declare `dirs` -- market's, which
   names more than one direction -- are left as declared. A config with
   one group has nothing to split and is passed through.

   Why: the served group defs carry only a heading and a size (competitive 6 + 99,
   technology 13 + 99), written against a demo dataset in which the first n cards
   happened to be the threats. On the live-shape dump every technology card is
   dir=watch, and the heading over all five of them read "Priority -- Capability Gaps
   -- rivals advancing in KSSL categories"; with 254 cards the other way round, 37
   threats sat under "Capability-Frontier Moves". `n` stays for any consumer still
   reading it, but it no longer decides who is in the group. */
/* A card carries a space-separated `tags` string. Both the feed grouping and the filter
   pills can select on a tag (technology's rival/adopt) as well as on `dir` (market's
   tenders/opportunities), so this one predicate is shared by both. */
export function cardHasTag(card, tag) {
  return String((card && card.tags) || "").split(/\s+/).includes(tag);
}

/* Does a card belong under a direction-filter pill? A pill may select by a single `dir`
   (the default, e.g. competitive threat/watch), an array of `dirs` (market "Latest
   Tenders" = kind tender), or a `tag` (technology "Competitor Advancements" = rival). One
   resolver so Overview.jsx's feed, its filter counts and Layout.jsx's count line agree. */
export function filterMatch(card, filterKey, filters) {
  if (!filterKey || filterKey === "all") return true;
  const fo = (filters || []).find((x) => x.f === filterKey);
  if (fo && fo.tag) return cardHasTag(card, fo.tag);
  if (fo && Array.isArray(fo.kinds) && fo.kinds.length) return fo.kinds.indexOf(card.kind) >= 0;
  if (fo && Array.isArray(fo.dirs) && fo.dirs.length) return fo.dirs.indexOf(card.dir) >= 0;
  return card.dir === filterKey;
}

export function cutGroupsByDirection(groups, firstDirs = ["threat"]) {
  const list = Array.isArray(groups) ? groups : [];
  if (list.length < 2) return list.map((g) => ({ ...g }));
  if (list.some((g) => g && ((g.dirs && g.dirs.length) || (g.kinds && g.kinds.length)))) return list.map((g) => ({ ...g }));
  return list.map((g, i) => (i === 0 ? { ...g, dirs: firstDirs.slice() } : { ...g }));
}

/* THE ONE COMPARATOR. Every surface that orders signal cards calls this.

   Direction first (threat, watch; no stance last), then the card's date, newest first, then the sequence number the database
   stores for the card (ruling R5). Nothing here grades a card: severity, impact and shortlist ordering are
   judgements the browser does not make, and a severity field on a card is never read.

   A CARD WITH NO DATE SORTS LAST. dateVal("") is 0 and the date key is descending, so an undated card falls to the
   bottom of its direction band rather than sorting as though it were published today; SignalCard prints "date not
   known" on it rather than an empty corner. A card with no stored sequence follows the sequenced ones of its date,
   in the order it was served. */
export const DIR_RANK = { threat: 0, watch: 1 };
export const NO_DATE_LABEL = "date not known";

const seqOf = (c) => {
  const n = c && c.seq != null && c.seq !== "" ? Number(c.seq) : NaN;
  return Number.isFinite(n) ? n : null;
};
const bySeq = (a, b) => {
  const x = seqOf(a);
  const y = seqOf(b);
  return x === y ? 0 : x === null ? 1 : y === null ? -1 : x - y;
};

/* THE RISK ORDER (competitive spec): probability x impact first (card.risk, from the stored scores); on a tie the one that
   lands sooner (stored time_to_effect), then the one in a client market (stored in_client_market). */
const TTE_RANK = { lt_1y: 0, "1_3y": 1, gt_3y: 2 };
const tteOf = (c) => (c && c.timeToEffect in TTE_RANK ? TTE_RANK[c.timeToEffect] : 3);
const inMarketOf = (c) => (c && String(c.inClientMarket || "").toLowerCase() === "yes" ? 0 : 1);
export const compareRisk = (a, b) => (b.risk || 0) - (a.risk || 0) || tteOf(a) - tteOf(b) || inMarketOf(a) - inMarketOf(b);

/* At most THREAT_CAP threats are shown (competitive spec): the riskiest by compareRisk; the cards behind them stay on
   record but are not offered on the overview. Every other card passes through, in its order. */
export function capThreats(cards, cap) {
  const top = new Set((cards || []).filter((c) => c && c.dir === "threat").sort(compareRisk).slice(0, cap));
  return (cards || []).filter((c) => !c || c.dir !== "threat" || top.has(c));
}

export function compareCards(data) {
  const when = (c) => dateVal(signalDate(c, data));
  return (a, b) =>
    (DIR_RANK[a.dir] === undefined ? 9 : DIR_RANK[a.dir]) -
      (DIR_RANK[b.dir] === undefined ? 9 : DIR_RANK[b.dir]) ||
    /* card.risk is probability x impact, computed by the backend (a_competitive.signal risk), then sooner effect,
       then in a client market (compareRisk). Riskier first inside a stance band. */
    compareRisk(a, b) ||
    when(b) - when(a) ||
    bySeq(a, b);
}

/* Ordered, re-ranked and split into the groups the feed renders.

   `data` is what the cards are DISPLAYED with: the date on a card comes from
   signalDate(card, data), which prefers the day-precision date in the detail panel over
   the card's own month-only `ago`. Sorting on `ago` while printing signalDate() is what
   produced a threat list reading Sep 2026, 11 Aug, 30 Aug, 11 Aug, 20 Aug, 4 Aug -- the
   order was real, it just belonged to a different set of values than the ones on screen.
   The comparator and the label have to read the same field. */
export function buildFeed(cfg, seqMode, data) {
  const cmp = compareCards(data);
  const when = (c) => dateVal(signalDate(c, data));
  let cards = (cfg.cards || []).slice();
  /* EVERY MODE ENDS IN THE SAME COMPARATOR. A sequence option changes which key leads,
     never the order inside a tie. */
  if (seqMode === "recency") {
    cards.sort((a, b) => when(b) - when(a) || cmp(a, b));
  } else if (seqMode === "category") {
    cards.sort((a, b) => String(a.meta).localeCompare(String(b.meta)) || cmp(a, b));
  } else {
    cards.sort(cmp);
  }
  // re-rank display numbers after sort (a copy — the dataset card is not renumbered)
  cards = cards.map((c, n) => ({ ...c, rank: String(n + 1).padStart(2, "0") }));

  /* Only the "priority" branch needs group defs; without them, fall back to the single
     "All signals" bucket the other modes use, so buildFeed(cfg, "priority") on a cfg
     that carries no `groups` degrades to one flat group instead of throwing on the
     `groupDefs.some(...)` deref below. */
  const groupDefs =
    seqMode === "priority" && cfg.groups && cfg.groups.length
      ? cfg.groups
      : [{ n: 99, h: SEQ_LABEL[seqMode] || "All signals", s: SEQ_SUB[seqMode] || "" }];

  const groups = [];
  let idx = 0;
  /* CONTENT, NOT POSITION. A group def carrying `dirs` claims the cards whose direction
     it names, wherever they sort. Without this the heading described a slice of the
     ranking -- "Live Opportunities" was simply the top three cards, whatever they were.
     Feeds whose defs carry no `dirs` keep the index behaviour below unchanged. */
  const byContent = groupDefs.some((g) => (g.dirs && g.dirs.length) || (g.kinds && g.kinds.length) || (g.tags && g.tags.length));
  if (byContent) {
    const claimed = new Set();
    const claims = (g, c) =>
      (g.dirs || []).indexOf(c.dir) >= 0 ||
      (g.kinds || []).indexOf(c.kind) >= 0 ||
      (g.tags || []).some((t) => cardHasTag(c, t));
    groupDefs.forEach((g, i) => {
      const last = i === groupDefs.length - 1;
      const slice = cards.filter(
        (c) => !claimed.has(c) && (last || claims(g, c)),
      );
      slice.forEach((c) => claimed.add(c));
      if (slice.length) groups.push({ h: g.h, s: g.s, cards: slice });
    });
    return { groups, total: (cfg.cards || []).length };
  }
  groupDefs.forEach((g, i) => {
    /* The LAST group takes everything still unassigned. The group defs carry fixed
       sizes (competitive is 6 + 99) that were written against a demo dataset of about
       forty cards; production serves 429, so a plain `slice(idx, idx + g.n)` dropped
       324 of them on the floor while the footer still counted all 429 -- the feed said
       "end of active signals, 429 total" under a list that stopped at 105. A group
       total is a layout hint for the first bucket, never a limit on the corpus. */
    const last = i === groupDefs.length - 1;
    const slice = last ? cards.slice(idx) : cards.slice(idx, idx + g.n);
    if (!slice.length) return;
    idx += slice.length;
    groups.push({ h: g.h, s: g.s, cards: slice });
  });
  return { groups, total: (cfg.cards || []).length };
}

/* The date a signal is shown with, in ONE format everywhere.

   The card aside printed the pipeline's `ago` ("Aug 2026") while the detail panel beside
   it printed the same event's day-precision date ("11 Aug 2026") -- 730 of 813 cards
   disagreed with their own panel, both on screen at once. That is what the report meant
   by dates being wrong and the format inconsistent: not that the day was incorrect, but
   that the same signal carried two different answers.

   The panel's value is the richer one and comes from the same pipeline field, so it wins
   when it exists; `ago` remains the fallback for the 83 rows that carry no day. Nothing
   is reformatted or re-derived here -- deriving a date a fourth way is how this started. */
export function signalDate(card, data) {
  const facts = ((data && data.details && data.details[card && card.id]) || {}).facts || [];
  let raw = "";
  for (const row of facts) {
    if (Array.isArray(row) && row[0] === "Date" && row[1]) { raw = String(row[1]); break; }
  }
  /* a stored ISO day ("2026-10-11") is written in the house style ("11 Oct 2026"), like every other date on screen;
     inline for the same reason as the padding below */
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const house = (v) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:$|[T\s])/.exec(String(v || ""));
    return m && MON[Number(m[2]) - 1] ? `${m[3]} ${MON[Number(m[2]) - 1]} ${m[1]}` : String(v || "");
  };
  raw = house(raw);
  const ago = house((card && card.ago) || "");
  if (!raw) raw = ago;
  /* THE VALUE WITH A DAY WINS. The facts "Date" is normally the richer field, but a
     few rows carry it month-only ("Sep 2026") while `ago` was upgraded to the exact day
     from the article's dated URL (see dataset.urlDate). A month-precision fact must not
     override a day-precision one, or a Sep-9 story reads "Sep 2026" beside its own URL. */
  const dayish = (s) => /^\d{1,2}\s+[A-Za-z]/.test(s);
  if (!dayish(raw) && dayish(ago)) raw = ago;
  /* Zero-pad a single-digit DAY so every card and panel reads "04 Aug 2026", not
     "4 Aug 2026" (the operator's one-width ask, mirrored in utils/formatDate). Only a
     "D Mon YYYY" value carries a day to pad: a month-only value ("Sep 2026") and a
     relative one ("1d ago") have none and pass through untouched. Kept inline --
     test_signal_date imports this function alone, so it can call no other module. */
  return raw.replace(/^(\d)(\s+[A-Za-z]{3}[A-Za-z]*\.?\s+\d{4})$/, "0$1$2");
}

/* How many signals one page of the feed shows. */
export const FEED_PAGE_SIZE = 50;

/* The page the reader was on, remembered per pillar for the session.

   `page` was React state and nothing else, so a reload, or a detour to Competitor and
   back (Layout remounts the feed per view), put the reader on page 1 again: the route
   remembered the pillar and the view but not the page. This keeps it in a Storage-shaped
   object (sessionStorage in the browser -- a tab's worth, not a stale page number from
   last week) under one key, as {pillar: {key, page}}.

   `key` names the FILTER the page was saved under (sequence, direction, tile, both
   search strings). A page is restored only for the same key: page 7 saved on "All" must
   not land on "Threat", which may be one page long. paginateFeed still clamps whatever
   comes back, so a corpus that shrank cannot produce a blank feed. Storage access is
   wrapped because a private window throws on it. */
export const FEED_PAGE_KEY = "kssl_feed_page";

function readFeedPages(store) {
  try {
    const raw = store && store.getItem(FEED_PAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (e) {
    return {};
  }
}

export function readFeedPage(store, pillar, key) {
  const saved = readFeedPages(store)[pillar];
  if (!saved || saved.key !== key) return 1;
  const n = parseInt(saved.page, 10);
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

export function writeFeedPage(store, pillar, key, page) {
  try {
    if (!store) return;
    const all = readFeedPages(store);
    all[pillar] = { key, page: Math.max(1, parseInt(page, 10) || 1) };
    store.setItem(FEED_PAGE_KEY, JSON.stringify(all));
  } catch (e) {
    /* storage refused (private mode, quota) -- the page simply is not remembered */
  }
}

/* ONE rule, two names. Two QA passes found this bug independently and each wrote its
   own helper: a search box that matched nothing said "no signals served yet" -- the
   message for an EMPTY CORPUS -- beneath a box holding the reader's own query.
   emptyFeedNote below is the one that survives; it says the same thing and quotes the
   query back. `emptyNote` is kept as an alias because a test names it, and because two
   functions computing one rule is how this codebase has produced disagreeing answers
   before. */
export const emptyNote = (args) => emptyFeedNote(args);

/* The sequence the reader chose, remembered per pillar for the session, beside the
   page. It was React state only, so a reload put the reader back on "Priority" --
   and since the remembered page is keyed by the sequence, the page that survived was
   page 1 of a sequence they had not chosen. Only a mode this build offers is
   restored; storage access is wrapped for the same reason as the page's. */
export const FEED_SEQ_KEY = "kssl_feed_seq";
const SEQ_MODES = new Set(SEQ_OPTIONS.map(([v]) => v));

export function readFeedSeq(store, pillar) {
  try {
    const raw = store && store.getItem(FEED_SEQ_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    const v = parsed && typeof parsed === "object" ? parsed[pillar] : null;
    return SEQ_MODES.has(v) ? v : "priority";
  } catch (e) {
    return "priority";
  }
}

export function writeFeedSeq(store, pillar, mode) {
  try {
    if (!store) return;
    const raw = store.getItem(FEED_SEQ_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    const all = parsed && typeof parsed === "object" ? parsed : {};
    all[pillar] = mode;
    store.setItem(FEED_SEQ_KEY, JSON.stringify(all));
  } catch (e) {
    /* storage refused -- the sequence simply is not remembered */
  }
}

/* Flatten the grouped feed to the cards a filter keeps, remembering which group each
   came from, then hand back one page of them re-grouped for render. Pure, so the page
   maths can be checked without a browser.

   `page` is 1-based and clamped: a filter that shrinks the list under the current page
   must not leave the reader staring at an empty feed. */
export function paginateFeed(groups, keep, page, size = FEED_PAGE_SIZE) {
  const flat = [];
  (groups || []).forEach((g) => {
    (g.cards || []).forEach((c) => {
      if (!keep || keep(c)) flat.push({ g, c });
    });
  });
  const pageCount = Math.max(1, Math.ceil(flat.length / size));
  const cur = Math.min(Math.max(1, page || 1), pageCount);
  const from = (cur - 1) * size;
  const slice = flat.slice(from, from + size);

  // re-group the slice: consecutive cards from the same group share one header
  const pageGroups = [];
  slice.forEach(({ g, c }) => {
    const tail = pageGroups[pageGroups.length - 1];
    if (tail && tail.h === g.h) tail.cards.push(c);
    else pageGroups.push({ h: g.h, s: g.s, cards: [c] });
  });

  return {
    groups: pageGroups,
    page: cur,
    pageCount,
    shown: flat.length,
    /* 1-based inclusive range, for "showing 101-150 of 429" */
    from: flat.length ? from + 1 : 0,
    to: from + slice.length,
    firstId: flat.length ? flat[0].c.id : null,
    /* which page a given card sits on -- the global search jumps straight to it */
    pageOf: (id) => {
      const at = flat.findIndex((x) => x.c.id === id);
      return at < 0 ? null : Math.floor(at / size) + 1;
    },
  };
}

/* The open / awarded / closed split, defined once so the nav badges, the tender
   tabs and the market metric tiles can never disagree on what "open" means. */
export function bucketTenders(tenders) {
  const list = tenders || [];
  const isAwarded = (t) => (t.status || "").toLowerCase() === "awarded" || t.urlKind === "award";
  const isClosed = (t) =>
    !isAwarded(t) && (t.isLive === false || t.dl <= 0 || (t.deadline || "").includes("Closed"));
  return {
    awarded: list.filter(isAwarded),
    closed: list.filter(isClosed),
    open: list.filter((t) => !isAwarded(t) && !isClosed(t)),
  };
}

/* The Market OVERVIEW "Latest Tenders" section is the head of the pipeline, not the pipeline. The report and the
   Tender Pipeline list every tender; the overview lists the first ATTENTION_HEAD open tenders in the order the
   database ranks them (serving.market_tender.rank_position), the unranked after them, newest first.

   No score is computed: a fit weight, a market bonus or a closing-soon bonus would be a judgement the database does
   not hold. The count is deterministic -- min(head, open) -- and pure: the promoter (dataset.js) and the metric
   strip (metricsFor) both read this, so the visible list and the "Latest tenders" tile count can never drift. */
export const ATTENTION_DAYS = 14;
export const ATTENTION_HEAD = 20;
export function marketAttention(openTenders) {
  const open = openTenders || [];
  const rec = (t) => dateVal(t.posted || t.closingDate || t.ago);
  const rank = (t) => (t.rank != null && t.rank !== "" && Number.isFinite(Number(t.rank)) ? Number(t.rank) : null);
  return open
    .slice()
    .sort((a, b) => {
      const x = rank(a);
      const y = rank(b);
      return (x === y ? 0 : x === null ? 1 : y === null ? -1 : x - y) || rec(b) - rec(a);
    })
    .slice(0, ATTENTION_HEAD);
}

/* The Technology OVERVIEW is KNOWLEDGE, not a threat board. Competitive already owns the
   threat comparison -- anything that directly impacts KSSL is a competitive threat there --
   so this pillar drops the gap/watch framing entirely and reads as two knowledge streams:
   COMPETITOR ADVANCEMENTS (a tech move by a tracked competitor) and ADOPTABLE ADVANCES
   (defence-tech from anyone else that KSSL could learn from or adopt). The split is
   grounded: the pipeline sets `card.competitor` only when it resolved the actor to a
   tracked competitor, so that field's presence IS the classifier -- no name-matching.

   Every card is neutralised to dir='watch' (knowledge, so no red "gap" band) and tagged
   `rival` or `adopt`; the feed groups and the filter pills select on that tag. The two
   streams are each capped so both are represented on the shortlist. Pure -- the promoter
   (dataset.js) reads it for the feed, metricsFor counts the tags, navCounts counts the
   same cards. The full lane stays in d.techCards for global search; nothing is deleted. */
export const TECH_ATTENTION_HEAD = 30;
export function isRivalCard(c) {
  return !!(c && c.competitor && String(c.competitor).trim());
}
function withTag(card, tag) {
  const t = String((card && card.tags) || "").trim();
  // a stored threat stays a threat (red-team 2026-10-18: forcing "watch" hid 52 stored threats); anything else reads
  // as watch (the UI shows only the threat and watch stances)
  return { ...card, dir: card && card.dir === "threat" ? "threat" : "watch", kind: tag, tags: t ? `${t} ${tag}` : tag };
}
export function technologyAttention(cards, isRival = isRivalCard, head = TECH_ATTENTION_HEAD) {
  const list = Array.isArray(cards) ? cards : [];
  const rivalFn = typeof isRival === "function" ? isRival : isRivalCard;
  const byRecent = (a, b) => dateVal(b && b.ago) - dateVal(a && a.ago);
  const rival = list.filter((c) => c && rivalFn(c)).sort(byRecent).map((c) => withTag(c, "rival"));
  const adopt = list.filter((c) => c && !rivalFn(c)).sort(byRecent).map((c) => withTag(c, "adopt"));
  // both streams represented: competitor advances lead a ~60% share, adoptable fills the rest
  const rHead = rival.slice(0, Math.ceil(head * 0.6));
  const aHead = adopt.slice(0, head - rHead.length);
  return rHead.concat(aHead);
}

/* Live counts from the served data, so the strip can never drift from the feed.
   Every pillar computes its tiles — the config carries labels and phrasing only;
   a number the service didn't back is never rendered. */
export function metricsFor(cfg, pillar, d) {
  /* EVERY TILE STARTS AT "NOT MEASURED".

     The binding at the bottom of this function is by KEY (the tile key, chrome.js), never by the tile's
     label text -- the label is a database word that may be edited -- and a key no
     branch computes used to keep whatever `v` the config shipped -- the sample
     constants baked into overviewConfig ("13", "73,895", "6") -- which CountUp then
     animated up exactly like a measured figure. Two ways that happened with nothing
     on screen to show it: a served label renamed on the backend, and the catch below
     firing part-way through the block (that is how "Open opportunities 7" once sat
     over 89 open tenders). Blanking the values FIRST means both cases render "—",
     and the unbound branch at the end names the tile that missed, loudly. */
  const metrics = (cfg.metrics || []).map((m) => ({ ...m, v: "—" }));
  try {
    const cards = cfg.cards || [];
    /* A DIRECTION TILE COUNTS SOMETHING ITS FEED MAY NOT CARRY AT ALL.

       serving_fill.py assigns dir='threat' only where pillar=='competitive', so the
       technology feed's "Capability threats" counted a value that cannot exist and
       printed a measured-looking 0 under the served subtitle "rivals ahead /
       closing". A 0 there reads as "no rival is ahead" -- a finding nobody made.
       When NO card in the pillar carries the direction, the tile says so instead of
       counting to zero; when one does, it counts normally, so the day the backend
       starts assigning threats on technology this tile starts working by itself. */
    const dirCount = (dir) => {
      const n = cards.filter((c) => c.dir === dir).length;
      return n || "—";
    };
    const dirSub = (dir, word) =>
      cards.some((c) => c.dir === dir)
        ? null
        : `no served ${pillar} signal is assigned a ${word} direction - not assessed`;
    /* Two tiles showing one number is one tile. Every served technology card carries
       dir='watch', so "Watch signals" and "All signals" sit side by side reading the
       same count -- and a reader has no way to tell that from two measurements that
       happen to agree. The subtitle says which it is. */
    const dirIsAll = (dir) => {
      const n = cards.filter((c) => c.dir === dir).length;
      return n > 0 && n === cards.length
        ? `every one of the ${cards.length} served signals - no other direction is assigned`
        : null;
    };
    let byKey = {};
    const subByKey = {};
    /* The sublines above that report a MISSING measurement rather than describing a
       present one. See the note where m.warn is set. */
    const WARN_SUBS = new Set();
    if (pillar === "competitive") {
      byKey = {
        threats: dirCount("threat"),
        watch: dirCount("watch"),
        companies_tracked: new Set(cards.map((c) => c.company).filter(Boolean)).size,
      };
      const tSub = dirSub("threat", "threat");
      if (tSub) { subByKey.threats = tSub; WARN_SUBS.add(tSub); }
      const wSub = dirSub("watch", "watch") || dirIsAll("watch");
      if (wSub) { subByKey.watch = wSub; WARN_SUBS.add(wSub); }
    } else if (pillar === "market") {
      /* THE TILES PRINT THE STORED TOP OPPORTUNITY METRICS (serving.market_top_opportunity_metric), matched on the
         tile key; the value and the line under it are the stored formatted_value and note. A key with no stored row
         is "—" and says so: nothing is counted here. The doors still filter the feed (tilePredicate). */
      const stored = new Map(((d && d.topOpportunities && d.topOpportunities.metrics) || []).map((x) => [x.key, x]));
      const NOT_STORED = "not on record yet";
      (cfg.metrics || []).filter((t) => !t.blank).forEach((t) => {
        const x = stored.get(t.key);
        const has = x && x.value != null && String(x.value).trim() !== "";
        byKey[t.key] = has ? x.value : "—";
        subByKey[t.key] = has ? x.note : NOT_STORED;
      });
      WARN_SUBS.add(NOT_STORED);
    } else if (pillar === "technology") {
      const innovations = (d && d.innovations) || {};
      const domains = Object.keys(innovations).filter((k) => (innovations[k] || []).length);
      // Technology is knowledge, not a threat board: the two streams are competitor
      // advancements (a tracked rival's tech move) and adoptable advances (everyone
      // else's). Counted from the tags the promoter (technologyAttention) stamps.
      const tagCount = (t) => cards.filter((c) => cardHasTag(c, t)).length;
      byKey = {
        competitor_advances: tagCount("rival"),
        adoptable: tagCount("adopt"),
        domains_tracked: domains.length,
      };
      const rSub = tagCount("rival") ? null : "no competitor advancement is served";
      if (rSub) { subByKey.competitor_advances = rSub; WARN_SUBS.add(rSub); }
      const aSub = tagCount("adopt") ? null : "no adoptable advance is served";
      if (aSub) { subByKey.adoptable = aSub; WARN_SUBS.add(aSub); }
      const nameOf = (id) => {
        const c = ((d && d.techCats) || []).find((x) => x.id === id);
        return c ? c.name : id;
      };
      subByKey.domains_tracked = domains.length
        ? domains.map(nameOf).join("·")
        : "no domains served yet";
    }
    metrics.forEach((m) => {
      if (m.blank) { m.v = ""; return; } // an empty slot of the strip: nothing to measure
      if (byKey[m.key] == null) {
        /* LOUD, NOT SILENT. Nothing above computed a value for this key, so there
           is no measurement to show: the tile keeps its "—" and says why. */
        m.sub = `not wired - no measurement is computed for "${m.key}"`;
        m.warn = true;
        if (typeof console !== "undefined" && console.warn)
          console.warn(`metricsFor(${pillar}): no measurement bound to tile key "${m.key}"`);
        return;
      }
      m.v = String(byKey[m.key]);
      if (subByKey[m.key] != null) {
        m.sub = subByKey[m.key];
        /* AN ABSENCE OF MEASUREMENT STILL HAS TO SPEAK. The sublines marked `warn` are the sentence that
           stops a "—" or a coincidental count being read as a finding; they keep showing. */
        if (WARN_SUBS.has(subByKey[m.key])) m.warn = true;
      }
    });
  } catch (e) {
    /* The strip is cosmetic; a missing field must never blank the feed. Values were
       blanked before the try, so what survives a throw is "—", never a served demo
       number wearing the authority of a measurement. */
  }
  return metrics;
}

/* metric tile -> which signals it opens. `tags` is a space-separated string on
   each card. */
export const TILE_LABELS = {
  atstake: "at-stake items",
  threat: "threat-marked items",
  /* the Watch tile's `act` is "watch"; without this the count line ended in a bare
     " · " -- "13 of 26 signals ·" */
  watch: "watch signals",
  deadline: "by submission deadline",
  open: "latest tenders",
  fit: "strong fit",
  closing: "closing within 14 days",
  valued: "published a value",
  opps: "perceived opportunities",
  rival: "competitor advancements",
  adopt: "adoptable advances",
  geo: "markets",
  positioning: "rival matchups",
  gap: "gap comparisons",
  patents: "patent filings",
  emission: "emission items",
  all: "all signals",
};

export function tilePredicate(act) {
  const has = (c, t) => String(c.tags || "").split(" ").includes(t);
  if (act === "all") return () => true;
  if (act === "atstake") return (c) => c.dir === "threat" || c.dir === "atstake" || has(c, "atstake");
  if (act === "threat") return (c) => c.dir === "threat" || has(c, "threat");
  if (act === "watch") return (c) => c.dir === "watch" || has(c, "opening") || has(c, "watch");
  /* The promoted open tenders are the cards of kind `tender`; the opportunity cards on
     the same feed are `watch` and are not open tenders. */
  if (act === "open") return (c) => c.kind === "tender";
  /* Perceived opportunities: the demand/geopolitical watch stream, no tender required. */
  if (act === "opps") return (c) => c.kind === "opportunity";
  /* Technology streams, selected by the tag technologyAttention stamps. */
  if (act === "rival") return (c) => has(c, "rival");
  if (act === "adopt") return (c) => has(c, "adopt");
  /* Market shortlist tiles narrow the promoted set by the tag the promoter stamps
     (see dataset.js): a strong fit, a tender closing within 14 days, or a priced one. */
  if (act === "fit") return (c) => has(c, "fit");
  if (act === "closing") return (c) => has(c, "closing");
  if (act === "valued") return (c) => has(c, "valued");
  if (act === "deadline") return () => true;
  if (act === "gap") return (c) => c.dir === "threat" || has(c, "gap") || has(c, "tech");
  if (act === "patents") return () => true;
  return () => true;
}

/* ===== Dynamic nav counts (computed from live data, never hardcoded) ===== */
export function navCounts(d, gapModel) {
  const counts = {};
  try {
    // Positioning: distinct competitor companies across matchups
    const posCompanies = new Set();
    Object.values(d.matchups).forEach((m) => {
      const co = (m.comp || "").split("·")[0].trim();
      if (co) posCompanies.add(co);
    });
    counts.positioning = posCompanies.size;
    // Partnerships: competitor profiles (exclude the client's own reference network)
    counts.partnerships = Object.keys(d.competitors).filter((k) => k !== ((d.client && d.client.id))).length;
    // Geo: distinct countries across all companies' footprints
    const geoCountries = new Set();
    Object.values(d.geoData).forEach((byCountry) =>
      Object.keys(byCountry || {}).forEach((c) => geoCountries.add(c)),
    );
    counts.geo = geoCountries.size;
    /* WHAT THE OVERVIEW SHOWS, NOT WHAT THE LANE HOLDS.
       This read d.competitiveCards.length, so the rail badge said 1,212 beside a feed
       carrying 30 -- the reader's obvious conclusion being that 1,182 cards had gone
       missing. The overview is a shortlist now (lib/shortlist), so the badge counts the
       shortlist. A lane reported UNSCORED is returned whole, and there the badge counts
       the whole lane again, which is still "what the overview shows". */
    const ovCfg = (d.overviewConfig && d.overviewConfig.competitive) || null;
    counts.overview = ovCfg && Array.isArray(ovCfg.cards)
      ? ovCfg.cards.length
      : d.competitiveCards.length;
    /* Profile lists the rivals — the client's own row is not a competitor profile.
       `d.client.id` is the slug by the time this runs; wireDataset resolves it from
       the row whose dir is "client", precisely so this join is not on a display label. */
    counts.profile = Object.keys(d.competitors).filter(
      (k) => k !== ((d.client && d.client.id)),
    ).length;
    counts["threat-analysis"] = Object.entries(d.competitorNews || {}).filter(([k]) => k !== ((d.client && d.client.id))).reduce((n, [, v]) => n + momentsOf(v).length, 0);  // competitor moments on record: the competitorNews rows that carry a level
    counts.projects = (d.projects || []).length;
    if (isVisible("finances")) counts.finances = 0;

    /* Products explorer lists COMPETITOR products (Products.jsx builds them from the
       comp side of matchups + each competitor's own products), so the badge counts
       those — not KSSL's own SKUs, which is what it used to show (a "1" over a catalog
       of dozens). Same two sources the page reads, deduped by name. */
    const clientId = (d.client && d.client.id);
    const compProds = new Set();
    Object.values(d.matchups || {}).forEach((m) => {
      const nm = (m.comp || "").replace(/.*·\s*/, "").trim();
      if (nm) compProds.add(nm.toLowerCase());
    });
    Object.entries(d.competitors || {}).forEach(([cid, co]) => {
      if (cid === clientId) return;
      (co.products || []).forEach((p) => {
        const nm = typeof p === "string" ? p : (p.name || p.n || "");
        if (nm) compProds.add(nm.toLowerCase());
      });
    });
    counts.products = compProds.size;

    const { open, awarded, closed } = bucketTenders(d.tenders);
    /* The Market overview badge counts the TENDERS it opens — all of them, since the
       page carries open, awarded, closed and the portals as tabs. It used to count
       `marketCards` — three signal cards — and sat as a "3" above a page listing
       eighty-nine tenders. Tender Pipeline below it is the open subset, so the two
       rows now say different things. */
    /* The overview badge counts the CARDS the feed actually opens. That is the curated
       tender shortlist served on overviewConfig.market.cards -- NOT d.marketCards, which
       still carries the demand-news lane for search and the top bar. Counting the raw
       lane here put a 141 on a feed that shows the shortlist. */
    /* The Market overview is the tender tables now (Top tenders, Projects): its badge counts their rows. The signal
       cards moved to Global Requirements, whose badge counts them. */
    counts["m-overview"] = ["topTenders", "projectsBeforeTender"].reduce((n, k) => n + ((d.topOpportunities && d.topOpportunities[k]) || []).length, 0);   // the stored rows the two tables list
    counts["global-requirement"] = globalRequirements(d).length;   // the rows the page lists
    counts["m-report"] = (d.tenders || []).length;
    counts.tender = open.length;
    counts["awarded-tenders"] = awarded.length;
    counts["closed-tenders"] = closed.length;

    // patents badge: indexed filings, not a hardcoded 1
    counts["patents-comp"] = (d.PATENTS && d.PATENTS._meta && d.PATENTS._meta.total) || 0;
    const innovTotal = Object.keys(d.innovations).reduce(
      (n, k) => n + (d.innovations[k] || []).length,
      0,
    );
    // the Overview badge counts the FEED it opens (tech signal cards); the Innovation
    // badge counts innovations. Labelling one with the other's number was a mismatch
    // visible on screen: badge 29 above a feed of 11.
    /* And it counts the CURATED overview cards, not the whole tech lane -- the same rule
       as m-overview above. The overview is a shortlist (technologyAttention, applied in
       dataset.js), so counting d.techCards here put the whole-lane number (e.g. 904) on a
       feed showing 30. d.techCards stays the source for global search. */
    counts["t-overview"] =
      ((d.overviewConfig && d.overviewConfig.technology && d.overviewConfig.technology.cards) ||
        d.techCards || []).length;
    counts.innovation = innovTotal;
    // gap badge: how many 'behind' gaps this pillar carries -- only while the section is on
    if (isVisible("gap-analysis"))
      counts["gap-competitive"] = (gapModel || []).filter(
        (g) => g.direction === "behind" && g.pillar === "competitive",
      ).length;
  } catch (e) {
    /* counts are cosmetic; never break the app over one */
  }
  return counts;
}

/* Header strings, computed rather than hardcoded. */
export function viewMetaFor(d) {
  /* Degrade, do not throw. The try/catch below only wrapped the two loops, but the
     count lines under it dereferenced d.competitors/d.geoData/d.competitiveCards
     unguarded -- so viewMetaFor(null) / viewMetaFor({}) threw straight past the
     "static copy" the catch promises. Default d and each field so a missing dataset
     reaches the static copy with zero counts. */
  d = d || {};
  const competitors = d.competitors || {};
  const geoData = d.geoData || {};
  let allianceCount = 0;
  let geoCountries = new Set();
  try {
    Object.entries(competitors).forEach(([k, c]) => {
      if (k !== ((d.client && d.client.id)) && c.partners) allianceCount += c.partners.length;
    });
    Object.values(geoData).forEach((byCountry) =>
      Object.keys(byCountry || {}).forEach((c) => geoCountries.add(c)),
    );
  } catch (e) {
    /* fall through to the static copy below */
  }
  const partnerCount = Object.keys(competitors).filter((k) => k !== ((d.client && d.client.id))).length;
  const geoCompCount = Object.keys(geoData).filter((k) => k !== ((d.client && d.client.short))).length;
  const alertCount = (d.competitiveCards || []).length;
  const momentCount = Object.entries(d.competitorNews || {})
    .filter(([k]) => k !== ((d.client && d.client.id)))
    .reduce((n, [, v]) => n + momentsOf(v).length, 0);   // the same count as the rail badge: rows that carry a level
  const meta = {
    overview: {
      title: COMPETITIVE_TITLE,
      cnt: `${alertCount} signals`,
      filters: true,
    },
    profile: {
      title: navTitle("competitive", "profile"),
      cnt: `${partnerCount} companies tracked`,
      filters: false,
    },
    "threat-analysis": {
      title: navTitle("competitive", "threat-analysis"),
      cnt: `${momentCount} competitor moves on record · newest first`,
      filters: false,
    },
    products: {
      title: navTitle("competitive", "products"),
      /* British spelling and singular "catalogue", as every other heading (FE 18) */
      cnt: "Competitor and client products",
      filters: false,
    },
    positioning: {
      title: navTitle("competitive", "positioning"),
      cnt: `${Object.keys(d.matchups || {}).length} product matchups`,
      filters: true,
    },
    partnerships: {
      title: navTitle("competitive", "partnerships"),
      cnt: `${partnerCount} competitors · ${allianceCount} alliances mapped`,
      filters: false,
    },
    projects: {
      title: navTitle("competitive", "projects"),
      cnt: `${(d.projects || []).length} competitor projects on record`,
      filters: false,
    },
    finances: {
      title: "Finances",
      cnt: "Financial records",
      filters: false,
    },
    geo: {
      title: navTitle("competitive", "geo"),
      cnt: `${geoCompCount} competitors · ${geoCountries.size} markets · competitor activity by country`,
      filters: false,
    },
    /* m-report was the only view with no entry here, which is why Layout carried a
       hardcoded "Market Report" -- and that literal was gated on a flag covering all
       four tender views, so the page labelled "Tender Pipeline" on the rail rendered
       under the heading "Market Report". */
    "m-report": {
      title: navTitle("market", "m-report"),
      cnt: "Demand shape, spec and requirement",
      filters: false,
    },
    tender: {
      title: navTitle("market", "tender"),
      cnt: "Open tenders",
      filters: false,
    },
    "global-requirement": {
      title: navTitle("market", "global-requirement"),
      cnt: "Global requirements",
      filters: false,
    },
    "awarded-tenders": {
      title: "Awarded Tenders",
      cnt: "Awarded tenders",
      filters: false,
    },
    "closed-tenders": {
      title: "Closed Tenders",
      cnt: "Closed tenders",
      filters: false,
    },
    innovation: {
      title: navTitle("technology", "innovation"),
      cnt: "Technology developments",
      filters: false,
    },
    "patents-comp": {
      title: navTitle("competitive", "patents-comp"),
      cnt: "Patent filings",
      filters: false,
    },
    "gap-competitive": {
      title: "Gap Analysis",
      cnt: "Gap comparisons",
      filters: false,
    },
  };
  /* a section the database has switched off has no header entry either */
  Object.keys(meta).forEach((v) => {
    if (!viewVisible(v)) delete meta[v];
  });
  return meta;
}

/* What an empty feed says. It named only the tile and the direction pill, so a
   query that matched nothing -- in the feed's own box or the global search -- showed
   the served-nothing message: a reader who mistyped was told the pipeline had
   produced nothing. The query is the narrowest cut, so it is named first. */
export function emptyFeedNote({ tile, dirFilter, query, globalQuery } = {}) {
  const q = String(query || globalQuery || "").trim();
  if (q) return `no signals match "${q}"`;
  if (tile || (dirFilter && dirFilter !== "all")) return "no signals match this filter";
  return "no signals served yet";
}
