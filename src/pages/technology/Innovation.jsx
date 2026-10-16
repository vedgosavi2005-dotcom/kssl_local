import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import ScopeChat from "../../components/scopeChat/ScopeChat";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { srcChips } from "../../lib/html";
import { cls, has, filterInnovations } from "../../lib/innovation";
import { Review } from "../../components/review/Review";

/* Every value on this page is a stored column: maturity_label, position_label,
   assessment_badge, horizon, the companies and sources behind the record. A column the
   record leaves empty is not printed. */
/* one shared empty list, so a domain with no rows does not mint a new array per render
   (the header report is memoised on `list`) */
const EMPTY = [];

const Section = ({ label, lead, children }) => (
  <div className={`tech-d-sec${lead ? " lead" : ""}`}>
    <span className={`eyebrow${lead ? " accent" : ""}`}>{label}</span>
    <div className={lead ? "lead-body" : "body"}>{children}</div>
  </div>
);

export default function Innovation() {
  const { data } = useData();
  const { setScope, takePending, searchQuery } = useAppState();
  const clientName = (data.client && (data.client.short || data.client.name)) || "KSSL";

  const getSavedInnov = () => {
    try {
      const s = localStorage.getItem("kssl_innov_state");
      return s ? JSON.parse(s) : {};
    } catch (e) { return {}; }
  };
  const savedInnov = getSavedInnov();

  const [cat, setCat] = useState(savedInnov.cat || (data.techCats && data.techCats[0] ? data.techCats[0].id : null));
  const [sel, setSel] = useState(savedInnov.sel !== undefined ? savedInnov.sel : null);
  const detRef = useRef(null);

  useEffect(() => {
    if (detRef.current) {
      detRef.current.scrollTop = 0;
    }
  }, [sel, cat]);

  useEffect(() => {
    try {
      localStorage.setItem("kssl_innov_state", JSON.stringify({ cat, sel }));
    } catch (e) {}
  }, [cat, sel]);

  const list = useMemo(() => data.innovations[cat] || EMPTY, [data.innovations, cat]);
  const iv = sel !== null ? list[sel] : null;

  /* The rows on screen: the domain's list narrowed to the global search box, as the
     box's footer promises ("the open page is filtered to this query where it has a
     list"). Each keeps its ORIGINAL index -- selection is by index into `list`. */
  const shown = useMemo(() => filterInnovations(list, searchQuery), [list, searchQuery]);
  const filtering = String(searchQuery || "").trim() !== "";

  /* A domain the reader picks starts unselected. Carrying the index across kept
     "row 2" selected in a list the reader had not chosen it from. The search jump
     below sets the domain directly and then selects by title. */
  const pickCat = (id) => {
    setCat(id);
    setSel(null);
  };

  /* Opened from the global search: switch to the row's domain first, then select it by
     title once `list` is that domain's list. */
  const [pendingTitle, setPendingTitle] = useState(null);
  useEffect(() => {
    const p = takePending("innovation");
    if (p && p.title) {
      if (p.catId && data.innovations[p.catId]) setCat(p.catId);
      setPendingTitle(p.title);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takePending]);
  useEffect(() => {
    if (pendingTitle === null) return;
    const i = list.findIndex((x) => x && x.t === pendingTitle);
    if (i >= 0) select(i);
    setPendingTitle(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingTitle, list]);

  const select = (i) => {
    const item = list[i];
    if (!item) return;
    setSel(i);
    setScope("tech", { type: "tech", data: item }, {
      pillar: "Technology",
      view: "Innovation Pipeline",
      selection: item.t,
    });
  };

  const catName = (data.techCats.find((c) => c.id === cat) || {}).name || "";
  const companyText = (x) =>
    (x.companies || []).length
      ? x.companies.map((c) => [c.name, c.relationship && `(${c.relationship})`].filter(has).join(" ")).join(", ")
      : x.driver;

  /* What the header's Copy / Export / Print act on: the open innovation with every
     stored field it carries, or the domain's list when none is open. */
  const headerReport = useMemo(() => {
    if (iv) {
      return {
        title: iv.t,
        subtitle: [catName, iv.matLabel].filter(has).join(" · "),
        sections: [
          {
            h: "Status",
            rows: [
              ["Maturity", iv.matLabel],
              ["Driven by", companyText(iv)],
              ["Horizon", iv.horizon],
              [`${clientName} position`, iv.gapLabel],
              ["Status", iv.listStatus],
            ].filter(([, v]) => has(v)),
          },
          has(iv.impact) ? { h: `Why this matters to ${clientName}`, rows: [iv.impact] } : null,
          has(iv.compNote) ? { h: "Competitive landscape", rows: [iv.compNote] } : null,
          has(iv.whatsNew) ? { h: "What's new", rows: [iv.whatsNew] } : null,
          has(iv.body) ? { h: "Background", rows: [iv.body] } : null,
          ...(iv.analysis || []).map((a) => ({ h: a.label, rows: [a.text] })),
          (iv.srcs || []).length ? { h: "Sources", rows: iv.srcs.map((s) => [s.label || "Source", s.url || ""]) } : null,
        ].filter(Boolean),
        payload: { domain: catName, innovation: iv },
      };
    }
    return {
      title: `${catName} · Innovations`,
      subtitle: `${list.length} tracked in this domain · none selected`,
      sections: [
        {
          h: "Innovations",
          rows: list.map((x) => [x.t, [x.matLabel, x.driver, x.horizon].filter(has).join(" · ")]),
        },
      ],
      payload: { domain: catName, innovations: list },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iv, list, catName, clientName]);
  useHeaderReport(headerReport);

  const statusRows = iv
    ? [
        ["Maturity", iv.matLabel],
        ["Driven by", companyText(iv)],
        ["Horizon", iv.horizon],
        [`${clientName} position`, iv.gapLabel],
        ["Status", iv.listStatus],
      ].filter(([, v]) => has(v))
    : [];
  const chips = iv ? srcChips(iv.srcs && iv.srcs.length ? iv.srcs : null) : "";

  return (
    <div className="tech-view v-innovation">
      <div className="tech-cats" id="tech-cats">
        {data.techCats.map((c) => (
          <div
            className={`tech-cat${cat === c.id ? " active" : ""}`}
            key={c.id}
            onClick={() => pickCat(c.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                pickCat(c.id);
              }
            }}
          >
            {c.num != null ? <span className="cc">{String(c.num).padStart(2, "0")}</span> : null}
            {c.name}
          </div>
        ))}
      </div>

      <div className={`tech-body ${iv ? "has-sel" : "no-sel"}`} id="tech-body">
        <div className="tech-list" id="tech-list">
          <div className="tech-list-h">
            <span className="eyebrow">{catName} · Innovations</span>
            {filtering ? (
              <span className="lh-note">
                {`${shown.length} of ${list.length} match "${String(searchQuery).trim()}"`}
              </span>
            ) : null}
          </div>
          {filtering && list.length && !shown.length ? (
            <div className="empty-note" style={{ padding: "18px 0" }}>
              {`no innovation in this domain matches "${String(searchQuery).trim()}" - clear the search box or pick another domain`}
            </div>
          ) : null}
          {shown.map(({ item, index: i }) => (
            <div
              className={`innov${sel === i ? " sel" : ""}`}
              key={`${item.t}-${i}`}
              onClick={() => select(i)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  select(i);
                }
              }}
            >
              <div className="ih">
                <span className="it">{item.t}</span>
                {/* the .mat box only exists when a maturity is stored */}
                {has(item.matLabel) ? (
                  <span className={`mat ${cls(item.mat)}`}>{item.matLabel}</span>
                ) : null}
              </div>
              {has(item.s || item.summary) ? <div className="ides">{item.s || item.summary}</div> : null}
              {/* built from the parts the record HAS, so a missing field leaves no separator */}
              <div className="imeta">
                {[
                  has(item.driver) ? <span key="driver">{item.driver}</span> : null,
                  has(item.horizon) ? <span key="horizon">{item.horizon}</span> : null,
                  has(item.gapLabel) ? (
                    <span className={`gappill ${cls(item.gap)}`} key="gap">
                      {item.gapLabel}
                    </span>
                  ) : null,
                ]
                  .filter(Boolean)
                  .map((el, n) => (
                    <Fragment key={el.key}>
                      {n ? <span className="sep">·</span> : null}
                      {el}
                    </Fragment>
                  ))}
              </div>
              <Review src={item._src} />
            </div>
          ))}
        </div>

        {/* No inline `display` — CSS owns show/hide via .tech-body.has-sel/.no-sel. */}
        <div className="tech-det" id="tech-det" style={{ height: "100%", overflow: "hidden", flexDirection: "column" }}>
          <div id="tech-dossier-inner" style={{ display: "flex", flex: 1, flexDirection: "column", height: "100%", overflow: "hidden" }}>
            <div className="tech-dossier-scroll" ref={detRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: "24px" }}>
              <div className={`tech-d-h ${iv ? cls(iv.gap) : ""}`} id="tech-d-h">
                {iv ? (
                  <>
                    <div className="ctx-h-actions">
                      <button
                        aria-label="Close"
                        className="col-close"
                        onClick={() => setSel(null)}
                        title="Close"
                        type="button"
                      >
                        ✕
                      </button>
                      {/* the stored assessment_badge, as stored */}
                      {has(iv.badge) ? <span className={`dirpill ${cls(iv.gap)}`}>{iv.badge}</span> : null}
                    </div>
                    <span className="eyebrow">Innovation Detail</span>
                    <div className="ct">{iv.t}</div>
                    <Review src={iv._src} />
                    <div className="sub">
                      {[iv.matLabel, iv.horizon, iv.gapLabel]
                        .filter(has)
                        .map((p, n) => (
                          <Fragment key={p}>
                            {n ? <span className="sep">·</span> : null}
                            <span>{p}</span>
                          </Fragment>
                        ))}
                    </div>
                  </>
                ) : null}
              </div>
              <div id="tech-d-body">
                {iv ? (
                  <>
                    {has(iv.gapLabel) && has(iv.gap) ? <div className={`tech-verdict-band ${cls(iv.gap)}`}>{iv.gapLabel}</div> : null}
                    {has(iv.impact) ? <Section label={`Why this matters to ${clientName}`} lead>{iv.impact}</Section> : null}
                    {has(iv.compNote) ? <Section label="Competitive landscape" lead>{iv.compNote}</Section> : null}
                    {has(iv.whatsNew) ? <Section label="What's new" lead>{iv.whatsNew}</Section> : null}
                    {has(iv.body) ? <Section label="Background · what it is">{iv.body}</Section> : null}
                    {(iv.analysis || []).map((a, i) => (
                      <Section key={`${a.code}-${i}`} label={a.label}>{a.text}</Section>
                    ))}
                    {statusRows.length || chips ? (
                      <div className="tech-d-sec">
                        <span className="eyebrow">Status</span>
                        {statusRows.map(([k, v]) => (
                          <div className="tech-kv" key={k}>
                            <span className="k">{k}</span>
                            <span className="v">{v}</span>
                          </div>
                        ))}
                        {chips ? (
                          <div className="tech-kv">
                            <span className="k">Sources</span>
                            <span className="v" dangerouslySetInnerHTML={{ __html: chips }} />
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>
            </div>
            <ScopeChat placeholder="Ask about this technology…" scopeKey="tech" />
          </div>
        </div>
      </div>
    </div>
  );
}
