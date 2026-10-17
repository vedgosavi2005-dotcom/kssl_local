/* The publisher line on an article, as a link that actually goes there.

   Reported: "News items do not consistently redirect to the original source. Each news
   item should link directly to its actual/original source URL."

   Inconsistently is right: the Geo drawer had an <a>, the Competitive profile drawer
   and the product drawer printed the publisher name as plain text. All three read the
   same field. 1,171 of the 1,177 served signal cards carry a url, so this was almost
   never a data gap -- the link existed and was not rendered.

   The six rows with no url say so, rather than looking identical to a link that does
   nothing. That distinction is the whole point of the report: a reader who clicks and
   gets no response cannot tell a missing source from a broken page. */

/* Only http(s) becomes a link. These urls come from the pipeline rather than from a
   person, but an href is a place a stray value would be honoured silently. */
export function sourceHref(u) {
  return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null;
}

/* THE SAME LINK, ON A CARD.

   SourceLink is the drawer's line -- it prints "Source Publisher:" and a full label. A
   news card has room for the publisher and nothing else, and the card itself is already
   a button that opens the article drawer. So the publisher becomes a link in place, and
   the click stops there rather than also opening the drawer behind the new tab.

   Reported as: clicking news should open the original source in a new tab. It could,
   but only from inside the drawer -- two clicks, and nothing on the card said so. The
   href rule is sourceHref above, unchanged: only http(s), and an article with no url
   stays plain text rather than becoming a link that goes nowhere. */
export function SourceChip({ url, source, style }) {
  const href = sourceHref(url);
  const name = source || "—";
  if (!href) return <span style={style}>{name}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      title={`Open the original article at ${name}`}
      style={{ color: "inherit", textDecoration: "underline", ...(style || {}) }}
    >
      {name} ↗
    </a>
  );
}

/* THE WHOLE CARD IS THE LINK.
 *
 * Every news item on the competitor pages opened a re-hosted copy of the article inside
 * the app -- a white panel that replaced the profile and showed the pipeline's own
 * summary of the piece under the publisher's headline. The operator asked for the
 * opposite: a news item should go to the news source.
 *
 * That is also the more honest surface. The in-app panel printed `signal_detail.what` as
 * the article BODY, so a reader had no way to tell the publisher's reporting from this
 * pipeline's paraphrase of it, and the actual article was another click further on. The
 * publisher's page has no such ambiguity.
 *
 * `<a>`, not an onClick that calls window.open: the reader gets the real affordances --
 * the status-bar preview, middle-click, "open in new tab", copy link address -- none of
 * which a div with a handler on it has ever offered. A row with no usable url stays a
 * plain container rather than becoming a link that goes nowhere; measured on the served
 * store, 0 of 914 articles are in that state, so this is a guard and not a common path.
 */
export function ArticleLink({ article, className, style, children, title }) {
  const href = sourceHref(article && (article.sourceUrl || article.url));
  const base = { color: "inherit", textDecoration: "none", display: "block", ...(style || {}) };
  if (!href) return <div className={className} style={base}>{children}</div>;
  return (
    <a
      className={className}
      href={href}
      rel="noopener noreferrer"
      style={{ ...base, cursor: "pointer" }}
      target="_blank"
      title={title || `Open this article at ${(article && article.source) || "the source"}`}
    >
      {children}
    </a>
  );
}

export default function SourceLink({ url, source, color, label = "Source Publisher" }) {
  const href = sourceHref(url);
  const name = source || "—";
  return (
    <>
      {label}:{" "}
      {href ? (
        <a
          href={href}
          rel="noopener noreferrer"
          style={{ color, fontWeight: 600, textDecoration: "underline" }}
          target="_blank"
        >
          <span className="src-dot"></span>
          {name}
        </a>
      ) : (
        <>
          <span style={{ color }}>
            <span className="src-dot"></span>
            {name}
          </span>{" "}
          <span style={{ color: "var(--d-txt-3)", fontSize: "10.5px" }}>
            (no source link on file)
          </span>
        </>
      )}
    </>
  );
}
