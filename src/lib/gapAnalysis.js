/* ==================== GAP ANALYSIS (Competitive) ====================
   Which rivals beat KSSL in this category, on what, and what it wins them.

   WHY THIS DOES NOT USE THE EDGE INDEX AS ITS VERDICT
   The stored edge score reduces a matchup to one number, which cannot answer "does this rival
   have an advantage": advantages on different dimensions CANCEL in a single figure, so a
   matchup can read near parity while the rival leads more dimensions than the client. Dimensions
   are not fungible: a buyer does not average a spec sheet, they buy the product that wins the
   dimensions their site cares about.

   So this view aggregates DIMENSION OUTCOMES directly. For each dimension it
   counts how often each side is ahead across the rival's matchups, and reports
   who owns it. Nothing cancels, nothing is averaged twice, and every claim
   carries the denominator it was computed from.

   A dimension is only claimed when there is enough data to claim it: `comparable`
   counts matchups where BOTH products published that spec. A lead seen on 1 of a
   rival's 25 matchups is a coverage fact, not a competitive one, and it says so. */
import { clientShort } from "./client.js";
import { computeSpecEdge } from "./edge.js";
import { escAll } from "./html.js";

export const GAP_OWN = 0.65; // share of the DECIDED matchups needed to own a dimension
export const GAP_MINDEC = 3; // and at least this many matchups must separate the machines
export const GAP_MINMARGIN = 2; // won by at least this many more than it lost
export const GAP_MINCMP = 3; // and at least this many, and this share of the rival's matchups
export const GAP_MINCOV = 0.4;
export const GAP_THIN = 5; // fewer matchups than this and the whole row is indicative only
const GAP_AXIS = 5; // the bar's domain: net dimensions owned, -5..+5

export const gesc = escAll;
export const gshort = (s) => escAll((s || "").split("·")[0].trim());
const gmed = (xs) => {
  const p = xs.slice().sort((a, b) => a - b);
  return p.length ? p[Math.floor(p.length / 2)] : 0;
};

/* Per-dimension presentation. Every dimension is a spec label exactly as stored; none is special, and no
   dimension is graded: the size of a lead is shown as the median percentage gap, never as a severity word. */
export const gdmeta = (l) => ({
  short: String(l).replace(/\s*\(.*\)$/, ""),
  dir: "",
  arrow: "",
  unit: "%",
  scale: 1,
});
export const gval = (l, pct) => {
  const m = gdmeta(l);
  const v = pct * m.scale;
  return (m.scale === 1 ? Math.round(v) : Math.round(v * 10) / 10) + m.unit;
};
/* THE TWO FIGURES MUST BE IN THE SAME UNIT.

   The comparison line printed "13000 kg vs 18 t" and "4.2 vs < 15 t": both are
   what the source page says, and neither reader can subtract them. The conversion
   needs no unit table — the record already carries each figure twice, once as the
   source wrote it and once in a base unit, so the ratio between them IS the
   factor. Anything that does not parse cleanly (a range, a "<" bound) is left
   exactly as its source wrote it; a guessed number would be worse than an awkward
   one. */
const NUM_RX = /-?\d[\d,]*(?:\.\d+)?/;
const unitOf = (v) => {
  const t = String(v == null ? "" : v);
  const m = t.match(NUM_RX);
  if (!m) return null;
  // "30-56 km" leaves "-56 km" behind the first number; the unit is what follows
  // the LAST number, not the rest of the string
  const u = t
    .slice(m.index + m[0].length)
    .replace(/^\s*(?:[-–—]|\bto\b)\s*[\d.,]+/, "")
    .trim();
  return { n: parseFloat(m[0].replace(/,/g, "")), u, pre: t.slice(0, m.index).trim(), raw: t };
};
const fmtNum = (n) =>
  Math.abs(n) >= 100 ? String(Math.round(n)) : String(Math.round(n * 10) / 10);

