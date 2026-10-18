/* THE GLOBAL SEARCH POPOVER MUST NOT BE CLIPPED BY THE BAR IT HANGS FROM.
 *
 * Reported twice as "global search bar doesnt work", and both times the search itself
 * was fine -- searchDataset returns 82 hits for "anduril" against the served dump. What
 * failed was that the result list is `position:absolute; top:calc(100% + 8px)`, i.e.
 * entirely BELOW the 54px .topbar, and .topbar carried `overflow:hidden`. The list
 * rendered, carried z-index 1000, and was invisible.
 *
 * WHY A TEST AND NOT JUST A COMMENT. It had already been "fixed" once. chrome.css
 * declares `.topbar` TWICE:
 *
 *     .topbar{display:flex;...;overflow:hidden}     <- overflow lives here
 *     .topbar{position:relative}                    <- and was removed from here
 *
 * The second rule declares only `position`, so deleting `overflow` from it changed
 * nothing whatsoever, while leaving behind a comment saying the bar had stopped
 * clipping its children. Reading the diff, the bug was fixed. Reading the built
 * stylesheet, it was not. This is the third cascade collision of exactly this shape in
 * this codebase, so the check resolves the cascade the way a browser would -- last
 * declaration wins among equal-specificity rules -- rather than grepping for a string.
 *
 * The rule this pins is not "never write overflow:hidden". It is: whatever .topbar
 * ends up computing, an absolutely-positioned child that hangs below it must still be
 * visible. A future clipping fix has to keep that true some other way.
 */
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../../src/styles/chrome.css", import.meta.url), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "");        // the prose above names every property below

let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(68)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails += 1;
};

/* Every top-level rule, in source order. */
function rules(text) {
  const out = [];
  let depth = 0, start = 0, sel = "";
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (c === "{") {
      if (depth === 0) { sel = text.slice(start, i).trim(); start = i + 1; }
      depth += 1;
    } else if (c === "}") {
      depth -= 1;
      if (depth === 0) {
        if (!sel.startsWith("@")) out.push({ sel, body: text.slice(start, i) });
        start = i + 1;
      }
    }
  }
  return out;
}
const RULES = rules(css);

/* The winning declaration for one property on one selector: equal specificity, so the
   LAST one wins. Returns null when no rule declares it -- which is the answer that
   matters here, because `overflow` then computes to `visible`. */
function win(selector, prop) {
  let value = null;
  for (const r of RULES) {
    if (!r.sel.split(",").map((s) => s.trim()).includes(selector)) continue;
    const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, "i").exec(r.body);
    if (m) value = m[1].trim();
  }
  return value;
}

const topbarRules = RULES.filter((r) => r.sel.split(",").map((s) => s.trim()).includes(".topbar"));
console.log("global search popover");
ck(`.topbar is declared ${topbarRules.length}x, and the cascade is resolved, not grepped`,
   topbarRules.length >= 1);

/* THE CHECK. `visible` is the initial value, so "no rule declares it" passes too. */
const overflow = (win(".topbar", "overflow") || "visible").trim();
ck("the top bar does not clip its own children",
   !/hidden|clip|auto|scroll/.test(overflow), `overflow: ${overflow}`);
ck("nor on one axis only, which computes the other axis to auto",
   !/hidden|clip|auto|scroll/.test((win(".topbar", "overflow-y") || "visible").trim())
   && !/hidden|clip|auto|scroll/.test((win(".topbar", "overflow-x") || "visible").trim()));

/* The popover has to actually hang below the bar for any of this to matter -- if it
   ever becomes a fixed/portalled element the clipping question changes shape, and this
   test should be revisited rather than silently passing on a different design. */
const pos = (win(".topbar-search-popover", "position") || "").trim();
const top = (win(".topbar-search-popover", "top") || "").trim();
ck("the popover is still absolutely positioned below the bar",
   pos === "absolute" && /100%/.test(top), `${pos} / ${top}`);
ck("and still carries a stacking order above the page", !!win(".topbar-search-popover", "z-index"));

/* The wrap is the popover's containing block. Lose `position:relative` and the popover
   escapes to the nearest positioned ancestor, which is a different bug with the same
   symptom. */
ck("the search wrap is the popover's containing block",
   (win(".topbar-search-wrap", "position") || "").trim() === "relative");

/* THE THING THAT MADE REMOVING IT SAFE, checked rather than asserted in a comment.
   The sweep still must not give the page horizontal scroll -- it just gets clipped
   further out. That clip is declared in theme.css, a different stylesheet, so it is
   looked up there: a claim about another file is worth exactly as much as a lookup. */
const theme = readFileSync(new URL("../../src/styles/theme.css", import.meta.url), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "");
const clipsViewport = (sel) =>
  rules(theme).filter((r) => r.sel.split(",").map((x) => x.trim()).includes(sel))
    .some((r) => /overflow\s*:\s*hidden/i.test(r.body));
ck("#root still clips the scan sweep at the viewport", clipsViewport("#root"));
ck("and body does too, so nothing gains horizontal scroll", clipsViewport("body"));

console.log(fails ? `  ${fails} FAILED` : "  all ok");
process.exit(fails ? 1 : 0);
