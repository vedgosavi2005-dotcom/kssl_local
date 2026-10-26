import { useMemo, useState } from "react";
import { WINDOW_DAYS } from "../../lib/marketOutlook";
import { segmentDetail, winnerDetail, calibreDetail, buyerDetail, driverDetail } from "../../lib/outlookDetail";
import { formatTotals } from "../../lib/tenderValue";
import { formatDate } from "../../utils/formatDate";
import OutlookPanel from "./OutlookPanel";
import "../../styles/market-overview.css";
import "../../styles/tender-intel.css";
import { Review } from "../review/Review";
import { SourceChip } from "../sourceLink/SourceLink";
import { hostOf } from "../../lib/marketOverview";

// the article a signal came from, as a link to it (owner 22 Oct: "add the latest signal's source")
const SignalSource = ({ url }) => (url ? <span className="od-sub">Source: <SourceChip url={url} source={hostOf(url) || "article"} /></span> : null);

/* Market outlook: five tables, each headed with the records it was counted from (lib/marketOutlook), so a reader can
   see what a number rests on. A row opens the analytics panel on the right (OutlookPanel, lib/outlookDetail), as in
   the Cummins Market outlook. The page passes the computed outlook (open tenders from its own bucketTenders split). */

const fmtDate = (d) => (d ? formatDate(d.toISOString().slice(0, 10)) : "—");
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const pct = (x) => `${Math.round(x * 100)}%`;

/* a stored code ("need_stated", "approved_funded") read as words ("Need stated") */
const codeWord = (v) => {
  const w = String(v || "").replace(/_/g, " ").trim();
  return w ? w.charAt(0).toUpperCase() + w.slice(1) : "";
};

/* `cols`: the column widths, so every table lines up the same way whatever its text (fixed layout, text wraps) */
function Block({ title, note, source, empty, rows, head, cols, children, className = "" }) {
  return (
    <section className={`ovt ${className}`.trim()}>
      <div className="ovc-h">
        <span className="eyebrow">{title}</span>
        <span className="ovc-note">{note}</span>
      </div>
      {rows.length ? (
        <div className="ovt-scroll">
          <table className={cols ? "ovt-fixed" : undefined}>
            {cols ? <colgroup>{cols.map((w, i) => <col key={i} style={{ width: w }} />)}</colgroup> : null}
            <thead>
              <tr>{head.map(([h, num]) => <th className={num ? "num" : undefined} key={h}>{h}</th>)}</tr>
            </thead>
            <tbody>{children}</tbody>
          </table>
        </div>
      ) : (
        <div className="ovc-empty">{empty}</div>
      )}
      {source ? <div className="ovc-note ovt-data">Data: {source}</div> : null}
    </section>
  );
}