export function pairVals(x) {
  const rv = x.cv != null ? String(x.cv) : x.cn != null ? String(x.cn) : "—";
  const kv = x.kv != null ? String(x.kv) : x.kn != null ? String(x.kn) : "—";
  const r = unitOf(rv);
  const k = unitOf(kv);
  if (!r || !k || x.cn == null || x.kn == null) return [rv, kv];
  const ru = r.u.toLowerCase();
  const ku = k.u.toLowerCase();
  if (ru === ku) return [rv, kv];
  // the side that names its unit sets the unit; the factor comes from that side's
  // own pair of figures (base value / written value)
  const target = ku ? k : r;
  const targetBase = ku ? x.kn : x.cn;
  if (!target.n || !targetBase) return [rv, kv];
  const factor = targetBase / target.n;
  if (!isFinite(factor) || factor <= 0) return [rv, kv];
  /* A range is not a number. "30-56" parses as 30, and converting it printed
     "30 km" for a gun whose published range runs to 56 -- dropping the upper bound
     silently. A range keeps its own text and only gains the unit. */
  const isRange = (t) => /\d\s*(?:[-–—]|\bto\b)\s*\d/.test(t);
  const conv = (base, own) =>
    isRange(own.raw)
      ? `${own.raw}${own.u || !target.u ? "" : ` ${target.u}`}`
      : `${own.pre ? `${own.pre} ` : ""}${fmtNum(base / factor)}${target.u ? ` ${target.u}` : ""}`;
  return ku ? [conv(x.cn, r), kv] : [rv, conv(x.kn, k)];
}

/* One rival in one band. Ownership decides the verdict (no cancellation); the
   margin, record and worst-case are kept because they are real facts the table
   shows alongside it. */
