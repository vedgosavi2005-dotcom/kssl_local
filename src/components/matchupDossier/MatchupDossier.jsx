import { useEffect, useRef, useState } from "react";
import HtmlBlock from "../htmlBlock/HtmlBlock";
import { Review } from "../review/Review";
import { specPanelHtml, matchupGapHtml, SHOW_POSITIONING_SOURCES } from "../../lib/specs";

const TABS = [
  ["adv", "Analytics"],
  ["specs", "Spec Comparison"],
];

/* The right-hand dossier for one matchup: verdict, stored decision band, product identity,
   then two tabs: Analytics and Spec Comparison. Every value is a stored column (see
   backend/areas/b_products.py); nothing here judges or recomputes. */
export default function MatchupDossier({ m, data, onClose }) {
  const clientName = (data.client && data.client.short) || "KSSL";
  const [tab, setTab] = useState("adv");
  const dossierRef = useRef(null);

  // a new matchup resets the panel to its default tab and scrolls to top
  useEffect(() => {
    setTab("adv");
    if (dossierRef.current) {
      dossierRef.current.scrollTop = 0;
    }
  }, [m]);

  return (
    <div className="mu-dossier">
      <div className="mu-dossier-scroll" ref={dossierRef}>
        <div className="mu-d-h" style={{ position: "relative", paddingRight: "84px" }}>
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">
              ✕
            </button>
          </div>
          <span className="eyebrow">{m.cat}</span>
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

        {/* verdict: the stored headline as the label, the stored verdict as the body */}
        {m.verdictH || m.verdict ? (
          <div className="mu-sec" style={{ background: "var(--l-bg-2)" }}>
            <div className="pos-takeaway">
              {m.verdictH ? <span className="tl">{m.verdictH}</span> : null}
              <span>{m.verdict}</span>
            </div>
          </div>
        ) : null}

        {/* the stored decision_level and edge_score; nothing when no decision is stored */}
        <HtmlBlock className="mu-sec" html={matchupGapHtml(m, clientName)} />

        {/* the pair: name + thin accent line + the stored pairing basis */}
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
              {m.country ? <div className="pp2-desc">{m.country}</div> : null}
            </div>
            <div className="pp2-col bf">
              <div className="pp2-name">{m.bf}</div>
              <div className="pp2-line bf" />
            </div>
          </div>
          {m.matchBasis ? <div className="pp2-desc" style={{ marginTop: "10px" }}>Paired on: {m.matchBasis}</div> : null}
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
                  {(m.advComp || []).length ? null : (
                    <div className="adv-empty">None recorded from the sources for this matchup.</div>
                  )}
                  {(m.advComp || []).map((a, i) => (
                    <div className="adv-item" key={i}>
                      <span className="mk">▲</span>
                      <span>{a}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="adv-col bf">
                <div className="ah">
                  <span className="dot" />
                  <span>{clientName} analytics</span>
                </div>
                <div>
                  {(m.advBf || []).length ? null : (
                    <div className="adv-empty">None recorded from the sources for this matchup.</div>
                  )}
                  {(m.advBf || []).map((a, i) => (
                    <div className="adv-item" key={i}>
                      <span className="mk">▲</span>
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
            <HtmlBlock html={specPanelHtml(m, clientName)} />
            {SHOW_POSITIONING_SOURCES && (m.sources || []).length ? (
              <div className="adv-empty">
                {m.sources.map((x) => (
                  <div key={x.id}>
                    <a href={x.url} rel="noopener noreferrer" target="_blank">{x.label}</a>
                    {x.type ? ` · ${x.type}` : ""}{x.date ? ` · ${x.date}` : ""}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
