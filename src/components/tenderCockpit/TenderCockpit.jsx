import { useMemo } from "react";
import { clientShort } from "../../lib/client.js";
import { useData } from "../../state/DataProvider";
import { useAppState } from "../../state/AppState";
import { topTenders, topProjects, nextMoves } from "../../lib/tenderIntel.js";
import { bucketTenders } from "../../lib/overview.js";
import { cockpitWords } from "../../lib/chrome.js";
import "../../styles/market-overview.css";
import "../../styles/tender-intel.css";
import { Review } from "../review/Review";

/* Tender Intelligence, at a glance: the platform's own table style (the Market Intelligence .ovt table).
   Both tables are built here in the browser from the STORED tender and project fields (lib/tenderIntel.js):
   which rows, their order, the fit word, the model, the rival and the revenue are stored values, ordered by
   deterministic rules and nothing else; nothing is weighted or estimated. A cell the record leaves empty shows a
   dash. Every row opens its detail beside the table. */

const show = (v) => (v == null || String(v).trim() === "" ? "—" : v);
const cls = (v) => String(v || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
const dueWord = (days) => (days === 0 ? "today" : `in ${days} day${days === 1 ? "" : "s"}`);

export default function TenderCockpit({ onOpen }) {
  const { data } = useData();
  const { jumpTo } = useAppState();
  const today = useMemo(() => new Date(), []);
  const open = useMemo(() => bucketTenders(data.tenders).open, [data.tenders]);
  const top = useMemo(() => topTenders(open), [open]);
  const projects = useMemo(() => topProjects(data.projects), [data.projects]);
  const moves = useMemo(() => nextMoves(open, today), [open, today]);

  const client = clientShort();
  const W = cockpitWords(client);
  const est = (rows) => (rows.some((r) => r.estimate) ? ` · ${W.estimateNote}` : "");
  // a row opens its tender (or project) beside the table; the Tender Pipeline jump is the fallback
  const openTender = (t) => {
    if (onOpen) onOpen(t);
    else jumpTo("market", "tender", { tenderTitle: t.title });
  };
  const openProject = (row) => { if (onOpen) onOpen(null, row.p); };
  const rowKey = (e, fn) => { if (e.key === "Enter") fn(); };
  const fitCell = (row) => (row.fit ? <span className={`ti-fit ${cls(row.fit)}`}>{row.fit}</span> : "—");

  return (
    <section className="ti-simple" aria-label="Tender intelligence">
      <div className="ovt">
        <div className="ovc-h">
          <span className="eyebrow">{W.tendersHead}</span>
          <span className="ovc-note">{W.tendersNote}{est(top)}</span>
        </div>
        {top.length ? (
          <div className="ovt-scroll">
            <table>
              <thead>
                <tr>
                  {W.tendersCols.map((h, i) => <th className={i === 0 || i === 6 ? "num" : undefined} key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {top.map((r, i) => (
                  <tr key={r.id} className="ti-row-link" tabIndex={0} onClick={() => openTender(r.t)} onKeyDown={(e) => rowKey(e, () => openTender(r.t))}>
                    <td className="num">{i + 1}</td>
                    <td className="ovt-t">
                      <span className="ti-title" title={r.title}>{show(r.title)}</span>
                      <span className="ovt-buyer" title={r.issuer}>{r.where}</span>
                      <Review src={r._src} />
                    </td>
                    <td className="num">{show(r.decides)}</td>
                    <td>{fitCell(r)}</td>
                    <td>{show(r.model)}</td>
                    <td>{show(r.rival)}</td>
                    <td className="num">{show(r.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-note">{W.tendersEmpty}</div>
        )}
      </div>

      <div className="ovt">
        <div className="ovc-h">
          <span className="eyebrow">{W.projectsHead}</span>
          <span className="ovc-note">{W.projectsNote}{est(projects)}</span>
        </div>
        {projects.length ? (
          <div className="ovt-scroll">
            <table>
              <thead>
                <tr>
                  {W.projectsCols.map((h, i) => <th className={i === 0 || i === 6 ? "num" : undefined} key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {projects.map((r, i) => (
                  <tr key={r.id} className="ti-row-link" tabIndex={0} onClick={() => openProject(r)} onKeyDown={(e) => rowKey(e, () => openProject(r))}>
                    <td className="num">{i + 1}</td>
                    <td className="ovt-t">
                      <span className="ti-title" title={r.title}>{show(r.title)}</span>
                      <span className="ovt-buyer" title={r.issuer}>{r.where}</span>
                      <Review src={r._src} />
                    </td>
                    <td className="ovt-t ti-stage">
                      <span className="ti-title" title={r.stage}>{show(r.stage)}</span>
                    </td>
                    <td>{fitCell(r)}</td>
                    <td>{show(r.model)}</td>
                    <td>{show(r.rival)}</td>
                    <td className="num">{show(r.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-note">{W.projectsEmpty}</div>
        )}
      </div>

      {moves.length ? (
        <div className="ovt">
          <div className="ovc-h">
            <span className="eyebrow">{W.movesHead}</span>
            <span className="ovc-note">{W.movesNote}</span>
          </div>
          <div className="ovt-scroll">
            <table>
              <thead>
                <tr>
                  {W.movesCols.map((h, i) => <th className={i === 0 ? "num" : undefined} key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {moves.map((m) => (
                  <tr key={m.id} className="ti-row-link" tabIndex={0} onClick={() => openTender(m.t)} onKeyDown={(e) => rowKey(e, () => openTender(m.t))}>
                    <td className="num">{dueWord(m.days)}</td>
                    <td>{show(m.action)}</td>
                    <td className="ovt-t"><span className="ti-title" title={m.t.title}>{show(m.t.title)}</span><Review src={m._src} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