export function gapRivals(matchups, cat, clientName = clientShort()) {
  const by = {};
  Object.keys(matchups).forEach((id) => {
    const m = matchups[id];
    if (m.cat !== cat || m.edge == null) return;
    const co = (m.compBy || m.comp || "—").trim();
    const r = (by[co] = by[co] || { co, rows: [], d: {} });
    const dims = computeSpecEdge(m).dims || [];
    r.rows.push({ id, m, dims, lead: 50 - m.edge, edge: m.edge });
    dims.forEach((x) => {
      const s = (r.d[x.l] = r.d[x.l] || {
        win: 0,
        loss: 0,
        level: 0,
        winMag: [],
        lossMag: [],
      });
      if (x.a < 0) {
        s.win++;
        s.winMag.push(-x.raw * 100);
      } else if (x.a > 0) {
        s.loss++;
        s.lossMag.push(x.raw * 100);
      } else s.level++;
    });
  });
  return Object.values(by)
    .map((r) => {
      const n = r.rows.length;
      const presentLabels = Object.keys(r.d);
      const orderList = presentLabels;

      const all = orderList.map((l) => {
        const s = r.d[l];
        if (!s)
          return {
            l,
            own: "nodata",
            comparable: 0,
            cover: 0,
            n,
            win: 0,
            loss: 0,
            level: 0,
            wr: 0,
            lr: 0,
            med: 0,
            medLoss: 0,
          };
        const comparable = s.win + s.loss + s.level;
        const cover = n ? comparable / n : 0;
        const minCmp = n < 3 ? 1 : GAP_MINCMP;
        const enough = comparable >= minCmp && (cover >= GAP_MINCOV || n < 3);
        const decided = s.win + s.loss;
        const wr = decided ? s.win / decided : 0;
        const lr = decided ? s.loss / decided : 0;
        let own;
        /* Apply the rule the screen publishes. The methodology note and the
           scale caption both state 65% of decided matchups with a margin; the
           test here was a bare 50% and no margin, so a dimension won 3-2 was
           reported to the CEO as "owned" by a rival. */
        if (!enough) own = "nodata";
        else if (decided < GAP_MINDEC) own = "contested";
        else if (wr >= GAP_OWN && s.win - s.loss >= GAP_MINMARGIN) own = "rival";
        else if (lr >= GAP_OWN && s.loss - s.win >= GAP_MINMARGIN) own = "koel";
        else own = "contested";
        return {
          l,
          own,
          comparable,
          cover: Math.round(cover * 100),
          n,
          win: s.win,
          loss: s.loss,
          level: s.level,
          wr: Math.round(wr * 100),
          lr: Math.round(lr * 100),
          med: Math.round(gmed(s.winMag)),
          medLoss: Math.round(gmed(s.lossMag)),
        };
      });
      const rivalOwns = all.filter((d) => d.own === "rival");
      const koelOwns = all.filter((d) => d.own === "koel");
      const contested = all.filter((d) => d.own === "contested").length;
      const nodata = all.filter((d) => d.own === "nodata").length;
      let k;
      // Per-matchup outcome also has to come from dimensions. Classifying by the index
      // (lead>8) reintroduced the cancellation: a rival can own more dimensions than the
      // client while its index margin points the other way.
      // A matchup goes to whichever side is ahead on more dimensions.
      const rivalWins = r.rows.filter(
        (x) => x.dims.filter((dd) => dd.a < 0).length > x.dims.filter((dd) => dd.a > 0).length,
      ).length;
      const koelWins = r.rows.filter(
        (x) => x.dims.filter((dd) => dd.a > 0).length > x.dims.filter((dd) => dd.a < 0).length,
      ).length;
      // the bar plots the ownership balance, which is exactly what the verdict compares,
      // so its direction can never contradict the verdict
      const balance = rivalOwns.length - koelOwns.length;
      if (nodata === all.length) {
        k = "nodata";
      } else if (rivalOwns.length > koelOwns.length) {
        k = "behind";
      } else if (koelOwns.length > rivalOwns.length) {
        k = "ahead";
      } else if (!rivalOwns.length && !koelOwns.length) {
        k = "contested";
      } else {
        k = "contested";
      }
      // A one-dimension ownership margin is weak evidence. If the matchup-by-matchup
      // count points the other way, the two granularities disagree and neither should
      // claim a direction — say Traded rather than let the table contradict itself.
      if (
        Math.abs(balance) === 1 &&
        ((balance > 0 && rivalWins < koelWins) || (balance < 0 && rivalWins > koelWins))
      ) {
        k = "contested";
      }
      // open the matchup where the rival takes the most dimensions outright
      const scored = r.rows.map((x) => ({
        ...x,
        net: x.dims.filter((d) => d.a < 0).length - x.dims.filter((d) => d.a > 0).length,
      }));
      const worst = scored.reduce(
        (a, b) => (b.net > a.net || (b.net === a.net && b.edge < a.edge) ? b : a),
        scored[0],
      );
      return {
        co: r.co,
        n,
        // the individual comparisons behind `n`, so the page can list what it counts
        rows: r.rows,
        all,
        rivalOwns,
        koelOwns,
        contested,
        nodata,
        verdict: { k },
        balance,
        rivalWins,
        koelWins,
        parity: n - rivalWins - koelWins,
        worst,
        thin: n < GAP_THIN,
        /* a count, not a grade: the rival wins at least one comparison without owning a dimension */
        takesOne: k !== "behind" && rivalWins > 0,
        dims: rivalOwns.slice().sort((a, b) => b.med - a.med),
      };
    })
    .sort((a, b) => {
      const rank = { behind: 0, contested: 1, ahead: 2, nodata: 3 };
      return (
        rank[a.verdict.k] - rank[b.verdict.k] ||
        b.rivalOwns.length -
          b.koelOwns.length -
          (a.rivalOwns.length - a.koelOwns.length) ||
        b.rivalWins - b.koelWins - (a.rivalWins - a.koelWins) ||
        b.n - a.n
      );
    });
}

export function gapCategories(matchups) {
  const by = {};
  Object.keys(matchups).forEach((id) => {
    const m = matchups[id];
    if (m.edge == null) return;
    const c = (by[m.cat] = by[m.cat] || { n: 0 });
    c.n++;
  });
  return Object.keys(by)
    .map((cat) => {
      const rv = gapRivals(matchups, cat);
      return {
        cat,
        n: by[cat].n,
        rivals: rv.length,
        behind: rv.filter((r) => r.verdict.k === "behind").length,
        ahead: rv.filter((r) => r.verdict.k === "ahead").length,
        balance: rv.reduce((t, r) => t + r.balance, 0),
      };
    })
    .sort(
      (a, b) =>
        b.behind / (b.rivals || 1) - a.behind / (a.rivals || 1) ||
        b.behind - a.behind ||
        b.n - a.n,
    );
}

