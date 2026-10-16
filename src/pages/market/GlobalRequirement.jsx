import { useEffect, useMemo, useRef, useState } from "react";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { smartTitleCase } from "../../lib/profile";
import { Review } from "../../components/review/Review";

const has = (v) => v != null && String(v).trim() !== "";
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
/* The fit word is shown as stored; its CSS class is the stored word, lower-cased. */
const fitClass = (v) => (has(v) ? String(v).trim().toLowerCase() : "");

export default function GlobalRequirement() {
  const { data } = useData();
  const { setScope } = useAppState();
  const clientName = (data?.client && (data.client.short || data.client.name)) || "KSSL";

  const reqList = useMemo(() => {
    return data?.globalRequirements || [];
  }, [data]);

  const [country, setCountry] = useState(null);
  const [cat, setCat] = useState(null);
  const [menu, setMenu] = useState(null);
  const [menuQuery, setMenuQuery] = useState("");
  const [sel, setSel] = useState(null);
  const asmtRef = useRef(null);

  useEffect(() => {
    if (asmtRef.current) {
      asmtRef.current.scrollTop = 0;
    }
  }, [sel]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (!e.target.closest(".tp-dd")) setMenu(null);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  // Filtered requirements list
  const filteredList = useMemo(() => {
    return reqList
      .filter((r) => !country || r.country === country)
      .filter((r) => !cat || r.cat === cat)
      .sort((a, b) => (a.dl == null) - (b.dl == null) || (a.dl || 0) - (b.dl || 0));
  }, [reqList, country, cat]);

  // Selected requirement record
  const selectedReq = useMemo(() => {
    return sel ? reqList.find((r) => r.id === sel) : null;
  }, [sel, reqList]);

  const select = (id) => {
    const item = reqList.find((r) => r.id === id);
    if (!item) return;
    setSel(id);
    setScope("requirement", { type: "requirement", data: item }, {
      pillar: "Market",
      view: "Global Requirements",
      selection: `${item.title} (${item.country})`,
    });
  };

  // Header Report integration for Copy / Export / Print
  const report = useMemo(() => {
    const sections = [];
    if (selectedReq) {
      sections.push({
        h: "Selected Requirement",
        rows: [
          ["Title", selectedReq.title],
          ["Buyer", selectedReq.buyer],
          ["Country", selectedReq.country],
          ["Region", selectedReq.region],
          ["Category", selectedReq.cat],
          ["Estimated Value", selectedReq.value],
          ["Deadline", selectedReq.deadline],
          ["Status", selectedReq.status],
          ["KSSL Fit", [selectedReq.ksslFit, selectedReq.ksslModel].filter(has).join(" · ")],
          ["Description", selectedReq.desc],
        ].filter(([, v]) => has(v)),
      });
      if (Array.isArray(selectedReq.specs) && selectedReq.specs.length) {
        sections.push({ h: "Technical Specifications", rows: selectedReq.specs });
      }
      if (selectedReq.strategicAssessment) {
        sections.push({ h: "Strategic Assessment", rows: [["Assessment", selectedReq.strategicAssessment]] });
      }
    }
    sections.push({
      h: `Requirements List (${filteredList.length})`,
      rows: filteredList.map((r) => [
        r.title,
        [r.country, r.buyer, r.cat, r.value, has(r.ksslFit) ? `Fit: ${r.ksslFit}${has(r.ksslModel) ? ` (${r.ksslModel})` : ""}` : ""].filter(has).join(" · "),
      ]),
    });
    return {
      title: "Global Defence Requirements",
      subtitle: [country, cat].filter(Boolean).join(" · ") || `${reqList.length} global requirements tracked`,
      sections,
      payload: { filters: { country, category: cat }, selected: selectedReq, requirements: filteredList },
    };
  }, [selectedReq, filteredList, country, cat, reqList.length]);

  useHeaderReport(report);

  // Facet options
  const countryOptions = useMemo(() => {
    const counts = {};
    reqList
      .filter((r) => !cat || r.cat === cat)
      .forEach((r) => {
        if (r.country) counts[r.country] = (counts[r.country] || 0) + 1;
      });
    const q = menuQuery.trim().toLowerCase();
    return Object.entries(counts)
      .map(([v, n]) => ({ v, n }))
      .filter((o) => !q || o.v.toLowerCase().includes(q))
      .sort((a, b) => b.n - a.n || a.v.localeCompare(b.v));
  }, [reqList, cat, menuQuery]);

  const catOptions = useMemo(() => {
    const counts = {};
    reqList
      .filter((r) => !country || r.country === country)
      .forEach((r) => {
        if (r.cat) counts[r.cat] = (counts[r.cat] || 0) + 1;
      });
    return Object.entries(counts)
      .map(([v, n]) => ({ v, n }))
      .sort((a, b) => b.n - a.n || a.v.localeCompare(b.v));
  }, [reqList, country]);

  const renderDropdown = (which, label, value, setValue, options) => (
    <div className="tp-dd" data-tpdd={which}>
      <div
        className={`tp-dd-input${value ? " has-val" : ""}`}
        onClick={() => {
          setMenuQuery("");
          setMenu(menu === which ? null : which);
        }}
        role="button"
        tabIndex={0}
      >
        <span className="ddlbl">{label}</span>
        <span className={`ddval${value ? "" : " placeholder"}`}>{value || "All"}</span>
        <span className="caret">▾</span>
        <span
          className="ddclear"
          onClick={(e) => {
            e.stopPropagation();
            setValue(null);
          }}
        >
          ×
        </span>
      </div>
      <div className={`tp-dd-menu${menu === which ? " open" : ""}`}>
        {which === "country" && (
          <div className="tp-dd-search">
            <input
              autoComplete="off"
              onChange={(e) => setMenuQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder="Search country…"
              type="text"
              value={menu === "country" ? menuQuery : ""}
            />
          </div>
        )}
        <div
          className="tp-dd-pick tp-dd-all"
          onClick={() => {
            setValue(null);
            setMenu(null);
          }}
        >
          All {which === "country" ? "countries" : "categories"} ({options.length})
        </div>
        {options.map(({ v, n }) => (
          <div
            className="tp-dd-pick"
            key={v}
            onClick={() => {
              setValue(v);
              setSel(null);
              setMenu(null);
            }}
          >
            {v}
            <span className="m">{n}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className={`tp-view v-tender ${selectedReq ? "has-sel" : "no-sel"}`}>
      <div className="tp-list">
        <div className="tp-fbar">
          <span className="eyebrow">Filter</span>
          {renderDropdown("country", "Country", country, setCountry, countryOptions)}
          {renderDropdown("cat", "Category", cat, setCat, catOptions)}
          <span className="sortnote">sorted by requirement deadline</span>
        </div>

        <div id="tp-cards">
          {filteredList.length ? (
            filteredList.map((row) => {
              /* the stored fit word, as stored; no word stored, no fit line */
              const fit = row.ksslFit;

              return (
                <div
                  className={`tcard${sel === row.id ? " sel" : ""}`}
                  key={row.id}
                  onClick={() => select(row.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      select(row.id);
                    }
                  }}
                >
                  <div className="trow1">
                    <div className="ttl">{smartTitleCase(row.title)}</div>
                    {has(row.deadline) ? <span className="ddl normal">{row.deadline}</span> : null}
                  </div>

                  <div className="tpgrid">
                    {[
                      ["Buyer", row.buyer],
                      ["Country", row.country],
                      ["Category", row.cat],
                      ["Value", row.value],
                      ["Status", row.status],
                    ].filter(([, v]) => has(v)).map(([k, v]) => (
                      <div className="tpp" key={k}>
                        <span className="tpk">{k}</span>
                        <span className="tpv" title={v}>{v}</span>
                      </div>
                    ))}
                  </div>

                  {has(fit) ? (
                    <div className="fitbar">
                      <span className="fitlab">{clientName} fit</span>
                      <span className={`fitpct grade ${fitClass(fit)}`}>{cap(fit)}</span>
                    </div>
                  ) : null}
                  <Review src={row._src} />
                </div>
              );
            })
          ) : (
            <div className="tp-list-empty">
              {country || cat ? "No requirements match this filter" : "No global requirements are on record."}
            </div>
          )}
        </div>
      </div>

      {/* Side Assessment Drawer */}
      <div className="tp-asmt" id="tp-asmt">
        {selectedReq ? (
          <div id="tp-asmt-body" style={{ display: "flex", flex: 1, flexDirection: "column", height: "100%", overflow: "hidden" }}>
            <div className="tp-asmt-scroll" ref={asmtRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: "24px" }}>
              <div className="tp-asmt-h">
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
                </div>
                <span className="eyebrow">Requirement Intelligence</span>
                <div className="ct">{smartTitleCase(selectedReq.title)}</div>
                <Review src={selectedReq._src} />
                <div className="sub" style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "8px" }}>
                  <div>{[selectedReq.buyer, selectedReq.country, selectedReq.value].filter(Boolean).join(" · ")}</div>
                  <div>{[selectedReq.region, selectedReq.cat, selectedReq.deadline, selectedReq.status].filter(Boolean).join(" · ")}</div>
                </div>
              </div>

              {/* Requirement Scope & Context */}
              {selectedReq.desc && (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Requirement Scope</span>
                  <div className="cd-prose">{selectedReq.desc}</div>
                </div>
              )}

              {/* Key Specifications */}
              {Array.isArray(selectedReq.specs) && selectedReq.specs.length > 0 && (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Target Specifications</span>
                  <div style={{ marginTop: "8px" }}>
                    {selectedReq.specs.map(([label, val], idx) => (
                      <div className="kv" key={idx}>
                        <span className="k">{label}</span>
                        <span className="v">{val}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Strategic Fit: stored fit word and model only */}
              {has(selectedReq.ksslFit) || has(selectedReq.ksslModel) ? (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">{clientName} Platform Match</span>
                  <div className="tp-fit-verdict">
                    {[has(selectedReq.ksslFit) ? `${cap(selectedReq.ksslFit)} fit` : "", selectedReq.ksslModel].filter(has).join(" · ")}
                  </div>
                </div>
              ) : null}

              {/* Strategic Assessment */}
              {selectedReq.strategicAssessment && (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Strategic Assessment</span>
                  <div className="cd-prose">{selectedReq.strategicAssessment}</div>
                </div>
              )}

              {/* Source */}
              {Array.isArray(selectedReq.sources) && selectedReq.sources.length > 0 && (
                <div className="tp-asmt-sec">
                  <span className="eyebrow">Source</span>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "6px" }}>
                    {selectedReq.sources.filter((src) => has(src.url)).map((src, i) => (
                      <a
                        key={i}
                        className="ovt-host"
                        href={src.url}
                        rel="noreferrer"
                        style={{ color: "var(--fav-badge)", textDecoration: "none", fontSize: "11px", fontFamily: "var(--mono)" }}
                        target="_blank"
                      >
                        ↗ {src.label || src.url}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="tp-asmt-empty" style={{ padding: "40px 20px", textAlign: "center", color: "var(--d-txt-4)", fontFamily: "var(--mono)", fontSize: "11px" }}>
            Select a global requirement to inspect operational specifications, strategic match, and intelligence assessment.
          </div>
        )}
      </div>
    </div>
  );
}
