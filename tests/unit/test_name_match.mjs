// node tests/unit/test_name_match.mjs -- the Products search matches names by word start only
import assert from "node:assert/strict";
import { nameMatches } from "../../src/lib/nameMatch.js";

assert.ok(nameMatches("LOCUST X3", "loc"), "a word start matches");
assert.ok(!nameMatches("Switchblade 300 Block 20", "loc"), "a match inside a word does not");
assert.ok(nameMatches("K9 / K9A1 Thunder", "k9 thun"), "every typed word must start some word");
assert.ok(!nameMatches("K9 / K9A1 Thunder", "k9 howitzer"), "a word the name does not have fails");
assert.ok(nameMatches("F-35A Lightning II", "f-35"), "a hyphenated designation is found by its first part");
assert.ok(nameMatches(".338 Lapua Magnum", ".338"), "a calibre with a dot");
assert.ok(!nameMatches("Anything", ""), "an empty query matches nothing");
console.log("ok - product search: names only, word starts");
