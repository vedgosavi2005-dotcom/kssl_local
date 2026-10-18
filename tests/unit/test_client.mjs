import test from "node:test";
import assert from "node:assert/strict";
import { setClient, clientName, clientShort } from "../../src/lib/client.js";

test("name and short come from the client record", () => {
  setClient({ name: "KSSL Test", short: "KSSL" });
  assert.equal(clientName(), "KSSL Test");
  assert.equal(clientShort(), "KSSL");
});

test("short falls back to name, nothing else", () => {
  setClient({ name: "X" });
  assert.equal(clientShort(), "X");
  assert.equal(clientName(), "X");
});

test("unset client gives empty strings, no default name", () => {
  setClient(null);
  assert.equal(clientName(), "");
  assert.equal(clientShort(), "");
  setClient({});
  assert.equal(clientName(), "");
  assert.equal(clientShort(), "");
});