function gapDimRows(rivals) {
  // the dimensions are the spec labels the rivals carry, in the order they first appear
  const orderList = [];
  rivals.forEach((r) => (r.all || []).forEach((x) => {
    if (x.own !== "nodata" && !orderList.includes(x.l)) orderList.push(x.l);
  }));

  return orderList
    .map((l) => {
      const cells = rivals.map((r) => ({ co: r.co, d: r.all.find((x) => x.l === l) }));
      const owned = cells.filter((c) => c.d && c.d.own === "rival");
      return {
        l,
        cells,
        rivalOwns: owned.length,
        koelOwns: cells.filter((c) => c.d && c.d.own === "koel").length,
        med: owned.length ? Math.round(gmed(owned.map((c) => c.d.med))) : 0,
      };
    })
    .filter((row) => row.cells.some((c) => c.d && c.d.own !== "nodata"))
    .sort((a, b) => b.rivalOwns - a.rivalOwns || b.med - a.med);
}

/* Diverging bar drawn INSIDE each table row, so the ranking chart and the table
   are the same eleven rows rather than eleven rows printed twice. Fixed +/-5
   domain on every category so bands are directly comparable. Raw SVG — no chart
   library for two rectangles and a rule. */
function gapBar(lead, thin) {
  const W = 200;
  const H = 20;
  const MID = W / 2;
  const HALF = W / 2 - 6;
  const x = (v) => MID + (Math.max(-GAP_AXIS, Math.min(GAP_AXIS, v)) / GAP_AXIS) * HALF;
  let s = `<svg class="ga-bar" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">`;
  const o = thin ? ' opacity="0.45"' : "";
  if (Math.abs(lead) < 0.5) {
    // exact ownership tie
    s += `<rect x="${MID - 1.5}" y="5" width="3" height="10" class="ga-b-level"${o}/>`;
  } else if (lead > 0) {
    s += `<rect x="${MID}" y="5" width="${Math.max(x(lead) - MID, 1)}" height="10" rx="2" class="ga-b-rival"${o}/>`;
  } else {
    s += `<rect x="${x(lead)}" y="5" width="${Math.max(MID - x(lead), 1)}" height="10" rx="2" class="ga-b-koel"${o}/>`;
  }
  if (lead > GAP_AXIS)
    s += `<path d="M${W - 6} 6 L${W - 1} 10 L${W - 6} 14 Z" class="ga-b-rival"/>`;
  if (lead < -GAP_AXIS) s += '<path d="M6 6 L1 10 L6 14 Z" class="ga-b-koel"/>';
  s += `<line x1="${MID}" y1="2" x2="${MID}" y2="18" class="ga-zero" shape-rendering="crispEdges"/>`;
  return `${s}</svg>`;
}
function gapBarAxis() {
  const W = 200;
  const H = 16;
  const MID = W / 2;
  const HALF = W / 2 - 6;
  let s = `<svg class="ga-bar" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">`;
  [-5, -3, 0, 3, 5].forEach((t) => {
    const gx = MID + (t / GAP_AXIS) * HALF;
    s += `<line x1="${gx}" y1="10" x2="${gx}" y2="14" class="ga-tick"/>`;
    s += `<text x="${gx}" y="7" class="ga-tickl" text-anchor="middle">${t > 0 ? "+" : ""}${t}</text>`;
  });
  return `${s}</svg>`;
}

