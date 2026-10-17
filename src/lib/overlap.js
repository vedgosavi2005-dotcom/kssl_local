/* WHERE A RIVAL'S PARTNER IS ALSO THE CLIENT'S -- computed, because nothing computed it.
 *
 * Reported as "the overlaps are not shown". They were not, and the reason is in the
 * served data rather than in the render: of 258 partner ties on the roster, 256 carry
 * NEITHER a `shared` flag NOR a `cid`. partners.js already reads that correctly and
 * calls it "Overlap Unchecked" -- the honest label for a join that has not run
 * (mark_shared.py is wired into no pass on this database). So the page was not hiding
 * overlaps; it was truthfully reporting that nobody had looked.
 *
 * Nobody had to. The client's own partner roster is served, in full, on the same
 * response: KSSL_PARTNERS, 17 rows. "Is this rival's partner also ours" is a comparison
 * between two lists that are both already in memory, and it resolves 6 ties across 5
 * rivals -- Adani and Bharat Dynamics on DRDO, Premier Explosives on DRDO (HEMRL, ARDE),
 * IDV on AM General, Tata Advanced Systems on Boeing.
 *
 * THIS ADDS, IT NEVER OVERRULES. A tie the backend has already flagged stays flagged
 * (AWEIL/Saab is marked shared by a pass this join cannot reproduce, because Saab is not
 * on KSSL_PARTNERS). A tie this join cannot match is left exactly as it was -- still
 * "unchecked", not downgraded to "no overlap". A name comparison finding nothing is not
 * evidence that nothing is there, and saying so would be the same false confidence the
 * green "Direct Partner" badge used to project.
 *
 * MATCHING, AND ITS ONE REAL RISK. Names arrive written differently on the two sides:
 * "DRDO (HEMRL, ARDE)" against "DRDO", "PLR Systems Pvt Ltd" against "PLR Systems". So
 * the key drops a parenthetical, the legal suffixes, and the industry filler words that
 * then everything that is not a letter or a digit.
 *
 * That stripping is what can go wrong, in BOTH directions -- reduce a name far enough
 * and two different companies collide; reduce it too far and a real one disappears. The
 * second happened on the first pass here, which is why the list below is short.
 *
 * It strips the LEGAL suffix only (Pvt, Ltd, Inc, GmbH, PLC), NOT the industry words.
 * Stripping "Systems", "Industries" and "Defence" as well took "PLR Systems Pvt Ltd"
 * down to "plr" -- three characters, which the length guard then refused, so the more
 * aggressive rule lost a match it had been written to find. It would also have collapsed
 * "Defence Systems" and "Aerospace Industries" to nothing at all, and made any two names
 * sharing one distinctive word collide on it.
 *
 * MIN_KEY is the remaining guard: under three characters is not an identity, and neither
 * is a name that reduces to nothing. Both are asserted in test_partner_overlap.mjs
 * against the real roster.
 *
 * 2026-09-21: the key derivation moved to orgident.js (`orgKey`), shared with the graph,
 * and now also folds a trailing national qualifier ("Saab Australia" -> "saab") so the
 * roster join stops missing the country-variant spellings.
 */
import { orgKey } from "./orgident.js";

/* The shortest residue this will trust as an identity. "PLR", "ITI" and "IAI" are real
   names at three characters; two is not enough to tell two companies apart. */
export const MIN_KEY = 3;

/* Identity now comes from the shared canonicaliser (orgident.js), so "Saab Australia"
   keys to the same "saab" as the roster's "Saab AB" and the overlap actually resolves --
   the old key stripped only legal suffixes and a national qualifier collided every time. */
export function partnerKey(label) {
  const key = orgKey(label);
  return key.length >= MIN_KEY ? key : "";
}

/* key -> the client's own label for it, so the badge can name what it matched */
export function clientPartnerIndex(ksslPartners) {
  const idx = {};
  (ksslPartners || []).forEach((p) => {
    const k = partnerKey(p && p.label);
    if (k && !idx[k]) idx[k] = String((p && p.label) || "");
  });
  return idx;
}

/* Does this tie overlap the client's roster? Returns the client's label for the match,
   or "" for no match. A row the backend already flagged is not re-tested here -- see
   markOverlaps, which unions the two. */
export function overlapMatch(partner, idx) {
  const k = partnerKey(partner && partner.label);
  return (k && idx[k]) || "";
}

/* Stamps `shared` and `sharedWith` on every rival partner that matches the client's own
   roster. Returns a new dataset; the input is not mutated. */
export function markOverlaps(d) {
  const idx = clientPartnerIndex(d && d.KSSL_PARTNERS);
  if (!d || !d.competitors || !Object.keys(idx).length) return d;

  let found = 0;
  const competitors = {};
  Object.keys(d.competitors).forEach((cid) => {
    const c = d.competitors[cid];
    const parts = c && Array.isArray(c.partners) ? c.partners : null;
    if (!parts) {
      competitors[cid] = c;
      return;
    }
    competitors[cid] = {
      ...c,
      partners: parts.map((p) => {
        /* already flagged upstream: leave it exactly as served */
        if (p && (p.koel || p.shared)) return p;
        const with_ = overlapMatch(p, idx);
        /* A name-comparison miss is NOT proof of no overlap -- the row stays "unchecked"
           (test_partner_overlap). The clutter the user saw is handled at the badge layer
           (overlapBadge no longer prints a badge for the unchecked norm), not by claiming
           a match was ruled out here. */
        if (!with_) return p;
        found += 1;
        return { ...p, shared: true, sharedWith: with_ };
      }),
    };
  });
  if (!found) return d;
  return { ...d, competitors };
}

export default markOverlaps;