export default function MarketOutlook({ data, o, onSegment }) {
  const client = (data.client && (data.client.short || data.client.name)) || "the client";
  const win = o.winners;
  const seg = o.segments;
  const cal = o.calibres;
  const bu = o.buyers;
  const dr = o.drivers;
  const dated = seg.reduce((n, r) => n + r.recent + r.before, 0);
  /* one selected row opens the analytics panel on the right: { t: segment|winner|calibre|buyer|driver, k: key } */
  const [sel, setSel] = useState(null);
  const today = useMemo(() => new Date(), []);
  const detail = useMemo(() => {
    if (!sel) return null;
    if (sel.t === "segment") return segmentDetail(data, sel.k, seg.find((r) => r.segment === sel.k), today);
    if (sel.t === "winner") return winnerDetail(data, sel.k, win.rows.find((r) => r.winner === sel.k), today);
    if (sel.t === "calibre") return calibreDetail(data, cal.rows.find((r) => r.key === sel.k), cal, today);
    if (sel.t === "buyer") return buyerDetail(data, sel.k, bu.find((r) => r.buyer === sel.k), today);
    const [c, sg] = sel.k.split("||");
    return driverDetail(data, c, sg, dr.find((r) => r.country === c && r.segment === sg), today);
  }, [sel, data, seg, win, cal, bu, dr, today]);
  const pick = (t, k) => ({
    className: `ti-row-link${sel && sel.t === t && sel.k === k ? " on" : ""}`, tabIndex: 0,
    onClick: () => setSel({ t, k }), onKeyDown: (e) => { if (e.key === "Enter") setSel({ t, k }); },
  });
  const stop = (e) => e.stopPropagation();

  return (
    <div className={`ol-split${detail ? " has-panel" : ""}`}>
    <div className="ti-simple">
      <Block
        empty="no segment has dated records in the last 12 months"
        head={[["Segment"], ["Activity, last 6 months", true], ["Open tenders that fit", true], ["Who wins here"], ["What to do"], ["Latest signal"]]}
        cols={["13%", "13%", "17%", "19%", "13%", "25%"]}
        note="activity counts new tenders, market news and contract awards, over the last 6 months against the 6 months before · pick a row for its analysis"
        rows={seg}
        source={`${plural(dated, "dated record")} in the two ${Math.round(WINDOW_DAYS / 30.5)}-month windows (tenders by published or closing date, market signals by their date, awards with a date; year-only awards are not counted as activity). The change is the signed difference between the two windows, and none is called when the earlier window is empty. Open tenders that fit are open for bids with a strong or partial ${client} fit; projects are the stored projects to win before they tender; "closed, awaiting award" counts tenders past their closing date with no award yet. Who wins here is ranked by award value in rupees at stored rates, then by count. What to do is the stored assessment.`}
        title="Where demand is heading"
        className="ovt-demand"
      >
        {seg.map((r) => (
          <tr key={r.segment} {...pick("segment", r.segment)}>
            <td className="ovt-t">
              {r.segment}
              {onSegment ? (
                <button className="od-seg-link" onClick={(e) => { stop(e); onSegment(r.segment); }} title={`Open all ${r.segment} tenders`} type="button">
                  tenders <span aria-hidden="true">→</span>
                </button>
              ) : null}
            </td>
            <td className="od-act">
              <span className="od-big">{r.recent}</span>
              {r.change != null ? (
                <span className={`od-trend ${r.change > 0 ? "up" : r.change < 0 ? "down" : ""}`}>
                  {r.change > 0 ? "▲" : r.change < 0 ? "▼" : "•"} {r.change ? `${Math.abs(r.change)}%` : "level"}
                </span>
              ) : (
                <span className="od-trend">no change called</span>
              )}
              <span className="od-sub">{r.before} in the prior 6 months</span>
            </td>
            <td>
              {r.open ? (
                <>
                  <span className="od-main">{plural(r.open, "tender")}</span>
                  <span className="od-sub">{formatTotals(r.totals)} stated value</span>
                </>
              ) : (
                <span className="od-none">None open</span>
              )}
              {r.projects ? <span className="od-sub">{plural(r.projects, "project")} to win fit</span> : null}
              {r.pending.n ? (
                <span className="od-sub od-pend" title={r.pending.titles.join("\n")}>
                  + {r.pending.n} closed, awaiting award{r.pending.totals.length ? ` (${formatTotals(r.pending.totals)})` : ""}
                </span>
              ) : null}
            </td>
            <td>
              {r.winner ? (
                <>
                  <span className="od-main clamp3" title={r.winner}>{r.winner}</span>
                  <span className="od-sub">{r.winnerShare != null ? `${pct(r.winnerShare)} of value · ` : ""}{r.winnerWins} of {r.named} award{r.named === 1 ? "" : "s"}</span>
                </>
              ) : (
                <span className="od-none">No past award on record</span>
              )}
            </td>
            <td onClick={stop}>{r.recommendation ? <span className="od-main clamp3" title={r.recommendation}>{r.recommendation}</span> : "—"}<Review src={r.assessmentSrc} /></td>
            <td>
              {r.latest ? (
                <>
                  <span className="od-main od-clip" title={r.latest.title}>{r.latest.title}</span>
                  <span className="od-sub">{[codeWord(r.latest.kind), r.latest.country, r.latest.date ? fmtDate(r.latest.date) : null].filter(Boolean).join(" · ")}</span>
                  <span onClick={stop}><SignalSource url={r.latest.url} /></span>
                </>
              ) : (
                <span className="od-none">No signal on record</span>
              )}
            </td>
          </tr>
        ))}
      </Block>

      <Block
        empty="no past award with a named winner"
        head={[["Winner"], ["Brand"], ["Wins", true], ["Contract value", true], ["Share of value", true], ["Buyers", true]]}
        cols={["38%", "14%", "8%", "18%", "12%", "10%"]}
        note={`rival contracts · ${win.named} awards with a named winner · ${formatTotals(win.totals)} stated contract value; not company revenue`}
        rows={win.rows}
        source={`${win.priced} of ${win.named} awards with a named winner state a value. ${client}'s own awards are not counted. Shares are of the stated values counted in rupees at stored exchange rates; an amount in a currency with no stored rate is left out of the share, and an unstated value stays unknown. Top 10 of ${win.rows.length} winners shown, ranked by value, then by number of wins.`}
        title="Who wins"
      >
        {win.rows.slice(0, 10).map((r) => (
          <tr key={r.winner} {...pick("winner", r.winner)}>
            <td className="ovt-t"><span className="clamp3" title={r.winner}>{r.winner}</span></td>
            <td>{r.brand || "—"}</td>
            <td className="num">{r.wins}</td>
            <td className="num">{r.totals.length ? formatTotals(r.totals) : "Not stated"}</td>
            <td className="num">{r.share != null ? pct(r.share) : "—"}</td>
            <td className="num">{r.buyers.length}</td>
          </tr>
        ))}
      </Block>

      {cal.rows.length ? (
        <Block
          empty="no open tender names a calibre"
          head={[["Calibre · category"], ["Open tenders", true], ["Stated value", true], [`${client} covers it`]]}
          cols={["24%", "18%", "18%", "40%"]}
          note={`the calibres buyers ask for, against the ${client} catalogue · a gap is a calibre with tenders and no ${client} model`}
          rows={cal.rows}
          source={`${cal.read} of ${cal.ranked} open tenders and projects state a calibre in millimetres in their title or equipment scope ("7.62 x 51 mm" reads 7.62 mm); a figure counts as a calibre only when some catalogue product states it as its calibre, and calibres stated only in inches are not read. Covered means a ${client} product whose stored Calibre spec names the same figure, or a range holding it, in the same category. Pick a row for its tenders, awards and models.`}
          title="Calibres buyers need"
        >
          {cal.rows.map((r) => (
            <tr key={r.key} {...pick("calibre", r.key)}>
              <td className="ovt-t">{r.key}</td>
              <td className="num">{plural(r.tenders, "open tender")}<span className="ovt-buyer">{plural(r.projects, "project lead")}</span></td>
              <td className="num">{formatTotals(r.totals)}</td>
              <td>{r.covered ? <span className="clamp3" title={r.models.join(", ")}>{r.models.join(", ")}</span> : <span className="ti-fit weak">Gap</span>}</td>
            </tr>
          ))}
        </Block>
      ) : null}

      <Block
        empty="no buyer has two or more tenders or awards"
        head={[["Buyer"], ["Tenders and awards", true], ["Value / basis", true], ["Last dated record", true], ["Next known deadline", true]]}
        cols={["36%", "16%", "20%", "14%", "14%"]}
        note="buyers with two or more tenders or awards · pick a row for its record"
        rows={bu}
        source={`${bu.length} buyers. Award value sums the stated values of its awards, not buyer spend; open-tender value is what the open notices state and is not added to awards. The next known deadline is the stored closing date of an open tender; no next round is forecast. Top 10 shown.`}
        title="Repeat buyers"
      >
        {bu.slice(0, 10).map((r) => (
          <tr key={r.buyer} {...pick("buyer", r.buyer)}>
            <td className="ovt-t">
              {r.buyer}
              <span className="ovt-buyer">{r.segments.join(" · ")}</span>
            </td>
            <td className="num">{r.count}<span className="ovt-buyer">{r.openN} open · {plural(r.tenders, "tender")} · {plural(r.awards, "award")}</span></td>
            <td className="num">
              {r.awardTotals.length ? <>{formatTotals(r.awardTotals)}<span className="ovt-buyer">Stated awards · {r.pricedAwards} priced</span></> : <span className="ovt-buyer">Award value not stated</span>}
              {r.openTotals.length ? <span className="ovt-buyer">{formatTotals(r.openTotals)} open tenders</span> : null}
            </td>
            <td className="num">{r.last ? fmtDate(r.last) : "Date not published"}</td>
            <td className="num">{r.nextDeadline ? <>{fmtDate(r.nextDeadline)}<span className="ovt-buyer">Bid deadline</span></> : "No open deadline"}</td>
          </tr>
        ))}
      </Block>

      <Block
        empty="no market signal names a location and a segment"
        head={[["Location · segment"], ["Signals", true], ["Open tenders / projects", true], ["Stated value", true], ["Latest signal"]]}
        cols={["24%", "9%", "15%", "14%", "38%"]}
        note="the news and pipeline signals behind each segment, beside the tenders and projects in the same place"
        rows={dr}
        source={`market signals that name a location and a segment (${dr.reduce((n, r) => n + r.signals.length, 0)} signals in ${dr.length} location and segment pairs). A tender or project is in the same place when its country is one of the parts of the signal's location. Values are what the open notices state. Top 10 shown.`}
        title="What is driving it"
      >
        {dr.slice(0, 10).map((r) => (
          <tr key={`${r.country}${r.segment}`} {...pick("driver", `${r.country}||${r.segment}`)}>
            <td className="ovt-t">{r.country} · {r.segment}</td>
            <td className="num">{r.signals.length}</td>
            <td className="num">{plural(r.openN, "open tender")}<span className="ovt-buyer">{plural(r.projects, "project lead")}</span></td>
            <td className="num">{formatTotals(r.totals)}</td>
            <td>
              <span className="ti-title" title={r.signals[0].title}>{r.signals[0].title}</span>
              {r.signals[0].date ? <span className="ovt-buyer">{codeWord(r.signals[0].kind)} · {fmtDate(r.signals[0].date)}</span> : null}
              <span onClick={stop}><SignalSource url={r.signals[0].url} /></span>
            </td>
          </tr>
        ))}
      </Block>
    </div>
    <OutlookPanel detail={detail} onClose={() => setSel(null)} />
    </div>
  );
}