function gapDimGrid(rivals, clientName = clientShort()) {
  const rows = gapDimRows(rivals);
  if (!rows.length)
    return '<div class="gd-note">No dimension has enough published data in this band to judge.</div>';
  let h =
    `<div class="ws-sec-l">▸ What they beat ${gesc(clientName)} on <span class="ws-sec-note">median size of the lead, and which competitors own each dimension</span></div>`;
  h += '<div class="ga-acc-container">';

  rows.forEach((row, index) => {
    const m = gdmeta(row.l);
    const title = gesc(m.short);
    const isOpen = index === 0 ? " open" : "";

    const gapVal = row.rivalOwns > 0 ? gval(row.l, row.med) : "—";
    const compCount = row.rivalOwns;

    const ownedCells = row.cells.filter((c) => c.d && c.d.own === "rival");
    const sortedOwned = ownedCells
      .slice()
      .sort((a, b) => (b.d ? b.d.med : 0) - (a.d ? a.d.med : 0));
    const topRivalObj = sortedOwned[0];
    const topRival = topRivalObj ? gshort(topRivalObj.co) : row.rivalOwns > 0 ? "—" : "None";


    h += `<details class="ga-acc-item"${isOpen}>`;
    h += `<summary class="ga-acc-summary">`;
    h += `<span class="ga-acc-arrow"></span>`;
    h += `<span class="ga-acc-title">${title}</span>`;
    h += `</summary>`;

    /* the record and coverage for this dimension across every rival in the
       category — real numbers that balance the rival list on the right */
    const tot = { win: 0, loss: 0, level: 0, comparable: 0 };
    row.cells.forEach((c) => {
      if (!c.d) return;
      tot.win += c.d.win || 0;
      tot.loss += c.d.loss || 0;
      tot.level += c.d.level || 0;
      tot.comparable += c.d.comparable || 0;
    });
    const ksslOwnCells = row.cells.filter((c) => c.d && c.d.own === "koel").length;

    h += `<div class="ga-acc-body">`;
    h += `<div class="ga-acc-left">`;
    h += `<div class="ga-acc-grid">`;
    h += `<span class="ga-acc-label">Gap</span><span class="ga-acc-val">${gapVal}</span>`;
    h += `<span class="ga-acc-label">Competitors</span><span class="ga-acc-val">${compCount}</span>`;
    h += `<span class="ga-acc-label">Top Rival</span><span class="ga-acc-val">${topRival}</span>`;
    h += `<span class="ga-acc-label">Record</span><span class="ga-acc-val">rival ${tot.win} · level ${tot.level} · ${clientShort()} ${tot.loss}</span>`;
    h += `<span class="ga-acc-label">${clientShort()} owns vs</span><span class="ga-acc-val">${ksslOwnCells} of ${row.cells.filter((c) => c.d && c.d.own !== "nodata").length} rivals</span>`;
    h += `<span class="ga-acc-label">Coverage</span><span class="ga-acc-val">${tot.comparable} matchups publish both sides</span>`;

    h += `</div>`;
    h += `</div>`;

    h += `<div class="ga-acc-right">`;
    if (sortedOwned.length > 0) {
      h += `<span class="ga-acc-label ga-acc-right-heading">Competitors Leading in this Gap</span>`;
      h += `<div class="ga-acc-rivals-list">`;
      sortedOwned.forEach((c) => {
        const rivalName = gesc(c.co);
        const rGap = gval(row.l, c.d.med);
        const rRec = `leads in ${c.d.win}/${c.d.comparable} matchups`;
        h += `<div class="ga-acc-rival-row">`;
        h += `<span class="ga-acc-rival-name">${rivalName}</span>`;
        h += `<span class="ga-acc-rival-gap">${rGap} <i style="font-weight:normal;font-size:11px;color:var(--d-txt-3);font-style:normal;">(${rRec})</i></span>`;
        h += `</div>`;
      });
      h += `</div>`;
    } else {
      h += `<span class="ga-acc-label ga-acc-right-heading">Competitors</span>`;
      h += `<div style="font-size:12px;color:var(--d-txt-3);font-style:italic;margin-top:2px;">No rival currently owns a spec lead in this dimension.</div>`;
    }
    h += `</div>`;

    h += `</div>`;
    h += `</details>`;
  });

  h += "</div>";
  return h;
}

/* The whole right-hand canvas for one category, as one string. Rows carry
   data-mu so the React page can delegate the click through to Positioning. */
/* Every comparison the subtitle counts, one line each.

   The table above holds ONE row per rival, and clicking it opens only that rival's
   WORST pairing -- so of the eleven head-to-head comparisons the header advertised
   in Artillery, six were unreachable and none of the underlying numbers appeared
   anywhere. A count the reader cannot open is a claim, not evidence. */
