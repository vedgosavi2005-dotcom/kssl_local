/* ===================================================================
   GEO FOOTPRINT -- lookups over the served footprint tables.

   geoData[companyId][country]      the company's product rows there (competitive_geo_product)
   geoPresence[companyId][country]  its presence rows there (competitive_geo_company_presence):
                                    activity, status, overlap_status, matched_ranges, ...
   geoComps                         every company with a presence row

   Overlap is the STORED overlap_status / matched_ranges of the presence row, and the KSSL
   counterpart is the stored competitive_geo_product_match. The keyword-category engine that
   used to guess both from free text is gone: a rival is never declared to contest KSSL here by
   a rule in the browser.
   =================================================================== */

export function createGeo(d) {
  const geoData = d.geoData || {};
  const geoPresence = d.geoPresence || {};
  const geoComps = d.geoComps || [];

  const countriesForComp = (cid) => Object.keys(geoData[cid] || {});
  const compsInCountry = (country) => geoComps.filter((c) => geoData[c.id] && geoData[c.id][country]);
  const productsFor = (cid, country) => (geoData[cid] && geoData[cid][country]) || [];
  const presencesFor = (cid, country) => (geoPresence[cid] && geoPresence[cid][country]) || [];

  return {
    countriesForComp,
    compsInCountry,
    productsFor,
    presencesFor,
  };
}
