/* Fetch pages in a real browser for sites that refuse a plain request (403/429 to urllib); feeds
 * scripts/backfill_published_dates.py --pages.
 *     node scripts/browser_pages.mjs urls.txt pages.json
 */
import { chromium } from "playwright";
import fs from "node:fs";
const urls = fs.readFileSync(process.argv[2], "utf8").split("\n").filter(Boolean);
const b = await chromium.launch(); const ctx = await b.newContext({ userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" });
const out = {};
for (const u of urls) { const p = await ctx.newPage(); try { const r = await p.goto(u, { waitUntil: "domcontentloaded", timeout: 45000 }); await p.waitForTimeout(2500); out[u] = { status: r && r.status(), html: await p.content() }; } catch (e) { out[u] = { status: String(e).slice(0, 80), html: "" }; } await p.close(); }
await b.close(); fs.writeFileSync(process.argv[3], JSON.stringify(out));
