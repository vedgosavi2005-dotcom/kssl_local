/* Market outlook panel and the Cummins-port additions (lib/outlookDetail.js, lib/marketOutlook.js), 2026-10-26.
 *
 *     node tests/unit/test_outlook_detail.mjs
 *
 *   - a calibre is a millimetre figure some catalogue product states as its calibre; KSSL covers it with a product of
 *     the same category whose Calibre spec names it or a range holding it;
 *   - the client's own awards never count as a rival's;
 *   - a project to win takes its segment from its opportunity's market card;
 *   - awards group under the tracked competitor whose name they carry, one per source URL;
 *   - every panel draws 12 months, and no forecast or trend word is written.
 */
import assert from "node:assert/strict";
import * as MO from "../../src/lib/marketOutlook.js";
import * as OD from "../../src/lib/outlookDetail.js";
import { setFxRates } from "../../src/lib/tenderValue.js";

const today = new Date("2026-10-15T00:00:00Z");
const sheet = (cal) => ({ key: [{ l: "Calibre", v: cal }] });
const d = {
  client: { id: "1", short: "KSSL", name: "KSSL" },
  competitors: {
    1: { name: "Kalyani Strategic Systems", products: [{ name: "Gun 155", category: "Artillery", sheet: sheet("155 mm / 52 cal") }, { name: "Empty shells", category: "Ammunition", sheet: sheet(["70 to 155 mm"]) }] },
    r: { name: "Rheinmetall", products: [{ name: "P9", category: "Small Arms", sheet: sheet("9 mm") }] },
    b: { name: "RTX (Raytheon)", products: [] },
  },
  sipriArms: { r: { entity: "Rheinmetall", rank: 20, year: 2024, armsUsdM: 7000, share: 0.7, source: { url: "https://sipri.org/x" } } },
  tenders: [
    { id: "t1", title: "Supply of 155 mm shells", cat: "Ammunition", status: "open", clientFit: "partial", country: "India", issuer: "MoD", req: [["published_date", "2026-10-01"]],
      competitorFit: [{ company: "Rheinmetall", products: ["Shell X"], fit: "partial", why: "a 155 mm shell" }] },
    { id: "t2", title: "Pistols 9 x 19 mm", cat: "Small Arms", status: "open", clientFit: "weak", country: "France", issuer: "Police", req: [["published_date", "2026-09-01"]] },
    { id: "t3", title: "Steel forging 210 mm bar", cat: "Ammunition", status: "open", country: "India", issuer: "MoD", req: [] },
  ],
  awards: [
    { segment: "Ammunition", winner: "Rheinmetall Waffe Munition GmbH", value: 100, currency: "EUR", buyer: "MoD", country: "India", date: "2026-08-01", url: "https://a.test/1", title: "155 mm rounds" },
    { segment: "Ammunition", winner: "Kalyani Strategic Systems", value: 50, currency: "EUR", buyer: "MoD", country: "India", date: "2026-07-01", url: "https://a.test/2" },
    { segment: "Ammunition", winner: "Raytheon Missiles", value: null, currency: null, buyer: "MoD", date: "2026-06-01", url: "https://a.test/3" },
    { segment: "Ammunition", winner: "Rheinmetall Waffe Munition GmbH", value: 10, currency: "EUR", buyer: "MoD", date: "2026-05-01", url: "https://a.test/1" },
  ],
  marketCards: [{ id: "upd-9", title: "Project card", tags: "Ammunition", meta: "need_stated · India · Ammunition · 2026-10-02", _src: { t: "market_opportunity", id: "77" } }],
  topOpportunities: { projectsBeforeTender: [{ id: "p1", opportunityId: "77", title: "70 mm rockets lead", country: "India", ksslFit: "strong", sources: [{ url: "https://p.test" }] }] },
};
setFxRates({ EUR: 100 });
const open = d.tenders;

// calibres: 210 mm is a dimension (no catalogue product states it), 155 mm is covered by the range in the same category
const cal = MO.calibres(d, open);
assert.deepEqual(cal.rows.map((r) => r.key).sort(), ["155 mm · Ammunition", "9 mm · Small Arms"]);
assert.ok(!cal.rows.some((r) => r.cal === 210), "210 mm is not a calibre");
assert.equal(cal.rows.find((r) => r.key === "155 mm · Ammunition").covered, true);
assert.equal(cal.rows.find((r) => r.key === "9 mm · Small Arms").covered, false, "only a rival lists 9 mm");

// projects take the stored category of their opportunity card
assert.equal(MO.projectRows(d)[0].cat, "Ammunition");

// the client's own award is not a rival's; the leading winner is ranked by rupee value
const seg = MO.segments(d, open, today, []).find((r) => r.segment === "Ammunition");
assert.equal(seg.winner, "Rheinmetall Waffe Munition GmbH");
assert.equal(seg.named, 3);
assert.equal(seg.projects, 1);
const w = MO.winners(d);
assert.ok(!w.rows.some((r) => /kalyani/i.test(r.winner)));
assert.equal(w.rows[0].share, 1);

// panels: 12 months, client wins on their own tile, SIPRI for a tracked rival
const sd = OD.segmentDetail(d, "Ammunition", seg, today);
assert.equal(sd.charts[0].rows.length, 12);
assert.equal(sd.tiles.find((t) => t.k === "Won by KSSL").v, 1);
assert.equal(sd.sections.find((s) => s.h === "Competitors active here").rows[0].title, "Rheinmetall");
assert.match(sd.sections.find((s) => s.h === "How big the competitors are").rows[0].title, /SIPRI Top 100 #20/);
const wd = OD.winnerDetail(d, "Rheinmetall Waffe Munition GmbH", w.rows[0], today);
assert.equal(wd.tiles[0].v, 2);
const words = JSON.stringify([sd, wd]);
assert.ok(!/rising|falling|steady|overdue|next expected|recommendation:/i.test(words), "no trend word or forecast");

// awarded per competitor: grouped by the tracked name, one per URL, the client left out, a bracket alias read
const abc = OD.awardedByCompetitor(d, 8);
assert.deepEqual(abc.map((r) => [r.competitor, r.awards]), [["Rheinmetall", 1], ["RTX (Raytheon)", 1]]);

console.log("ok - outlook panel, calibres, projects and competitor awards read the stored records");
