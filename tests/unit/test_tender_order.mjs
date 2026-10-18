/* Tenders list: a stored client fit first (stored % else grade), then the nearest deadline.
 *
 *     node --test test_tender_order.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { compareTenders } from "../../src/lib/tenderRow.js";

test("fit first, strongest first, then deadline; no fit last", () => {
  const rows = [
    { id: "none-soon", dl: 1 },
    { id: "weak", dl: 5, fit: "weak" },
    { id: "pct80", dl: 30, matches: [{ fit: "partial", pct: "80%" }] },
    { id: "partial-late", dl: 20, matches: [{ fit: "partial" }] },
    { id: "partial-soon", dl: 2, matches: [{ fit: "partial" }] },
  ];
  assert.deepEqual(rows.sort(compareTenders).map((r) => r.id), ["pct80", "partial-soon", "partial-late", "weak", "none-soon"]);
});
