import { useEffect, useMemo, useState } from "react";
import MatchupList from "../../components/matchupList/MatchupList";
import MatchupDossier from "../../components/matchupDossier/MatchupDossier";
import { useAppState, useHeaderReport } from "../../state/AppState";
import { useData } from "../../state/DataProvider";
import { specValueWithUnit } from "../../lib/specs";
import { buildProductIndex, compareProducts } from "../../lib/compareProducts";

/* The right pane for a FREE comparison: any two products the user picked. Same frame as
   the matchup dossier, but no KSSL-vs-rival wording -- either side can be anyone's. */
function CompareView({ a, b, onClose }) {
  const r = compareProducts(a, b);
  const sameCat = a.cat === b.cat;
  return (
    <div className="mu-dossier">
      <div className="mu-dossier-scroll">
        <div className="mu-d-h" style={{ position: "relative", paddingRight: "60px" }}>
          <div className="ctx-h-actions">
            <button aria-label="Close" className="col-close" onClick={onClose} title="Close" type="button">✕</button>
          </div>
          <span className="eyebrow">Free comparison · {sameCat ? a.cat : `${a.cat} vs ${b.cat}`}</span>
          <div className="matchup">
            <div className="side comp">
              <div className="pn">{a.name}</div>
              <div className="by">{a.maker}{a.country ? ` · ${a.country}` : ""}</div>
            </div>
            <span className="vsbadge">VS</span>
            <div className="side bf">
              <div className="pn">{b.name}</div>
              <div className="by">{b.maker}{b.country ? ` · ${b.country}` : ""}</div>
            </div>
          </div>
        </div>
        <div className="fc-body">
          <div className="fc-summary level">
            The published figures for the two products are side by side. No winner is scored for a free comparison.
          </div>
          {!sameCat ? (
            <div className="fc-warn">These products are in different categories, so their specs may not be like-for-like.</div>
          ) : null}
          <table className="fc-table">
            <thead>
              <tr><th>Spec</th><th>{a.name}</th><th>{b.name}</th></tr>
            </thead>
            <tbody>
              {r.rows.map((row) => (
                <tr key={row.l}>
                  <td className="fc-l">{row.l}</td>
                  <td>{row.av == null ? <span className="fc-na">not published</span> : specValueWithUnit(row.av, row.u)}</td>
                  <td>{row.bv == null ? <span className="fc-na">not published</span> : specValueWithUnit(row.bv, row.u)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="fc-foot">
            Figures are the specifications held for each product, matched by name. The stored better-side and gap
            are shown on a matched pair, not here.
          </div>
        </div>
      </div>
    </div>
  );
}
/* A SELECTION IS REMEMBERED WHILE YOU STAY IN THIS PILLAR, not for ever. This page
   persisted to localStorage, which survives the tab, the browser and the machine's
   next reboot -- so a company opened once was still the landing selection weeks
   later, on a dashboard whose job is "what is new". Same key/value shape, held in
   memory, cleared on a pillar change. See lib/viewState. */
import * as viewState from "../../lib/viewState";

/* Positioning: every rating-matched KSSL-vs-rival pair, and the dossier for the one
   selected. Gap Analysis jumps in here with a matchup id, which arrives as `pending`. */
export default function Positioning() {
  const { data } = useData();
  const { setScope, takePending } = useAppState();
  const [selected, setSelectedState] = useState(() => {
    try {
      return viewState.getItem("kssl_pos_selected") || null;
    } catch (e) {
      return null;
    }
  });

  const setSelected = (val) => {
    setSelectedState(val);
    try {
      if (val) viewState.setItem("kssl_pos_selected", val);
      else viewState.removeItem("kssl_pos_selected");
    } catch (e) {}
  };

  const select = (id) => {
    if (!id) {
      setSelected(null);
      return;
    }
    const m = data.matchups[id];
    if (!m) return;
    setSelected(id);
    setScope("matchup", { type: "matchup", data: m }, {
      pillar: "Competitive",
      view: "Positioning",
      selection: `${m.comp} vs ${m.bf}`,
    });
  };

  // restore selection scope if selected is present on mount
  useEffect(() => {
    if (selected && data.matchups[selected]) {
      const m = data.matchups[selected];
      setScope("matchup", { type: "matchup", data: m }, {
        pillar: "Competitive",
        view: "Product Evaluation",
        selection: `${m.comp} vs ${m.bf}`,
      });
    }
  }, [selected, data.matchups, setScope]);

  // a cross-pillar jump from Gap Analysis lands here with the matchup to open
  useEffect(() => {
    const p = takePending("positioning");
    if (p && p.matchupId) select(String(p.matchupId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [takePending]);

  const m = selected ? data.matchups[selected] : null;
  /* Free comparison of any two products (keys into the product index), or null. Opening
     a matched pair closes it; a comparison closes the matched pair. */
  const clientShortName = (data.client && data.client.short) || "KSSL";
  const products = useMemo(() => buildProductIndex(data, clientShortName), [data, clientShortName]);
  const [compare, setCompare] = useState(null);
  const byKey = useMemo(() => new Map(products.map((p) => [p.key, p])), [products]);
  const cmpA = compare && byKey.get(compare.a);
  const cmpB = compare && byKey.get(compare.b);

  /* What the header's Copy / Export / Print act on: the open matchup -- its verdict,
     every spec row as served, both advantage lists -- or, with nothing selected, the
     list of pairs that survived the comparability gate. */
  const clientShort = (data.client && data.client.short) || "KSSL";
  const report = useMemo(() => {
    if (m) {
      const val = (v) => (v == null || v === "" ? "—" : String(v));
      return {
        title: `${m.comp} vs ${m.bf}`,
        subtitle: `${m.cat || ""} · edge index ${m.edge == null ? "not stored" : `${m.edge}/100`}`,
        sections: [
          { h: m.verdictH || "Verdict", rows: [m.verdict || "No verdict on file."] },
          {
            h: `Specifications (${m.compBy || "rival"} vs ${clientShort})`,
            rows: (m.specs || []).map((s) => [s.l, `${val(s.cv)} vs ${val(s.kv)}${s.u ? ` ${s.u}` : ""}`]),
          },
          { h: `${clientShort} analytics`, rows: m.advBf || [] },
          { h: "Competitor analytics", rows: m.advComp || [] },
        ],
        payload: {
          id: selected,
          category: m.cat || null,
          competitor: m.comp || null,
          competitorBy: m.compBy || null,
          client: m.bf || null,
          country: m.country || null,
          edge: m.edge == null ? null : m.edge,
          decision: m.decision == null ? null : m.decision,
          specs: m.specs || [],
          advantagesClient: m.advBf || [],
          advantagesCompetitor: m.advComp || [],
          verdictHeadline: m.verdictH || null,
          verdict: m.verdict || null,
        },
      };
    }
    const all = Object.entries(data.matchups || {});
    return {
      title: "Product Evaluation",
      subtitle:
        `${all.length} pair${all.length === 1 ? "" : "s"} on file · none selected`,
      sections: [
        {
          h: "Pairs on file",
          rows: all.map(([, x]) => [
            x.comp,
            `${x.bf} · ${x.cat}`,
          ]),
        },
      ],
      payload: {
        pairs: all.map(([id, x]) => ({
          id,
          category: x.cat || null,
          competitor: x.comp || null,
          client: x.bf || null,
          edge: x.edge == null ? null : x.edge,
          comparableSpecs: x.comparable == null ? null : x.comparable,
        })),
      },
    };
  }, [m, selected, data.matchups, clientShort]);
  useHeaderReport(report);

  return (
    <div className={`pos-view v-positioning ${m || (cmpA && cmpB) ? "has-sel" : "no-sel"}`}>
      <MatchupList
        data={data}
        onSelect={(id) => { setCompare(null); select(id); }}
        selected={selected}
        products={products}
        compare={compare}
        onCompare={(a, b) => { setSelected(null); setCompare({ a, b }); }}
      />
      {cmpA && cmpB ? (
        <CompareView a={cmpA} b={cmpB} onClose={() => setCompare(null)} />
      ) : m ? (
        <MatchupDossier
          data={data}
          m={m}
          onClose={() => setSelected(null)}
          /* The competitor product name is a plain label now (operator's ask), so the
             dossier no longer navigates to the rival's own product page from here. */
        />
      ) : (
        <div className="mu-dossier">
          <div className="mu-d-h">
            {/* not "comparable pair": nothing is selected, so nothing has been
                assessed as comparable. The word was a label on an empty slot. */}
            <span className="eyebrow">Category · pair</span>
            <div className="matchup">
              <div className="side comp">
                <div className="pn">Select a rival model</div>
              </div>
              <span className="vsbadge">VS</span>
              <div className="side bf">
                <div className="pn">{data.client?.short || "KSSL"} · —</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
