/* SERVER-SIDE "trending" headlines (Google News RSS, keyless): the one agreed exception to the
 * DB-only rule. Runs on the server (vite dev/preview middleware) -- never in the browser,
 * because the page's CSP forbids cross-origin fetches and the host would block them anyway.
 * It fetches, parses and normalises; it invents nothing. The search terms come ONLY from the
 * request (the UI builds them from dataset names): no default company, no added keywords.
 * A source that returns nothing yields [], and the card says so. There is no stock lane.
 *
 * ponytail: plain regex RSS parse -- no xml dependency for one well-known feed. Upgrade to a
 * parser if the shape ever gets hairy.
 */
const UA = "Mozilla/5.0 (compatible; ParallaxPulse/1.0)";

/* Decode the handful of XML/HTML entities an RSS title carries. */
function unent(s) {
  return String(s || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n))
    .trim();
}

/* Resolve a news.google.com/rss/articles/CBMi... link to the REAL article URL via
 * Google's batchexecute endpoint (mirrors backend _pulse_resolve). Cached 24h; returns ""
 * on any failure so the caller falls back to the publisher homepage. Fragile by nature. */
const _resolveCache = new Map();
async function resolveArticle(googleUrl) {
  if (!googleUrl || !googleUrl.includes("news.google.com/rss/articles/")) return "";
  const id = googleUrl.split("/articles/")[1].split("?")[0];
  const c = _resolveCache.get(id);
  if (c && c.exp > Date.now()) return c.url;
  let url = "";
  try {
    const html = await (await fetch(googleUrl, { headers: { "User-Agent": UA } })).text();
    const sg = html.match(/data-n-a-sg="([^"]+)"/);
    const ts = html.match(/data-n-a-ts="([^"]+)"/);
    if (sg && ts) {
      const payload = [[["Fbv4je", `["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"${id}",${ts[1]},"${sg[1]}"]`, null, "generic"]]];
      const body = "f.req=" + encodeURIComponent(JSON.stringify(payload));
      const resp = await (await fetch("https://news.google.com/_/DotsSplashUi/data/batchexecute", { method: "POST", headers: { "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" }, body })).text();
      const seg = resp.includes("garturlres") ? resp.split("garturlres")[1] : resp;
      const m = seg.match(/https?:\/\/[^\\"]+/);
      if (m) url = m[0];
    }
  } catch { url = ""; }
  _resolveCache.set(id, { url, exp: Date.now() + 86400000 });
  return url;
}
/* The article's OWN og:image, from the resolved page -- grounded (the publisher's declared
 * image for THIS story, the same basis the sourced cards use), so never a wrong photo.
 * Cached 24h; null on failure so the card shows the honest placeholder. Only real article
 * pages (never the news.google.com wrapper). Mirrors backend _pulse_ogimage. */
const _imgCache = new Map();
async function articleImage(url) {
  if (!url || !/^https?:/.test(url) || url.includes("news.google.com")) return null;
  const c = _imgCache.get(url);
  if (c && c.exp > Date.now()) return c.img;
  let img = null;
  try {
    const html = await (await fetch(url, { headers: { "User-Agent": UA } })).text();
    const m = html.match(/<meta[^>]+property=["']og:image(?::url)?["'][^>]+content=["']([^"']+)/i)
           || html.match(/<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']/i)
           || html.match(/<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)/i);
    if (m && /^https?:/.test(m[1])) img = unent(m[1]);
  } catch { img = null; }
  _imgCache.set(url, { img, exp: Date.now() + 86400000 });
  return img;
}

/* One Google-News RSS query -> up to 6 normalised, link-resolved items. */
async function _rssItems(query) {
  const q = encodeURIComponent(query);
  const url = `https://news.google.com/rss/search?q=${q}&hl=en-US&gl=US&ceid=US:en`;
  const r = await fetch(url, { headers: { "User-Agent": UA } });
  if (!r.ok) return [];
  const xml = await r.text();
  const items = xml.split("<item>").slice(1);
  const out = [];
  for (const it of items) {
    const title = unent((it.match(/<title>([\s\S]*?)<\/title>/) || [])[1]);
    const link = unent((it.match(/<link>([\s\S]*?)<\/link>/) || [])[1]);
    const srcurl = unent((it.match(/<source[^>]*url="([^"]*)"/) || [])[1]);
    const date = unent((it.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1]);
    const source = unent((it.match(/<source[^>]*>([\s\S]*?)<\/source>/) || [])[1]);
    if (!title) continue;
    // Google appends " - <Source>" to the title; strip it, we show source separately
    const clean = source && title.endsWith(" - " + source) ? title.slice(0, -(source.length + 3)) : title;
    // Resolve to the EXACT article (fall back to publisher homepage); card image is the
    // article's own og:image, only when we resolved the real page (else the placeholder).
    const resolved = await resolveArticle(link);
    const finalUrl = resolved || srcurl || link || null;
    const image = resolved ? await articleImage(resolved) : null;
    out.push({ title: clean, url: finalUrl, source: source || null, image, date: date ? new Date(date).toISOString() : null });
    if (out.length >= 6) break;
  }
  return out;
}

export async function fetchTrending(name, product = "") {
  if (!name) return [];
  const p = String(product || "").trim();
  /* Progressive broadening: an exact quoted product first, then the product unquoted with
     its maker, then maker-only -- so a terse/obscure product code ("HE M 107") that the
     strict query returns nothing for still surfaces relevant coverage instead of an empty
     feed. Each step runs only when the previous found nothing; a zero-result RSS fetch is
     cheap (no link-resolution happens until a step actually returns items). */
  const queries = p
    ? [`"${p}" ${name}`, `${p} ${name}`, `"${name}"`]
    : [`"${name}"`];
  for (const query of queries) {
    const items = await _rssItems(query);
    if (items.length) return items;
  }
  return [];
}
