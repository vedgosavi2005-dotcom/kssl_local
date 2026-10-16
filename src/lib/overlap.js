/* WHERE A RIVAL'S PARTNER IS ALSO THE CLIENT'S.

   No stored column says it: competitive_partnership.partner_id (uuid) and
   client_partner.client_partner_id (bigint) are different key spaces, and
   client_partner_relationship.competitor_overlap is a client-side flag with no competitor in it.
   So the only join there is is the partner's NAME. This is a presentation rule over two DB
   columns (competitive_partnership.partner_name, client_partner.partner_name): both names are
   reduced to letters and digits with parentheticals and corporate-form words dropped
   ("Helix Propulsion Ltd" and "Helix Propulsion" meet), and equal keys are the same company.

   A tie this cannot match is left as it was: a name comparison that finds nothing is not proof
   there is no overlap, so no "no overlap" claim is made either. If a column carrying the match
   is added (an overlap flag or client_partner_id on competitive_partnership), this file goes. */

/* The shortest residue trusted as an identity: two characters cannot tell two companies apart. */
export const MIN_KEY = 3;

const CORPORATE_FORM =
  /\b(inc|incorporated|ltd|limited|llc|llp|plc|gmbh|ag|sa|oy|ab|as|bv|nv|corp|corporation|co|company|pvt|private|spa|srl|sas|kg)\b/g;

export function partnerKey(label) {
  const key = String(label == null ? "" : label)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\(.*?\)/g, " ")
    .replace(CORPORATE_FORM, " ")
    .replace(/[^a-z0-9]+/g, "");
  return key.length >= MIN_KEY ? key : "";
}

/* key -> the client's own partner row, so a match can name what the client uses it for */
export function clientPartnerIndex(ksslPartners) {
  const idx = {};
  (ksslPartners || []).forEach((p) => {
    const k = partnerKey(p && p.label);
    if (k && !idx[k]) idx[k] = p;
  });
  return idx;
}

/* Stamps `shared` and `koel` (the client's own partner row) on every rival partner whose name
   matches one of the client's. Returns a new dataset; the input is not mutated. */
export function markOverlaps(d) {
  const idx = clientPartnerIndex(d && d.KSSL_PARTNERS);
  if (!d || !d.competitors || !Object.keys(idx).length) return d;
  const competitors = {};
  Object.keys(d.competitors).forEach((cid) => {
    const c = d.competitors[cid];
    if (!c || !Array.isArray(c.partners)) {
      competitors[cid] = c;
      return;
    }
    competitors[cid] = {
      ...c,
      partners: c.partners.map((p) => {
        const hit = idx[partnerKey(p && p.label)];
        return hit ? { ...p, shared: true, koel: hit } : p;
      }),
    };
  });
  return { ...d, competitors };
}

export default markOverlaps;
