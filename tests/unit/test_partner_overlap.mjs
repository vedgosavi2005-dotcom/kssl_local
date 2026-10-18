/* "The overlaps are not shown" -- and they were not, for a reason in the data.
 *
 * 256 of 258 served partner ties carry neither a `shared` flag nor a `cid`, so
 * partners.overlapState called them "unchecked", which is what they were: mark_shared.py
 * is wired into no pass on this database. The client's OWN roster is served on the same
 * response, though, so the join is computable in the app -- and it resolves 5 rivals.
 *
 * What is asserted here is mostly the danger in a name match: that it does not invent
 * overlaps, does not overrule the backend, and does not quietly downgrade "we have not
 * looked" into "we looked and there is nothing".
 */
import { markOverlaps, partnerKey, overlapMatch, clientPartnerIndex, MIN_KEY } from "../../src/lib/overlap.js";
import { overlapState } from "../../src/lib/partners.js";

let fail = 0;
const ck = (name, ok, d) => {
  console.log(`  ${name.padEnd(64)} ${ok ? "PASS" : "FAIL"}${d !== undefined && !ok ? "  " + JSON.stringify(d) : ""}`);
  if (!ok) fail++;
};

/* ---- the key: the ways one company's name is written on two rosters ---- */
ck("a parenthetical qualifier is dropped", partnerKey("DRDO (HEMRL, ARDE)") === "drdo", partnerKey("DRDO (HEMRL, ARDE)"));
ck("the legal suffix is dropped", partnerKey("PLR Systems Pvt Ltd") === partnerKey("PLR Systems"), partnerKey("PLR Systems Pvt Ltd"));
ck("case and punctuation do not matter", partnerKey("A.M. GENERAL") === partnerKey("AM General"));
ck("the industry word is NOT dropped -- it is often the name",
   partnerKey("PLR Systems") === "plrsystems", partnerKey("PLR Systems"));
ck("two different companies do not collide on a shared word",
   partnerKey("Bharat Dynamics") !== partnerKey("Bharat Electronics"));
ck("a name too short to identify anything is refused", partnerKey("BE") === "" && partnerKey("X") === "");
ck("an empty or missing label is refused", partnerKey("") === "" && partnerKey(null) === "" && partnerKey(undefined) === "");
ck("MIN_KEY admits real three-letter names", MIN_KEY <= 3 && partnerKey("PLR") === "plr");

/* ---- the join ---- */
const KSSL_PARTNERS = [
  { id: "k1", label: "DRDO" },
  { id: "k2", label: "AM General" },
  { id: "k3", label: "PLR Systems" },
];
const idx = clientPartnerIndex(KSSL_PARTNERS);
ck("the client index names what it matched", overlapMatch({ label: "DRDO (HEMRL, ARDE)" }, idx) === "DRDO");
ck("a partner not on the client roster is no match", overlapMatch({ label: "Kalashnikov" }, idx) === "");

const data = () => ({
  KSSL_PARTNERS,
  competitors: {
    adani: {
      name: "Adani Defence",
      partners: [
        { id: "p1", label: "DRDO", overlap: { kind: "same_partner_other_scope", clientPartner: "DRDO", clientPartnerId: "kp1" } },
        { id: "p2", label: "Elbit Systems" },
      ],
    },
    aweil: {
      name: "AWEIL",
      /* flagged by a backend pass this join cannot reproduce: Saab is not on the client
         roster at all, so a name match would say "no" where the pipeline said "yes" */
      partners: [{ id: "p3", label: "Saab", shared: true }],
    },
    nopartners: { name: "Thin Co" },
  },
});

const out = markOverlaps(data());
const adani = out.competitors.adani.partners;
ck("a rival partner on the client's roster is marked shared", adani[0].shared === true, adani[0]);
ck("it names WHICH client partner it matched", adani[0].sharedWith === "DRDO", adani[0].sharedWith);
ck("that tie now reads 'shared' to the badge", overlapState(adani[0]) === "shared");

ck("a partner NOT on the client roster is left alone", adani[1].shared === undefined, adani[1]);
ck("and stays UNCHECKED, not 'no overlap' -- a name miss is not evidence of absence",
   overlapState(adani[1]) === "unchecked", overlapState(adani[1]));

const saab = out.competitors.aweil.partners[0];
ck("a backend-flagged tie is never overruled", saab.shared === true && overlapState(saab) === "shared");
ck("and is not re-labelled with a match it does not have", saab.sharedWith === undefined, saab.sharedWith);

ck("a company with no partners does not crash", !!out.competitors.nopartners);
ck("the input is not mutated", data().competitors.adani.partners[0].shared === undefined);

/* ---- the guards ---- */
ck("a stored kind 'none' reads as checked, no badge",
   overlapState(markOverlaps({ competitors: { x: { partners: [{ label: "DRDO", overlap: { kind: "none" } }] } } }).competitors.x.partners[0]) === "none");
ck("no stored overlap: a NAME on the client roster is NOT marked (the browser no longer guesses)",
   markOverlaps({ KSSL_PARTNERS, competitors: { x: { partners: [{ label: "DRDO" }] } } }).competitors.x.partners[0].shared === undefined);
ck("no dataset, no crash", markOverlaps(null) === null && markOverlaps({}) !== undefined);
ck("nothing matched means the dataset comes back as it was",
   markOverlaps({ KSSL_PARTNERS, competitors: { x: { partners: [{ label: "Nobody Ltd" }] } } }).competitors.x.partners[0].shared === undefined);

console.log(fail ? `\n${fail} FAILED` : "\nall passed");
process.exit(fail ? 1 : 0);
