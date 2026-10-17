/* Check for the srcChips href scheme allow-list: only http/https/mailto reach an href;
   a javascript:/data:/vbscript: url (however it is obfuscated with leading or embedded
   control chars) is dropped to plain text. Run: node this file. */
import assert from "node:assert/strict";
import { safeUrl, srcChips } from "./html.js";

// dangerous schemes -> "" so the caller renders plain text
const BAD = [
  "javascript:alert(1)",
  "JavaScript:alert(1)",             // scheme match is case-insensitive
  "  javascript:alert(1)",           // leading spaces the browser trims
  "\u0001javascript:alert(1)",       // leading control char
  "java\tscript:alert(1)",           // tab inside the scheme (browsers strip it)
  "java\nscript:alert(1)",           // newline inside the scheme
  "data:text/html,<script>alert(1)</script>",
  "vbscript:msgbox(1)",
];
BAD.forEach((u) => assert.equal(safeUrl(u), "", `must reject: ${JSON.stringify(u)}`));

// allowed schemes pass through unchanged; a scheme-less (relative) url is safe too
const GOOD = [
  "https://example.com/a?b=1#c",
  "http://example.com",
  "HTTPS://EXAMPLE.COM",
  "mailto:tender@example.com",
  "/relative/path",
  "example.com/page",                // no scheme -> relative, not "example.com:"
  "#anchor",
];
GOOD.forEach((u) => assert.equal(safeUrl(u), u, `must allow: ${JSON.stringify(u)}`));

// end to end: a javascript: source yields no href, but its label still renders
const evil = srcChips([{ label: "Source", url: "javascript:alert(document.cookie)" }]);
assert.ok(!/href=/.test(evil), "no href is emitted for a javascript: source");
// the only place the raw url survives is the inert title tooltip; nowhere executable
assert.ok(!/javascript:/i.test(evil.replace(/title="[^"]*"/g, "")), "no javascript: in a live attribute");
assert.ok(/Source/.test(evil), "the label still renders as plain text");

// a normal https source still renders a proper link
const good = srcChips([{ label: "TED", url: "https://ted.europa.eu/notice/1" }]);
assert.ok(/href="https:\/\/ted\.europa\.eu\/notice\/1"/.test(good), "an https source renders an href");

console.log("html safeUrl: all assertions passed");
