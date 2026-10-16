/* Overview feed: the sequence logic, the group split, and the per-pillar metric
   strip. Pure — it returns data, and the React components render it. */
import { bucketTenders } from "./tenderCalc.js";
import { formatDate } from "../utils/formatDate.js";

export const SEQ_LABEL = {
  recency: "Most Recent First",
  depth: "Richest Analysis First",
  category: "Grouped by Domain",
};
export const SEQ_SUB = {
  recency: "newest signals at top",
  depth: "most analytical lenses first",
  category: "ordered by category",
};

/* WHAT THE DROPDOWN OFFERS, not what the engine can do. `depth` and `category` are off
   the menu at the operator's request; their comparators below are untouched, and
   seqMode() still ACCEPTS both, so a saved URL or a restored session carrying
   ?seq=depth keeps working and simply has no menu entry to show for itself.
   Re-listing them here is the whole of putting them back. */
export const SEQ_OPTIONS = [
  ["priority", "Priority order"],
  ["recency", "Most recent"],
];

/* The words for the stored direction codes (chrome). A code that is not listed is shown as
   stored (card.classification), never coerced into one of these. */
export const DIR_WORD = { threat: "Threat", watch: "Watch", fav: "Favourable" };

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

/* A card carries a space-separated `tags` string. Both the feed grouping and the filter
   pills can select on a tag (technology's rival/adopt) as well as on `dir` (market's
   tenders/opportunities), so this one predicate is shared by both. */
export function cardHasTag(card, tag) {
  return !!card && (card.kind === tag || String(card.tags || "").split(/\s+/).includes(tag));
}

/* Does a card belong under a direction-filter pill? A pill may select by a single `dir`
   (the default, e.g. competitive threat/watch), an array of `dirs` (market "Latest
   Tenders" = fav+threat), or a `tag` (technology "Competitor Advancements" = rival). One
   resolver so Overview.jsx's feed, its filter counts and Layout.jsx's count line agree. */
export function filterMatch(card, filterKey, filters) {
  if (!filterKey || filterKey === "all") return true;
  const fo = (filters || []).find((x) => x.f === filterKey);
  if (fo && fo.tag) return cardHasTag(card, fo.tag);
  if (fo && Array.isArray(fo.dirs) && fo.dirs.length) return fo.dirs.indexOf(card.dir) >= 0;
  return card.dir === filterKey;
}

/* THE ONE COMPARATOR. Cards are ordered by their stored sequence_no (card.seq), ascending;
   ties and cards without one go newest first. The sequence is the stored rank, never
   re-derived from direction, severity or keywords.

   A CARD WITH NO DATE SORTS LAST within equal sequence numbers; SignalCard prints "date not
   known" on it rather than an empty corner. */
export const NO_DATE_LABEL = "date not known";

const seqOf = (c) => (c && typeof c.seq === "number" && Number.isFinite(c.seq) ? c.seq : Infinity);

