/* The partner type graph is fitted into its fixed 960x540 viewBox: every circle (with its
 * radius) of every stage stays inside the frame, for every competitor in the dataset and
 * every type group that competitor carries.
 *
 *     node test_bounds.mjs
 *
 * Reads fixtures/kssl_dataset.json (the KSSL test dataset), never a hardcoded company.
 */
import fs from "fs";
import { createPartners } from "./src/lib/partners.js";

const data = JSON.parse(fs.readFileSync("fixtures/kssl_dataset.json", "utf-8"));
const p = createPartners(data);
const W = 960, H = 540;

let fails = 0, graphs = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(66)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails += 1;
};

const circles = (svg) =>
  [...svg.matchAll(/<circle[^>]*\bcx="(-?[\d.]+)"[^>]*\bcy="(-?[\d.]+)"[^>]*\br="(-?[\d.]+)"/g)].map((m) => ({
    cx: +m[1], cy: +m[2], r: +m[3],
  }));
const outside = (svg) =>
  circles(svg).filter((c) => c.cx - c.r < 0 || c.cy - c.r < 0 || c.cx + c.r > W || c.cy + c.r > H);

for (const [id, co] of Object.entries(data.competitors || {})) {
  for (const mode of ["type", "region"]) {
    for (const stage of ["root", "spread"]) {
      const svg = p.typeGraphSvg(co, { stage, mode });
      ck(`${id} ${mode}: ${stage} stage renders a string`, typeof svg === "string");
      ck(`${id} ${mode}: ${stage} stage inside the frame`, outside(svg).length === 0, JSON.stringify(outside(svg)[0]));
    }
    const spread = p.typeGraphSvg(co, { stage: "spread", mode });
    const keys = [...spread.matchAll(/data-type="([^"]*)"/g)].map((m) => m[1]);
    for (const key of new Set(keys)) {
      const svg = p.typeGraphSvg(co, { stage: "focus", type: key, mode });
      graphs += 1;
      ck(`${id} ${mode} focus "${key}": inside the frame`, outside(svg).length === 0, JSON.stringify(outside(svg)[0]));
    }
  }
}
ck("at least one competitor was drawn", Object.keys(data.competitors || {}).length > 0);
ck("at least one focus graph was drawn", graphs > 0);

console.log(fails ? `\nFAIL - ${fails} bound check(s) broken` : `\nOK - ${graphs} focus graphs inside the ${W}x${H} frame`);
process.exit(fails ? 1 : 0);
