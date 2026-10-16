import { useData } from "../../state/DataProvider";
import { NO_DATE_LABEL } from "../../lib/overview.js";
import { escRich } from "../../lib/html.js";
import { Review } from "../review/Review";

/* One row in the overview feed: stored title and summary only (escRich: markup other than
   b/i/em/strong/br is shown as text). `card.meta` (category) is deliberately NOT rendered.
   The status word is the stored classification, passed in as `dirWord`. */
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
        <span className={`sig ${card.dir}`} />
        <span className="rank">{card.rank}</span>
      </div>
      <div className="body">
        <div className="ttl" dangerouslySetInnerHTML={{ __html: escRich(card.title) }} />
        <div className="sowhat" dangerouslySetInnerHTML={{ __html: escRich(card.sowhat) }} />
        {card.match && card.match.length > 0 && card.match[0].n && (
          <div className="koel-prod-highlight-row">
            <span className="kph-label">{data.client?.short || data.client?.name} Product:</span>
            <span className="kph-val">{card.match[0].n}</span>
          </div>
        )}
        <Review src={card._src} />
      </div>
      <div className="aside">
        {/* a Technology card also carries its kind, so ADOPTABLE can read green (k-adopt) */}
        {dirWord ? <span className={`dirtag ${badgeClass || card.dir}${card.kind ? ` k-${card.kind}` : ""}`}>{dirWord}</span> : null}
        {/* `when` comes from signalDate() so the card and its detail panel cannot
            disagree about the same event. Falls back to the card’s own value.

            AND SAYS SO WHEN THERE IS NONE. An undated card sorts to the bottom of its
            severity band (dateVal("") is 0, and the date key is descending) -- printing
            an empty corner alongside that made it look like a rendering slip rather than
            a fact about the article. */}
        <span className="ago">{when || card.ago || NO_DATE_LABEL}</span>
      </div>
    </div>
  );
}
