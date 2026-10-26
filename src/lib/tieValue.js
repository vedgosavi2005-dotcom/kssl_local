/* Two small reads of a stored partnership tie, for the tie detail on the Partnership page
 * (functional test G14, 2026-10-25).
 */

/* "WHAT EACH SIDE GETS". The partnership prompt stores value_to_competitor /
   value_to_partner as "tag: one line" -- "market_access: a UAV assembly workshop..." --
   and the drawer printed the tag as written on 758 values. The tag becomes plain words;
   "other" says nothing a reader can use, so it is dropped. A value that is only "not
   stated" (with or without a tag, 69 of them) is no value and returns null. */
const TAG_WORDS = {
  market_access: "Market access",
  technology: "Technology",
  capacity: "Capacity",
  financing: "Financing",
  offsets: "Offsets",
  credibility: "Credibility",
  other: "",
};

export function tieValueParts(v) {
  const s = String(v == null ? "" : v).trim();
  if (!s) return null;
  const m = /^([a-z][a-z_]*)\s*:\s*([\s\S]*)$/.exec(s);
  const tagKey = m ? m[1] : null;
  const text = (m ? m[2] : s).trim();
  if (!text || /^(not stated|none stated|unknown|n\/a)\.?$/i.test(text)) return null;
  let tag = null;
  if (tagKey) {
    tag = tagKey in TAG_WORDS ? TAG_WORDS[tagKey] : tagKey.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }
  return { tag: tag || null, text };
}

/* "SINCE" AND THE TIMELINE MUST NOT DISAGREE. `date` on a tie is the date of the record
   the prompt read last-and-best, while `steps` are every dated piece of evidence; on 122
   of 160 multi-step ties the first step is EARLIER than `date` (NORINCO - Heavy
   Industries Taxila: since 2024-03-11, first step 2023-12-22). "Since" claims when the
   tie began, so it takes the earliest date either source states -- the first step when it
   is earlier, the stored date when a step is missing or later. ISO strings ("YYYY",
   "YYYY-MM", "YYYY-MM-DD") order correctly as text. */
export function tieSince(r) {
  const dates = [r && r.date, ...((r && Array.isArray(r.steps) ? r.steps : []).map((t) => t && t.date))]
    .filter((d) => typeof d === "string" && /^\d{4}(-\d{2}){0,2}/.test(d.trim()))
    .map((d) => d.trim());
  if (!dates.length) return (r && r.date) || null;
  return dates.sort()[0];
}
