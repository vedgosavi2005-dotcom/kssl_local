/* The overlap node must WIN THE CASCADE, not merely contain the red somewhere.
 *
 * WHY THIS TEST EXISTS, AND WHY THE LAST ONE WAS NOT ENOUGH.
 * test_partner_overlap_red.mjs asserts the emitted SVG string carries #e8483a on the
 * overlapping node. It passed. Production drew the node blue anyway, because
 * `fill="#e8483a"` on an SVG element is a PRESENTATION ATTRIBUTE, not inline style:
 * it sits below every stylesheet rule in the cascade. `.pg-node.ptr.rel-supply
 * circle{fill:#1d3147}` in partnerships.css therefore beat it on Saab -- the single
 * overlapping partner on the Anduril graph, whose tie is a supply agreement -- while
 * the caption underneath went on saying "red above".
 *
 * A string test cannot see that. This one reads the real stylesheet, resolves the
 * cascade the way a browser would for the exact class set graphSvg puts on an
 * overlapping node, and asserts the winning fill is the red. It fails if anyone
 * removes the !important rule, adds a later rel-* rule that outranks it, or renames
 * the class -- which is the whole family of ways this bug comes back.
 */
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("./src/styles/partnerships.css", import.meta.url), "utf8");

/* THE RED IS A TOKEN NOW, so the winning declaration reads `var(--overlap)` and this
   test has to follow it to a colour -- otherwise it would pass on a variable that
   resolves to anything at all, including nothing.

   --overlap is declared in theme.css, which is a different stylesheet from the one the
   cascade above is resolved in, and that separation is the point: a token that is used
   here and declared nowhere would resolve to an EMPTY value in the browser, and the node
   would draw unpainted. So the declaration is looked up rather than assumed, and its
   absence is a failure. */
const theme = readFileSync(new URL("./src/styles/theme.css", import.meta.url), "utf8");
const TOKENS = {};
theme.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(--[a-z0-9-]+)\s*:\s*([^;}]+)/gi, (_, k, v) => {
  if (!(k in TOKENS)) TOKENS[k] = v.trim();
  return "";
});

/* "var(--overlap)" -> "#ff2d2d". Leaves a literal alone. */
function resolve(value) {
  let v = String(value == null ? "" : value).trim();
  for (let i = 0; i < 4 && /var\(/.test(v); i += 1) {
    v = v.replace(/var\(\s*(--[a-z0-9-]+)\s*(?:,[^)]*)?\)/gi, (m, name) =>
      (name in TOKENS ? TOKENS[name] : m));
  }
  return v;
}

/* The one colour an overlap must be, resolved from the token rather than typed twice.
   If theme.css stops declaring it, this is empty and every assertion below fails --
   which is the correct outcome, not a false pass. */
const RED = resolve("var(--overlap)");

