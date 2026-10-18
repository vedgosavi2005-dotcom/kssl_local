/* GLOBAL REQUIREMENTS: the stored requirement rows of the market, as the dataset serves them.

   data.globalRequirements holds one row per stored requirement (serving.market_global_requirement). Each has a card
   in the market feed, whose id is the stored id behind the `req-` prefix the dataset gives requirement cards, so
   the prefixed id is the one every cross-link uses. Nothing is added here: `what` is the stored description, `why`
   the stored strategic assessment, the link and sources the stored ones. Rows keep their stored order. */
export const requirementCardId = (r) => `req-${r.id}`;

/* the predicate for the market feed: keep only the cards of stored requirement rows */
export function globalCardFilter(d) {
  const ids = new Set(((d && d.globalRequirements) || []).map(requirementCardId));
  return (c) => !!c && ids.has(c.id);
}

export function globalRequirements(d) {
  const det = (d && d.details) || {};
  const cards = new Map(((d && d.marketCards) || []).map((c) => [c.id, c]));
  return ((d && d.globalRequirements) || []).map((r) => {
    const id = requirementCardId(r);
    const c = cards.get(id) || {};
    const x = det[id] || {};
    const sources = Array.isArray(r.sources) ? r.sources : [];
    return {
      id, title: c.title || r.title || "", category: r.cat || "", segment: r.region || "", date: r.deadline || "",
      what: x.what || r.desc || "", why: x.why || r.strategicAssessment || "",
      url: x.url || (sources[0] && sources[0].url) || "", sources: x.srcs || sources,
    };
  });
}
