/* Tender buckets and days left.

   ONE rule for open / awarded / closed: the stored `status`. "awarded" and "closed" are
   their own tabs; every other stored value (open, closing, ...) is an open tender. The
   closing date never moves a tender between tabs. It only drives the days-left chip,
   which is presentation: whole days from today's local midnight to `closing_date`. */

export function tenderBucket(t) {
  const s = String((t && t.status) || "").trim().toLowerCase();
  return s === "awarded" ? "awarded" : s === "closed" ? "closed" : "open";
}

export function bucketTenders(tenders) {
  const out = { open: [], awarded: [], closed: [] };
  (tenders || []).forEach((t) => out[tenderBucket(t)].push(t));
  return out;
}

/* Whole days from `today` to an ISO "yyyy-mm-dd" closing date; null when there is none.
   Negative once the date has passed. */
export function daysLeft(closingDate, today = new Date()) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(closingDate || ""));
  if (!m) return null;
  const from = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const to = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Math.round((to - from) / 86400000);
}

/* Adds the presentation fields to each served tender; the stored fields (closingDate,
   deadline, status, ...) are left exactly as served.
     bucket      "open" | "awarded" | "closed"  (the rule above)
     dl          days left to closingDate (negative once passed); absent without a date
     statusClass urgency band for the chip: urgent <= 7 days, soon <= 14, else normal
     isLive      bucket === "open", so the shared overview bucketing reads the same rule */
export function wireTendersWithRealDays(tenders, today = new Date()) {
  if (!Array.isArray(tenders)) return [];
  return tenders.map((t) => {
    const bucket = tenderBucket(t);
    const dl = daysLeft(t.closingDate, today);
    const out = { ...t, bucket, isLive: bucket === "open" };
    if (dl !== null) out.dl = dl;
    out.statusClass = bucket !== "open" ? "settled" : dl === null ? "normal" : dl <= 7 ? "urgent" : dl <= 14 ? "soon" : "normal";
    return out;
  });
}
