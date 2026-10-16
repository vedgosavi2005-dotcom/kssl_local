import { Fragment, useMemo, useState } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { daysLeft } from "../../lib/tenderCalc";
import { formatDate } from "../../utils/formatDate";
import { Review } from "../../components/review/Review";

const has = (v) => v != null && String(v).trim() !== "";
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
/* The stored fit word is shown as stored; its colour class comes from the known words. */
const fitClass = (v) => {
  const k = String(v || "").trim().toLowerCase();
  return k === "weak" ? "poor" : k;
};

/* "Due": the stored due_text; else a count from the stored due_date. Nothing without either. */
const dueText = (m) => {
  if (has(m.due)) return m.due;
  const n = daysLeft(m.dueDate);
  if (n === null) return "";
  if (n === 0) return "today";
  const d = Math.abs(n);
  return n > 0 ? `in ${d} day${d === 1 ? "" : "s"}` : `${d} day${d === 1 ? "" : "s"} overdue`;
};

export default function TopOpportunity() {
  const { jumpTo } = useAppState();
  const { data } = useData();
  const [openProject, setOpenProject] = useState(null);

  const topOpp = data.topOpportunities || {};
  const topTenders = topOpp.topTenders || [];
  const projectsBeforeTender = topOpp.projectsBeforeTender || [];
  const nextMoves = topOpp.nextMoves || [];
  const notes = topOpp.notes || {};

  const openTender = (tenderId) => {
    if (has(tenderId)) jumpTo("market", "tender", { tenderId });
  };
  const rowKeys = (fn) => (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };

  // Header Report integration for Export / Copy
  const report = useMemo(() => {
    const sections = [];
    if (topTenders.length) {
      sections.push({
        heading: "Top Tenders",
        facts: topTenders.map((t) => [
          `#${t.rank ?? ""} ${t.title}`,
          [t.country, t.issuer, t.revenue && `Revenue: ${t.revenue}`, t.ksslFit && `KSSL Fit: ${t.ksslFit}${t.ksslModel ? ` (${t.ksslModel})` : ""}`]
            .filter(has).join(" · "),
        ]),
      });
    }
    if (projectsBeforeTender.length) {
      sections.push({
        heading: "Projects to Win Before They Tender",
        facts: projectsBeforeTender.map((p) => [
          `#${p.rank ?? ""} ${p.title}`,
          [p.country, p.stage && `Stage: ${p.stage}`, p.revenue && `Revenue: ${p.revenue}`, p.ksslFit && `KSSL Fit: ${p.ksslFit}`]
            .filter(has).join(" · "),
        ]),
      });
    }
    if (nextMoves.length) {
      sections.push({
        heading: "Next Moves",
        facts: nextMoves.map((m) => [dueText(m), [m.action, m.tenderTitle].filter(has).join(" - ")]),
      });
    }
    return {
      title: "Top Opportunity Intelligence",
      subtitle: `${topTenders.length} top tenders · ${projectsBeforeTender.length} pre-tender projects · ${nextMoves.length} next moves`,
      sections,
      payload: { topTenders, projectsBeforeTender, nextMoves },
    };
  }, [topTenders, projectsBeforeTender, nextMoves]);

  useHeaderReport(report);

  const isEmpty =
    topTenders.length === 0 &&
    projectsBeforeTender.length === 0 &&
    nextMoves.length === 0;

  if (isEmpty) {
    return (
      <div className="ti-simple" aria-label="Tender intelligence">
        <div className="empty-note" style={{ padding: "48px 24px", textAlign: "center" }}>
          No top opportunities or tender pipelines are on record.
        </div>
      </div>
    );
  }

  const fitCell = (v) => (has(v) ? <span className={`ti-fit ${fitClass(v)}`}>{cap(v)}</span> : "—");

  return (
    <div className="ti-simple" aria-label="Tender intelligence">
      {/* 1. Top tenders */}
      {topTenders.length > 0 && (
        <div className="ovt">
          <div className="ovc-h">
            <span className="eyebrow">Top tenders</span>
            {has(notes.topTenders) ? <span className="ovc-note">{notes.topTenders}</span> : null}
          </div>
          <div className="ovt-scroll">
            <table>
              <thead>
                <tr>
                  <th className="num">Rank</th>
                  <th>Tender</th>
                  <th>Decides</th>
                  <th>KSSL fit</th>
                  <th>KSSL model</th>
                  <th>Rival to beat</th>
                  <th className="num">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {topTenders.map((t, idx) => (
                  <tr
                    key={t.id || idx}
                    className="ti-row-link"
                    tabIndex={0}
                    onClick={() => openTender(t.tenderId)}
                    onKeyDown={rowKeys(() => openTender(t.tenderId))}
                  >
                    <td className="num">{t.rank ?? "—"}</td>
                    <td className="ovt-t">
                      <span className="ti-title" title={t.title}>
                        {t.title}
                      </span>
                      <span className="ovt-buyer" title={t.issuer}>
                        {[t.country, t.issuer].filter(Boolean).join(" · ")}
                      </span>
                      <Review src={t._src} />
                    </td>
                    <td className="num">{t.decides || "—"}</td>
                    <td>{fitCell(t.ksslFit)}</td>
                    <td>{t.ksslModel || "—"}</td>
                    <td>{t.rivalToBeat || "—"}</td>
                    <td className="num">{t.revenue || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 2. Projects to win before they tender. A row opens the stored opportunity record. */}
      {projectsBeforeTender.length > 0 && (
        <div className="ovt">
          <div className="ovc-h">
            <span className="eyebrow">Projects to win before they tender</span>
            {has(notes.projects) ? <span className="ovc-note">{notes.projects}</span> : null}
          </div>
          <div className="ovt-scroll">
            <table>
              <thead>
                <tr>
                  <th className="num">Rank</th>
                  <th>Project</th>
                  <th>Where it stands</th>
                  <th>KSSL fit</th>
                  <th>KSSL model</th>
                  <th>Rival to beat</th>
                  <th className="num">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {projectsBeforeTender.map((p, idx) => {
                  const isOpen = openProject === p.id;
                  const toggle = () => setOpenProject(isOpen ? null : p.id);
                  const o = p.opportunity;
                  return (
                    <Fragment key={p.id || idx}>
                      <tr
                        className="ti-row-link"
                        tabIndex={0}
                        aria-expanded={isOpen}
                        onClick={toggle}
                        onKeyDown={rowKeys(toggle)}
                      >
                        <td className="num">{p.rank ?? "—"}</td>
                        <td className="ovt-t">
                          <span className="ti-title" title={p.title}>
                            {p.title}
                          </span>
                          <span className="ovt-buyer" title={p.issuer}>
                            {[p.country, p.issuer].filter(Boolean).join(" · ")}
                          </span>
                          <Review src={p._src} />
                        </td>
                        <td className="ovt-t ti-stage">
                          <span className="ti-title" title={p.stage}>
                            {p.stage}
                          </span>
                        </td>
                        <td>{fitCell(p.ksslFit)}</td>
                        <td>{p.ksslModel || "—"}</td>
                        <td>{p.rivalToBeat || "—"}</td>
                        <td className="num">{p.revenue || "—"}</td>
                      </tr>
                      {isOpen ? (
                        <tr>
                          <td colSpan={7} style={{ padding: "12px 16px", background: "var(--d-bg-2)", whiteSpace: "normal" }}>
                            {o ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "12px", lineHeight: 1.5 }}>
                                <Review src={o._src} />
                                {[
                                  ["Kind", o.kind],
                                  ["Description", o.description],
                                  ["Scope", o.scope],
                                  ["Contractor", o.contractor],
                                  ["Location", o.location],
                                  ["Latest milestone", o.milestone],
                                  ["Fit rationale", o.rationale],
                                  ["Rival product", o.rivalProduct],
                                ].filter(([, v]) => has(v)).map(([k, v]) => (
                                  <div key={k}><span className="tpk">{k}</span> {v}</div>
                                ))}
                                {(p.updates || []).map((u, i) => (
                                  <div key={`u${i}`}>
                                    <span className="tpk">{[u.type, u.date && formatDate(u.date)].filter(has).join(" · ")}</span>{" "}
                                    {[u.headline, u.narrative].filter(has).join(" - ")}
                                  </div>
                                ))}
                                {(p.sources || []).filter((s) => has(s.url)).map((s, i) => (
                                  <div key={`s${i}`}>
                                    <a href={s.url} rel="noopener noreferrer" target="_blank">↗ {s.label || s.url}</a>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <span className="ovt-none">No opportunity record on file for this project</span>
                            )}
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 3. Next moves */}
      {nextMoves.length > 0 && (
        <div className="ovt">
          <div className="ovc-h">
            <span className="eyebrow">Next moves</span>
            {has(notes.nextMoves) ? <span className="ovc-note">{notes.nextMoves}</span> : null}
          </div>
          <div className="ovt-scroll">
            <table>
              <thead>
                <tr>
                  <th className="num">Due</th>
                  <th>Action</th>
                  <th>Tender</th>
                </tr>
              </thead>
              <tbody>
                {nextMoves.map((m, idx) => {
                  const go = has(m.tenderId) ? () => openTender(m.tenderId) : undefined;
                  return (
                    <tr
                      key={m.id || idx}
                      className={go ? "ti-row-link" : undefined}
                      tabIndex={go ? 0 : undefined}
                      onClick={go}
                      onKeyDown={go ? rowKeys(go) : undefined}
                    >
                      <td className="num">{dueText(m) || "—"}</td>
                      <td>
                        {m.action}
                        <Review src={m._src} />
                      </td>
                      <td className="ovt-t">
                        <span className="ti-title" title={m.tenderTitle}>
                          {m.tenderTitle}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
