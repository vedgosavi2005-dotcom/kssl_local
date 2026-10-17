/* Market outlook counts stored records and reads stored judgements (lib/marketOutlook.js).
 *
 *     node test_market_outlook.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as MO from "./src/lib/marketOutlook.js";

const today = new Date("2026-10-15T00:00:00Z");
const d = {
  tenders: [
    { cat: "Ships", req: [["published_date", "2026-10-01"]], clientFit: "strong", revenueMid: 1e6, country: "Norway", issuer: "Buyer One",
      valueAmount: 5e6, valueCurrency: "EUR" },
    { cat: "Ships", req: [["published_date", "2026-08-01"]], issuer: "Buyer One" },
    { cat: "Tanks", req: [["closing_date", "2026-03-01"]], issuer: "Buyer Two" },
  ],
  awards: [
    { segment: "Ships", winner: "A Trading Co.", value: 100, currency: "USD", buyer: "Buyer One", date: "2026-09-01" },
    { segment: "Ships", winner: "A Trading Co.", value: 50, currency: "USD", buyer: "Buyer One", date: null, year: 2025 },
    { segment: "Tanks", winner: "B", value: null, currency: null, buyer: "Buyer Two", date: "2026-02-01" },
  ],
  marketCards: [
    { meta: "news · Oslo, Norway · Ships · 2026-10-02", title: "S" },
    { meta: "milestone · Norway · Ships · 2026-10-03", title: "G" },
    { meta: "Tender · X · closes 08 Oct 2026", title: "T" },
  ],
  database: { serving: { market_segment_assessment: [{ segment: "Ships", recommendation: "Prioritise: stored words" }, { segment: "Tanks", recommendation: "" }] } },
};
const s = MO.segments(d, d.tenders.slice(0, 1), today, [{ cat: "Tanks", status: "evaluation", clientFit: "partial", title: "X" }]);
const ships = s.find((r) => r.segment === "Ships");
const tanks = s.find((r) => r.segment === "Tanks");

// dates come from the requirement CODES, not English labels
assert.equal(ships.recent, 5, "published_date rows, signals and the dated award fall in the last six months");
assert.equal(ships.open, 1);
assert.equal(tanks.pending.n, 1);

// the recommendation is the stored text for that segment, else null; nothing is composed
assert.equal(ships.recommendation, "Prioritise: stored words");
assert.equal(tanks.recommendation, null);
assert.equal(MO.recommendationOf({}, "Ships"), null);

// no trend words, no act sentence, no "called" flag
for (const k of ["trend", "act", "called"]) assert.equal(k in ships, false, `${k} must not be on a segment row`);
// the signed change between the two counted windows is plain arithmetic, null when the earlier window is empty
assert.equal(ships.change, ships.before > 0 ? Math.round(((ships.recent - ships.before) / ships.before) * 100) : null);

// values stay per currency
assert.deepEqual(ships.totals, [{ currency: "EUR", amount: 5e6, n: 1 }]);
const w = MO.winners(d);
assert.deepEqual(w.rows[0].totals, [{ currency: "USD", amount: 150, n: 2 }]);
assert.equal(w.rows[0].wins, 2);

// repeat buyers: counts and a last date; no usual gap, no forecast, no overdue flag
const b = MO.buyers(d);
assert.equal(b[0].buyer, "Buyer One");
assert.equal(b[0].count, 4);
for (const k of ["next", "overdue", "cadenceDays"]) assert.equal(k in b[0], false, `${k} must not be on a buyer row`);

// drivers group by the stored location text and join tenders on a country part
const dr = MO.drivers(d);
assert.equal(dr.length, 2);
assert.equal(dr.find((r) => r.country === "Oslo, Norway").tenders, 1);

// the genset size table and the other removed exports are gone
for (const gone of ["sizes", "usd", "SEGMENT_LABEL", "segmentLabel"]) assert.equal(gone in MO, false, `${gone} must not be exported`);
assert.equal("sizes" in MO.outlook(d, [], today, []), false);

// on the fixture, every stored recommendation reaches its own segment and nothing else does
const fx = JSON.parse(readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url)));
const stored = fx.database.serving.market_segment_assessment;
assert.ok(stored.length > 0);
const fs = MO.segments(fx, fx.tenders.filter((t) => t.status === "open"), new Date("2026-10-17T00:00:00Z"), []);
for (const r of fs) {
  const row = stored.find((x) => x.segment === r.segment);
  assert.equal(r.recommendation, row ? row.recommendation : null);
}

const src = readFileSync(new URL("./src/lib/marketOutlook.js", import.meta.url), "utf8");
assert.ok(!/genset|kva|BANDS|SEG_ALIAS|rising|falling|steady/i.test(src));

console.log("ok - outlook counts records; recommendations are stored; values per currency");
