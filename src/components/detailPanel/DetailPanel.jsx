import { clientShort } from "../../lib/client.js";
import { useEffect, useRef } from "react";
import AskBox from "../askBox/AskBox";
import { isVisible } from "../../lib/visibility";
import { articleBullets } from "../../lib/detail";
import { tenderFactRows, NOT_ON_RECORD } from "../../lib/tenderRow";
import { srcChips, attr } from "../../lib/html";
import { formatLabel } from "../../lib/profile";
import { useData } from "../../state/DataProvider";
import { useAppState } from "../../state/AppState";
import { productOwner } from "../../lib/productLink";
import { Review } from "../review/Review";
import { STANCE_WORD as DIR_WORD, stanceOf, TENDER_WORD as tenderWord } from "../../lib/chrome";

/* `badge` (optional): the ROW's own label for this signal, { word, cls }. A pillar that
   labels its rows by kind rather than by stance (Technology: ADOPTABLE, or nothing for a
   competitor advance) passes it so the panel says what the row says -- not "Watch". An
   empty word draws no pill. Without it, the stance pill as before. */
export default function DetailPanel({ detail, onClose, badge }) {
  const { data } = useData();
  const { jumpTo } = useAppState();
  const panelRef = useRef(null);

  useEffect(() => {
    if (panelRef.current) {
      panelRef.current.scrollTop = 0;
    }
  }, [detail]);

  if (!detail) return null;
  /* a stance is threat or watch, anything else has none */
  const dir = badge ? badge.cls || "none" : stanceOf(detail.dir) || "none";
  /* A TENDER IS NOT AN ARTICLE, AND detail.kind NEVER SAID SO.
     Market's overview opens on "Live Opportunities" -- 126 tender cards. A tender has
     no document body, which is why the summary backfill selects `id LIKE 'pl\_%'` and
     skips them: there is nothing to summarise. So the article block below renders
     nothing for any of them, and on 22 of the 126 `what` is an empty string as well,
     which left the panel showing no prose at all.
     `detail.kind` cannot detect this. It is NULL on every served row in every lane, so
     this branch has never once been true and the tender path was dead code. The id
     prefix is what the writer actually sets. */
  const tenderId = /^tender-/.test(String(detail.id || ""))
    ? String(detail.id).replace(/^tender-/, "")
    : null;
  const tenderRec = tenderId
    ? (data.tenders || []).find((t) => String(t.id) === tenderId) || null
    : null;
  const isTender = detail.kind === "tender" || !!tenderRec;
  const srcHtml =
    srcChips(detail.srcs) ||
    srcChips(detail.url ? [{ label: "", url: detail.url }] : null);

  /* "At a glance" used to be four rows out of the pipeline — Company, Category, Date,
     Primary lens (serving_fill.py) — and this panel used to append Publisher and Stance.

     TASKS #16 removes three of them: Stance, Date and Publisher. None is lost to the
     reader — each is still on screen, in the place it belongs:

       Stance     the coloured pill in this panel's own header, and the dirtag on the
                  feed row. A word in a fact list restated what the colour already says.
       Date       the feed row's `ago`, from signalDate(), which is the one value the
                  card and this panel are guaranteed to agree on.
       Publisher  the source chips at the foot of the panel, which carry the link as
                  well as the host — a bare hostname was the same fact without the URL.

     So the list keeps only what nothing else shows. The rows that were missing (deal
     value, quantity, counterparty, programme, system, key person) are now written by
     serving_fill.py from the document's TYPED spans (glance.py), each with the sentence
     that proves it in f[2] -- the tooltip and the "sourced" mark below. They were not
     regexed out of prose here, because that would be manufacturing structure the
     extractor never asserted.

     Primary lens goes the same way as Stance: the pillar is the coloured pill in this
     header and the dirtag on the feed row (the client: "we already tagged it there, so
     no need of redundant info"). The writer no longer emits it; this filter also hides
     the row on every card stored before the change, and on the reference rows, which
     carry it too. */
  const DROPPED_FACTS = new Set(["stance", "date", "publisher", "primary lens"]);
  /* A tender's glance is the documented eight -- the same set the Tender Pipeline row
     prints, resolved by the same function so the two surfaces cannot disagree. NEVER
     filtered: "Value -- not on record" is a fact about the tender, and hiding the row
     would present a partial record as a complete one. */
  const facts = tenderRec
    // operator override of the earlier keep-all stance: hide unresolved rows.
    ? tenderFactRows(tenderRec).filter((r) => r[1] !== NOT_ON_RECORD)
    : Array.isArray(detail.glance) && detail.glance.length
      // The per-pillar at-a-glance written by gen_signal_text (Competitor / KSSL line /
      // Overlap / Severity, etc.) -- clearer than the raw pipeline facts for a signal.
      ? detail.glance.map((g) => [g[0], g[1], false])
      : (detail.facts || []).filter(
          (f) => !DROPPED_FACTS.has(String(f[0]).trim().toLowerCase()),
        );
  const bullets = articleBullets(detail.lens);
  /* signal v2 (detail.v2): every key point, with its label */
  const v2 = !!detail.v2;
  const keyPoints = v2 ? (detail.lens || []).filter((p) => p && p[1]) : [];

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
              <span className="dirpill dir-tender">{tenderWord}</span>
            ) : badge ? (
              badge.word ? <span className={`dirpill dir-${dir}`}>{badge.word}</span> : null
            ) : DIR_WORD[dir] ? (
              <span className={`dirpill dir-${dir}`}>{DIR_WORD[dir]}</span>
            ) : null}
          </div>
          {/* signal numbering kept in the record, not shown -- operator request */}
          <div className="ct">
            <span dangerouslySetInnerHTML={{ __html: detail.title }} />
          </div>
          <Review src={detail._src} />
        </div>

        {/* The article's own lead image, resolved from its page markup by
            serving_fill.py and carried on the record. No placeholder when it is
            absent: a stock photo standing in for a story we could not illustrate
            is the same fabrication as an invented figure, just quieter. */}
        {detail.image ? (
          <div className="ctx-sec">
            <img
              alt=""
              src={detail.image}
              style={{ width: "100%", borderRadius: "6px", display: "block",
                       aspectRatio: "16 / 9",
                       background: "var(--d-bg-1)" }}
            />
          </div>
        ) : null}

        {/* THE HEADLINE INSIGHT, up top: how this signal bears on KSSL, written per pillar
            by gen_signal_text (threat read / opportunity read / knowledge read) and
            grounded in the card's own facts. The eyebrow names the kind so the reader
            knows at a glance whether to worry, act, or note it. */}
        {!isTender && detail.ksslImpact ? (
          <div className={detail.ksslImpactKind ? `ctx-sec cd-kssl kssl-${detail.ksslImpactKind}` : "ctx-sec cd-kssl"}>
            {/* the stored impact_eyebrow of the signal's detail row (serving.competitive_signal_detail) leads; a
                row that stores none is named by its kind. These name WHAT THE SIGNAL IS: the reader decides
                whether to bid or adopt; the panel reports the facts. */}
            <span className="eyebrow">
              {detail.eyebrow ||
                {
                  threat: `Threat to ${clientShort()}`,
                  demand: "Demand in a client line",
                  "tech-advance": "Technology advance",
                  "rival-advance": "Competitor advance",
                  opportunity: "Demand in a client line",
                  adoptable: "Technology advance",
                }[detail.ksslImpactKind] ||
                `How ${clientShort()} is impacted`}
            </span>
            <div className="cd-prose">{detail.ksslImpact}</div>
          </div>
        ) : null}

        <div className="ctx-sec">
          <span className="eyebrow">At a glance</span>
          <div className="cd-facts">
            {facts.map((f, i) => (
              <div
                className={`cd-frow${f[2] ? " sourced" : ""}`}
                key={`${f[0]}-${i}`}
                /* f[2] is the proving sentence (string) OR a bare `true` sourced flag;
                   only a string is a valid title, else React warns "non-boolean attribute". */
                title={typeof f[2] === "string" ? f[2] : undefined}
              >
                {/* The KEY is a label and wears the house capitalisation; the VALUE
                    is data and is never touched. These keys are written by the
                    pipeline ("Primary lens") and by Tenders.jsx ("Estimated value",
                    "Closing date"), and .cd-fk sets no text-transform, so whatever
                    a writer typed reached the screen -- sentence case sitting
                    beside Company, Category and Date. Doing it here fixes both
                    writers' labels, and every row already stored, at once. */}
                <span className="cd-fline">
                  <span className="cd-fk">{formatLabel(f[0])}</span>
                  <span className="cd-fv" dangerouslySetInnerHTML={{ __html: f[1] }} />
                  {/* THE ❝ IS GONE at the operator's request. It marked a row whose
                      proving sentence is in the tooltip, and it was not the only thing
                      that did: `.sourced` paints the row's own left edge, which is a
                      state on the row rather than a glyph sitting between the label and
                      its value. */}
                </span>
                {/* The per-field gloss ("the product class the signal falls in", ...)
                    was removed at QA's request -- it repeated on every card and read as
                    filler under the real value. The label alone stands. */}
              </div>
            ))}
          </div>
        </div>

        {/* THE ARTICLE, not a fragment of it. `summary` is written by
            extraction/signals/summarize.py from extracted.document.text -- a short
            paragraph and then the specifics (quantities, sums, dates, programme names,
            people) -- and it is in English whatever the article was in, because it is
            written, not located.

            What it replaced: `what`, one sentence from a prompt that was never shown
            the article (serving_fill feeds the card model the extracted propositions,
            so `what` summarised a summary). On a row with no `summary` -- everything
            stored before the migration, and any article that yielded nothing worth
            showing -- `what` is still what there is, so it is the fallback rather than
            a deletion. The section is deliberately not headed "Executive Summary": it
            says what the article says, and that is what the heading says.  */}
        {!isTender && (detail.summary || detail.what) ? (
          <div className="ctx-sec">
            <span className="eyebrow">What the article says</span>
            <div
              className="cd-prose cd-summary"
              dangerouslySetInnerHTML={{ __html: detail.summary || detail.what }}
            />
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

        {/* KEPT, AND MOVED BELOW THE SUMMARY. These rows are no longer how the reader
            finds out what happened -- `summary` above does that, in English and in
            whole sentences. What they are for now is proof: each one shows the
            publisher's own sentence, so a reader who doubts a line in the summary can
            check it against the source without leaving the panel. That is worth a
            section; it was never worth the top of the panel.

            Up to six propositions from the extraction layer, each shown WITH the
            article sentence that proves it.

            HALF OF EACH ROW IS THE PUBLISHER'S WORDS AND HALF IS NOT, and this comment
            used to claim both were. The quoted half is `ev_quote`, located in the
            article by character offset (ev_start/ev_end are NOT NULL in the schema), so
            it is provably the publisher's sentence: it stays in the article's own
            language, carries a lang= tag, and is never translated -- doing so would put
            words inside quotation marks that nobody wrote. The lead-in before the dash
            is NOT located and never was: comprehend asks the model for "a SHORT phrase,
            max 6 words" and caps it, so it is the extraction layer's paraphrase. It is
            rendered in English, because translating a paraphrase invents nothing and
            leaving it alone produced rows like "sette veicoli ruotati 8x8 Centauro II
            are forniti" -- an English verb welded to an Italian subject and object. */}
        {/* KEY POINTS: 3-4 clean bullets about the article, from the extracted
            propositions (articleBullets). Replaces the raw "publisher's words" quotes
            at the operator's request -- the quotes stay in the record as proof, they are
            just no longer the reader-facing view. */}
        {v2 && keyPoints.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Key points</span>
            <ul className="cd-bullets">
              {keyPoints.map((p, i) => (
                <li key={`k-${i}`}>{p[0] ? <b>{p[0]}. </b> : null}{p[1]}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {v2 && detail.story && detail.story.steps.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Story timeline{detail.story.label ? ` · now ${detail.story.label}` : ""}</span>
            <ol className="cd-timeline">
              {detail.story.steps.map((s, i) => (
                <li key={`s-${i}`} className={s.current ? "cur" : ""}>
                  <span className="tl-d">{s.date || "date not stated"}</span>
                  <span className="tl-t">{s.type}</span>
                  <span className="tl-l">
                    {s.url ? <a href={s.url} rel="noreferrer" target="_blank">{s.line}</a> : s.line}
                    {s.changed ? <span className="tl-c"> · {s.changed}</span> : null}
                    {s.label ? <span className="tl-c"> · {s.label}</span> : null}
                    {s.current ? <span className="tl-c"> · this article</span> : null}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        {v2 && detail.productNews && detail.productNews.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Product news</span>
            <div className="cd-facts">
              {detail.productNews.map((n, i) => (
                <div className="cd-frow" key={`pn-${i}`} title={n.relevance || undefined}>
                  <span className="cd-fline">
                    <span className="cd-fk">
                      {n.productId && productOwner(data, n.product) ? (
                        <button className="prod-link" onClick={() => jumpTo("competitive", "products", productOwner(data, n.product))} type="button">{n.product}</button>
                      ) : n.product || "Product not named"}
                      {n.variant ? ` (${n.variant})` : ""}
                    </span>
                    <span className="cd-fv">{n.type}{n.date ? ` · ${n.date}` : ""}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {!v2 && !isTender && bullets.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Key points</span>
            <ul className="cd-bullets">
              {bullets.map((b, i) => (
                <li key={`b-${i}`}>{b}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {isTender && detail.match && detail.match.length ? (
          <div className="ctx-sec">
            <span className="eyebrow">Matched {clientShort()} product</span>
            <div>
              {detail.match.map((m, i) => (
                <div className="cd-match" key={`${m.n}-${i}`}>
                  <div className="cm-h">
                    <span className="cm-n">
                      {productOwner(data, m.n) ? (
                        <button className="prod-link" onClick={() => jumpTo("competitive", "products", productOwner(data, m.n))} title="Open this product in Products" type="button">{m.n}</button>
                      ) : m.n}
                    </span>
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

      {isVisible("chat") ? <AskBox suggest={detail.suggest} /> : null}
    </div>
  );
}
