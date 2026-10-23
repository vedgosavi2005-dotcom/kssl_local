/* THE RISK ASSESSMENT IN PLAIN WORDS (owner 22 Oct: "the six parameters are very hard to understand; add plain-English reasoning
   for each score, and an analytical reading of why it is a threat or a watch"). Both sites since 24 Oct (labelBasis goes live).

   Nothing here is new judgement: every sentence is the reason the signal prompt itself wrote for that score (staged as a
   'judgement' row in fact_source, shipped as labelBasis.reasons), stripped of its leading code ("5: ", "lt_1y: ", "adverse: ").
   This file only picks the right reason for each check and puts them in reading order. */

// which stored reason explains which check (prompts/derive.signal_label_tests keys)
const TEST_REASON = {
  direction: () => "direction",
  probability: () => "probability",
  impact: (b) => (b.mainDimension ? `impact_${b.mainDimension}` : null),
  time_to_effect: () => "time_to_effect",
  in_client_market: () => "in_client_market",
  subtype_match: () => "subtype_match",
};

/* "5: the army has ordered ..." -> "The army has ordered ..." */
export function plainReason(text) {
  const s = String(text || "").trim()
    .replace(/^(?:\d(?:\.\d)?|lt_\w+|gt_\w+|\d+_\d+y|adverse|positive|neutral|same|adjacent|none|unknown|yes|no)\s*:\s*/i, "")
    .replace(/\s*\(anchor:[^)]*\)/gi, "");          // the prompt's scoring-anchor tag is for the model, not for a reader
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

export function reasonFor(test, basis) {
  const col = TEST_REASON[test && test.key] ? TEST_REASON[test.key](basis || {}) : null;
  return col ? plainReason(((basis || {}).reasons || {})[col]) : "";
}

export function dimensionReason(key, basis) {
  return plainReason(((basis || {}).reasons || {})[`impact_${key}`]);
}

const end = (s) => (/[.!?]$/.test(s) ? s : `${s}.`);

/* the analytical reading: why this signal is a threat or a watch, as a short chain of plain sentences.
   [] when the basis has no tests (a signal scored before rule s3). */
export function analyticalReading(basis, title) {
  const b = basis || {};
  const tests = b.tests || [];
  if (!tests.length) return [];
  const get = (k) => tests.find((t) => t.key === k);
  const why = (k) => reasonFor(get(k), b);
  const out = [];
  if (title) out.push(`What happened: ${end(String(title))}`);
  const dir = why("direction");
  if (dir) out.push(`Why it concerns KSSL: ${end(dir)}`);
  const sub = why("subtype_match");
  if (sub) out.push(`Which KSSL product it touches: ${end(sub)}`);
  const mkt = why("in_client_market");
  if (mkt) out.push(`Where: ${end(mkt)}`);
  const p = get("probability"), pr = why("probability");
  if (p) out.push(`How sure it is: ${p.answer || ""}${pr ? ` — ${end(pr.charAt(0).toLowerCase() + pr.slice(1))}` : "."}`);
  const i = get("impact"), ir = why("impact");
  if (i) out.push(`How hard it hits: ${i.answer || ""}${ir ? ` — ${end(ir.charAt(0).toLowerCase() + ir.slice(1))}` : "."}`);
  const tt = get("time_to_effect"), tr = why("time_to_effect");
  if (tt) out.push(`When KSSL feels it: ${tt.answer || ""}${tr ? ` — ${end(tr.charAt(0).toLowerCase() + tr.slice(1))}` : "."}`);
  const failed = tests.filter((t) => !t.pass);
  if (b.label === "threat" && !failed.length) {
    out.push(`Hence a Threat: it passes all ${tests.length} checks — it is bad news for KSSL, ${p && p.answer ? "near certain" : "likely"}, ` +
      `hits hard, comes soon, lands in a KSSL market and competes with a KSSL product.`);
  } else if (failed.length) {
    const miss = failed.map((t) => `${(t.question || t.test || "").replace(/\?$/, "").toLowerCase()} (${t.answer || "not known"}; a threat needs: ${t.need || "—"})`);
    out.push(`Hence a ${b.label === "threat" ? "Threat" : "Watch"}, not a Threat: it misses ${failed.length} of the ${tests.length} checks — ${miss.join("; ")}.`);
  }
  return out;
}

/* Self-check: node src/lib/riskReading.js */
export function riskReadingSelfCheck() {
  const bad = [];
  const ok = (n, c) => { if (!c) bad.push(n); };
  ok("a score prefix and the anchor tag are dropped", plainReason("5: the army has ordered the prototypes (anchor: done).") === "The army has ordered the prototypes.");
  ok("a code prefix is dropped", plainReason("lt_1y: the order is already placed") === "The order is already placed");
  ok("a reason without a prefix is kept", plainReason("XM1776 is a wheeled gun") === "XM1776 is a wheeled gun");
  const basis = {
    label: "watch", mainDimension: "orders_revenue",
    reasons: { probability: "5: ordered.", impact_orders_revenue: "4: like-for-like gun.", time_to_effect: "gt_3y: deliveries from 2030." },
    tests: [{ key: "probability", pass: true, answer: "Already happening (5 of 5)" }, { key: "impact", pass: true, answer: "Hard (4 of 5)" },
      { key: "time_to_effect", pass: false, question: "When will KSSL feel it?", answer: "After 3 years", need: "Within 3 years" }],
  };
  ok("the impact check reads the main dimension's reason", reasonFor(basis.tests[1], basis) === "Like-for-like gun.");
  const r = analyticalReading(basis, "Army orders guns");
  ok("the reading starts with what happened", r[0] === "What happened: Army orders guns.");
  ok("a watch names the check it misses", /misses 1 of the 3 checks — when will kssl feel it \(After 3 years; a threat needs: Within 3 years\)/.test(r[r.length - 1]));
  ok("no tests, no reading", analyticalReading({}, "x").length === 0);
  return bad;
}

if (typeof process !== "undefined" && process.argv && /riskReading\.js$/.test(process.argv[1] || "")) {
  const bad = riskReadingSelfCheck();
  console.log(bad.length ? "FAIL: " + bad.join("; ") : "riskReading self-check ok");
  if (bad.length) process.exit(1);
}
