/* Fail when genset / kVA / data-centre / AED / SAR / Saudi / Gulf wording or logic is in src/.
 *
 *   node scripts/checks/check_no_genset.mjs
 *
 * The client's market is data, never code. The only files allowed to name countries are
 * the two neutral lookup tables (country flags and country geometry), which list every
 * country by name and carry no market logic.
 *
 * It also fails when the name of the reference UI's original client appears anywhere in src/, index.html or
 * public/ (no allowlist): the port is client-neutral and a name that can reach the screen is a defect.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const ROOT = join(process.cwd(), "src");
const ALLOW = new Set(["src/lib/countryFlags.js", "src/lib/geoCountries.js"]);
const RX = /genset|\bkva\b|\bkw\b band|data.?cent|\bAED\b|\bSAR\b|saudi|gulf/i;

function* walk(dir) {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (/\.(js|jsx|mjs|css|html|json)$/.test(n)) yield p;
  }
}

function* walkAll(dir) {   // every text file, whatever its extension (binary assets are skipped)
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) yield* walkAll(p);
    else if (!/\.(png|jpe?g|gif|webp|ico|woff2?|ttf|otf|pdf|mp4|webm)$/i.test(n)) yield p;
  }
}

let bad = 0;
for (const f of walk(ROOT)) {
  const rel = relative(process.cwd(), f).split(sep).join("/");
  if (ALLOW.has(rel)) continue;
  readFileSync(f, "utf8").split(/\r?\n/).forEach((line, i) => {
    if (RX.test(line)) {
      bad++;
      console.error(`${rel}:${i + 1}: ${line.trim().slice(0, 140)}`);
    }
  });
}
const NAME = /cummins/i;
for (const root of [ROOT, join(process.cwd(), "index.html"), join(process.cwd(), "public")]) {
  if (!existsSync(root)) continue;
  for (const f of statSync(root).isDirectory() ? walkAll(root) : [root]) {
    readFileSync(f, "utf8").split(/\r?\n/).forEach((line, i) => {
      if (NAME.test(line)) {
        bad++;
        console.error(`${relative(process.cwd(), f).split(sep).join("/")}:${i + 1}: ${line.trim().slice(0, 140)}`);
      }
    });
  }
}
if (bad) {
  console.error(`\ncheck_no_genset: ${bad} line(s) match`);
  process.exit(1);
}
console.log("check_no_genset: OK");
