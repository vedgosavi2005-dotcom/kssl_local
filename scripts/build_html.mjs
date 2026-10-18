/* Standalone HTML build: the React app and its data in one page, beside two image folders.
 *
 *   node scripts/build_html.mjs [outDir]          needs the backend on 127.0.0.1:8600 (it is the data source)
 *
 * What it does, in order:
 *   1. vite build                          the app, as the dev server runs it
 *   2. GET /api/dataset                    the exact dataset the app shows, overlays included
 *   3. product photos                      public/product-images -> <out>/product-images, paths made relative
 *   4. news images                         each `image` url fetched through the backend's /api/img proxy
 *                                          (browser UA, no referer: the same route the app uses) and saved as
 *                                          <out>/news-images/<hash>.<ext>; a url that cannot be fetched keeps
 *                                          its original address and the app's own fallback tile
 *   5. one HTML file                       JS and CSS inlined, dataset in window.__EMBEDDED_DATASET__
 *
 * Needs the internet only for the page's fonts, icon font, map tiles and any news image that could not be
 * saved. Live panels that need the server (stock price, web mentions: /api/pulse) show their empty state.
 */
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL("..", import.meta.url));     // a plain path: the project folder has a space in its name
const OUT = resolve(process.argv[2] || join(HERE, "..", "parallax-html"));
const API = process.env.KSSL_API || "http://127.0.0.1:8600";
const EXT = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/svg+xml": "svg", "image/avif": "avif" };

console.log("1. vite build");
execSync(`"${process.execPath}" node_modules/vite/bin/vite.js build`, { cwd: HERE, stdio: "ignore" });
const dist = join(HERE, "dist");

console.log("2. dataset");
const data = await (await fetch(`${API}/api/dataset`)).json();
if (!data || !data.matchups) throw new Error("the backend did not return a dataset");

rmSync(OUT, { recursive: true, force: true });
mkdirSync(join(OUT, "product-images"), { recursive: true });
mkdirSync(join(OUT, "news-images"), { recursive: true });

console.log("3. product photos");
cpSync(join(HERE, "public", "product-images"), join(OUT, "product-images"), { recursive: true });

// walk every string; product paths become relative, `image` urls collected for step 4
const images = new Map();
(function walk(o) {
  if (Array.isArray(o)) return o.forEach(walk);
  if (!o || typeof o !== "object") return;
  for (const [k, v] of Object.entries(o)) {
    if (typeof v === "string") {
      if (k === "image" && v.startsWith("/product-images/")) o[k] = v.slice(1);
      else if (k === "image" && /^https?:\/\//i.test(v)) (images.get(v) || images.set(v, []).get(v)).push([o, k]);
    } else walk(v);
  }
})(data);

console.log(`4. news images (${images.size})`);
let saved = 0, failed = 0;
const queue = [...images.keys()];
async function worker() {
  while (queue.length) {
    const url = queue.shift();
    try {
      const r = await fetch(`${API}/api/img?u=${encodeURIComponent(url)}`, { signal: AbortSignal.timeout(25000) });
      const type = (r.headers.get("content-type") || "").split(";")[0].trim();
      const buf = Buffer.from(await r.arrayBuffer());
      if (!r.ok || !EXT[type] || buf.length < 1500) throw new Error(`${r.status} ${type} ${buf.length}B`);
      const name = `${createHash("sha1").update(url).digest("hex").slice(0, 12)}.${EXT[type]}`;
      writeFileSync(join(OUT, "news-images", name), buf);
      images.get(url).forEach(([o, k]) => (o[k] = `news-images/${name}`));
      saved++;
    } catch (e) {
      failed++;
    }
  }
}
await Promise.all(Array.from({ length: 8 }, worker));
console.log(`   saved ${saved}, kept original address for ${failed}`);

console.log("5. html");
const asset = (re) => {
  const f = readdirSync(join(dist, "assets")).find((n) => re.test(n));
  if (!f) throw new Error(`no ${re} in dist/assets`);
  return readFileSync(join(dist, "assets", f), "utf8");
};
const js = asset(/^index-.*\.js$/).replace(/<\/script/gi, "<\\/script");
const css = asset(/^index-.*\.css$/);
let html = readFileSync(join(dist, "index.html"), "utf8")
  .replace(/<script type="module"[^>]*><\/script>/, "")
  .replace(/<link rel="stylesheet"[^>]*assets\/[^>]*>/, "")
  .replace(/<title>[^<]*<\/title>/, `<title>137Parallax — ${(data.client && data.client.name) || "Competitive"} Competitive Intelligence</title>`);
const json = JSON.stringify(data).replace(/</g, "\\u003c");
// function replacers: the minified code is full of "$&" and "$'" that String.replace would expand
html = html
  .replace("</head>", () => `<style>${css}</style>\n</head>`)
  .replace("</body>", () => `<script>window.__EMBEDDED_DATASET__=${json};</script>\n<script type="module">${js}</script>\n</body>`);
writeFileSync(join(OUT, "parallax.html"), html);

const mb = (p) => (statSync(p).size / 1e6).toFixed(1);
console.log(`done: ${join(OUT, "parallax.html")} ${mb(join(OUT, "parallax.html"))} MB, ${readdirSync(join(OUT, "product-images")).length} product photos, ${saved} news images`);
