import { useMemo } from "react";
import { useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { globalRequirements } from "../../lib/globalRequirements";
import { navTitle } from "../../lib/route";

/* Global Requirements: the worldwide demand, capacity and supply signals (lib/globalRequirements), shown in the
   Overview's own feed -- numbered rows, Search and Sequence, the white detail panel on a click. Layout mounts
   that feed and hands it in; this page adds the header report. */
export default function GlobalRequirement({ feed }) {
  const { data } = useData();
  const rows = useMemo(() => globalRequirements(data), [data]);
  const report = useMemo(() => ({
    title: navTitle("market", "global-requirement"),
    subtitle: rows.length ? `${rows.length} worldwide signals` : "No requirements on record",
    sections: rows.map((r) => ({ heading: r.title, body: r.why })),
    payload: { requirements: rows },
  }), [rows]);
  useHeaderReport(report);

  if (!rows.length)
    return <div style={{ flex: 1, padding: "48px 24px", color: "var(--d-txt-3)", fontFamily: "var(--mono)", fontSize: "12px", textAlign: "center" }}>No global requirements data on record.</div>;
  return feed || null;
}
