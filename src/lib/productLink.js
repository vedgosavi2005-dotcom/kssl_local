/* Which catalogue product a name on a tender refers to. A tender's "Matched products" and "Competitor fit" lists
   name catalogue models next to labels that are not products ("Service job: no product to quote"). Only a name that is a model in data.competitors[cid].products is a link; the label stays plain text. */
/* compared by letters and digits only, ignoring case: the served catalogue is re-cased on load ("Alpha 155 (Mk2)")
   while a tender's fit list keeps the researcher's spelling ("alpha 155 mk2") */
const key = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");

export function productOwner(data, name) {
  const want = key(name);
  if (!want) return null;
  const comps = (data && data.competitors) || {};
  for (const cid of Object.keys(comps)) {
    const hit = ((comps[cid] && comps[cid].products) || []).find((p) => key(p && p.name) === want);
    if (hit) return { cid, productName: hit.name };
  }
  return null;
}
