/* orgident.js -- partner identity, at serve time.
 *
 * One organisation, one identity: a CANONICALISER that strips a parenthetical and trailing
 * legal suffixes and merges a name into a shorter one that fully contains its distinctive
 * tokens. Both the graph (partners.js) and the overlap matcher (overlap.js) key on it, so
 * identity is decided in exactly one place. It is string normalisation only: no company,
 * country or demonym list lives here, and no partner row is dropped or renamed to a
 * hand-typed alias. Verified in orgident.test.mjs.
 */

export const fold = (s) =>
  String(s == null ? "" : s)
    .normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .replace(/&/g, " and ")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

/* Line-of-business / filler tokens: present in a name but not identifying. Used only to
   decide what is DISTINCTIVE (for the containment merge); never stripped from the key. */
const GENERIC = new Set(
  "defence defense systems system aerospace industries industry technologies technology solutions international group holdings holding corporation company advanced global marine naval motors engineering works enterprises the of and".split(" "),
);

/* Legal-form tokens stripped from the tail of a name. */
const LEGAL = new Set(
  "inc incorporated corp corporation co company ltd limited pvt private plc llc llp gmbh ag sa sas srl spa ab as oy oyj bv nv pty pte kk kg ohg".split(" "),
);

const titleCase = (s) =>
  String(s || "")
    .split(" ")
    .filter(Boolean)
    .map((w) => (w.length <= 3 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)))
    .join(" ");

/* ---------- CANONICALISER ----------
   One organisation -> one identity. Strips a parenthetical and trailing legal suffixes.
   `distinctive` (name tokens minus generics) drives the containment merge in partners.js,
   which collapses "Lockheed Martin Skunk Works" into "Lockheed Martin". */
export function orgCanonical(label) {
  const raw = String(label == null ? "" : label).replace(/\(.*?\)/g, " ").trim();
  const toks = fold(raw).split(" ").filter(Boolean);
  while (toks.length > 1 && LEGAL.has(toks[toks.length - 1])) toks.pop();
  const head = toks.join(" ");
  const display = titleCase(head) || raw;
  const key = head.replace(/\s+/g, "") || fold(raw).replace(/\s+/g, "");
  const distinctive = toks.filter((t) => t && !GENERIC.has(t));
  return { key, name: display, country: null, tokens: toks, distinctive };
}
/* The bare canonical key, for callers that only need to compare identity (overlap.js). */
export const orgKey = (label) => orgCanonical(label).key;

/* Given a set of partner labels, return label(raw) -> canonical key, with a containment
   merge so "Lockheed Martin Skunk Works" folds into "Lockheed Martin". Containment fires
   only when the shorter name's DISTINCTIVE tokens are all present in the longer's — so
   "Israel Aerospace Industries" and "Israel Weapon Industries" (share only generics) stay
   apart, and "General Dynamics"/"General Atomics" (distinctive dynamics vs atomics) stay
   apart. Returns { keyOf(label), canon:{key->{name,countries[]}} }. */
export function canonicalizeLabels(labels) {
  const info = new Map(); // key -> {name, tokens, distinctive, countries:Set}
  const keyOfLabel = new Map();
  (labels || []).forEach((lbl) => {
    const c = orgCanonical(lbl);
    keyOfLabel.set(lbl, c.key);
    const cur = info.get(c.key) || { name: c.name, tokens: c.tokens, distinctive: c.distinctive, countries: new Set() };
    if (c.name.length < cur.name.length) cur.name = c.name; // shortest display wins
    if (c.country) cur.countries.add(c.country);
    info.set(c.key, cur);
  });
  // containment merge: map a longer key onto a shorter one it fully contains (distinctively)
  const keys = [...info.keys()].sort((a, b) => info.get(a).tokens.length - info.get(b).tokens.length);
  const remap = {};
  for (let i = 0; i < keys.length; i++) {
    const a = keys[i];
    const ia = info.get(a);
    if (!ia.distinctive.length) continue; // no distinctive token -> never absorbs anything
    for (let j = i + 1; j < keys.length; j++) {
      const b = keys[j];
      if (remap[b]) continue;
      const ib = info.get(b);
      const bset = new Set(ib.tokens);
      if (ia.tokens.length < ib.tokens.length && ia.distinctive.every((t) => bset.has(t))) {
        remap[b] = a;
        ib.countries.forEach((x) => ia.countries.add(x));
      }
    }
  }
  const resolve = (k) => { let g = 0; while (remap[k] && g++ < 8) k = remap[k]; return k; };
  const keyOf = (lbl) => resolve(keyOfLabel.get(lbl) || orgCanonical(lbl).key);
  const canon = {};
  keys.forEach((k) => {
    const r = resolve(k);
    canon[r] = canon[r] || { name: info.get(r).name, countries: new Set() };
    info.get(k).countries.forEach((x) => canon[r].countries.add(x));
    if (info.get(k).name.length < canon[r].name.length) canon[r].name = info.get(k).name;
  });
  Object.keys(canon).forEach((k) => { canon[k].countries = [...canon[k].countries].sort(); });
  return { keyOf, canon };
}
