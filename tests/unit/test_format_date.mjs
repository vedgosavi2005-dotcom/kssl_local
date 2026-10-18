/* formatDate: what the source states, no more. No value -> "" (never today); a year-only value stays the year.
 *
 *     node --test test_format_date.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { formatDate } from "../../src/utils/formatDate.js";

test("no value is no date, never today or 1970", () => {
  for (const v of [undefined, null, ""]) assert.equal(formatDate(v), "");
});

test("precision is kept: full day, month only, year only", () => {
  assert.equal(formatDate("2026-09-05"), "05 Sep 2026");
  assert.equal(formatDate("2019-05"), "May 2019");
  assert.equal(formatDate("2019"), "2019", "published_precision 'year' ships the year alone");
});
