import { STANCE_WORD } from "../../lib/chrome";
import { clientShort } from "../../lib/client.js";
import { useEffect, useMemo, useRef, useState } from "react";
import SignalCard from "../../components/signalCard/SignalCard";
import DetailPanel from "../../components/detailPanel/DetailPanel";
import ErrorBoundary from "../../components/ErrorBoundary";
import TenderCockpit from "../../components/tenderCockpit/TenderCockpit";
import FeedFilters from "../../components/subHead/FeedFilters";
import { useAppState, useHeaderReport, PILLAR_LABEL } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { OVERVIEW_VIEW } from "../../lib/route";
import {
  buildFeed,
  emptyFeedNote,
  filterMatch,
  paginateFeed,
  readFeedPage,
  signalDate,
  tilePredicate,
  writeFeedPage,
  SEQ_LABEL,
  TILE_LABELS,
} from "../../lib/overview";

/* sessionStorage, guarded: a private window throws on the property itself */
const pageStore = () => {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null;
  } catch (e) {
    return null;
  }
};

/* The overview feed and its detail column. Shared by all three pillars — the pillar
   only decides which card set and which metric strip config is in play, which is
   exactly how the original's buildOverviewFeed(pillarKey) worked. */
export default function Overview({
  pillarKey,
  seqMode,
  dirFilter,
  tile,
  filters,
  onFilter,
  onSeq,
  onSelectionChange,
  title,   // optional: the feed's heading, where the pillar's own would be wrong (Global Requirements)
  cardFilter,   // optional: keep only the signal cards this returns true for (Global Requirements keeps the Global ones)
  part,   // market only: "cockpit" = the tender tables (Market overview), "feed" = the signal cards (Global Requirements)
}) {
  const { data } = useData();
  const { setScope, takePending } = useAppState();
  const [selected, setSelected] = useState(null);
  /* A detail the feed does not carry: a Top-tenders row can be a tender outside the Latest Tenders
     cards, so it has no data.details entry. DetailPanel reads such a tender off data.tenders by id. */
  const [extraDetail, setExtraDetail] = useState(null);
  const [feedSearchQuery, setFeedSearchQuery] = useState("");

  /* What the feed is filtered and ordered by, as one string. The page is remembered
     under it and reset when it changes. */
  const filterKey = JSON.stringify([pillarKey, seqMode, dirFilter || "all", tile || "", feedSearchQuery]);

  /* Restored on mount, per pillar and for this filter. Layout keys the boundary above
     this component on the view, so a detour to Competitor and back is a remount -- and
     before this the reader came back to page 1 every time, as they did on reload. */
  const [page, setPage] = useState(() => readFeedPage(pageStore(), pillarKey, filterKey));

  // the shell's third column collapses when nothing is selected, so Layout has to know
  useEffect(() => {
    onSelectionChange?.(!!selected);
  }, [selected, onSelectionChange]);

  const cfg0 = data.overviewConfig[pillarKey] || data.overviewConfig.competitive;
  const cfg = useMemo(
    /* A cardFilter reads the pillar's WHOLE served lane, not the overview cards: those keep the
       latest tenders and only the 24 newest perceived opportunities, so filtering them listed 8 of the 27 Global
       signals. */
    () => (cardFilter || title ? { ...cfg0, ...(cardFilter ? { cards: (data[`${pillarKey}Cards`] || cfg0.cards || []).filter(cardFilter) } : {}), ...(title ? { title } : {}) } : cfg0),
    [cfg0, cardFilter, title, data, pillarKey],
  );
  /* The card's status word. Technology cards are grouped by kind (rival/adopt), not by
     dir, so a flat dir->word map stamped the same "Advancement" on every card; read the
     tag word when the config carries one. Every other pillar keeps the dir map. */
  /* A tag word that is present but empty means "no badge for this kind" -- it must not
     fall through to the dir word. */
  const labelFor = (c) => {
    const w = cfg.tagWord && c.kind && c.kind in cfg.tagWord ? cfg.tagWord[c.kind] : cfg.dirWord[c.dir] || c.dir;
    return w || "";
  };
  // the badge's colour class: a config may repaint a dir without changing the dir itself
  const badgeFor = (c) => (cfg.badgeClass && cfg.badgeClass[c.dir]) || c.dir;
  const clientLabel = clientShort();
  // `data` is a dependency because the sort now reads the same date the card prints,
  // which lives in data.details, not on the card
  const feed = useMemo(() => buildFeed(cfg, seqMode, data), [cfg, seqMode, data]);

  // a pillar change or a re-sequence drops the selection, same as the original's
  // "collapsed until a signal is clicked" reset
  useEffect(() => {
    setSelected(null);
  }, [pillarKey, seqMode]);

  /* Anything that changes WHAT the feed contains sends the reader back to page 1.
     The search boxes are in this list because they were not in the pre-port version --
     they did not exist yet -- and a query that shrinks 453 signals to 3 would otherwise
     leave the reader on page 7 of a 1-page feed, looking at nothing.

     Guarded by the PREVIOUS key rather than firing on mount: an effect with these deps
     also runs once after the first render, and that first run was throwing away the
     page just restored above. */
  const lastKey = useRef(filterKey);
  useEffect(() => {
    if (lastKey.current === filterKey) return;
    lastKey.current = filterKey;
    setPage(1);
  }, [filterKey]);

  /* Memoised on the tile NAME, not rebuilt per render: an identity that changed every
     render made the auto-select effect below re-fire forever. */
  const tilePred = useMemo(() => (tile ? tilePredicate(tile) : null), [tile]);

  /* Split so the filter counts can reuse this predicate verbatim rather than
     paraphrasing it. A count computed from a paraphrase is the exact bug this page was
     fixed for: a two-word query, or a hit that lives only in the detail text, made the
     badges read 0 while matching cards were plainly on screen -- and since an empty
     filter is disabled, every button including "All" went dead beneath a full feed. */
  /* TWO BOXES, TWO SCOPES -- and this reads only its own.
     It used to fall through to the global query, so typing in the top bar filtered this
     feed as well: the reader saw the card list shrink while the box above the list was
     visibly EMPTY, with no control on the page that would undo it. The top bar is the
     whole-dataset search and answers in its own popover, which routes across all three
     pillars; this box filters the cards of the open pillar. Neither reaches into the
     other. */
  const visibleExceptDir = (card) => {
    if (tilePred && !tilePred(card)) return false;
    const activeQ = (feedSearchQuery || "").trim().toLowerCase();
    if (activeQ) {
      const qTokens = activeQ.split(/\s+/).filter(Boolean);
      const detail = (data.details && data.details[card.id]) || {};
      const fullText = `${card.title || ""} ${card.company || ""} ${card.tags || ""} ${card.sowhat || ""} ${card.ago || ""} ${detail.facts || ""} ${detail.what || ""} ${detail.why || ""}`.toLowerCase();
      if (!qTokens.every((tok) => fullText.includes(tok))) return false;
    }
    return true;
  };

  const visible = (card) =>
    filterMatch(card, dirFilter, filters) && visibleExceptDir(card);

  /* Picking a signal moves both chat contexts: the scoped ask box answers about this
     signal, and the floating assistant's context line names it. */
  const select = (id, adhoc) => {
    const detail = data.details[id] || adhoc;
    if (!detail || id === selected) return;
    setExtraDetail(adhoc || null);
    setSelected(id);
    /* The context line names the pillar and heading the reader is actually on. It
       said "Competitive / Overview" on all three pillars, so a technology signal was
       announced under a page it is not listed on (FE 18). */
    setScope("signal", { type: "signal", data: detail }, {
      pillar: PILLAR_LABEL[pillarKey] || "Competitive",
      view: cfg.title || "",
      selection: detail.title,
    });
  };

  /* A Top-tenders / Projects / Next-moves row opens its detail here, beside the table, instead of
     leaving for the Tender Pipeline. A tender row passes the tender; a project row (no tender is
     issued yet) passes the stored project (data.projects), whose facts are its own stored fields. */
  const openTender = (t, project) => {
    if (project) {
      const id = `project-${project.id}`;
      const src = Array.isArray(project.sources) ? project.sources : [];
      return select(id, {
        id, title: project.name,
        facts: [["Customer", project.customer], ["Location", project.location], ["Stage", project.stage], ["Competitor", project.company]]
          .filter((f) => f[1] != null && String(f[1]).trim() !== ""),
        summary: project.stageNote || (Array.isArray(project.overview) && project.overview[0]) || "", what: "", why: "",
        lens: "Market", actions: [], match: null, url: (src[0] && src[0].url) || null,
      });
    }
    return select(`tender-${t.id}`, {
      id: `tender-${t.id}`, title: t.title, facts: [], summary: "", what: "", why: "",
      lens: "Market", actions: [], match: t.matches || null, url: t.url,
    });
  };

  /* Opened from global search targeting a specific signal card. The payload is taken
     under THIS pillar's overview view -- it asked for the literal "overview", which is
     the competitive pillar's only, so a hit on a technology or market signal landed on
     the right feed and opened nothing. */
  useEffect(() => {
    const pend = takePending(OVERVIEW_VIEW[pillarKey] || "overview");
    if (pend && pend.cardId && data.details && data.details[pend.cardId]) {
      /* A hit is usually not on the page in view -- 453 signals is ten pages -- so turn
         to the page holding it BEFORE selecting, or the reader gets a detail panel
         beside a feed that does not list what it describes. */
      const at = pageView.pageOf(pend.cardId);
      if (at && at !== pageView.page) goPage(at);
      select(pend.cardId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takePending]);

  /* A filter or search that removes the selected card from the feed also closes its
     panel: a detail column describing a card the list no longer shows is a page that
     disagrees with itself. Declared BEFORE the tile effect below, so when a tile both
     narrows the feed and opens its first match, the open wins. */
  useEffect(() => {
    if (!selected) return;
    const card = (cfg.cards || []).find((c) => c.id === selected);
    if (!card || !visible(card)) setSelected(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

  /* A TILE FILTERS THE FEED. IT DOES NOT OPEN A CARD.
     Clicking "Competitive threats" used to narrow the feed AND select its first card, so
     the detail panel sprang open over a list the reader had not finished reading yet --
     on every tile, on every pillar. Reported as: "it show only threats but automatically
     first signal card pops, it should not happen".
     The filter is the whole of what the tile was asked to do; opening a card is the
     reader's next decision, and it is one click away. */

  /* paginateFeed takes the `keep` predicate, so the pager runs over the search-filtered
     set rather than fighting it -- the two cannot disagree about what is on screen. */
  const pageView = useMemo(
    () => paginateFeed(feed.groups, visible, page),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [feed, dirFilter, tilePred, feedSearchQuery, page],
  );
  const shownCount = pageView.shown;
  const firstVisibleId = pageView.firstId;

  /* The page actually on screen -- pageView.page, which is clamped -- is what is
     remembered, never the raw state. */
  useEffect(() => {
    writeFeedPage(pageStore(), pillarKey, filterKey, pageView.page);
  }, [pillarKey, filterKey, pageView.page]);
  /* What the header's Copy / Export / Print act on: the signals on THIS page of the
     feed, under the sequence and filter in force. Every field is the card's own. */
  const report = useMemo(() => {
    const cards = pageView.groups.flatMap((g) => g.cards);
    const filterLabel = tile
      ? TILE_LABELS[tile] || tile
      : dirFilter && dirFilter !== "all"
        ? ((filters || []).find((f) => f.f === dirFilter) || {}).l || dirFilter
        : "all signals";
    return {
      title: cfg.title || "",
      subtitle: `${SEQ_LABEL[seqMode] || seqMode} · ${filterLabel} · page ${pageView.page} of ${pageView.pageCount}`,
      sections: [
        {
          h: `Signals ${pageView.from}-${pageView.to} of ${pageView.shown}`,
          rows: cards.map((c) => [`${c.company ? `${c.company} - ` : ""}${c.title || ""}`, c.sowhat || ""]),
        },
      ],
      payload: {
        pillar: pillarKey,
        sequence: seqMode,
        filter: filterLabel,
        page: pageView.page,
        pageCount: pageView.pageCount,
        shown: pageView.shown,
        total: feed.total,
        signals: cards.map((c) => ({
          id: c.id,
          title: c.title || null,
          company: c.company || null,
          direction: c.dir || null,
          date: signalDate(c, data) || null,
          sowhat: c.sowhat || null,
          url: c.url || null,
        })),
      },
    };
  }, [pageView, cfg, seqMode, tile, dirFilter, filters, pillarKey, feed.total, data]);
  useHeaderReport(report);

  const goPage = (n) => {
    setPage(n);
    const el = document.getElementById("feed");
    if (el) el.scrollTop = 0;
  };

  /* first, last, and a window around the current page -- 453 signals is ten pages, and a
     corpus that grows to eighty must not put eighty buttons on screen */
  const pageNumbers = (cur, count) => {
    if (count <= 7) return Array.from({ length: count }, (_, i) => i + 1);
    const out = [1];
    const from = Math.max(2, cur - 1);
    const to = Math.min(count - 1, cur + 1);
    if (from > 2) out.push("…");
    for (let n = from; n <= to; n += 1) out.push(n);
    if (to < count - 1) out.push("…");
    out.push(count);
    return out;
  };

  /* How many cards each direction filter would show, before it is applied. Counted over
     the tile/search-filtered set so the number matches what clicking it produces. */
  const filterCounts = useMemo(() => {
    const inScope = (cfg.cards || []).filter(visibleExceptDir);
    const out = {};
    (filters || []).forEach((f) => {
      out[f.f] = f.f === "all" ? inScope.length : inScope.filter((c) => filterMatch(c, f.f, filters)).length;
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg, filters, tilePred, feedSearchQuery, data.details]);

  const isFiltered = dirFilter && dirFilter !== "all";
  const activeFilterObj = (filters || []).find((f) => f.f === dirFilter);

  /* paginateFeed already applied `visible` and re-grouped the slice, so this keeps the
     ported shape ({...g, visibleCards}) while showing one page rather than all 453. */
  const groupsWithCards = pageView.groups.map((g) => ({ ...g, visibleCards: g.cards }));

  let topHeaderTitle = "";
  let topHeaderSub = "";

  if (isFiltered && activeFilterObj) {
    topHeaderTitle = activeFilterObj.l || "";
    /* No group strapline here. The filtered feed is flat, and the first group's
       sub-heading ("what's live now") described a grouping the rows on screen no
       longer follow -- a heading that names a structure the page is not showing. */
    topHeaderSub = "";
  } else if (groupsWithCards.length > 0) {
    /* The feed title, NOT the first group's name. This banner is sticky, so naming
       group 0 pinned "Live Opportunities" to the top of the window and left it there
       for all 138 cards below it -- of which three were in that group. The group split
       is by INDEX (`cards.slice(idx, idx + g.n)`), not by content, so the label was
       never a property of what the reader was looking at. Each group now carries its
       own inline header instead; see the `gi > 0` guard removed below. */
    topHeaderTitle = cfg.title || "";
    topHeaderSub = "";
  } else {
    const fallback = (cfg.groups || [])[0] || { h: cfg.title || "", s: "" };
    topHeaderTitle = fallback.h;
    topHeaderSub = "";           // no straplines under section titles (owner request)
  }

  return (
    <div className="ov-wrap">
      {/* FIXED TOP HEADER LINE: Fixed header bar with controls */}
      <div className="feed-grp-h ov-fixed-header">
        <span className="eyebrow">
          {topHeaderTitle} <span className="sub">{topHeaderSub}</span>
        </span>
        {part === "cockpit" ? null : <FeedFilters
          active={tile ? null : dirFilter}
          filters={cfg.hideFilterButtons ? [] : filters}
          onFilter={onFilter}
          onSeq={onSeq}
          seqMode={seqMode}
          searchQuery={feedSearchQuery}
          onSearch={setFeedSearchQuery}
          counts={filterCounts}
        />}
      </div>

      <div className={`ov-body${selected ? " has-sel" : ""}`}>
        <div className="feed v-overview" id="feed">
          {/* the ranked tenders and the projects to win before they tender, above the evidence feed;
              hidden while filtering or searching and past page 1, so it never pushes results down */}
          {pillarKey === "market" && part !== "feed" && (part === "cockpit" || (!isFiltered && !feedSearchQuery && pageView.page === 1)) ? <TenderCockpit onOpen={openTender} /> : null}
          {part === "cockpit" ? null : (<>
          {isFiltered ? (
            <div className="feed-grp">
              {groupsWithCards.flatMap((g) => g.visibleCards).map((c) => (
                <SignalCard
                  card={c}
                  dirWord={labelFor(c)}
                  badgeClass={badgeFor(c)}
                  fresh={c.id === firstVisibleId}
                  key={c.id}
                  onSelect={select}
                  when={signalDate(c, data)}
                  selected={selected === c.id}
                />
              ))}
            </div>
          ) : (
            groupsWithCards.map((g) => (
              <div className="feed-grp" key={g.h}>
                {/* THE GROUP BANNER IS OFF; THE GROUPING IS NOT. Each group used to print
                    its served heading and strapline here -- "Priority — Competitive
                    Threats" over "— rivals winning scale in KSSL categories" -- and both
                    are gone at the operator's request. The split itself is untouched: the
                    groups still cut the feed in the same order, `key={g.h}` still keys on
                    the served heading, and the rule between .feed-grp blocks still shows
                    where one ends and the next begins. */}
                {g.visibleCards.map((c) => (
                  <SignalCard
                    card={c}
                    dirWord={labelFor(c)}
                  badgeClass={badgeFor(c)}
                    fresh={c.id === firstVisibleId}
                    key={c.id}
                    onSelect={select}
                    when={signalDate(c, data)}
                    selected={selected === c.id}
                  />
                ))}
              </div>
            ))
          )}
          {shownCount === 0 ? (
            <div className="empty-note">
              {/* an empty feed with no filter and no query is a served-nothing state;
                  a search miss and a filter miss each say so -- the search miss used
                  to read "no signals served yet" under a box holding the query */}
              {emptyFeedNote({ tile, dirFilter, query: feedSearchQuery })}
            </div>
          ) : (
            <div className="pager">
              <div className="pager-range">
                showing {pageView.from}–{pageView.to} of {shownCount}
                {shownCount !== feed.total ? ` filtered · ${feed.total} total` : " signals"}
              </div>
              {pageView.pageCount > 1 ? (
                <div className="pager-ctl">
                  <button
                    className="pgbtn"
                    disabled={pageView.page <= 1}
                    onClick={() => goPage(pageView.page - 1)}
                    type="button"
                  >
                    ‹ Prev
                  </button>
                  {pageNumbers(pageView.page, pageView.pageCount).map((n, i) =>
                    n === "…" ? (
                      <span className="pgap" key={`gap${i}`}>
                        …
                      </span>
                    ) : (
                      <button
                        className={`pgbtn num${n === pageView.page ? " on" : ""}`}
                        key={n}
                        onClick={() => goPage(n)}
                        type="button"
                      >
                        {n}
                      </button>
                    ),
                  )}
                  <button
                    className="pgbtn"
                    disabled={pageView.page >= pageView.pageCount}
                    onClick={() => goPage(pageView.page + 1)}
                    type="button"
                  >
                    Next ›
                  </button>
                </div>
              ) : null}
            </div>
          )}
          </>)}
        </div>

        {/* Its own boundary as well as the app's: one malformed signal must cost the reader that
            one signal, not the feed they were reading it from. */}
        {selected ? (
          <ErrorBoundary label="signal detail">
            <DetailPanel
              detail={data.details[selected] || (extraDetail && extraDetail.id === selected ? extraDetail : null)}
              onClose={() => setSelected(null)}
              /* a pillar that labels rows by kind (Technology) gives the panel the same label */
              badge={(() => {
                if (!cfg.tagWord) return undefined;
                const card = (cfg.cards || []).find((c) => c.id === selected);
                if (!card || !card.kind) return undefined;
                const st = cfg.panelStance && cfg.panelStance[card.kind];
                if (st) return { word: STANCE_WORD[st], cls: st };
                return { word: labelFor(card), cls: card.kind === "adopt" ? "adopt" : null };
              })()}
            />
          </ErrorBoundary>
        ) : null}
      </div>
    </div>
  );
}
