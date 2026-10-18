import { clientShort } from "../../lib/client.js";
import { useEffect, useRef, useState } from "react";
import HtmlBlock from "../htmlBlock/HtmlBlock";
import { specPanelHtml, matchupGapHtml, advantageText } from "../../lib/specs";
import { isVisible } from "../../lib/visibility";
import { Review } from "../review/Review";

const TABS = [
  ["adv", "Analytics"],
  ["specs", "Spec Comparison"],
];

/* The right-hand dossier for one matchup: verdict, gap block, product identity,
   then two tabs: Analytics and Spec Comparison. */
export default function MatchupDossier({ m, data, gapModel, onClose, onJumpToTender }) {
  const [tab, setTab] = useState("adv");
  const dossierRef = useRef(null);

  // a new matchup resets the panel to its default tab and scrolls to top
  useEffect(() => {
    setTab("adv");
    if (dossierRef.current) {
      dossierRef.current.scrollTop = 0;
    }
  }, [m]);

  const prodRow = (m.specs || []).find((s) => s.l === "Product (sourced)") || {};
  const compDesc = prodRow.cv && prodRow.cv !== "—" ? prodRow.cv : "";
  const bfDesc = prodRow.kv && prodRow.kv !== "—" ? prodRow.kv : "";

  return (
    <div className="mu-dossier">
      <div className="mu-dossier-scroll" ref={dossierRef}>
        <div className="mu-d-h" style={{ position: "relative", paddingRight: "84px" }}>
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">
              ✕
            </button>
          </div>
          {/* "Verified specs · analysed" was stamped on EVERY matchup, the majority of
              which have no dimension published on both sides at all -- their client
              column reads "no published figure" from top to bottom. A verification
              badge over a comparison that never happened is the worst kind of claim on
              this page, because a badge is what a reader checks before trusting the
              numbers under it. `m.global` did not help: it selects a global-prime
              PAIRING, which says nothing about the evidence, and both of its branches
              asserted analysis anyway.

              specDims is how many independent dimensions BOTH products publish (stored
              with the matchup), so the badge states that count and
              says plainly when it is zero.

              NOTE: shell.css carries `.srcbadge{display:none !important}`, so nothing
              in this slot is on screen today -- the false version was invisible too.
              The class is kept, because hiding these badges was a deliberate change
              and un-hiding them is not this fix's call; what changes is that whatever
              this slot says is now true if it is ever shown again. */}
          <span className="eyebrow">
            {m.cat}{" "}
            <span
              className="srcbadge"
              style={{ marginLeft: "6px" }}
              title={
                m.specDims
                  ? "Dimensions published by both products and compared line by line. Pairing axes (calibre, length, weight class) are excluded."
                  : "Neither product publishes a dimension the other also publishes, so nothing here has been compared."
              }
            >
              {m.specDims
                ? `${m.specDims} spec${m.specDims === 1 ? "" : "s"} compared on both sides`
                : "No spec published on both sides"}
            </span>
          </span>
          <div className="matchup">
            <div className="side comp">
              <div className="pn">{m.comp}</div>
            </div>
            <span className="vsbadge">VS</span>
            <div className="side bf">
              <div className="pn">{m.bf}</div>
            </div>
          </div>
          <Review src={m._src} />
        </div>

        {/* verdict always visible */}
        <div className="mu-sec" style={{ background: "var(--l-bg-2)" }}>
          <div className="pos-takeaway">
            <span className="tl">{m.verdictH || "—"}</span>
            <span dangerouslySetInnerHTML={{ __html: (m.verdict || "").replace(/\s*Based only on values sourced for both products\.?/i, "").replace(/\s*on \d+ of \d+ comparable field\(s\)/i, "").trim() }} />
          </div>
        </div>

        {/* gap block — this matchup's gap in cross-pillar context */}
        {isVisible("gap-analysis") ? (
          <HtmlBlock
            className="mu-sec"
            handlers={{
              "[data-tender]": (el) => onJumpToTender(el.getAttribute("data-tender")),
            }}
            html={matchupGapHtml(m, gapModel)}
          />
        ) : null}

        {/* product profile: name + thin accent line + sourced descriptor */}
        <div className="mu-sec pp2-sec">
          <div className="pp2">
            <div className="pp2-col comp">
              {/* PLAIN, NON-INTERACTIVE LABEL -- identical to the KSSL side below. The
                  competitor name used to be an underlined button that navigated to the
                  rival product's own page, while the KSSL side was plain text; the two
                  sides of one comparison read as different kinds of thing. The operator
                  asked for both to be a plain label, so the navigation, the anchor and
                  the underline are gone. */}
              <div className="pp2-name">{m.comp}</div>
              <div className="pp2-line comp" />
              {compDesc ? <div className="pp2-desc">{compDesc}</div> : null}
            </div>
            <div className="pp2-col bf">
              <div className="pp2-name">{m.bf}</div>
              <div className="pp2-line bf" />
              {bfDesc ? <div className="pp2-desc">{bfDesc}</div> : null}
            </div>
          </div>
        </div>

        <div className="mu-tabs">
          {TABS.map(([k, label]) => (
            <div
              className={`mu-tab${tab === k ? " on" : ""}`}
              key={k}
              onClick={() => setTab(k)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setTab(k);
                }
              }}
            >
              {label}
            </div>
          ))}
        </div>

        <div className={`mu-panel${tab === "adv" ? " on" : ""}`} data-panel="adv">
          <div className="mu-sec" style={{ padding: 0 }}>
            <div className="adv-grid">
              <div className="adv-col comp">
                <div className="ah">
                  <span className="dot" />
                  <span>Competitor analytics</span>
                </div>
                <div>
                  {(m.advComp || []).length || (m.advCompQ || []).length ? null : (
                    <div className="adv-empty">None recorded from the sources for this matchup.</div>
                  )}
                  {(m.advComp || []).map((a, i) => (
                    <div className="adv-item" key={i}>
                      <span className="mk">▲</span>
                      <span>{advantageText(a)}</span>
                    </div>
                  ))}
                  {(m.advCompQ || []).map((a, i) => (
                    <div className="adv-item" key={`q${i}`}>
                      <span className="mk">◆</span>
                      <span>{a}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="adv-col bf">
                <div className="ah">
                  <span className="dot" />
                  <span>{clientShort()} analytics</span>
                </div>
                <div>
                  {(m.advBf || []).length || (m.advBfQ || []).length ? null : (
                    <div className="adv-empty">None recorded from the sources for this matchup.</div>
                  )}
                  {(m.advBf || []).map((a, i) => (
                    <div className="adv-item" key={i}>
                      <span className="mk">▲</span>
                      <span>{advantageText(a)}</span>
                    </div>
                  ))}
                  {(m.advBfQ || []).map((a, i) => (
                    <div className="adv-item" key={`q${i}`}>
                      <span className="mk">◆</span>
                      <span>{a}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className={`mu-panel${tab === "specs" ? " on" : ""}`} data-panel="specs">
          <div className="mu-sec">
            <div className="spec-head">
              <span className="sh-comp">{m.comp}</span>
              <span className="sh-bf">{m.bf}</span>
            </div>
            <HtmlBlock html={specPanelHtml(m)} />
          </div>
        </div>
      </div>
    </div>
  );
}
