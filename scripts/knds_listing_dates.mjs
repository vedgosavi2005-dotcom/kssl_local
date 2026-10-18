/* knds.com article pages carry no publication date; only their LISTING cards do ("14 October 2026" above the title).
   This opens each listing, presses "Load more articles" until every card is on the page, and prints
   { "<article url>": "YYYY-MM-DD" } as JSON, read from each card's own date line.

     node scripts/knds_listing_dates.mjs > knds_dates.json
*/
import { chromium } from "playwright";

const LISTINGS = ["https://knds.com/en/press-releases", "https://knds.com/en/news"];
const MON = { january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12 };
const iso = (t) => {
  const m = /(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/.exec(t || "");
  const mo = m && MON[m[2].toLowerCase()];
  return mo ? `${m[3]}-${String(mo).padStart(2, "0")}-${m[1].padStart(2, "0")}` : null;
};

const out = {};
const browser = await chromium.launch();
const page = await browser.newPage();
for (const url of LISTINGS) {
  await page.goto(url, { waitUntil: "networkidle", timeout: 120000 });
  for (let i = 0; i < 60; i++) {
    const more = page.getByRole("button", { name: /load more/i });
    if (!(await more.count()) || !(await more.first().isVisible())) break;
    const before = await page.locator("article").count();
    await more.first().click();
    await page.waitForFunction((n) => document.querySelectorAll("article").length > n, before, { timeout: 20000 }).catch(() => {});
    if ((await page.locator("article").count()) === before) break;
  }
  const cards = await page.locator("article").evaluateAll((els) =>
    els.map((a) => ({ date: (a.querySelector("p") || {}).textContent || "", href: (a.querySelector("a[href]") || {}).href || "" })));
  for (const c of cards) {
    const d = iso(c.date);
    if (d && c.href) out[c.href.replace(/\/$/, "")] = d;
  }
  console.error(`${url}: ${cards.length} cards`);
}
await browser.close();
console.log(JSON.stringify(out, null, 1));
