/* One document, one card.
 *
 * Adani Defence's news panel printed the same press release twice, stacked, because the
 * row was ingested under two categories with two headlines -- and ONE url. Across the
 * served store this happens 11 times over 8 companies (Rheinmetall 3, Anduril 2, ...).
 *
 * The url is the identity and the test is about what the fold must not cost: the
 * article keeps both of its categories, an article with no url is never folded into
 * another one, and two genuinely different articles stay two.
 */
import { companyNews } from "./src/lib/news.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(60)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

const U = "https://www.adanidefence.com/media/media-release/Adani-2500-Crore";

const data = {
  competitorNews: {
    adani: [
      { id: 1, date: "2026-07-05", category: "Financial", title: "Adani to Invest 2,500 Crore in the Largest Missile Ecosystem", url: U },
      { id: 2, date: "2026-07-05", category: "Defence", title: "Adani to Build the Largest Missile Ecosystem", url: U, description: "only the second row has this" },
      { id: 3, date: "2026-06-10", category: "Markets", title: "A different story entirely", url: "https://example.test/other" },
    ],
    /* two rows, no url on either: nothing identifies them as one document */
    nourl: [
      { id: 4, date: "2026-07-05", category: "Defence", title: "Untraceable one" },
      { id: 5, date: "2026-07-05", category: "Defence", title: "Untraceable two" },
    ],
    /* the backend's own marker, for the day news_chain.py has run here */
    chained: [
      { id: 6, date: "2026-07-05", title: "The original", url: "https://a.test/1" },
      { id: 7, date: "2026-07-05", title: "A rewrite of it", url: "https://b.test/2", duplicate_of_url: "https://a.test/1" },
      { id: 8, date: "2026-07-04", title: "Points at something not in this feed", url: "https://c.test/3", duplicate_of_url: "https://gone.test/9" },
    ],
  },
};

const adani = companyNews(data, "adani");
ck("the repeated press release collapses to one card", adani.length === 2, adani.map((a) => a.title));
ck("the distinct article is untouched", adani.some((a) => a.title === "A different story entirely"));
ck("the surviving card leads with the first headline",
   adani[0].title === "Adani to Invest 2,500 Crore in the Largest Missile Ecosystem", adani[0].title);
ck("BOTH categories survive -- neither tab loses the article",
   /Financial/.test(adani[0].category) && /Defence/.test(adani[0].category), adani[0].category);
ck("a field only the absorbed row carried is filled in",
   adani[0].excerpt === "only the second row has this", adani[0].excerpt);
ck("the url is preserved so the card still links out", adani[0].sourceUrl === U);

const nourl = companyNews(data, "nourl");
ck("two undated-source rows with no url stay two", nourl.length === 2, nourl.map((a) => a.title));

const chained = companyNews(data, "chained");
ck("a row marked duplicate_of a row PRESENT here is dropped",
   !chained.some((a) => a.title === "A rewrite of it"), chained.map((a) => a.title));
ck("a row pointing outside this feed is kept -- it is the only copy we have",
   chained.some((a) => a.title === "Points at something not in this feed"), chained.map((a) => a.title));
ck("the original stays", chained.some((a) => a.title === "The original"));

ck("no company, no crash", companyNews(data, null).length === 0 && companyNews(null, "adani").length === 0);
ck("an unknown company is empty, not an error", companyNews(data, "nobody").length === 0);

console.log(fail ? `\n${fail} FAILED` : "\nall passed");
process.exit(fail ? 1 : 0);
