/* WHAT THE MAP SAYS ABOUT ONE COUNTRY -- as data, so it can be tested without Leaflet.

   Every word is a stored value: the location's kssl_presence_summary (shown verbatim by the
   map), and each company's activity_type values. Nothing is asserted from a missing row --
   an "absent" or "contested" verdict used to be derived here from the lack of a client row,
   which is an absent input printed as a finding.

   Activity vocabulary (documented for the prompts): free text such as "Local production",
   "Licensed production", "Export", "Sales and service". It is shown as stored; the short
   codes lp / pt / ex / sv only pick a dot colour (see activityClass). */

/** The distinct non-empty values, in first-seen order. */
export const distinct = (values) => {
  const seen = new Set();
  const out = [];
  (values || []).forEach((v) => {
    const t = String(v == null ? "" : v).trim();
    const k = t.toLowerCase();
    if (!t || seen.has(k)) return;
    seen.add(k);
    out.push(t);
  });
  return out;
};

/** The activity labels one company shows in one country: its presence activity and its
    product rows' own activities. */
export function activityLabels({ presences, rows }) {
  return distinct([...(presences || []).map((p) => p.activity), ...(rows || []).map((r) => r.c)]);
}

/** WHAT ONE COMPANY DOES IN ONE COUNTRY, for the tooltip's company list. `isHq` is decided by
    lib/geoCountries.isHeadOffice from the stated origin column. An empty string is a real
    answer: nothing is recorded. */
export function companyRole({ presences, rows, isHq }) {
  const parts = activityLabels({ presences, rows });
  return (isHq ? ["Head office", ...parts] : parts).join(" · ");
}

/** The dot colour class for an activity: the short codes only, anything else is neutral. */
export const activityClass = (activity) => {
  const k = String(activity == null ? "" : activity).toLowerCase();
  return ["lp", "pt", "ex", "sv", "bf"].includes(k) ? k : "sv";
};
