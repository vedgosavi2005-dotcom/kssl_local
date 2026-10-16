/* Company names are data: competitive_competitor.display_name / short_name / legal_name,
   served as `name` / `short` / `legal` on data.competitors[cid]. This file used to hold a
   hand-typed table of full names and notes for ~45 companies; it is gone. What stays is
   the one helper other views import. */

/* A company label as stored (entities decoded). No abbreviation is guessed from letters. */
export const companyShort = (name) => String(name == null ? "" : name).replace(/&amp;/g, "&").trim();