function gapComparisons(rivals, clientName = clientShort(), held = 0) {
  const total = rivals.reduce((t, r) => t + r.n, 0);
  if (!total) return "";
  let h =
    '<div class="ws-sec-l">▸ Every head-to-head comparison ' +
    `<span class="ws-sec-note">the ${total} that the count above is made of` +
    (held > total
      ? ` · ${held - total} further pairing${held - total === 1 ? "" : "s"} in this ` +
        "category publish too little on both sides to compare"
      : "") +
    " · click a line to open it in Positioning</span></div>";
  h += '<div class="ga-cmps">';
  rivals.forEach((r) => {
    h += `<div class="ga-cmp-co">${gesc(r.co)}<i>${r.n} comparison${r.n === 1 ? "" : "s"}</i></div>`;
    r.rows
      .slice()
      .sort((x, y) => x.edge - y.edge)
      .forEach((row) => {
        const m = row.m;
        /* Name the products, not the makers: the maker is already the group heading,
           and "Hanwha vs KSSL" does not say which gun. */
        const rivalProduct = gesc(String(m.comp || "").split("·").pop().trim());
        const ourProduct = gesc(String(m.bf || "").split("·").pop().trim());
        const who =
          row.edge < 50 ? "rival ahead" : row.edge > 50 ? `${gesc(clientName)} ahead` : "level";
        const dims = row.dims
          .map((x) => {
            const lab = gesc(gdmeta(x.l).short);
            const pair = pairVals(x);
            const rv = gesc(pair[0]);
            const kv = gesc(pair[1]);
            const lead = x.a === 0 ? "level" : x.a < 0 ? "rival" : "client";
            return `<i class="ga-cmp-d ${lead}">${lab} <b>${rv}</b> vs <b>${kv}</b></i>`;
          })
          .join("");
        h +=
          `<div class="ga-cmp" role="button" tabindex="0" data-mu="${gesc(row.id)}"` +
          ` aria-label="${rivalProduct} against ${ourProduct}, ${row.edge} of 100. Opens in Positioning.">` +
          `<span class="ga-cmp-p">${rivalProduct} <i>vs</i> ${ourProduct}</span>` +
          `<span class="ga-cmp-dims">${dims || '<i class="ga-none">no dimension decided</i>'}</span>` +
          `<span class="num ga-cmp-e ${row.edge < 50 ? "behind" : row.edge > 50 ? "ahead" : "level"}">` +
          `${row.edge}<i>/100</i></span><span class="ga-cmp-w">${who}</span>` +
          '<span class="ga-go">↗</span></div>';
      });
  });
  return h + "</div>";
}


