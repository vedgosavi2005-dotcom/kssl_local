/* IS THE SOURCE LINK THE ARTICLE, OR THE PAGE THE ARTICLE WAS FOUND ON?
 *
 * Reported as an image fault -- "there are news but their source is not proper hence
 * img is not shown" -- with two screenshots of what a card actually opened: the Defense
 * News AIR WARFARE section, and the Defense News video hub. Neither contains the story
 * whose headline was on the card.
 *
 * THE MISSING IMAGE IS A SYMPTOM, NOT THE FAULT. A section index has no article-level
 * og:image, so a row whose url is a section index arrives with image null -- and the
 * card then prints "no image published with this article", which is a claim about the
 * ARTICLE that nobody checked. The article may well have a picture. We are looking at
 * the wrong page.
 *
 * WHAT WENT WRONG UPSTREAM. The crawler stored a listing page as a document; the
 * extractor read a headline off that listing and recorded the LISTING's url as the
 * story's source. Measured on the served feed (2026-09-10): 1,092 news rows, of which
 *
 *     77   point at a publisher index rather than an article  (63 of them imageless)
 *     69   point at a real article that carries no image      (nothing to fix in the UI)
 *
 * The 21 Defense News rows are the reported ones, and their urls carry `feedOffset`
 * pagination -- `/air/?...feedOffset=379`. That offset is a MOVING WINDOW: fetched
 * today, that page holds stories published this week, not the August story we stored.
 * So the article cannot be recovered from the url we hold; it has to come from the
 * crawled document, which is a backfill against the corpus and not a frontend change.
 *
 * WHAT THIS FILE DOES, THEN, IS REFUSE TO PRETEND. A card whose source is an index
 * still shows -- the headline and date are real, and the extraction that produced them
 * is not in doubt -- but it says where its link actually goes, it never takes the lead
 * slot, and its empty image says why it is empty instead of blaming the publisher.
 *
 * THE RULE IS DELIBERATELY NARROW. A false positive libels a working link, which is
 * worse than the fault being fixed, so anything ambiguous stays "article". Checked
 * against the served feed: an article with tracking parameters
 * (`.../first-anduril-yfq-44a-rolls-off-production-line/?contentFeatureId=...`), an
 * article with a category suffix (`/marines-plan-sole-source-deal-to-anduril/navy-usmc`),
 * a numeric-id url (`vpk.name/news/1146795_pentagon_...`) and a manufacturer's own
 * product page (`baesystems.com/en/product/thaad-seeker`) are all left alone.
 */

/* Pagination and feed-assembly parameters. Their presence says the url addresses a
   POSITION IN A FEED rather than a document -- and a position moves. */
const FEED_PARAM = /(?:^|&)(?:feedoffset|searchpageno|contentquery|contentfeatureid|paged?)=/i;

/* Path segments that name a collection. Kept multilingual because the feed is:
   `argomento` is what carries the Italian rows. */
const INDEX_SEG = /^(?:tag|tags|argomento|argomenti|category|categoria|categorie|topic|topics|author|autore|section|sections|feed|rss|archive|archivio)$/i;

/* A headline slug: four or more hyphen-joined words, or a long numeric id. Checked
   against EVERY segment, not just the last, because a publisher may append its own
   category to the story's path. */
function hasSlug(segs) {
  return segs.some((s) => s.split("-").length >= 4 || /^\d{5,}/.test(s));
}

export const ARTICLE = "article";
export const INDEX = "index";
export const UNKNOWN = "unknown";

/* "article"  the url addresses one story
   "index"    the url addresses a page that LISTS stories -- section, tag, archive, feed
   "unknown"  not a url we can parse; treated as an article everywhere, because a
              malformed url is a different bug and this one must not absorb it */
export function sourceKind(url) {
  let p;
  try {
    p = new URL(String(url == null ? "" : url));
  } catch {
    return UNKNOWN;
  }
  const segs = p.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
  if (!segs.length) return INDEX;                       // the publisher's front page
  const slug = hasSlug(segs);
  if (slug) return ARTICLE;                             // a headline beats every rule below
  if (segs.some((s) => INDEX_SEG.test(s))) return INDEX;
  const last = segs[segs.length - 1];
  if (/^\d{4}(?:-\d{2})?$/.test(last)) return INDEX;    // a year or month archive
  if (FEED_PARAM.test(p.search.replace(/^\?/, ""))) return INDEX;
  if (segs.length <= 2) return INDEX;                   // /air, /video/dntv, /unmanned
  return ARTICLE;
}

export function isPublisherIndex(url) {
  return sourceKind(url) === INDEX;
}

/* What the card says instead of pretending. Short, because it sits on the source line
   beside the publisher's name. */
export const INDEX_NOTE = "publisher index, not the article page";

/* And what its empty image band says. The default caption asserts the ARTICLE has no
   image, which is exactly the thing not known here. */
export const INDEX_THUMB = "No image: this link is a publisher index, not the article";
