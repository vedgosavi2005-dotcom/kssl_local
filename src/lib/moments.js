/* competitorNews carries two kinds of row: plain news, and competitor MOMENTS (rows that carry a stored `level`;
   ruling R4). The Competitor Moment page and its rail count list moments only. */
export const isMoment = (m) => !!m && m.level != null && String(m.level).trim() !== "";
export const momentsOf = (list) => (Array.isArray(list) ? list.filter(isMoment) : []);
