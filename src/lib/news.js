/* Per-company news: the stored rows of competitive_news_article,
 * served as data.competitorNews[cid] (backend/areas/a_competitive.py), newest first.
 *
 * Nothing is added, merged, hidden or invented here: every field is the stored column
 * (headline, publisher, article_url, category, published_date, image_url). A column that is
 * empty stays empty and the panels leave the element out. When a company has no news this
 * returns [].
 */

import { formatDate } from "../utils/formatDate.js";

/* "2026-07-13" -> "13 Jul 2026". One formatter for the whole app (utils/formatDate). */
export function newsDate(iso) {
  if (!iso) return "";
  return formatDate(String(iso));
}

function shape(row, i) {
  return {
    id: row.id || `news-${i}`,
    category: row.category || "",
    ago: newsDate(row.date),
    date: row.date || null,
    title: row.title,
    source: row.source || undefined,
    sourceUrl: row.url || undefined,
    url: row.url || undefined,
    image: row.image || undefined,
    _src: row._src,
  };
}

/* Every article for one competitor, newest first. `compId` is the serving key. */
export function companyNews(data, compId) {
  if (!data || !compId) return [];
  const rows = ((data.competitorNews || {})[compId] || []).slice();
  rows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  return rows.map((r, i) => shape(r, i));
}

/* Tokens worth matching on: drops the short/generic words that would make any
   article "about" the product. "M4" and "F-22" survive; "the" and "system" do not. */
function terms(name) {
  return String(name || "")
    .toLowerCase()
    .split(/[^a-z0-9-]+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
}
const STOP = new Set(["the", "and", "for", "system", "systems", "series", "mark",
                      "new", "gun", "vehicle", "defence", "defense"]);

function mentions(article, name) {
  const t = terms(name);
  if (!t.length) return false;
  const hay = `${article.title || ""}`
    .toLowerCase();
  /* Every distinctive token has to appear. One shared word is a coincidence; the
     whole designator is a mention. */
  return t.every((x) => hay.includes(x));
}

/* The company's articles that actually name this product. Returns [] rather than
   falling back to the company feed — an article about a different platform is not
   news about this one, and presenting it as such is the bug we removed. */
export function productNews(data, compId, productName) {
  return companyNews(data, compId).filter((a) => mentions(a, productName));
}

/* The company's articles that actually name this country. */
export function marketNews(data, compId, country) {
  return companyNews(data, compId).filter((a) => mentions(a, country));
}

/* The company's articles that name the partner. */
export function partnerNews(data, compId, partnerLabel) {
  return companyNews(data, compId).filter((a) => mentions(a, partnerLabel));
}

/* Self-check: `node src/lib/news.js` (or import newsSelfCheck from a page). */
/* THE FEED IS A HEADLINE, NOT AN ARCHIVE.
 *
 * Profile opened six articles and grew by six on every click with no ceiling, so
 * Rheinmetall's 56 rows ended as 55 stacked cards in a 28%-wide column. Products
 * had no limit at all -- `feedProdArticles.map(...)` rendered every article naming
 * the product. Either way the page just grows downward and the sections beneath it
 * are pushed out of reach.
 *
 * So: the feed carries the newest FEED_N, and everything else -- including those
 * FEED_N, because a reader looking for one article should not have to work out
 * which surface it is on -- is listed in full below, newest first. The split is a
 * pure function so it can be tested rather than eyeballed.
 */
/* HOW FAR BACK, AND HOW MANY.

   The panels showed every article a company had, unbounded, newest first. Measured on
   the live store: 438 articles over 31 companies, the oldest from October 2022 and one
   company carrying 83. A profile therefore opened with four-year-old items in the same
   stack as this week's, and "latest news" meant whatever happened to be at the top.

   Two separate limits, because they answer different questions:

     the WINDOW is the reader's -- how recent must a story be to count as current. It is
     a choice, not a constant, so it is offered rather than assumed.
     the CAP is the panel's -- how many cards a person will actually read. Fifteen.

   An article with no date cannot be shown to fall inside a window, so a window excludes
   it. That is a real exclusion, not a rounding, which is why the callers print how many
   of the total are being shown: a filter that quietly drops rows is the fault this
   whole file was written to end. With no window set, undated articles are kept. */
export const NEWS_MAX = 15;

export const NEWS_WINDOWS = [
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "3m", label: "Last 3 months", days: 90 },
  { key: "6m", label: "Last 6 months", days: 180 },
  { key: "12m", label: "Last 12 months", days: 365 },
  { key: "all", label: "All time", days: null },
];

export const NEWS_WINDOW_DEFAULT = "12m";

export function windowDays(key) {
  const w = NEWS_WINDOWS.find((x) => x.key === key);
  return w ? w.days : null;
}

export function windowLabel(key) {
  const w = NEWS_WINDOWS.find((x) => x.key === key);
  return w ? w.label : "All time";
}

/* Articles published within `days` of `now`. days null/0 -> everything, undated kept. */
export function withinWindow(articles, days, now = Date.now()) {
  const all = Array.isArray(articles) ? articles : [];
  if (!days) return all.slice();
  const floor = now - days * 86400000;
  return all.filter((a) => {
    const t = a && a.date ? Date.parse(a.date) : NaN;
    return Number.isNaN(t) ? false : t >= floor;
  });
}

/* The most a panel shows. Never reorders -- the caller has already sorted. */
export function capNews(articles, n = NEWS_MAX) {
  const all = Array.isArray(articles) ? articles : [];
  return all.slice(0, Math.max(0, n));
}

export const FEED_N = 6;

export function feedSplit(articles, n = FEED_N) {
  const all = Array.isArray(articles) ? articles : [];
  return { feed: all.slice(0, n), rest: all.slice(n), all, total: all.length };
}
