import { useEffect, useMemo, useState } from "react";
import GeoMap from "../../components/geoMap/GeoMap";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { activityClass, activityLabels } from "../../lib/geoBadge";
import { formatDate } from "../../utils/formatDate";
import { Review } from "../../components/review/Review";

/* Enumerations this page reads (documented for the prompts), compared case-insensitively and
   shown as stored when outside the set:
     overlap_status       confirmed | category | none     (presence row)
     decision_level       1 = KSSL behind, 2 = near parity, 3 = KSSL ahead   (product match)
     better_side          client | competitor | level     (match specification)
     threat_level         threat | watch | fav            (competitor dot)
     activity_type        free text; lp / pt / ex / sv only pick a dot colour */

const lc = (v) => String(v == null ? "" : v).toLowerCase();
const valueOrNull = (value) => (value === null || value === undefined || value === "" ? null : String(value));
const compact = (values) => values.filter(Boolean);

const OVERLAP = {
  confirmed: { label: "Confirmed overlap", tier: "spec" },
  category: { label: "Category overlap", tier: "cat" },
  none: { label: "No indexed overlap", tier: "none" },
};
/* the stored overlap_status of a presence set: the first non-empty one, as {label, tier} */
function overlapOf(presences) {
  const status = (presences || []).map((p) => p.overlap).find(Boolean);
  if (!status) return null;
  return OVERLAP[lc(status)] || { label: status, tier: "none" };
}

const levelClass = (level) => (level === 1 ? "threat" : level === 3 ? "fav" : "");
const CLIENT_SIDE = ["client", "kssl", "bf"];
const RIVAL_SIDE = ["competitor", "rival", "comp"];

function threatClass(value) {
  return lc(value);
}

function footprintCountries(data, geo) {
  const preferred = data?.geoCountries || [];
  return preferred.map((name) => {
    const comps = geo.compsInCountry(name);
    const rows = comps.reduce((sum, company) => sum + geo.productsFor(company.id, name).length, 0);
    return { name, rows, companies: comps.length };
  }).filter((country) => country.companies > 0);
}

