import { WINDOW_DAYS } from "../../lib/marketOutlook";
import { formatTotals } from "../../lib/tenderValue";
import { formatDate } from "../../utils/formatDate";
import "../../styles/market-overview.css";
import "../../styles/tender-intel.css";
import { Review } from "../review/Review";

/* Market outlook: five tables, each headed with the records it was counted from (lib/marketOutlook), so a reader
   can see what a number rests on. The page passes the computed outlook (open tenders from its own bucketTenders split). */

const fmtDate = (d) => (d ? formatDate(d.toISOString().slice(0, 10)) : "—");
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

/* a stored code ("need_stated", "approved_funded") read as words ("Need stated") */
const codeWord = (v) => {
  const w = String(v || "").replace(/_/g, " ").trim();
  return w ? w.charAt(0).toUpperCase() + w.slice(1) : "";
};

/* `cols`: the column widths, so every table lines up the same way whatever its text (fixed layout, text wraps) */
function Block({ title, note, empty, rows, head, cols, children, className = "" }) {
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
    </section>
  );
}

export default function MarketOutlook({ data, o }) {
  const win = o.winners;
  const seg = o.segments;
  const bu = o.buyers;
  const dr = o.drivers;

  return (
    <div className="ti-simple">
      <Block
        empty="no segment has dated records in the last 12 months"
        head={[["Segment"], ["Activity, last 6 months", true], ["Open tenders that fit", true], ["Who wins here"], ["What to do"], ["Latest signal"]]}
        cols={["13%", "13%", "17%", "20%", "12%", "25%"]}
        note="activity counts new tenders, market news and contract awards, over the last 6 months against the 6 months before"
        rows={seg}
        title="Activity by segment"
        className="ovt-demand"
      >
        {seg.map((r) => (
          <tr key={r.segment}>
            <td className="ovt-t">{r.segment}</td>
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
                  <span className="od-sub">{r.winnerWins} of {r.named} award{r.named === 1 ? "" : "s"}</span>
                </>
              ) : (
                <span className="od-none">No past award on record</span>
              )}
            </td>
            <td>{r.recommendation ? <span className="od-main clamp3" title={r.recommendation}>{r.recommendation}</span> : "—"}<Review src={r.assessmentSrc} /></td>
            <td>
              {r.latest ? (
                <>
                  <span className="od-main od-clip" title={r.latest.title}>{r.latest.title}</span>
                  <span className="od-sub">{[codeWord(r.latest.kind), r.latest.country, r.latest.date ? fmtDate(r.latest.date) : null].filter(Boolean).join(" · ")}</span>
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
        head={[["Winner"], ["Brand"], ["Wins", true], ["Value", true], ["Buyers", true]]}
        cols={["44%", "16%", "10%", "20%", "10%"]}
        note={`who wins the contracts · ${win.named} awards with a named winner, valued ${formatTotals(win.totals)}`}
        rows={win.rows}
        title="Who wins"
      >
        {win.rows.slice(0, 10).map((r) => (
          <tr key={r.winner}>
            <td className="ovt-t"><span className="clamp3" title={r.winner}>{r.winner}</span></td>
            <td>{r.brand || "—"}</td>
            <td className="num">{r.wins}</td>
            <td className="num">{formatTotals(r.totals)}</td>
            <td className="num">{r.buyers.length}</td>
          </tr>
        ))}
      </Block>

      <Block
        empty="no buyer has two or more tenders or awards"
        head={[["Buyer"], ["Tenders and awards", true], ["Value", true], ["Last", true]]}
        cols={["46%", "18%", "20%", "16%"]}
        note="buyers with two or more tenders or awards"
        rows={bu}
        title="Repeat buyers"
      >
        {bu.slice(0, 10).map((r) => (
          <tr key={r.buyer}>
            <td className="ovt-t">
              {r.buyer}
              <span className="ovt-buyer">{r.segments.join(" · ")}</span>
            </td>
            <td className="num">{r.count}<span className="ovt-buyer">{r.tenders} tender{r.tenders === 1 ? "" : "s"} · {r.awards} award{r.awards === 1 ? "" : "s"}</span></td>
            <td className="num">{formatTotals(r.totals)}</td>
            <td className="num">{fmtDate(r.last)}</td>
          </tr>
        ))}
      </Block>

      <Block
        empty="no market signal names a location and a segment"
        head={[["Location · segment"], ["Signals", true], ["Tenders", true], ["Value", true], ["Latest signal"]]}
        cols={["24%", "9%", "9%", "18%", "40%"]}
        note="the news and pipeline signals behind each segment, beside the tenders in the same place"
        rows={dr}
        title="What is driving it"
      >
        {dr.slice(0, 10).map((r) => (
          <tr key={`${r.country}${r.segment}`}>
            <td className="ovt-t">{r.country} · {r.segment}</td>
            <td className="num">{r.signals.length}</td>
            <td className="num">{r.tenders}</td>
            <td className="num">{formatTotals(r.totals)}</td>
            <td>
              <span className="ti-title" title={r.signals[0].title}>{r.signals[0].title}</span>
              {r.signals[0].date ? <span className="ovt-buyer">{codeWord(r.signals[0].kind)} · {fmtDate(r.signals[0].date)}</span> : null}
            </td>
          </tr>
        ))}
      </Block>
    </div>
  );
}
