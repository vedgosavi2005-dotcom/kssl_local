/* The Latest Tenders head is the first ATTENTION_HEAD open tenders in stored rank order, unranked after, newest first.
 * No score is computed from fit, geography or closing date.
 *
 *     node tests/unit/test_market_attention.mjs
 */
import assert from "node:assert/strict";
import { marketAttention, ATTENTION_HEAD } from "../../src/lib/overview.js";

const t = (id, rank, posted, extra = {}) => ({ id, rank, posted, ...extra });
const open = [
  t("c", 3, "2026-01-01", { lean: "go" }),
  t("u-old", null, "2026-01-01"),
  t("a", 1, "2026-01-01", { lean: "no", dl: 400 }),
  t("u-new", null, "2026-09-01", { lean: "go", dl: 2 }),
  t("b", 2, "2026-01-01"),
];
assert.deepEqual(marketAttention(open).map((x) => x.id), ["a", "b", "c", "u-new", "u-old"]);
// a fit code or a near deadline does not move a tender
assert.deepEqual(marketAttention(open.slice().reverse()).map((x) => x.id), ["a", "b", "c", "u-new", "u-old"]);
// capped at the head
const many = Array.from({ length: ATTENTION_HEAD + 5 }, (_, i) => t(`t${i}`, i + 1, "2026-01-01"));
assert.equal(marketAttention(many).length, ATTENTION_HEAD);
assert.equal(marketAttention(many)[0].id, "t0");
assert.deepEqual(marketAttention(null), []);
console.log("ok - the head follows the stored rank");
