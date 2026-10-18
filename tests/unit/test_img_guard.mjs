/* /api/img SSRF guard: only public http(s) hosts.   node --test test_img_guard.mjs */
import test from "node:test";
import assert from "node:assert/strict";
import { privateAddress, publicImageUrl } from "../../src/lib/imgGuard.js";

test("private, loopback, link-local, metadata and v6 local addresses are blocked", () => {
  for (const ip of ["127.0.0.1", "10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fd00::1", "fe80::1", "::ffff:127.0.0.1"])
    assert.ok(privateAddress(ip), ip);
  for (const ip of ["8.8.8.8", "172.32.0.1", "62.72.59.79", "2606:4700::1111"]) assert.ok(!privateAddress(ip), ip);
});

test("urls: scheme, port, credentials and private hosts refused", async () => {
  for (const u of ["file:///etc/passwd", "http://127.0.0.1/x.png", "http://localhost:8600/api/dataset", "http://169.254.169.254/latest",
    "http://[::1]/", "http://8.8.8.8:5432/", "http://user:pw@8.8.8.8/", "gopher://8.8.8.8/", "not a url"])
    assert.equal(await publicImageUrl(u), false, u);
  assert.equal(await publicImageUrl("https://8.8.8.8/a.png"), true);
});
