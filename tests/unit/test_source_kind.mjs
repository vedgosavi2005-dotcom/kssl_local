/* A CARD MUST NOT CLAIM A LINK IT HAS NOT GOT.
 *
 * Reported as an image fault: "there are news but their source is not proper hence img
 * is not shown". Two screenshots came with it, and both were of the page a card opened
 * -- the Defense News AIR WARFARE section and the Defense News video hub. Neither holds
 * the story the card was headlined with.
 *
 * So the missing image was the symptom and the wrong url was the fault. A section index
 * has no article-level og:image, which is why exactly these rows arrive imageless.
 *
 * THE FALSE POSITIVE IS THE EXPENSIVE ERROR HERE. Labelling a working article link
 * "publisher index, not the article page" libels a link that opens the story perfectly,
 * on a dashboard whose whole claim is that every card traces to a real source. So the
 * sanity list below is longer than the positive list, and it holds the four url shapes
 * that a naive rule gets wrong -- each one taken from the served feed, not invented:
 *
 *   - an article carrying feed-pagination tracking parameters
 *   - an article with the publisher's category appended after the headline slug
 *   - an article addressed by numeric id rather than by slug
 *   - a manufacturer's own product page, which is not news but is not a listing either
 */
import { sourceKind, isPublisherIndex, ARTICLE, INDEX, UNKNOWN } from "../../src/lib/articleUrl.js";
import { readFileSync } from "node:fs";

let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(66)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails += 1;
};
const isIndex = (u, why) => ck(why, sourceKind(u) === INDEX, `${sourceKind(u)}: ${u}`);
const isArticle = (u, why) => ck(why, sourceKind(u) === ARTICLE, `${sourceKind(u)}: ${u}`);

console.log("a publisher index is not an article");
isIndex("https://www.defensenews.com/air/?contentFeatureId=f0finyqZXdsP54A&contentQuery=%7B%22includeSections%22%3A%22%2Fair%22%2C%22feedSize%22%3A10%2C%22feedOffset%22%3A379%7D",
        "a section with feed pagination (the reported one)");
isIndex("https://www.defensenews.com/unmanned", "a bare section");
isIndex("https://www.defensenews.com/video/dntv", "a video hub");
isIndex("http://www.defensenews.com/defense-news-tv", "a programme page, http and all");
isIndex("https://www.analisidifesa.it/argomento/general-dynamics", "an Italian tag page");
isIndex("https://www.armyrecognition.com/news/army-news/2026", "a year archive");
isIndex("https://www.baesystems.com/en-pl", "a country landing page");
isIndex("https://www.defensenews.com/", "the publisher's front page");

console.log("\nan article is left alone -- the false positive is the expensive error");
isArticle("https://www.defensenews.com/industry/techwatch/2026/07/24/anduril-in-talks-to-raise-funding-at-about-100-billion-valuation",
          "a dated headline slug");
isArticle("https://www.airforcetimes.com/industry/techwatch/2026/07/28/first-anduril-yfq-44a-rolls-off-production-line-for-us-cca-program/?contentFeatureId=f0f&contentQuery=%7B%22feedOffset%22%3A26%7D",
          "an article carrying the same feed parameters");
isArticle("https://www.defensedaily.com/marines-plan-sole-source-deal-to-anduril-for-acv-c-suas-tech-eye-initial-fielding-in-early-fy-27/navy-usmc",
          "an article with the category appended AFTER the slug");
isArticle("https://vpk.name/news/1146795_pentagon_zaklyuchil_pervyi_kontrakt.html",
          "an article addressed by numeric id");
isArticle("https://www.sandboxx.us/news/anduril-reveals-thunder-its-newest-large-attack-drone?product-page=1",
          "an article with a paging parameter");
isArticle("https://www.baesystems.com/en/product/thaad-seeker",
          "a manufacturer product page is not a listing");