export default function Geo() {
  const { data, geo } = useData();
  const { setScope } = useAppState();
  const [selectedComp, setSelectedComp] = useState(null);
  const [selectedCountry, setSelectedCountry] = useState(null);
  const [pair, setPair] = useState(null);
  const [selectedRowIndex, setSelectedRowIndex] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [activeMenu, setActiveMenu] = useState(null);
  const [menuSearch, setMenuSearch] = useState("");
  const [drillBack, setDrillBack] = useState(false);

  const clientKey = data?.client?.id;
  const clientName = data?.client?.short || data?.client?.name || "";

  useEffect(() => {
    const closeMenus = (event) => { if (!event.target.closest(".geo-dd")) setActiveMenu(null); };
    document.addEventListener("click", closeMenus);
    return () => document.removeEventListener("click", closeMenus);
  }, []);

  const closeDetail = () => {
    setShowDetail(false); setSelectedComp(null); setSelectedCountry(null); setPair(null); setSelectedRowIndex(null); setDrillBack(false);
  };

  const competitorsList = useMemo(() => (data?.geoComps || [])
    .filter((company) => !company.isBf && geo.countriesForComp(company.id).length > 0)
    .map((company) => {
      const profile = data.competitors?.[company.id] || {};
      return { ...company, cid: company.id, name: company.name || profile.name || company.id, presenceCount: geo.countriesForComp(company.id).length, threat: profile.threat };
    })
    .sort((a, b) => a.name.localeCompare(b.name)), [data, geo]);

  const countriesList = useMemo(() => footprintCountries(data, geo), [data, geo]);

  const ownRowsForCountry = useMemo(() => (selectedCountry && clientKey ? geo.productsFor(clientKey, selectedCountry) : []), [selectedCountry, clientKey, geo]);
  const ownPresences = useMemo(() => (selectedCountry && clientKey ? geo.presencesFor(clientKey, selectedCountry) : []), [selectedCountry, clientKey, geo]);

  const compsInSelectedCountry = useMemo(() => {
    if (!selectedCountry) return [];
    return geo.compsInCountry(selectedCountry)
      .filter((company) => !company.isBf)
      .map((company) => {
        const presences = geo.presencesFor(company.id, selectedCountry);
        return { ...company, name: company.name || company.id, rows: geo.productsFor(company.id, selectedCountry), presences, overlap: overlapOf(presences) };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [selectedCountry, geo]);

  const countriesForSelectedComp = useMemo(() => !selectedComp ? [] : geo.countriesForComp(selectedComp).map((country) => {
    const presences = geo.presencesFor(selectedComp, country);
    return { country, rows: geo.productsFor(selectedComp, country), presences, overlap: overlapOf(presences) };
  }), [selectedComp, geo]);

  const activeRows = pair ? geo.productsFor(pair.cid, pair.country) : [];
  const activePresences = pair ? geo.presencesFor(pair.cid, pair.country) : [];
  const currentRow = selectedRowIndex != null ? activeRows[selectedRowIndex] || null : null;
  const locationOf = (country) => (data.geoLocations || []).find((l) => l.name === country) || null;

  const selectedCompany = selectedComp ? data.competitors?.[selectedComp] || {} : null;
  const selectedCompanyName = competitorsList.find((company) => company.cid === selectedComp)?.name || selectedCompany?.name || selectedComp;

  const headerDetails = useMemo(() => {
    if (pair) {
      const companyName = competitorsList.find((company) => company.cid === pair.cid)?.name || data.competitors?.[pair.cid]?.name || pair.cid;
      const activityCounts = activeRows.reduce((counts, row) => { if (row.c) counts[row.c] = (counts[row.c] || 0) + 1; return counts; }, {});
      return { kind: "Products supplied", title: `${companyName} → ${pair.country}`, sub: `${activeRows.length} footprint record${activeRows.length === 1 ? "" : "s"} in this market`, pills: Object.entries(activityCounts).map(([label, count]) => `${count} ${label}`) };
    }
    if (selectedCountry) {
      const confirmed = compsInSelectedCountry.filter((item) => item.overlap?.tier === "spec").length;
      const category = compsInSelectedCountry.filter((item) => item.overlap?.tier === "cat").length;
      const overlapCopy = confirmed || category ? ` · ${confirmed} confirmed overlap${category ? `, ${category} category overlap` : ""}` : "";
      const summary = locationOf(selectedCountry)?.summary;
      return { kind: "Market", title: selectedCountry, sub: `${compsInSelectedCountry.length} competitor${compsInSelectedCountry.length === 1 ? "" : "s"} active${summary ? ` · ${summary}` : ""}${overlapCopy}` };
    }
    if (selectedComp) return { kind: "Competitor global footprint", title: selectedCompanyName, sub: `${countriesForSelectedComp.length} market${countriesForSelectedComp.length === 1 ? "" : "s"} with served footprint records` };
    const totalRows = countriesList.reduce((sum, country) => sum + country.rows, 0);
    return { kind: `${clientName} global footprint`, title: `${clientName} Geo Footprint`.trim(), sub: `${competitorsList.length} tracked competitors · ${countriesList.length} served markets · ${totalRows} footprint records` };
  }, [pair, selectedCountry, activeRows, selectedComp, selectedCompanyName, competitorsList, compsInSelectedCountry, countriesForSelectedComp, data, clientName, countriesList]);

  const headerReport = useMemo(() => ({
    title: headerDetails.title,
    subtitle: headerDetails.sub,
    sections: [{
      heading: "Footprint records",
      facts: activeRows.map((row) => [
        row.name,
        compact([row.c, valueOrNull(row.since)]).join(" · "),
      ]),
    }],
    payload: { country: selectedCountry, competitor: selectedComp, pair },
  }), [
    headerDetails.title,
    headerDetails.sub,
    activeRows.length,
    pair?.cid,
    pair?.country,
    selectedCountry,
    selectedComp,
    data,
  ]);

  useHeaderReport(headerReport);

  useEffect(() => {
    setScope("competitive", { country: selectedCountry, competitor: selectedComp, platforms: activeRows.length }, { pillar: "Competitive", view: "Geo Footprint", selection: headerDetails.title });
  }, [selectedCountry, selectedComp, activeRows.length, headerDetails.title, setScope]);

  const selectCountry = (country) => { setSelectedCountry(country); setSelectedComp(null); setPair(null); setSelectedRowIndex(null); setDrillBack(false); setShowDetail(true); };
  const selectCompetitor = (cid) => { setSelectedComp(cid); setSelectedCountry(null); setPair(null); setSelectedRowIndex(null); setDrillBack(false); setShowDetail(true); };
  const selectPair = (cid, country, fromCountry = false) => { setSelectedComp(cid); setSelectedCountry(country); setPair({ cid, country }); setSelectedRowIndex(null); setDrillBack(fromCountry); setShowDetail(true); };

  return (
    <div className="geo-view v-geo" style={{ position: "relative" }}>
      <div className="geo-bar">
        <span className="eyebrow" style={{ marginRight: 6 }}>Geo Footprint</span>
        <div className="geo-dd">
          <div className={`geo-dd-input${selectedComp ? " has-val" : ""}`} onClick={(event) => { event.stopPropagation(); setActiveMenu(activeMenu === "comp" ? null : "comp"); setMenuSearch(""); }}><span className="ddlbl">Competitor</span><span className={`ddval${!selectedComp ? " placeholder" : ""}`}>{selectedComp ? selectedCompanyName : `All Rivals (${competitorsList.length})`}</span><span className="caret">▾</span>{selectedComp && <span className="ddclear" onClick={(event) => { event.stopPropagation(); setSelectedComp(null); setPair(null); if (!selectedCountry) setShowDetail(false); }}>✕</span>}</div>
          <div className={`geo-dd-menu${activeMenu === "comp" ? " open" : ""}`}><div className="geo-dd-search"><input type="text" placeholder="Search competitor…" value={menuSearch} onChange={(event) => setMenuSearch(event.target.value)} onClick={(event) => event.stopPropagation()} /></div>{competitorsList.filter((company) => !menuSearch || company.name.toLowerCase().includes(menuSearch.toLowerCase())).map((company) => <div key={company.cid} className={`geo-pick${selectedComp === company.cid ? " sel" : ""}`} onClick={() => { selectCompetitor(company.cid); setActiveMenu(null); }}><span className={`pk-dot ${threatClass(company.threat)}`} /><span className="pk-nm">{company.name}</span><span className="pk-meta">{company.presenceCount} markets</span></div>)}</div>
        </div>
        <div className="geo-dd">
          <div className={`geo-dd-input${selectedCountry ? " has-val" : ""}`} onClick={(event) => { event.stopPropagation(); setActiveMenu(activeMenu === "country" ? null : "country"); setMenuSearch(""); }}><span className="ddlbl">Country</span><span className={`ddval${!selectedCountry ? " placeholder" : ""}`}>{selectedCountry || `All Markets (${countriesList.length})`}</span><span className="caret">▾</span>{selectedCountry && <span className="ddclear" onClick={(event) => { event.stopPropagation(); setSelectedCountry(null); setPair(null); if (!selectedComp) setShowDetail(false); }}>✕</span>}</div>
          <div className={`geo-dd-menu${activeMenu === "country" ? " open" : ""}`}><div className="geo-dd-search"><input type="text" placeholder="Search country / market…" value={menuSearch} onChange={(event) => setMenuSearch(event.target.value)} onClick={(event) => event.stopPropagation()} /></div>{countriesList.filter((country) => !menuSearch || country.name.toLowerCase().includes(menuSearch.toLowerCase())).map((country) => <div key={country.name} className={`geo-pick${selectedCountry === country.name ? " sel" : ""}`} onClick={() => { selectCountry(country.name); setActiveMenu(null); }}><span className="pk-dot ovl" /><span className="pk-nm">{country.name}</span><span className="pk-meta">{country.rows} records</span></div>)}</div>
        </div>
        {(selectedComp || selectedCountry || showDetail) && <button type="button" className="geo-back geo-clear-action" onClick={closeDetail}>Clear / View Full Map</button>}
      </div>

      <div className="geo-content-map"><div className="geo-map-full"><GeoMap data={data} geo={geo} selectedCountry={selectedCountry || pair?.country || null} onSelectCountry={selectCountry} /></div></div>

      {showDetail && (selectedCountry || pair || selectedComp) && <div className="geo-det-overlay" id="geo-det">
        <div className="geo-d-h geo-overlay-header"><div className="geo-hdr-controls">{drillBack && <button type="button" className="geo-back geo-overlay-btn" onClick={() => { setPair(null); setSelectedRowIndex(null); setDrillBack(false); }}>‹ Back</button>}<button type="button" className="geo-close-btn" onClick={closeDetail} title="Close and view full map" aria-label="Close">✕</button></div><span className="eyebrow geo-overlay-eyebrow">{headerDetails.kind}</span><div className="geo-hdr-main"><div className="ct">{headerDetails.title}</div><div className="geo-rel-sub">{headerDetails.sub}</div>{headerDetails.pills?.length > 0 && <div className="geo-header-pills">{headerDetails.pills.map((pill) => <span key={pill} className="geo-header-pill">{pill}</span>)}</div>}</div></div>
        <div className={`geo-det-overlay-body ${pair ? `geo-products-mode${currentRow ? " has-comparison" : ""}` : selectedCountry ? "geo-market-mode" : "has-prod"}`}>
          {selectedCountry && !pair && <CountryMarketView clientName={clientName} country={selectedCountry} location={locationOf(selectedCountry)} ownRows={ownRowsForCountry} ownPresences={ownPresences} companies={compsInSelectedCountry} onSelectPair={selectPair} />}
          {pair && <SuppliedProductsView clientName={clientName} companyName={selectedCompanyName} country={pair.country} rows={activeRows} presences={activePresences} currentRow={currentRow} selectedRowIndex={selectedRowIndex} onSelectRow={(index) => setSelectedRowIndex(index)} />}
          {selectedComp && !pair && !selectedCountry && <><div className="geo-rel-overlay-list"><div className="geo-list-pad"><span className="eyebrow geo-list-title">Markets for {selectedCompanyName} ({countriesForSelectedComp.length})</span>{countriesForSelectedComp.map((market) => <div key={market.country} className={`geo-rel-item${market.overlap ? ` ov-${market.overlap.tier}` : ""}`} onClick={() => selectPair(selectedComp, market.country)}><div className={`ri-act ${activityClass(market.rows[0]?.c || market.presences[0]?.activity)}`} /><div className="ri-main"><div className="ri-nm">{market.country} {market.overlap && <span className={`geo-ovb ${market.overlap.tier}`}>{market.overlap.label}</span>}</div><div className="ri-desc">{market.rows.length} footprint record{market.rows.length === 1 ? "" : "s"}</div>{(market.presences[0]?.summary || market.rows[0]?.name) && <span className="ri-tag">{market.presences[0]?.summary || market.rows[0]?.name}</span>}{market.presences.map((p) => <Review key={p.id} src={p._src} />)}</div><span className="ri-chev">›</span></div>)}</div></div><div className="geo-det-product-sec"><CompetitorDetail company={selectedCompany} name={selectedCompanyName} countries={countriesForSelectedComp} /></div></>}
        </div>
      </div>}
    </div>
  );
}

function CountryMarketView({ clientName, country, location, ownRows, ownPresences, companies, onSelectPair }) {
  const confirmed = companies.filter((company) => company.overlap?.tier === "spec").length;
  const category = companies.filter((company) => company.overlap?.tier === "cat").length;
  const ownActs = activityLabels({ presences: ownPresences, rows: ownRows });
  const hasOwn = ownPresences.length > 0 || ownRows.length > 0;
  return <div className="geo-market-view">
    <div className="geo-market-list-head"><span className="eyebrow geo-list-title">Companies active in {country}</span><span className="geo-market-count">{companies.length + (hasOwn ? 1 : 0)} tracked entities</span></div>
    <Review src={location?._src} />
    {location?.summary && <div className="geo-note"><span className="geo-field-label">{clientName} footprint</span><p>{location.summary}</p></div>}
    {hasOwn && <div className="geo-market-row own"><div className={`ri-act ${activityClass(ownRows[0]?.c || ownPresences[0]?.activity)}`} /><div className="ri-main"><div className="ri-nm">{clientName}</div><div className="ri-desc">{compact([`${ownRows.length} footprint record${ownRows.length === 1 ? "" : "s"}`, ownActs.join(" / ")]).join(" · ")}</div>{(ownPresences[0]?.summary || ownRows[0]?.name) && <span className="ri-tag">{ownPresences[0]?.summary || ownRows[0]?.name}</span>}{ownPresences.map((p) => <Review key={p.id} src={p._src} />)}</div><span className="geo-market-mark">Own footprint</span></div>}
    {companies.length > 0 ? companies.map((company) => {
      const acts = activityLabels({ presences: company.presences, rows: company.rows });
      const ranges = company.presences.map((p) => p.ranges).find(Boolean);
      return <div key={company.id} className={`geo-market-row${company.overlap ? ` ov-${company.overlap.tier}` : ""}`} onClick={() => onSelectPair(company.id, country, true)}><div className={`ri-act ${activityClass(company.rows[0]?.c || company.presences[0]?.activity)}`} /><div className="ri-main"><div className="ri-nm">{company.name} {company.overlap && <span className={`geo-ovb ${company.overlap.tier}`}>{company.overlap.label}</span>}</div><div className="ri-desc">{compact([`${company.rows.length} footprint record${company.rows.length === 1 ? "" : "s"}`, acts.join(" / "), ranges ? `meets KSSL in ${ranges}` : ""]).join(" · ")}</div>{(company.presences[0]?.summary || company.rows[0]?.name) && <span className="ri-tag">{company.presences[0]?.summary || company.rows[0]?.name}</span>}{company.presences.map((p) => <Review key={p.id} src={p._src} />)}</div><span className="ri-chev">›</span></div>;
    }) : <div className="geo-rel-empty">No competitor footprint rows are served for this market.</div>}
    <div className="geo-market-footnote">{confirmed || category ? `${confirmed} confirmed overlap${confirmed === 1 ? "" : "s"}${category ? ` · ${category} category overlap${category === 1 ? "" : "s"}` : ""}. ` : ""}Select a company to inspect its supplied records.</div>
  </div>;
}

function SuppliedProductsView({ clientName, companyName, country, rows, presences, currentRow, selectedRowIndex, onSelectRow }) {
  const matchedCount = rows.filter((row) => row.matches.length).length;
  return <div className="geo-products-view">
    <div className="geo-products-list">
      <div className="geo-products-list-head"><div><span className="eyebrow geo-list-title">Products and footprint records {companyName} serves</span><div className="geo-products-sub">Select a record to see its detail and any KSSL comparison on file.</div></div><span className="geo-products-count">{rows.length} RECORDS · {matchedCount} MATCHED TO A KSSL COMPARISON</span></div>
      {presences.length > 0 && <PresenceFacts presences={presences} />}
      {rows.map((row, index) => {
        const match = row.matches[0] || null;
        return <div key={row.id} className={`geo-product-record${selectedRowIndex === index ? " active" : ""}`} onClick={() => onSelectRow(index)}><div className={`ri-act ${activityClass(row.c || presences[0]?.activity)}`} /><div className="geo-product-record-main"><div className="geo-product-name">{row.name}</div><div className="geo-product-meta">{compact([row.c, row.since ? `Since ${formatDate(row.since)}` : ""]).join(" · ")}</div><div className={`geo-product-counter${match ? " matched" : " unmatched"}`}><span className="geo-counter-label">{clientName.toUpperCase()} COUNTERPART</span><b>{match ? match.kssl || match.title : "No matched KSSL model"}</b>{match && match.label && <span className={`geo-verdict-pill ${levelClass(match.level)}`}>{match.label}</span>}</div></div><span className="ri-chev">›</span></div>;
      })}
      {!rows.length && <div className="geo-rel-empty">No footprint rows are served for this competitor and country.</div>}
    </div>
    {currentRow && <RecordPanel clientName={clientName} companyName={companyName} country={country} row={currentRow} />}
  </div>;
}

/* the presence rows themselves: activity, status, overlap and matched ranges as stored */
function PresenceFacts({ presences }) {
  return <>{presences.map((p) => {
    const overlap = overlapOf([p]);
    return <div key={p.id}><Review src={p._src} /><DataFieldGrid fields={[["Activity", valueOrNull(p.activity)], ["Status", valueOrNull(p.status)], ["KSSL overlap", overlap?.label || null], ["Matched ranges", valueOrNull(p.ranges)], ["Products", valueOrNull(p.summary)]]} />{p.relationship && <div className="geo-note"><span className="geo-field-label">Relationship</span><p>{p.relationship}</p></div>}</div>;
  })}</>;
}

function RecordPanel({ clientName, companyName, country, row }) {
  const rating = row.ratedPower != null ? `${row.ratedPower}${row.ratedUnit ? ` ${row.ratedUnit}` : ""}` : null;
  const fields = [["Activity", valueOrNull(row.c)], ["Reported value", valueOrNull(row.value)], ["Quantity / place", valueOrNull(row.qty)], ["Product range", valueOrNull(row.range)], ["Rated power", rating], ["Fuel", valueOrNull(row.fuel)], ["Frequency", row.hz != null ? `${row.hz} Hz` : null], ["Since", row.since ? formatDate(row.since) : null]];
  return <div className="geo-comparison-panel"><span className="eyebrow geo-detail-eyebrow">Footprint record · {companyName} in {country}</span><h3>{row.name}</h3><DataFieldGrid fields={fields} />{row.note && <div className="geo-note"><span className="geo-field-label">Record note</span><p>{row.note}</p></div>}
    {row.matches.map((match) => <ProductComparison key={match.id} clientName={clientName} companyName={companyName} row={row} match={match} />)}
    <SourceList sources={row.srcs} />
    {row.news.length > 0 && <NewsList news={row.news} />}
  </div>;
}

function ProductComparison({ clientName, companyName, row, match }) {
  const sideLabel = (better) => {
    const side = lc(better);
    if (CLIENT_SIDE.includes(side)) return `${clientName} advantage`;
    if (RIVAL_SIDE.includes(side)) return `${companyName} advantage`;
    return better;
  };
  const facts = [[`${clientName} score`, match.kssl_score], [`${companyName} score`, match.rival_score], ["Rating delta", match.delta], ["Match basis", valueOrNull(match.basis)], ["Match status", valueOrNull(match.status)]].map(([k, v]) => [k, v === null || v === undefined ? null : String(v)]);
  return <div className="geo-section-block"><span className="eyebrow geo-section-title">KSSL comparison</span><h3>{match.title || `${match.kssl} vs ${row.name}`}</h3>{match.label && <div className="geo-comparison-verdict"><span className={`geo-verdict-pill ${levelClass(match.level)}`}>{match.label}</span></div>}<DataFieldGrid fields={facts} />{match.summary && <div className="geo-note"><p>{match.summary}</p></div>}{match.specs.length > 0 && <div className="geo-spec-table-wrap"><table className="geo-spec-table"><thead><tr><th>SPEC</th><th>{clientName.toUpperCase()}<small>{match.kssl}</small></th><th>{companyName.toUpperCase()}<small>{row.name}</small></th><th>GAP</th></tr></thead><tbody>{match.specs.map((spec, i) => <tr key={`${spec.name}-${i}`}><td>{spec.name}</td><td className={CLIENT_SIDE.includes(lc(spec.better)) ? "winner" : ""}>{[spec.kssl, spec.unit].filter(Boolean).join(" ") || "—"}</td><td className={RIVAL_SIDE.includes(lc(spec.better)) ? "winner" : ""}>{[spec.rival, spec.unit].filter(Boolean).join(" ") || "—"}</td><td>{compact([sideLabel(spec.better), spec.gap]).join(" · ") || "—"}</td></tr>)}</tbody></table></div>}<SourceList sources={match.srcs} /></div>;
}

function CompetitorDetail({ company, name, countries }) {
  const profile = company || {};
  return <div className="geo-detail-content"><span className="eyebrow geo-detail-eyebrow">Competitor profile</span><h3>{name}</h3>{profile.threat && <div className="geo-detail-sub">{profile.threat}</div>}<DataFieldGrid fields={[["Sector", valueOrNull(profile.sector)], ["Headquarters", valueOrNull(profile.hq)], ["Threat", valueOrNull(profile.threat)]]} /><div className="geo-section-block"><span className="eyebrow geo-section-title">Footprint markets ({countries.length})</span>{countries.map((market) => <div className="geo-country-presence-row" key={market.country}><div className={`ri-act ${activityClass(market.rows[0]?.c || market.presences[0]?.activity)}`} /><div><b>{market.country}</b><span>{market.rows.length} record{market.rows.length === 1 ? "" : "s"}{market.overlap ? ` · ${market.overlap.label}` : ""}</span></div></div>)}</div></div>;
}

function DataFieldGrid({ fields }) {
  const visible = fields.filter(([, value]) => value);
  if (!visible.length) return null;
  return <div className="geo-field-grid">{visible.map(([label, value]) => <div className="geo-field" key={label}><span className="geo-field-label">{label}</span><span className="geo-field-value">{value}</span></div>)}</div>;
}

function SourceList({ sources }) {
  const list = (sources || []).filter((source, index, all) => source.url && all.findIndex((item) => item.url === source.url) === index);
  if (!list.length) return null;
  return <div className="geo-section-block"><span className="eyebrow geo-section-title">Source evidence</span>{list.map((source) => <div className="geo-source" key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.label || source.url}</a>{source.type && <span>{source.type}</span>}</div>)}</div>;
}

function NewsList({ news }) {
  return <div className="geo-section-block"><span className="eyebrow geo-section-title">Footprint-linked intelligence</span>{news.map((item, index) => <div className="geo-news-item" key={`${item.title}-${index}`}><b>{item.title}</b>{(item.publisher || item.date) && <p>{compact([item.publisher, item.date ? formatDate(item.date) : ""]).join(" · ")}</p>}{item.url && <a href={item.url} target="_blank" rel="noreferrer">Source</a>}</div>)}</div>;
}