export function compareCards(data) {
  const when = (c) => dateVal(signalDate(c, data));
  return (a, b) => (seqOf(a) === seqOf(b) ? 0 : seqOf(a) < seqOf(b) ? -1 : 1) || when(b) - when(a);
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
  const depth = (c) => (c.sec ? c.sec.length : 0);
  let cards = (cfg.cards || []).slice();
  /* EVERY MODE ENDS IN THE SAME COMPARATOR. A sequence option changes which key leads,
     never what "worse" means -- so "most recent" still puts a high-severity card above a
     low-severity one published the same day, and there is exactly one definition of the
     severity order in this file. */
  if (seqMode === "recency") {
    cards.sort((a, b) => when(b) - when(a) || cmp(a, b));
  } else if (seqMode === "depth") {
    cards.sort((a, b) => depth(b) - depth(a) || cmp(a, b));
  } else if (seqMode === "category") {
    cards.sort((a, b) => String(a.meta).localeCompare(String(b.meta)) || cmp(a, b));
  } else {
    cards.sort(cmp);
  }
  /* The number shown on a card is its position in the sorted feed. The stored sequence_no
     only orders the feed (the loader writes a stable, date-based value, not a display
     number). A copy: the dataset card is not renumbered. */
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
  const byContent = groupDefs.some((g) => (g.dirs && g.dirs.length) || (g.tags && g.tags.length));
  if (byContent) {
    const claimed = new Set();
    const claims = (g, c) =>
      (g.dirs || []).indexOf(c.dir) >= 0 ||
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

/* The date a signal is shown with, in ONE format everywhere: the stored date
   (card.ago = event_date / published_on) through utils/formatDate. "" when there is none. */
export function signalDate(card) {
  return card && card.ago ? formatDate(String(card.ago)) : "";
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

/* TECHNOLOGY STREAMS. A Technology card's stream comes from its stored classification
   (technology_overview_article.classification): "competitor_advance" -> kind "rival"
   (tile "Competitor advances", no badge on the row), "adoptable" -> kind "adopt" (tile
   "Adoptable advances", badge "Adoptable"). Case and spaces/hyphens are ignored. Any
   other value gets no kind: it is shown as stored and counted in neither tile. */
const TECH_KIND = { competitor_advance: "rival", competitor_advancement: "rival", adoptable: "adopt" };
export function techKindOf(classification) {
  const k = String(classification == null ? "" : classification).trim().toLowerCase().replace(/[\s-]+/g, "_");
  return TECH_KIND[k] || "";
}

/* Live counts from the served data, so the strip can never drift from the feed.
   Every pillar computes its tiles — the config carries labels and phrasing only;
   a number the service didn't back is never rendered. */
export function metricsFor(cfg, pillar, d) {
  /* EVERY TILE STARTS AT "NOT MEASURED".

     The binding at the bottom of this function is by LABEL STRING, and a label no
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
    /* A tile is a count of the stored rows it names (0 is a real count). */
    const dirCount = (dir) => cards.filter((c) => c.dir === dir).length;
    let byLabel = { "All signals": cards.length };
    let actByLabel = {};
    if (pillar === "competitive") {
      byLabel = {
        ...byLabel,
        "Competitive threats": dirCount("threat"),
        "Watch signals": dirCount("watch"),
        /* the number of competitor rows (competitive_competitor), the client excluded */
        "Companies tracked": Object.keys((d && d.competitors) || {}).filter(
          (k) => k !== (d && d.client && d.client.id),
        ).length,
      };
    } else if (pillar === "technology") {
      // The two streams, counted from each card's kind (techKindOf over its stored
      // classification); domains = the technology_category rows.
      const tagCount = (t) => cards.filter((c) => cardHasTag(c, t)).length;
      byLabel = {
        ...byLabel,
        "Competitor advances": tagCount("rival"),
        "Adoptable advances": tagCount("adopt"),
        "Domains tracked": ((d && d.techCats) || []).length,
      };
      actByLabel = { "Competitor advances": "rival", "Adoptable advances": "adopt" };
    }
    metrics.forEach((m) => {
      if (byLabel[m.l] == null) {
        /* LOUD, NOT SILENT. Nothing above computed a value for this label, so there
           is no measurement to show: the tile keeps its "—" and says why, and the
           served subtitle goes with it -- "rivals ahead / closing" over an unbound
           tile is a claim about a number that was never taken. */
        m.sub = `not wired - no measurement is computed for "${m.l}"`;
        m.warn = true;
        if (typeof console !== "undefined" && console.warn)
          console.warn(`metricsFor(${pillar}): no measurement bound to tile label "${m.l}"`);
        return;
      }
      m.v = String(byLabel[m.l]);
      if (actByLabel[m.l] != null) m.act = actByLabel[m.l];
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
  atstake: "contested bids, by value",
  threat: "threats to active bids",
  fav: "openings to press",
  /* the Watch tile's `act` is "watch"; without this the count line ended in a bare
     " · " -- "13 of 26 signals ·" */
  watch: "watch signals",
  deadline: "by submission deadline",
  rival: "competitor advancements",
  adopt: "advances KSSL can adopt",
  geo: "markets in play",
  positioning: "rating-matched rivals",
  gap: "capability gaps",
  patents: "patent activity",
  emission: "emission compliance",
  all: "sorted by relevance",
};

export function tilePredicate(act) {
  const has = (c, t) => String(c.tags || "").split(" ").includes(t);
  if (act === "all") return () => true;
  if (act === "atstake") return (c) => c.dir === "threat" || c.dir === "atstake" || has(c, "atstake");
  if (act === "threat") return (c) => c.dir === "threat" || has(c, "threat");
  if (act === "watch") return (c) => c.dir === "watch";
  if (act === "fav") return (c) => c.dir === "fav" || has(c, "opening") || has(c, "fav");
  /* Technology streams, selected by each card's kind (techKindOf). */
  if (act === "rival") return (c) => cardHasTag(c, "rival");
  if (act === "adopt") return (c) => cardHasTag(c, "adopt");
  if (act === "deadline") return () => true;
  if (act === "gap") return (c) => c.dir === "threat" || has(c, "gap");
  if (act === "patents") return () => true;
  return () => true;
}

/* ===== Dynamic nav counts (computed from live data, never hardcoded) ===== */
export function navCounts(d) {
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
    counts.partnerships = Object.keys(d.competitors).filter((k) => k !== (d.client && d.client.id)).length;
    // Geo: distinct countries across all companies' footprints
    const geoCountries = new Set();
    Object.values(d.geoData).forEach((byCountry) =>
      Object.keys(byCountry || {}).forEach((c) => geoCountries.add(c)),
    );
    counts.geo = geoCountries.size;
    /* The rail badge counts the cards the overview feed carries. */
    const ovCfg = (d.overviewConfig && d.overviewConfig.competitive) || null;
    counts.overview = ovCfg && Array.isArray(ovCfg.cards)
      ? ovCfg.cards.length
      : d.competitiveCards.length;
    /* Profile lists the rivals — the client's own row is not a competitor profile.
       `d.client.id` is the slug by the time this runs; wireDataset resolves it from
       the row whose dir is "client", precisely so this join is not on a display label. */
    counts.profile = Object.keys(d.competitors).filter(
      (k) => k !== (d.client && d.client.id),
    ).length;
    const served = (rows) => (Array.isArray(rows) ? rows.length : undefined);
    counts["threat-analysis"] = served(d.competitorMoment && d.competitorMoment.items);
    counts.projects = served(d.projects);

    /* Products explorer lists COMPETITOR products (Products.jsx builds them from the
       comp side of matchups + each competitor's own products), so the badge counts
       those — not KSSL's own SKUs, which is what it used to show (a "1" over a catalog
       of dozens). Same two sources the page reads, deduped by name. */
    const clientId = d.client && d.client.id;
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
    /* The Market overview badge counts the rows its page lists: top tenders and the projects
       before tender. */
    const topOpp = d.topOpportunities || {};
    counts["m-overview"] = (topOpp.topTenders || []).length + (topOpp.projectsBeforeTender || []).length;
    counts["m-report"] = (d.tenders || []).length;
    counts.tender = open.length;
    counts["awarded-tenders"] = awarded.length;
    counts["global-requirement"] = (d.globalRequirements || []).length;

    // patents badge: indexed filings, not a hardcoded 1
    counts["patents-comp"] = d.PATENTS && d.PATENTS._meta && d.PATENTS._meta.total;
    const innovTotal = Object.keys(d.innovations).reduce(
      (n, k) => n + (d.innovations[k] || []).length,
      0,
    );
    // the Overview badge counts the FEED it opens (tech signal cards); the Innovation
    // badge counts innovations. Labelling one with the other's number was a mismatch
    // visible on screen: badge 29 above a feed of 11.
    /* The overview's own cards (technology_overview_article rows). */
    counts["t-overview"] =
      ((d.overviewConfig && d.overviewConfig.technology && d.overviewConfig.technology.cards) ||
        d.techCards || []).length;
    counts.innovation = innovTotal;
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
      if (k !== (d.client && d.client.id) && c.partners) allianceCount += c.partners.length;
    });
    Object.values(geoData).forEach((byCountry) =>
      Object.keys(byCountry || {}).forEach((c) => geoCountries.add(c)),
    );
  } catch (e) {
    /* fall through to the static copy below */
  }
  const partnerCount = Object.keys(competitors).filter((k) => k !== (d.client && d.client.id)).length;
  const geoCompCount = Object.keys(geoData).filter((k) => k !== (d.client && d.client.id)).length;
  const alertCount = (d.competitiveCards || []).length;
  return {
    overview: {
      title: "Competitive Intelligence",
      cnt: `${alertCount} signals`,
      filters: true,
    },
    profile: {
      title: "Competitor Profile",
      cnt: `${partnerCount} companies tracked · everything we track on one rival`,
      filters: false,
    },
    "threat-analysis": {
      title: "Competitor Moment",
      cnt: `${((d.competitorMoment && d.competitorMoment.items) || []).length} competitor moments`,
      filters: false,
    },
    products: {
      title: "Products",
      /* British spelling and singular "catalogue", as every other heading (FE 18) */
      cnt: "Competitor & client product catalogue across tracked defence categories",
      filters: false,
    },
    positioning: {
      title: "Product Evaluation",
      cnt: "KSSL products mapped to rival products by spec category",
      filters: true,
    },
    partnerships: {
      title: "Partnership",
      cnt: `${partnerCount} competitors · ${allianceCount} alliances mapped`,
      filters: false,
    },
    projects: {
      title: "Projects",
      cnt: `${(d.projects || []).length} projects on record`,
      filters: false,
    },
    finances: {
      title: "Finances",
      cnt: "No financial records on record",
      filters: false,
    },
    geo: {
      title: "Geo Footprint",
      cnt: `${geoCompCount} competitors · ${geoCountries.size} markets · competitor activity by country`,
      filters: false,
    },
    /* m-report was the only view with no entry here, which is why Layout carried a
       hardcoded "Market Report" -- and that literal was gated on a flag covering all
       four tender views, so the page labelled "Tender Pipeline" on the rail rendered
       under the heading "Market Report". */
    "m-report": {
      title: "Market Intelligence",
      cnt: "Demand shape, spec and requirement",
      filters: false,
    },
    tender: {
      title: "Tenders",
      cnt: "Live opportunities matched to product portfolio",
      filters: false,
    },
    "global-requirement": {
      title: "Global Requirements",
      cnt: "Worldwide defence procurement requirements and capability demand",
      filters: false,
    },
    "awarded-tenders": {
      title: "Awarded Tenders",
      cnt: "Contracts awarded or settled",
      filters: false,
    },
    "closed-tenders": {
      title: "Closed Tenders",
      cnt: "Opportunities closed or expired",
      filters: false,
    },
    innovation: {
      title: "Innovation Pipeline",
      cnt: "Technology developments tracked across KSSL product domains",
      filters: false,
    },
    "patents-comp": {
      title: "Patent",
      cnt: "Filings by rival and by technology field",
      filters: false,
    },
  };
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