console.log("\nedges");
ck("an unparseable url is UNKNOWN, not INDEX", sourceKind("not a url") === UNKNOWN);
ck("null and undefined do not throw", sourceKind(null) === UNKNOWN && sourceKind(undefined) === UNKNOWN);
ck("isPublisherIndex agrees with sourceKind",
   isPublisherIndex("https://www.defensenews.com/unmanned") === true
   && isPublisherIndex("https://vpk.name/news/1146795_x.html") === false);
/* UNKNOWN must never be treated as an index: a malformed url is a different bug and
   this rule must not absorb it by quietly captioning every one of them. */
ck("UNKNOWN is not an index", !isPublisherIndex("not a url"));

/* The flag has to reach the card, or every rule above is about a function nobody calls. */
const profile = readFileSync(new URL("../../src/pages/competitive/Profile.jsx", import.meta.url), "utf8");
const news = readFileSync(new URL("../../src/lib/news.js", import.meta.url), "utf8");
ck("every shaped article carries its sourceKind", /sourceKind:\s*sourceKind\(row\.url\)/.test(news));
/* THE ROW LEAVES THE FEED ENTIRELY. Labelling the link was the first fix and it was
   not enough: the DATE on these rows is the listing page's date, measured wrong by a
   median of 192 days and a maximum of 1,552. A label on the link does not touch that,
   so a card grid answering "what is new" must not carry them at all. */
ck("index rows are split out of the feed at the source",
   /const unattributed = useMemo\(/.test(profile) && /const attributed = useMemo\(/.test(profile));
ck("the window filter runs on the attributed rows only",
   /withinWindow\(attributed,/.test(profile));
ck("the lead falls back to attributed, never the whole list",
   /filteredArticles\[0\] \|\| attributed\[0\]/.test(profile));
/* The summary caption ("showing N of M ... K more could not be attributed ...") was
   removed at the operator's request -- it read as the page explaining its own
   arithmetic. The honesty it carried is unchanged: the withheld rows still leave the
   card grid (the split above) and are still kept and marked in the full record below
   (the INDEX_NOTE check next). So the caption must be GONE, not present. */
ck("the withheld-count caption is removed", !/could not be attributed to an article/.test(profile));
ck("the full record keeps them and marks them", /INDEX_NOTE/.test(profile));
/* The date cell is the point of the whole change: do not print a date we have not got. */
ck("an unattributed row shows no date, it shows the not-measured dash",
   /item\.sourceKind !== INDEX && item\.date/.test(profile) && /\{fmtNewsDate\(item\)\}/.test(profile));

/* THE COUNT, ON REAL DATA. A detector that fires on nothing passes every check above. */
const path = process.env.KSSL_DATASET;
if (!path) {
  console.log("  (counts need KSSL_DATASET=<dataset.json>; skipped)");
} else {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  const rows = [];
  for (const arr of Object.values(raw.competitorNews || {})) for (const a of (arr || [])) rows.push(a);
  const idx = rows.filter((r) => isPublisherIndex(r.url));
  const idxNoImg = idx.filter((r) => !r.image).length;
  const artNoImg = rows.filter((r) => !isPublisherIndex(r.url) && !r.image).length;
  console.log(`\n  ${rows.length} news rows: ${idx.length} point at an index (${idxNoImg} imageless),`
              + ` ${artNoImg} are real articles with no image`);
  ck("the detector fires on the served feed", idx.length > 0);
  /* If this ever approaches the whole feed the rule has gone wrong, not the data. */
  ck("and on a small minority of it, not most", idx.length < rows.length * 0.2, `${idx.length}/${rows.length}`);
  /* The fault it was written for: an index row is overwhelmingly an imageless row. */
  ck("an index row is usually the imageless one", idxNoImg > idx.length * 0.5, `${idxNoImg}/${idx.length}`);
}

console.log(fails ? `  ${fails} FAILED` : "  all ok");
process.exit(fails ? 1 : 0);
