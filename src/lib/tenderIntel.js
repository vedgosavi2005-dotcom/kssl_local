/* Tender judgements are STORED fields; this module only reads them (ruling R6).

   The fit grade (`clientFit`) comes from the dataset. A field that is absent reads as null, never as a computed
   stand-in. The Top opportunity tables are not built here: they print the stored rank rows (data.topOpportunities). */
const has = (v) => v != null && String(v).trim() !== "";

/* the stored fit word (strong / partial / weak), as it is, or null */
export const fitOf = (t) => (t && has(t.clientFit) ? String(t.clientFit).trim() : t && has(t.fit) ? String(t.fit).trim() : null);
