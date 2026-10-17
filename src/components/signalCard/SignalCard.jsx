import { clientShort } from "../../lib/client.js";
import { useData } from "../../state/DataProvider";
import { NO_DATE_LABEL } from "../../lib/overview.js";
import { Review } from "../review/Review";

/* One row in the overview feed. `title` and `sowhat` carry markup from the dataset
   (bolded figures), so they are injected rather than escaped.

   `card.meta` ("Artillery · Hanwha Defense USA · from bench") is deliberately NOT
   rendered — the operator asked for title and description only. The field stays on the
   card because buildFeed's `category` sort orders on it (lib/overview.js). */
export default function SignalCard({ card, dirWord, badgeClass, selected, fresh, onSelect, when }) {
  const { data } = useData();
  return (
    <div
      className={`alert${selected ? " sel" : ""}${fresh ? " fresh" : ""}`}
      data-dir={card.dir}
      data-id={card.id}
      onClick={() => onSelect(card.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(card.id);
        }
      }}
    >
      <div className="gut">
        <span className={card.dir ? `sig ${card.dir}` : "sig"} />
        <span className="rank">{card.rank}</span>
      </div>
      <div className="body">
        {/* Prefer the understood, per-pillar rewrite (uiTitle) and the "why KSSL cares"
            line (ksslImpact) written by gen_signal_text on the GPU; fall back to the raw
            news title and the article-shaped sowhat when a card was not enriched. Both are
            plain text, so injecting is safe -- the raw title/sowhat carry bolded figures. */}
        <div className="ttl" dangerouslySetInnerHTML={{ __html: card.uiTitle || card.title }} />
        <div className="sowhat" dangerouslySetInnerHTML={{ __html: card.ksslImpact || card.sowhat }} />
        {card.match && card.match.length > 0 && card.match[0].n && (
          <div className="koel-prod-highlight-row">
            <span className="kph-label">{clientShort()} Product:</span>
            <span className="kph-val">{card.match[0].n}</span>
          </div>
        )}
        <Review src={card._src} />
      </div>
      <div className="aside">
        {/* a Technology card also carries its kind, so ADOPTABLE can read green (k-adopt) */}
        {dirWord ? <span className={`dirtag${badgeClass || card.dir ? ` ${badgeClass || card.dir}` : ""}${card.kind ? ` k-${card.kind}` : ""}`}>{dirWord}</span> : null}
        {/* `when` comes from signalDate() so the card and its detail panel cannot
            disagree about the same event. Falls back to the card’s own value.

            AND SAYS SO WHEN THERE IS NONE. An undated card sorts to the bottom of its
            direction band (dateVal("") is 0, and the date key is descending) -- printing
            an empty corner alongside that made it look like a rendering slip rather than
            a fact about the article. */}
        <span className="ago">{when || card.ago || NO_DATE_LABEL}</span>
      </div>
    </div>
  );
}
