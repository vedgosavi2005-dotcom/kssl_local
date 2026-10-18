/* The image proxy (/api/img) may fetch only public web hosts: http(s), default ports, and a name that resolves to
   no private, loopback, link-local, CGNAT, multicast or unspecified address (no docker hosts, no 169.254.169.254).
   ponytail: checks the DNS answer before fetch, so a DNS-rebinding host could still flip between check and fetch;
   pin the resolved IP in the request (undici dispatcher) if the proxy is ever exposed beyond image hotlinks. */
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

const V4_BLOCK = [[0, 8], [10, 8], [100.64, 10], [127, 8], [169.254, 16], [172.16, 12], [192.168, 16], [192.0, 24], [198.18, 15], [224, 4], [240, 4]];
const v4num = (ip) => ip.split(".").reduce((n, o) => n * 256 + Number(o), 0);
const cidr = (base) => { const [a, b = 0] = String(base).split(".").map(Number); return v4num(`${a}.${b}.0.0`); };

export function privateAddress(ip) {
  if (isIP(ip) === 4) {
    const n = v4num(ip);
    return V4_BLOCK.some(([base, bits]) => n >>> (32 - bits) === cidr(base) >>> (32 - bits));
  }
  const v = ip.toLowerCase();
  if (v.startsWith("::ffff:")) return privateAddress(v.slice(7));
  return v === "::" || v === "::1" || /^f[cd]/.test(v) || /^fe[89ab]/.test(v) || v.startsWith("ff");
}

export async function publicImageUrl(raw) {
  let u;
  try { u = new URL(raw); } catch { return false; }
  if (!/^https?:$/.test(u.protocol) || (u.port && u.port !== "80" && u.port !== "443") || u.username || u.password) return false;
  const host = u.hostname.replace(/^\[|\]$/g, "");
  try {
    const addrs = isIP(host) ? [{ address: host }] : await lookup(host, { all: true });
    return addrs.length > 0 && !addrs.some((a) => privateAddress(a.address));
  } catch { return false; }
}