export function gapCategoryBody(rivals, clientName = clientShort(), held = 0) {
  if (!rivals.length)
    return (
      '<div class="pat-empty"><div class="pe-ic">⊘</div><div class="pe-t">No measured matchups in this band</div>' +
      '<div class="pe-s">Products here have no rival paired on rating.</div></div>'
    );
  const total = rivals.reduce((t, r) => t + r.n, 0);
  const behind = rivals.filter((r) => r.verdict.k === "behind");
  const ahead = rivals.filter((r) => r.verdict.k === "ahead");
  const traded = rivals.filter((r) => r.verdict.k === "contested");
  const nodata = rivals.filter((r) => r.verdict.k === "nodata");
  const takesOne = rivals.filter((r) => r.takesOne);
  const deepest = rivals.reduce((a, b) => (b.worst.edge < a.worst.edge ? b : a), rivals[0]);

  let h = '<div class="ga-wrap">';
  const top = behind[0];
  /* THE HERO NUMBER MUST AGREE WITH THE ROWS UNDERNEATH IT.

     "Owning" a dimension needs GAP_MINDEC comparisons before it can be claimed, so
     with a thin category the hero read "0/5 rivals hold an edge" directly above a
     list in which four of those five rivals win a comparison outright. Both
     statements were true and the pair of them was a lie. When nothing is owned yet,
     the hero reports what the comparisons themselves say, and says which measure it
     is using. */
  const leadOne = rivals.filter((r) => r.takesOne);
  const useOwn = behind.length > 0 || leadOne.length === 0;
  const heroN = useOwn ? behind.length : leadOne.length;
  h +=
    `<div class="gk-hero even">` +
    `<div class="gk-hero-l"><div class="gk-big">${heroN}<span>/${rivals.length}</span></div>` +
    `<div class="gk-cap">${useOwn ? "rivals hold<br>an edge" : "rivals win a<br>comparison"}</div></div>` +
    `<div class="gk-hero-r"><div class="gk-line">` +
    (behind.length
      ? `<b>${behind.length} of ${rivals.length}</b> rivals own more measured dimensions than ${clientName} in this category` +
        (top && top.dims.length
          ? `, led by <b>${gshort(top.co)}</b> - ahead on ${top.rivalOwns.length}` +
            ` of ${top.all.length}, widest on ${gesc(gdmeta(top.dims[0].l).short).toLowerCase()} by ${gval(top.dims[0].l, top.dims[0].med)}` +
            ` in ${top.dims[0].win} of ${top.dims[0].comparable} comparable matchups`
          : "") +
        "."
      : leadOne.length
        ? `<b>${leadOne.length} of ${rivals.length}</b> rivals take at least one comparison outright, but none has enough ` +
          `matchups yet to own a dimension outright - that needs ${GAP_MINDEC} comparisons on the same spec. ` +
          `The comparisons themselves are listed below, with both figures.`
        : `No rival owns more measured dimensions than ${clientName} in this category.`) +
    ` ${traded.length}${traded.length === 1 ? " trades" : " trade"} dimensions evenly, ` +
    `${ahead.length}${ahead.length === 1 ? " is" : " are"} behind ${clientName}` +
    (nodata.length
      ? `, ${nodata.length}${nodata.length === 1 ? " publishes" : " publish"} too little to judge`
      : "") +
    `. The deepest single loss is <b>${deepest.worst.edge}/100</b> against ${gshort(deepest.co)}.</div>` +
    `<div class="gk-scale">A rival <b>owns</b> a dimension when it leads in at least ${Math.round(GAP_OWN * 100)}` +
    "% of the matchups where both machines publish that spec. Dimensions are counted, never averaged against " +
    "each other." +
    (takesOne.length && useOwn
      ? ` <b>${takesOne.length}</b> rival${takesOne.length !== 1 ? "s" : ""}${takesOne.length === 1 ? " still takes" : " still take"} at least one comparison outright - marked ⚠.`
      : "") +
    "</div></div></div>";

  h +=
    `<div class="ws-sec-l">▸ Every rival in this category <span class="ws-sec-note">ranked by dimensions owned · click a row to open its worst comparison in Positioning</span></div>`;
  h +=
    '<div class="ga-tbl" role="table">' +
    '<div class="ga-row ga-hd" role="row">' +
    '<span role="columnheader">#</span><span role="columnheader">Rival</span>' +
    '<span role="columnheader">Verdict</span>' +
    // Left is negative lead, which is clientName ahead; right is positive, the rival ahead.
    `<span role="columnheader" class="ga-axh"><span class="ga-poles"><i>← ${clientName} owns more</i><i>rival owns more →</i></span>${gapBarAxis()}</span>` +
    '<span role="columnheader" class="num">Owns</span>' +
    '<span role="columnheader" class="num">Worst</span>' +
    '<span role="columnheader">Record</span>' +
    '<span role="columnheader" class="num">N</span>' +
    '<span role="columnheader">Biggest edge</span><span></span></div>';
  rivals.forEach((r, i) => {
    const v = r.verdict;
    const tot = r.n || 1;
    const aria =
      `${gesc(r.co)}. Owns ${r.rivalOwns.length} of ${r.all.length} measured dimensions, ${clientName} owns ` +
      `${r.koelOwns.length}. Ahead on more dimensions in ${r.rivalWins} of ${r.n}` +
      ` comparisons, behind in ${r.koelWins}. Worst comparison ${r.worst.edge}` +
      ` of 100 across ${r.n} comparisons. Opens the worst comparison.`;
    h +=
      `<div class="ga-row ${v.k}" role="row" tabindex="0" data-mu="${gesc(r.worst.id)}" aria-label="${aria}">` +
      `<span class="ga-i">${i + 1 < 10 ? "0" : ""}${i + 1}</span>` +
      `<span class="ga-co">${gesc(r.co)}</span>` +
      `<span><i class="ga-chip ${v.k}" title="${r.rivalOwns.length} dimensions to the rival, ${r.koelOwns.length}` +
      ` to ${clientName}, ${r.contested} split, ${r.nodata} not enough data">${v.k === "nodata" ? "—" : `rival ${r.rivalOwns.length} · ${gesc(clientName)} ${r.koelOwns.length}`}${r.takesOne ? " ⚠" : ""}</i></span>` +
      `<span class="ga-barc">${gapBar(r.balance, r.thin)}</span>` +
      `<span class="num ga-owns"><b class="${v.k}">${r.rivalOwns.length}</b><i>vs ${r.koelOwns.length}</i></span>` +
      `<span class="num ga-worst">${r.worst.edge}<i>/100</i></span>` +
      `<span class="ga-rec" title="${r.rivalWins} rival wins · ${r.parity} level · ${r.koelWins} ${clientName} wins">` +
      `<i class="rw" style="width:${(r.rivalWins / tot) * 100}%"></i>` +
      `<i class="pw" style="width:${(r.parity / tot) * 100}%"></i>` +
      `<i class="kw" style="width:${(r.koelWins / tot) * 100}%"></i></span>` +
      `<span class="num ga-n${r.thin ? " thin" : ""}" ${r.thin ? `title="Only ${r.n} comparisons - indicative only"` : ""}>${r.n}${r.thin ? " ⚠" : ""}</span>` +
      `<span class="ga-lo">${
        r.dims.length
          ? `${gesc(gdmeta(r.dims[0].l).short)} <b>${gval(r.dims[0].l, r.dims[0].med)}</b>` +
            `<i class="ga-freq"> in ${r.dims[0].win}/${r.dims[0].comparable}</i>`
          : '<i class="ga-none">none owned</i>'
      }</span>` +
      '<span class="ga-go">↗</span></div>';
  });
  h += "</div>";
  h +=
    '<div class="ga-key"><span><i class="k-riv"></i> rival owns more dimensions</span>' +
    `<span><i class="k-koel"></i> ${clientName} owns more</span>` +
    "<span>bar = net dimensions owned, the same count the verdict uses</span>" +
    `<span>⚠ at least one comparison goes to the rival, or fewer than ${GAP_THIN} comparisons</span></div>`;
  h += gapComparisons(rivals, clientName, held);
  h += gapDimGrid(rivals, clientName);
  h +=
    '<div class="gd-note">The verdict counts dimensions: a rival owns one when it leads in at least ' +
    `${Math.round(GAP_OWN * 100)}% of the matchups where both products publish that spec, with at least ${GAP_MINCMP}` +
    ` such matchups covering ${Math.round(GAP_MINCOV * 100)}% of the pairing. Advantages are never averaged against ` +
    "each other, because tonnes and kilometres are not interchangeable. The bar and the record both count dimensions, " +
    "so neither can point against the verdict. <b>Worst</b> is the single hardest comparison on the Positioning index " +
    "(0-100, 50 = parity, below 50 the rival is stronger), read from the same computation the dossier shows. " +
    "</div></div>";
  return h;
}

export function gapCategorySub(rivals, held = 0) {
  const total = rivals.reduce((t, r) => t + r.n, 0);
  /* Say the denominator. "11 head-to-head comparisons" read as though the category
     held eleven pairings; it holds 91, and 80 of them publish too little on both
     sides to compare. Hiding that makes thin coverage look like a complete picture. */
  return rivals.length
    ? `${rivals.length} rivals · ${total}${held > total ? ` of ${held}` : ""} head-to-head comparisons · ` +
        `${Math.max(...rivals.map((r) => r.all.length))} measured spec dimensions`
    : "No measured comparisons in this band";
}
