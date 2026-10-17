import { useAppState } from "../../state/AppState";
import { railFor } from "../../lib/route";
import { useData } from "../../state/DataProvider";

/* The left rail. One section per pillar in the original markup, shown and hidden;
   here only the active pillar's rail is rendered at all. Counts come from
   navCounts() — every one is computed from the loaded corpus, never hardcoded. */
export default function Sidebar() {
  const { pillar, view, setView } = useAppState();
  const { counts } = useData();
  const items = railFor(pillar);

  const row = (item) => (
    <div
      className={`svc${view === item.view ? " active" : ""}${item.overview ? " nav-overview" : ""}`}
      key={item.view}
      onClick={() => setView(item.view)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setView(item.view);
        }
      }}
    >
      {/* The overview row asked for a grid glyph here; every other row carries its index
          (01, 02, ...). The icon rendered as a small filled box beside the word and is
          off at the operator's request. The span STAYS: it is the 16px column the
          numbered rows align on, and dropping it would pull "Overview" left by the width
          of the icon that is no longer there, out of line with everything under it. */}
      <span className="ix">{item.ix === "grid" ? null : item.ix}</span>
      <span className="nm">{item.label}</span>
      {/* The rail marker is off at the operator's request. The active row already names
          itself with its own highlight (.svc.active in shell.css: filled ground plus the
          left border), so the dot was a second, fainter copy of a state the row shows
          anyway. */}
      <span className="ct">{counts[item.view] ?? "—"}</span>
    </div>
  );

  return (
    <div className="rail">
      <div className="rail-pillar" data-railpillar={pillar}>
        {/* a view the database has switched off is not drawn, so any item may be missing */}
        <div className="rail-sec svc-sec">{items.filter((i) => i.overview).map(row)}</div>
        <div className="rail-sec svc-sec" style={{ borderTop: "none" }}>
          {items.filter((i) => !i.overview).map(row)}
        </div>
      </div>
    </div>
  );
}