let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(70)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + detail : ""}`);
  if (!ok) fails++;
};

/* A deliberately small cascade resolver: enough for the descendant selectors this
   stylesheet uses (".a.b.c circle.d"), and nothing more. */
function parseRules(text) {
  const rules = [];
  const stripped = text.replace(/\/\*[\s\S]*?\*\//g, "");
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  let order = 0;
  while ((m = re.exec(stripped))) {
    const decls = m[2];
    m[1].split(",").forEach((sel) => {
      const s = sel.trim();
      if (s) rules.push({ sel: s, decls, order: order++ });
    });
  }
  return rules;
}

// element under test: <circle class="net-circle"> inside
// <g class="pg-node ptr overlap rel-supply">
const EL = { tag: "circle", classes: ["net-circle"] };
const ANCESTOR = ["pg-node", "ptr", "overlap", "rel-supply"];

function partMatches(part, el, classes) {
  const tag = (part.match(/^[a-z]+/) || [""])[0];
  if (tag && tag !== el.tag) return false;
  const want = (part.match(/\.[-\w]+/g) || []).map((c) => c.slice(1));
  return want.every((c) => classes.indexOf(c) >= 0);
}

function matches(sel) {
  const parts = sel.split(/\s+/).filter(Boolean);
  if (parts.some((p) => /[>+~:]/.test(p))) return false; // out of scope, treat as no match
  const last = parts[parts.length - 1];
  if (!partMatches(last, EL, EL.classes)) return false;
  // every remaining part must match the single ancestor <g>
  return parts.slice(0, -1).every((p) => partMatches(p, { tag: "g" }, ANCESTOR));
}

function specificity(sel) {
  return (sel.match(/\.[-\w]+/g) || []).length * 10 + (sel.match(/(^|\s)[a-z]+/g) || []).length;
}

function winner(prop) {
  let best = null;
  parseRules(css).forEach((r) => {
    if (!matches(r.sel)) return;
    const d = new RegExp(`(?:^|;)\\s*${prop}\\s*:([^;]+)`, "i").exec(r.decls);
    if (!d) return;
    const raw = d[1].trim();
    const important = /!important/i.test(raw);
    const value = raw.replace(/!important/i, "").trim();
    const rank = [important ? 1 : 0, specificity(r.sel), r.order];
    if (!best || rank[0] > best.rank[0]
      || (rank[0] === best.rank[0] && rank[1] > best.rank[1])
      || (rank[0] === best.rank[0] && rank[1] === best.rank[1] && rank[2] > best.rank[2])) {
      best = { value, rank, sel: r.sel };
    }
  });
  return best;
}

// --- the resolver itself has to be trustworthy, so prove it reproduces the BUG ---
const relSupply = parseRules(css).filter((r) => /rel-supply circle$/.test(r.sel));
ck("the rel-supply rule that caused the bug is still in the file",
   relSupply.length === 1, `found ${relSupply.length}`);
ck("...and the resolver agrees it would match an overlap node's circle",
   matches(".pg-node.ptr.rel-supply circle"));

// --- the actual claim ---
const fill = winner("fill");
ck("theme.css actually declares --overlap, so the token is not empty",
   /^#[0-9a-f]{3,8}$/i.test(RED), `--overlap resolved to "${RED}"`);
ck("an overlapping node's fill resolves to the overlap red",
   !!fill && resolve(fill.value).toLowerCase() === RED.toLowerCase(),
   fill ? `${fill.value} -> ${resolve(fill.value)} from "${fill.sel}"` : "no rule set fill");
ck("...and it wins by !important, not by source order alone",
   !!fill && fill.rank[0] === 1, fill ? `important=${fill.rank[0]}` : "");

const halo = (() => {
  const saved = EL.classes;
  EL.classes = ["halo"];
  const w = winner("stroke");
  EL.classes = saved;
  return w;
})();
ck("the halo ring around an overlapping node is red too",
   !!halo && resolve(halo.value).toLowerCase() === RED.toLowerCase(),
   halo ? `${halo.value} -> ${resolve(halo.value)}` : "no rule set stroke");
ck("...the SAME red as the circle, not a second one that merely looks similar",
   !!halo && !!fill && resolve(halo.value).toLowerCase() === resolve(fill.value).toLowerCase(),
   halo && fill ? `${resolve(halo.value)} vs ${resolve(fill.value)}` : "");

// --- and an ORDINARY node must NOT be red, or the mark means nothing ---
const plain = (() => {
  const i = ANCESTOR.indexOf("overlap");
  ANCESTOR.splice(i, 1);
  const w = winner("fill");
  ANCESTOR.splice(i, 0, "overlap");
  return w;
})();
ck("a non-overlapping supply partner still draws in its tie colour, not red",
   !!plain && resolve(plain.value).toLowerCase() !== RED.toLowerCase(),
   plain ? `${plain.value} -> ${resolve(plain.value)}` : "no rule set fill");

console.log(fails ? `\n${fails} FAILED` : "\nok - the overlap red wins the cascade on the node itself");
process.exit(fails ? 1 : 0);
