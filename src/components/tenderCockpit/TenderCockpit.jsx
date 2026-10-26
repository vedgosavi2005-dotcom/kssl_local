import { clientShort } from "../../lib/client.js";
import { useData } from "../../state/DataProvider";
import { useAppState } from "../../state/AppState";
import { cockpitWords } from "../../lib/chrome.js";
import { whereItStands, revenueShort } from "../../lib/tenderIntel.js";
import "../../styles/market-overview.css";
import "../../styles/tender-intel.css";
import { Review } from "../review/Review";

/* Tender Intelligence, at a glance: the platform's own table style (the Market Intelligence .ovt table).
   The three tables print the STORED Top opportunity rows (data.topOpportunities, from serving
   market_top_opportunity_tender / _project / market_next_move), in their stored rank order, with their stored
   text. Nothing is ranked, filtered or derived here; a cell the row leaves empty shows a dash, an empty table says
   so. Every row opens its tender (or project) beside the table. */

const show = (v) => (v == null || String(v).trim() === "" ? "—" : v);
const cls = (v) => String(v || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
/* column widths: every table keeps the same columns in the same place, long text wraps and stops at three lines.
   In PIXELS, not percentages, with a table min-width (tender-intel.css .ti-cockpit): with the drawer open at 1366 px the
   table had ~730 px, so 5% / 9% columns were ~40 px and the headers broke letter by letter ("R/A/N/K", "REVEN/UE") and
   rank 15's revenue was clipped to "Stated". Now each column has room for its one-line header, the table keeps its
   width and the panel scrolls sideways instead (functional test G16, 2026-10-25). On a wide screen fixed layout spreads
   the spare width over the columns in these proportions. */
const COLS7 = ["60px", "260px", "150px", "90px", "180px", "160px", "120px"];
const COLS3 = ["16%", "54%", "30%"];
const Cols = ({ w }) => <colgroup>{w.map((x, i) => <col key={i} style={{ width: x }} />)}</colgroup>;
const clip = (v) => <span className="clamp3" title={v == null ? undefined : String(v)}>{show(v)}</span>;
/* the revenue in its short house form ("CZK 40.5 m" / "₹ 16.1 Cr"), the stored sentence as the tooltip */
const revenueCell = (v) => <span className="clamp3" title={v == null ? undefined : String(v)}>{show(revenueShort(v))}</span>;
const where = (r) => [r.country, r.issuer].filter((v) => v != null && String(v).trim() !== "").join(" · ");

export default function TenderCockpit({ onOpen }) {
  const { data } = useData();
  const { jumpTo } = useAppState();
  const top = (data.topOpportunities && data.topOpportunities.topTenders) || [];
  const projects = (data.topOpportunities && data.topOpportunities.projectsBeforeTender) || [];
  const moves = (data.topOpportunities && data.topOpportunities.nextMoves) || [];
  const tenderOf = (id) => (data.tenders || []).find((t) => String(t.id) === String(id));

  const W = cockpitWords(clientShort());
  // a row opens its tender (or project) beside the table; the Tender Pipeline jump is the fallback
  const openTender = (id, title) => {
    const t = tenderOf(id);
    if (onOpen && t) onOpen(t);
    else jumpTo("market", "tender", { tenderTitle: (t && t.title) || title });
  };
  const openProject = (r) => {
    if (onOpen) onOpen(null, { id: r.id, name: r.title, customer: r.issuer, location: r.country, stageNote: r.stage, sources: r.sources });
  };
  const rowKey = (e, fn) => { if (e.key === "Enter") fn(); };
  const fitCell = (fit) => (fit ? <span className={`ti-fit ${cls(fit)}`}>{fit}</span> : "—");

  return (
    <section className="ti-simple" aria-label="Tender intelligence">
      <div className="ovt">
        <div className="ovc-h">
          <span className="eyebrow">{W.tendersHead}</span>
          <span className="ovc-note">{W.tendersNote}</span>
        </div>
        {top.length ? (
          <div className="ovt-scroll">
            <table className="ovt-fixed ti-cockpit">
              <Cols w={COLS7} />
              <thead>
                <tr>
                  {W.tendersCols.map((h, i) => <th className={i === 0 || i === 6 ? "num" : undefined} key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {top.map((r) => (
                  <tr key={r.id} className="ti-row-link" tabIndex={0} onClick={() => openTender(r.tenderId, r.title)} onKeyDown={(e) => rowKey(e, () => openTender(r.tenderId, r.title))}>
                    <td className="num">{show(r.rank)}</td>
                    <td className="ovt-t">
                      <span className="ti-title" title={r.title}>{show(r.title)}</span>
                      <span className="ovt-buyer" title={r.issuer}>{where(r)}</span>
                      <Review src={r._src} />
                    </td>
                    <td>{clip(r.decides)}</td>
                    <td>{fitCell(r.ksslFit)}</td>
                    <td>{clip(r.ksslModel)}</td>
                    <td>{clip(r.rivalToBeat)}</td>
                    <td className="num">{revenueCell(r.revenue)}</td>
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
          <span className="ovc-note">{W.projectsNote}</span>
        </div>
        {projects.length ? (
          <div className="ovt-scroll">
            <table className="ovt-fixed ti-cockpit">
              <Cols w={COLS7} />
              <thead>
                <tr>
                  {W.projectsCols.map((h, i) => <th className={i === 0 || i === 6 ? "num" : undefined} key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {projects.map((r) => (
                  <tr key={r.id} className="ti-row-link" tabIndex={0} onClick={() => openProject(r)} onKeyDown={(e) => rowKey(e, () => openProject(r))}>
                    <td className="num">{show(r.rank)}</td>
                    <td className="ovt-t">
                      <span className="ti-title" title={r.title}>{show(r.title)}</span>
                      <span className="ovt-buyer" title={r.issuer}>{where(r)}</span>
                      <Review src={r._src} />
                    </td>
                    {/* the stored "approved_funded / ... / ..." read as words: the code's ui.code_label label, then the
                        detail with house-format dates (functional test G16, 2026-10-25) */}
                    {(() => {
                      const w = whereItStands(r.stage, data);
                      return (
                        <td className="ovt-t ti-stage" title={r.stage || undefined}>
                          <span className="ti-title">{show(w.label || w.detail)}</span>
                          {w.label && w.detail ? <span className="ti-stage-sub">{w.detail}</span> : null}
                        </td>
                      );
                    })()}
                    <td>{fitCell(r.ksslFit)}</td>
                    <td>{clip(r.ksslModel)}</td>
                    <td>{clip(r.rivalToBeat)}</td>
                    <td className="num">{revenueCell(r.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-note">{W.projectsEmpty}</div>
        )}
      </div>

      <div className="ovt">
        <div className="ovc-h">
          <span className="eyebrow">{W.movesHead}</span>
          <span className="ovc-note">{W.movesNote}</span>
        </div>
        {moves.length ? (
          <div className="ovt-scroll">
            <table className="ovt-fixed">
              <Cols w={COLS3} />
              <thead>
                <tr>
                  {W.movesCols.map((h, i) => <th className={i === 0 ? "num" : undefined} key={h}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {moves.map((m) => (
                  <tr key={m.id} className="ti-row-link" tabIndex={0} onClick={() => openTender(m.tenderId, m.tenderTitle)} onKeyDown={(e) => rowKey(e, () => openTender(m.tenderId, m.tenderTitle))}>
                    <td className="num">{show(m.due)}</td>
                    <td>{clip(m.action)}</td>
                    <td className="ovt-t"><span className="ti-title" title={m.tenderTitle}>{show(m.tenderTitle)}</span><Review src={m._src} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-note">{W.movesEmpty}</div>
        )}
      </div>
    </section>
  );
}
