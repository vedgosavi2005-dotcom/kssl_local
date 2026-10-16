import { useEffect, useRef } from "react";
import { tenderFactRows, NOT_ON_RECORD } from "../../lib/tenderRow";
import { srcChips, attr, escRich } from "../../lib/html";
import { DIR_WORD } from "../../lib/overview";
import { useData } from "../../state/DataProvider";
import Thumb from "../thumb/Thumb.jsx";
import { Review } from "../review/Review";

/* `badge` (optional): the ROW's own label for this signal, { word, cls }. A pillar that
   labels its rows by kind rather than by stance (Technology: ADOPTABLE, or nothing for a
   competitor advance) passes it so the panel says what the row says -- not "Watch". An
   empty word draws no pill. Without it, the stance pill as before. */
export default function DetailPanel({ detail, onClose, badge }) {
  const { data } = useData();
  const panelRef = useRef(null);

  useEffect(() => {
    if (panelRef.current) {
      panelRef.current.scrollTop = 0;
    }
  }, [detail]);

  if (!detail) return null;
  /* The stance is the stored classification: the row's own badge when the feed passes one,
     else the detail's stored `dir`. An unknown code has no colour class and no pill word. */
  const dir = badge ? badge.cls || "none" : detail.dir || "none";
  /* A TENDER IS NOT AN ARTICLE, AND detail.kind NEVER SAID SO.
     Market's overview opens on "Live Opportunities" -- 126 tender cards. A tender has
     no document body, which is why the summary backfill selects `id LIKE 'pl\_%'` and
     skips them: there is nothing to summarise. So the article block below renders
     nothing for any of them, and on 22 of the 126 `what` is an empty string as well,
     which left the panel showing no prose at all.
     `detail.kind` cannot detect this. It is NULL on every served row in every lane, so
     this branch has never once been true and the tender path was dead code. The id
     prefix is what the writer actually sets. */
  const tenderId = /^tender_/.test(String(detail.id || ""))
    ? String(detail.id).replace(/^tender_/, "")
    : null;
  const tenderRec = tenderId
    ? (data.tenders || []).find((t) => String(t.id) === tenderId) || null
    : null;
  const isTender = detail.kind === "tender" || !!tenderRec;
  const srcHtml =
    srcChips(detail.srcs) ||
    srcChips(detail.url ? [{ label: "", url: detail.url }] : null);

  /* A tender's glance is the documented eight, resolved by tenderRow (market). A signal's
     "At a glance" rows are its stored evidence/fact rows: [label, value, quote(tooltip)]. */
  const facts = tenderRec
    ? tenderFactRows(tenderRec).filter((r) => r[1] !== NOT_ON_RECORD)
    : (detail.facts || []).filter((f) => f && f[0] && f[1]);
  const points = Array.isArray(detail.points) ? detail.points : [];

  return (
    <div className="ctx v-overview revealed">
      <div className="ctx-scroll" ref={panelRef}>
        <div className={`ctx-h dir-${dir}`}>
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">
              ✕
            </button>
            {/* No STANCE pill on a TENDER. Its `dir` is the value split (priced ->
                threat), and a tender is not a "Threat" for having published a number --
                the misleading badge the market rework removes. A tender instead gets a
                neutral "Tender" type label (QA: the title section must name the kind);
                a signal keeps its coloured stance pill. */}
            {isTender ? (
              <span className="dirpill dir-tender">Tender</span>
            ) : badge ? (
              badge.word ? <span className={`dirpill dir-${dir}`}>{badge.word}</span> : null
            ) : (
              DIR_WORD[dir] ? <span className={`dirpill dir-${dir}`}>{DIR_WORD[dir]}</span> : null
            )}
          </div>
          {/* signal numbering kept in the record, not shown -- operator request */}
          <div className="ct">
            <span dangerouslySetInnerHTML={{ __html: escRich(detail.title) }} />
          </div>
          <Review src={detail._src} />
        </div>

        {/* The article's own lead image (stored image_url / thumbnail_url); nothing when absent. */}
        {detail.image ? (
          <div className="ctx-sec">
            <Thumb
              alt=""
              src={detail.image}
              style={{ width: "100%", borderRadius: "6px", display: "block", aspectRatio: "16 / 9" }}
            />
          </div>
        ) : null}

        {/* How the signal bears on the client: stored why_it_matters, headed by the stored
            impact_eyebrow (chrome heading when none is stored). */}
        {!isTender && detail.why ? (
          <div className={`ctx-sec cd-kssl kssl-${detail.dir || "watch"}`}>
            <span className="eyebrow">{detail.eyebrow || "How KSSL is impacted"}</span>
            <div className="cd-prose">{detail.why}</div>
          </div>
        ) : null}

        {facts.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">At a glance</span>
            <div className="cd-facts">
              {facts.map((f, i) => (
                <div
                  className={`cd-frow${f[2] ? " sourced" : ""}`}
                  key={`${f[0]}-${i}`}
                  /* f[2] is the proving sentence (string) OR a bare `true` sourced flag */
                  title={typeof f[2] === "string" && f[2] ? f[2] : undefined}
                >
                  <span className="cd-fline">
                    <span className="cd-fk">{f[0]}</span>
                    <span className="cd-fv" dangerouslySetInnerHTML={{ __html: escRich(f[1]) }} />
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {/* What the article says: the stored what_article_says / article_says (detail.what). */}
        {!isTender && detail.what ? (
          <div className="ctx-sec">
            <span className="eyebrow">What the article says</span>
            <div className="cd-prose cd-summary">{detail.what}</div>
          </div>
        ) : null}

        {/* A tender had no summary block at all -- the glance facts, then straight to the
            matched product -- so a reader could not tell what "Vane Large" is about. This
            is a grounded one-liner (tenderRow.tenderSummary): buyer, item, category,
            country, the pipeline's fit grade and the closing date, and it states the
            record for value/quantity rather than inventing a number. */}
        {isTender && (detail.summary || detail.what) ? (
          <div className="ctx-sec">
            <span className="eyebrow">What this tender is about</span>
            <div
              className="cd-prose cd-summary"
              dangerouslySetInnerHTML={{ __html: detail.summary || detail.what }}
            />
          </div>
        ) : null}

        {/* Key points: the stored key-point rows (evidence_group key_point / technology_overview_key_point);
            the proving sentence, when stored, is the tooltip. */}
        {!isTender && points.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Key points</span>
            <ul className="cd-bullets">
              {points.map((b, i) => (
                <li key={`b-${i}`} title={b.quote || undefined}>{b.text}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {!isTender && detail.companies && detail.companies.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Companies</span>
            <div className="cd-prose">
              {detail.companies.map((c) => (c.relationship ? `${c.name} (${c.relationship})` : c.name)).join(" · ")}
            </div>
          </div>
        ) : null}

        {isTender && detail.match && detail.match.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Matched {data.client?.short || data.client?.name} product</span>
            <div>
              {detail.match.map((m, i) => (
                <div className="cd-match" key={`${m.n}-${i}`}>
                  <div className="cm-h">
                    <span className="cm-n">{m.n}</span>
                    <span className={`cm-fit ${m.fit}`}>{m.pct} fit</span>
                  </div>
                  {(m.lines || []).map((l, j) => (
                    <div className="cm-line" key={`${l[1]}-${j}`}>
                      <span className={`cm-mk ${l[0]}`}>{l[0] === "up" ? "▲" : "▼"}</span>
                      <span dangerouslySetInnerHTML={{ __html: l[1] }} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {srcHtml ? (
          <div className="ctx-sec">
            <span className="eyebrow">Source</span>
            <div>
              <span dangerouslySetInnerHTML={{ __html: srcHtml }} />
              {detail.provenance ? (
                <div
                  className="cd-src-prov"
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: "9.5px",
                    color: "var(--l-txt-3)",
                    marginTop: "6px",
                  }}
                >
                  provenance · <span dangerouslySetInnerHTML={{ __html: attr(detail.provenance) }} />
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

    </div>
  );
}
