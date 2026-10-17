/* Serve-time partner identity: the canonicaliser only. The junk gate, the demonym map and the
   company aliases are gone: what the database stores is what is shown (MAPPING B, ruling R6). */
import assert from "node:assert/strict";
import fs from "node:fs";
import { orgKey, canonicalizeLabels } from "./orgident.js";
import * as orgident from "./orgident.js";

const src = fs.readFileSync(new URL("./orgident.js", import.meta.url), "utf8");
assert.ok(!("isJunkPartner" in orgident), "isJunkPartner is gone");
assert.ok(!/const (NATIONAL|ALIASES|COLLECTIVE|PLACES|FORCE_RX|QTY_RX|VAGUE_RX)\b/.test(src), "no word lists about places, forces or companies");
assert.ok(!/Hindustan|Hanwha|Rafael/.test(src), "no hand-typed company aliases");

// ---- canonical key: legal suffix folds to one identity ----
assert.equal(orgKey("Saab AB"), orgKey("Saab"));
assert.equal(orgKey("Acme Works Ltd"), orgKey("Acme Works"));
// distinct firms stay distinct
assert.notEqual(orgKey("Israel Aerospace Industries"), orgKey("Israel Weapon Industries"));
assert.notEqual(orgKey("General Dynamics"), orgKey("General Atomics"));
assert.notEqual(orgKey("Lockheed Martin"), orgKey("Martin-Baker"));
// no alias table: the short and long spelling are two names unless one contains the other's distinctive tokens
assert.notEqual(orgKey("Rafael Advanced Defence Systems"), orgKey("Rafael"));

// ---- containment merge ----
{
  const labels = ["Lockheed Martin", "Lockheed Martin Skunk Works", "Saab", "Israel Weapon Industries"];
  const { keyOf } = canonicalizeLabels(labels);
  const lm = keyOf("Lockheed Martin");
  assert.equal(keyOf("Lockheed Martin Skunk Works"), lm, "Skunk Works folds into Lockheed Martin");
  assert.notEqual(keyOf("Israel Weapon Industries"), lm);
  assert.equal(new Set(labels.map(keyOf)).size, 3);
}

console.log("orgident: all assertions passed");
