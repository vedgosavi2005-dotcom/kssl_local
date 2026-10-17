/* ===================================================================
   SHARED PARTNERS + ALLIANCE GRAPH

   Where a rival's partner is also one of KSSL's own: the dataset stamps p.koel
   (what KSSL uses that same company for) and p.cid (its canonical company id) at
   export time, matched on id rather than on name. Everything below is presentation
   over those two fields, plus the radial graph layout.

   Built as a factory over the dataset so the shared index memo lives in a closure
   rather than on `window`.
   =================================================================== */
import { clientShort } from "./client.js";
import { isVisible } from "./visibility.js";
import { esc, escAll, escAttr, escRich, joinParts, srcChips } from "./html.js";
import { canonicalizeLabels } from "./orgident.js";
import { countryFlagDisc } from "./countryFlags.js";
import { categoryDisc } from "./categorySymbols.js";
import { buildCategories, verdictOf, impactText } from "./partnerCategories.js";
import { stanceWords, OVERLAP_KINDS } from "./chrome.js";

/* THE CLIENT ROSTER AND A RIVAL'S PARTNER ROWS DO NOT SHARE A KEY SPACE.
   KSSL_PARTNERS is reference data and carries `plp_01`..`plp_03` with cid null; the rows
   on a rival carry a name slug (`paramount-group`) and no cid at all. Both name the same
   company. Every lookup that compared one to the other therefore missed every time --
   the overlap the server had already flagged could not be confirmed, and the client
   relation behind the red line never attached.

   So the roster is indexed under every key it can be found by: cid, id, and the
   normalised label. Used by dataset.js to attach `koel`, and by selfCheck() below to
   verify it -- one rule, so the join and its guard cannot disagree. */
export const rosterKey = (s) =>
  String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

export function rosterIndex(partners) {
  const ix = {};
  (partners || []).forEach((p) => {
    [p.cid, p.id, rosterKey(p.label || p.name)].forEach((k) => {
      if (k && !ix[k]) ix[k] = p;
    });
  });
  return ix;
}

/* The roster entry a partner row refers to, by any of the three. Falls back to the
   BASE name with any parenthetical qualifier stripped: a competitor lists the shared
   partner as "DRDO (HEMRL, ARDE)" while the roster carries plain "DRDO", and the two
   are the same organisation -- without this the shared-partner self-check flagged DRDO
   as "absent from roster" (FE-PART-02). */
export const rosterLookup = (ix, p) => {
  if (!p) return null;
  const direct = ix[p.cid] || ix[p.id] || ix[rosterKey(p.label || p.name)];
  if (direct) return direct;
  const base = String(p.label || p.name || "").replace(/\s*\(.*$/, "").trim();
  return (base && ix[rosterKey(base)]) || null;
};

/* ONE company = ONE node, everywhere the graph/drawer asks "is this the same partner?".
   Identity comes from the shared canonicaliser (orgident.js), which folds legal suffixes
   and a trailing national qualifier and then merges by distinctive-token containment:
   "Lockheed Martin Australia", "Lockheed Martin UK" and "Lockheed Martin Skunk Works" all
   become one "Lockheed Martin" node with country kept as an attribute. This replaced the
   old cid-or-slug key (cid is dead in served data -- 0/10,747 rows carry it -- and the
   raw slug split one firm per country). Built per competitor list; `keyer.canon` maps a
   key to {name, countries[]}. Unit-tested in orgident.test.mjs. */
export function pgKeyer(partners) {
  const labels = (partners || []).map((p) => (p && (p.label || p.name)) || "");
  const { keyOf, canon } = canonicalizeLabels(labels);
  /* A company the dataset has already identified (the same `cid` on several rows) is ONE node,
     whatever its rows' labels say: Zahid Group sits under Caterpillar as its distributor, two
     rental arms and a framework partner, and the four names share no token the label canonicaliser
     could merge on. The node is named by the "(Group)" every row carries, else its shortest label.
     Rows are kept under the node, so each tie still reads in full. */
  const byCid = {};
  (partners || []).forEach((p) => {
    if (p && p.cid != null && p.cid !== "") (byCid[p.cid] = byCid[p.cid] || []).push(p);
  });
  const merged = {};
  Object.keys(byCid).forEach((cid) => {
    const rows = byCid[cid];
    if (rows.length < 2) return;
    const parens = rows.map((r) => (/\(([^)]+)\)/.exec(r.label || r.name || "") || [])[1]);
    const group = parens.every((x) => x && x === parens[0]) ? parens[0] : null;
    const shortest = rows.map((r) => String(r.label || r.name || "")).sort((a, b) => a.length - b.length)[0];
    const countries = [...new Set(rows.map((r) => r.country).filter(Boolean))].sort();
    merged[cid] = `cid-${cid}`;
    canon[merged[cid]] = { name: group || shortest, countries };
  });
  const fn = (p) => (p && p.cid != null && merged[p.cid]) || keyOf((p && (p.label || p.name)) || "") || "x";
  fn.canon = canon;
  return fn;
}

/* radial layout constants. The ellipse is wider than tall because the pane is, and
   because labels are horizontal text: it buys room where labels actually need it. */
const PG_CX = 370;
const PG_CY = 228;
const PG_RX = 200;
const PG_RY = 158;
const PG_LBL_MAX = 22; // characters before an ellipsis; full name in <title>
/* The most partners a radial graph draws before labels crowd (the full roster is always
   in the sidebar; the graph is a summary). One constant so the two draw sites and the
   geometry self-check agree on the count -- 16 left the densest graph (Rheinmetall, 17
   partners) with overlapping labels, and made geomCheck compare a capped node count to
   the uncapped roster (FE-PART-01). */
const PG_MAX_NODES = 14;

/* LABEL COLLISION RESOLUTION.
   Two text rows per label (name + kind), ~11px and ~9px on a 12px rhythm, so a label
   occupies about 24px of height and charW*len of width from its anchor. Labels are
   planned for every node first, then nudged apart, then drawn -- a label cannot avoid
   a neighbour that has not been placed yet, which is why the fixed-offset version
   collided at exactly the points where the graph is most crowded.

   Vertical nudging only. Moving a label sideways detaches it from its node (the anchor
   side encodes which node it belongs to); moving it down keeps the association and is
   what a person does by hand. */
function pgResolveLabelCollisions(plan) {
  const CHAR_W = 6.2;          // 11px mono
  const H = 24;                // title + kind row
  const PAD = 3;
  const box = (p) => {
    const w = Math.max(String(p.text || "").length, String(p.sub || "").length) * CHAR_W;
    const x = p.anchor === "start" ? p.x : p.anchor === "end" ? p.x - w : p.x - w / 2;
    return { x1: x - PAD, x2: x + w + PAD, y1: p.y - 11 - PAD, y2: p.y + H - 11 + PAD };
  };
  // top-to-bottom: a label only ever moves DOWN, so one ordered pass settles the run
  const order = plan.slice().sort((a, b) => a.y - b.y || a.x - b.x);
  for (let i = 0; i < order.length; i++) {
    for (let j = 0; j < i; j++) {
      const a = box(order[i]);
      const b = box(order[j]);
      const hit = a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
      if (hit) {
        order[i].y += b.y2 - a.y1 + 2;
        j = -1;                // re-check against everything already placed
      }
    }
  }
  return plan;
}

/* ===================================================================
   RADIAL LAYOUT FOR THE ALLIANCE GRAPH

   Reported with a screenshot: "utillize the space artound the graph everthing
   clsutered and overlapped fix it". The layout was a table of fixed slot
   coordinates per cluster, hand-placed for one picture: seven partners landed on
   the same upper-left positions thirty would have, the fifth member of a cluster
   was "nudged" 20px diagonally onto the first, and nothing could ever reach the
   bottom half or the right third of the 960x540 canvas. The guide rings, drawn at
   fixed radii, then outlined exactly how much of the canvas was going unused.

   Now: one ellipse, sized from the canvas and from the widths of the labels that
   are actually on it. Partners sit on it at equal angular slices; a cluster is a
   contiguous sector, clockwise from the top in a fixed order, so cluster identity
   survives any count. A label sits outboard of its node -- start-anchored on the
   right half, end-anchored on the left, above or below at the poles -- so it runs
   out into the margin instead of across the graph. The plan is then checked as
   geometry (disc on disc, label on label, label on disc, edge through disc); if
   anything touches, the lowest-ranked node of the fullest sector drops to an inner
   ring inside its own sector and the plan is checked again. Nothing is ever moved
   by a constant. The label resolver below runs last, on whatever the ring search
   could not settle, which on this canvas is nothing up to the 16-node cap.

   The functions are pure and exported so test_graph_layout.mjs can drive them at
   canvas sizes the app never uses.
   =================================================================== */
const PG_VIEW = { w: 960, h: 540, top: 46, bottom: 34, side: 12 }; // toolbar strip, hint strip
const PG_CLUSTER_ORDER = ["amber", "purple", "teal", "coral"];
const PG_LBL_CHAR_W = 6.2; // 11px mono, the figure the resolver uses too
const PG_LBL_H = 24; // title row + kind row
const PG_LBL_PAD = 3;
const PG_LBL_GAP = 7; // disc edge to label
const PG_HALO = 6; // halo ring outside the disc
const PG_CENTER_R = 24;
const PG_CENTER_HALO = 40;
const PG_INNER = 0.58; // inner ring, as a fraction of the outer

function pgLabelBoxOf(p) {
  const w = Math.max(String(p.text || "").length, String(p.sub || "").length) * PG_LBL_CHAR_W;
  const x = p.anchor === "start" ? p.x : p.anchor === "end" ? p.x - w : p.x - w / 2;
  return { x1: x - PG_LBL_PAD, x2: x + w + PG_LBL_PAD, y1: p.y - 11 - PG_LBL_PAD, y2: p.y + PG_LBL_H - 11 + PG_LBL_PAD };
}
function pgBoxesHit(a, b) {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}
function pgBoxHitsDisc(b, x, y, r) {
  const px = Math.max(b.x1, Math.min(x, b.x2));
  const py = Math.max(b.y1, Math.min(y, b.y2));
  return Math.hypot(x - px, y - py) < r;
}
function pgSegDist(ax, ay, bx, by, px, py) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/* Where a node's label goes: hung off the point just outboard of the disc along
   the node's own ray, start-anchored on the right half and end-anchored on the
   left, so it runs out into the margin. Hanging it off the RAY rather than off
   the disc's side is what keeps two neighbours near a pole apart: their anchor
   points climb with the ring, so their rows stagger instead of sharing a line.
   At the pole itself (|cos| < 0.15) a horizontal label would run along the ring
   into the next node, so it goes above or below, centred.
   Returns the label origin and its box, both relative to the node centre. */
const PG_POLE = 0.15;
function pgLabelRel(ang, r, w) {
  const cos = Math.cos(ang);
  const sin = Math.sin(ang);
  const d = r + PG_LBL_GAP;
  if (Math.abs(cos) < PG_POLE) {
    return sin < 0
      ? { dx: 0, dy: -d - 1 - 12, anchor: "middle", x1: -w / 2 - PG_LBL_PAD, x2: w / 2 + PG_LBL_PAD, y1: -d - 27, y2: -d + 3 }
      : { dx: 0, dy: d + 1 + 11, anchor: "middle", x1: -w / 2 - PG_LBL_PAD, x2: w / 2 + PG_LBL_PAD, y1: d - 2, y2: d + 28 };
  }
  const dx = d * cos;
  const dy = d * sin;
  return cos > 0
    ? { dx, dy: dy - 2, anchor: "start", x1: dx - PG_LBL_PAD, x2: dx + w + PG_LBL_PAD, y1: dy - 16, y2: dy + 14 }
    : { dx, dy: dy - 2, anchor: "end", x1: dx - w - PG_LBL_PAD, x2: dx + PG_LBL_PAD, y1: dy - 16, y2: dy + 14 };
}
function pgPlanLabel(nd, w) {
  const rel = pgLabelRel(nd.ang, nd.r, w);
  return { x: nd.x + rel.dx, y: nd.y + rel.dy, anchor: rel.anchor };
}

/* Everything that may not touch, as a list of faults. Empty means the plan is clean. */
export function pgLayoutFaults(lay) {
  const f = [];
  const nodes = lay.nodes;
  const c = lay.center;
  const all = nodes.concat([c]);
  for (let i = 0; i < all.length; i++)
    for (let j = i + 1; j < all.length; j++) {
      const a = all[i];
      const b = all[j];
      if (Math.hypot(a.x - b.x, a.y - b.y) < a.halo + b.halo + 2) f.push(`disc ${a.id} on disc ${b.id}`);
    }
  const boxes = nodes.map((n) => ({ n, b: pgLabelBoxOf(n.lbl) }));
  if (c.box) boxes.push({ n: c, b: c.box });
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++)
      if (pgBoxesHit(boxes[i].b, boxes[j].b)) f.push(`label ${boxes[i].n.id} on label ${boxes[j].n.id}`);
    all.forEach((o) => {
      if (o !== boxes[i].n && pgBoxHitsDisc(boxes[i].b, o.x, o.y, o.halo)) f.push(`label ${boxes[i].n.id} on disc ${o.id}`);
    });
  }
  nodes.forEach((e) =>
    nodes.forEach((o) => {
      if (o !== e && pgSegDist(c.x, c.y, e.x, e.y, o.x, o.y) < o.halo + 2) f.push(`edge to ${e.id} through disc ${o.id}`);
    }),
  );
  return f;
}

/* items: [{id, label, sub, r, cluster}] in cluster-rank order.
   Returns the centre, the ring radii and every node with x, y, ring, ang and its
   label plan {x, y, anchor, text, sub}. */
export function pgRadialLayout(items, view, centerLabel) {
  const V = Object.assign({}, PG_VIEW, view || {});
  const cx = V.w / 2;
  const cy = V.h / 2;
  const cName = String(centerLabel || "");
  const center = {
    id: "center",
    x: cx,
    y: cy,
    r: PG_CENTER_R,
    halo: PG_CENTER_HALO,
    // the OEM name (13px) and the SELECTED OEM row under the disc
    box: {
      x1: cx - Math.max(cName.length * 7.6, 12 * 5.6) / 2 - PG_LBL_PAD,
      x2: cx + Math.max(cName.length * 7.6, 12 * 5.6) / 2 + PG_LBL_PAD,
      y1: cy + PG_CENTER_HALO - 13,
      y2: cy + PG_CENTER_HALO + 14 + PG_LBL_PAD,
    },
  };
  const m = items.length;
  if (!m) return { cx, cy, rx: 0, ry: 0, rings: 1, nodes: [], center, faults: [] };

  // clusters as contiguous sectors, clockwise from the top; unknown clusters last
  const known = {};
  PG_CLUSTER_ORDER.forEach((k) => (known[k] = 1));
  const groups = PG_CLUSTER_ORDER.map((k) => items.filter((it) => it.cluster === k));
  groups.push(items.filter((it) => !known[it.cluster]));
  const slice = (2 * Math.PI) / m;
  let a0 = m === 1 ? -Math.PI : -Math.PI / 2;
  const sectors = [];
  groups.forEach((g) => {
    if (!g.length) return;
    sectors.push({ items: g, a0, width: g.length * slice });
    a0 += g.length * slice;
  });
  const widthOf = (it) => {
    const t = String(it.text || it.label || "");
    return Math.max(t.length, String(it.sub || "").length) * PG_LBL_CHAR_W;
  };

  const attempt = (inner) => {
    // outer ring first: equal slices of each sector
    const placed = [];
    sectors.forEach((s, si) => {
      const outer = s.items.filter((it) => !inner[it.id]);
      outer.forEach((it, j) =>
        placed.push(Object.assign({}, it, { ring: 0, sec: si, ang: s.a0 + ((j + 0.5) * s.width) / outer.length })),
      );
    });
    // the ring is as large as the canvas allows: every outer disc, its halo and its
    // label must fit inside the margins along its own ray
    let rx = cx - V.side - 30;
    let ry = Math.min(cy - V.top, V.h - V.bottom - cy) - 30;
    placed.forEach((n) => {
      const cos = Math.cos(n.ang);
      const sin = Math.sin(n.ang);
      const h = n.r + PG_HALO;
      const rel = pgLabelRel(n.ang, n.r, widthOf(n));
      // the node's full footprint relative to its centre: halo and label together
      const x1 = Math.min(-h, rel.x1);
      const x2 = Math.max(h, rel.x2);
      const y1 = Math.min(-h, rel.y1);
      const y2 = Math.max(h, rel.y2);
      if (cos > 1e-6) rx = Math.min(rx, (V.w - V.side - cx - x2) / cos);
      if (cos < -1e-6) rx = Math.min(rx, (cx - V.side + x1) / -cos);
      if (sin > 1e-6) ry = Math.min(ry, (V.h - V.bottom - cy - y2) / sin);
      if (sin < -1e-6) ry = Math.min(ry, (cy - V.top + y1) / -sin);
    });
    rx = Math.max(rx, 0);
    ry = Math.max(ry, 0);
    // the inner ring is a fraction of the outer, but never so small that a disc on
    // it lands on the centre disc or its two-row label
    const rxi = Math.min(rx * 0.8, Math.max(rx * PG_INNER, PG_CENTER_HALO + 19 + PG_HALO + 4));
    const ryi = Math.min(ry * 0.8, Math.max(ry * PG_INNER, PG_CENTER_HALO + 20 + 19 + PG_HALO + 4));

    /* Inner ring. Every edge runs from the centre to an outer node, straight
       through the inner ring, so an inner node has to sit between two outer RAYS.
       On a 2:1 ellipse the rays are not where the parametric angles say: equal
       slices bunch up at the sides in polar terms. So the gaps are bisected in
       polar angle and only then mapped onto the inner ellipse. */
    const polar = (ang) => Math.atan2(ry * Math.sin(ang), rx * Math.cos(ang));
    const outerSorted = placed.slice().sort((p, q) => p.ang - q.ang);
    const gaps = []; // {sec, mid(parametric), phi(polar bisector)}
    for (let k = 0; k < outerSorted.length; k++) {
      const p = outerSorted[k];
      const q = outerSorted[(k + 1) % outerSorted.length];
      const qAng = k + 1 < outerSorted.length ? q.ang : q.ang + 2 * Math.PI;
      let pp = polar(p.ang);
      let pq = polar(q.ang);
      if (pq < pp) pq += 2 * Math.PI;
      const mid = (p.ang + qAng) / 2;
      gaps.push({ mid, phi: (pp + pq) / 2 });
    }
    // a gap belongs to the sector its parametric midpoint falls in
    const inSector = (s, mid) => {
      const rel = ((mid - s.a0) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
      return rel < s.width - 1e-9;
    };
    sectors.forEach((s) => {
      const inn = s.items.filter((it) => inner[it.id]);
      if (!inn.length) return;
      const cands = gaps.filter((g) => inSector(s, g.mid));
      inn.forEach((it, j) => {
        let ang;
        if (cands.length) {
          const k = Math.min(cands.length - 1, Math.floor(((j + 0.5) * cands.length) / inn.length));
          const phi = cands[k].phi;
          ang = Math.atan2(rxi * Math.sin(phi), ryi * Math.cos(phi));
        } else {
          ang = s.a0 + ((j + 0.5) * s.width) / inn.length;
        }
        placed.push(Object.assign({}, it, { ring: 1, ang }));
      });
    });

    const nodes = placed.map((n) => {
      const x = cx + (n.ring ? rxi : rx) * Math.cos(n.ang);
      const y = cy + (n.ring ? ryi : ry) * Math.sin(n.ang);
      const nd = Object.assign({}, n, { x, y, halo: n.r + PG_HALO });
      nd.lbl = Object.assign(pgPlanLabel(nd, widthOf(n)), { text: n.text || n.label || "", sub: n.sub || "" });
      return nd;
    });
    const lay = { cx, cy, rx, ry, rxi, ryi, rings: Object.keys(inner).length ? 2 : 1, nodes, center };
    lay.faults = pgLayoutFaults(lay);
    return lay;
  };

  // overflow: while something touches, drop the lowest-ranked outer node of the
  // fullest sector to the inner ring; keep the cleanest plan seen
  const inner = {};
  let best = attempt(inner);
  let moved = 0;
  while (best.faults.length && moved < Math.floor(m / 2)) {
    let pick = null;
    let pickCount = 0;
    sectors.forEach((s) => {
      const outer = s.items.filter((it) => !inner[it.id]);
      if (outer.length > pickCount) {
        pickCount = outer.length;
        pick = outer[outer.length - 1];
      }
    });
    if (!pick || pickCount < 2) break;
    inner[pick.id] = 1;
    moved++;
    const next = attempt(inner);
    // one move rarely clears a run of collisions on its own, so the moves are
    // cumulative and the cleanest plan seen is what is kept
    if (next.faults.length < best.faults.length) best = next;
  }
  // last resort, and only for what the rings could not settle
  if (best.faults.some((s) => s.indexOf("label") === 0)) {
    pgResolveLabelCollisions(best.nodes.map((n) => n.lbl));
    best.faults = pgLayoutFaults(best);
  }
  return best;
}

/* A relationship the source says is OVER, and how much its source is worth. Both
   were stored by the enrichment and read by nothing, so an ended joint venture drew
   as a live alliance and a tie from one blog looked like one from the manufacturer.
   Rendered as tags rather than folded into the type label, because "Historical Joint
   Venture (Ended 2013)" written INTO the type is the thing this replaces. */
/* "ACTIVE" IS ONLY EVER "ACTIVE AS OF THE ARTICLE". A tie read out of a 2010 story
   said `active` and drew identically to one read last week -- Oshkosh and General
   Dynamics Land Systems-Canada "have teamed up" for a Canadian programme Textron won
   in 2012, published as a current alliance. The enrichment stamps the document's own
   date on every tie; nothing read it.

   So the date is shown whenever the claim is a standing one, and past a threshold the
   tag says LAST SEEN rather than active -- the honest reading of an old article is
   "this was true then", not "this is true now". An ended tie needs no such hedge: the
   source says it is over, which does not go stale. */
const STALE_YEARS = 2;
const asOfYear = (p) => {
  const m = /^(\d{4})/.exec(String((p && p.as_of) || ""));
  return m ? Number(m[1]) : null;
};
const statusTag = (p) => {
  if (!p) return "";
  if (p.status === "ended")
    return `<span class="tie-tag ended">ended${p.ended ? ` ${esc(p.ended)}` : ""}</span>`;
  /* TALKS ARE NOT AN ALLIANCE. Before the enrichment had a word for it, "the two are in
     negotiations" was stored active and drew the same edge as a signed joint venture.
     It draws as what it is, and it is never stale -- a conversation reported in 2019
     is not a standing claim, so the year is part of the label. */
  if (p.status === "exploring")
    return `<span class="tie-tag exploring" title="The source says the two are in talks. `
         + `Nothing is signed.">in talks${asOfYear(p) !== null ? ` ${asOfYear(p)}` : ""}</span>`;
  const y = asOfYear(p);
  const stale = y !== null && new Date().getFullYear() - y >= STALE_YEARS;
  const when = y !== null ? ` ${y}` : "";
  if (stale)
    return `<span class="tie-tag stale" title="Read from an article published in ${y}. `
         + `Nothing since says it is still in force.">last seen${when}</span>`;
  if (p.status === "announced")
    return `<span class="tie-tag announced">announced${when}</span>`;
  return y !== null ? `<span class="tie-tag asof">as of ${y}</span>` : "";
};

/* the confidence word is the stored one (competitive_partnership.relationship_confidence), shown as it is */
const confTag = (p) => {
  const c = p && p.confidence ? String(p.confidence) : "";
  return c ? `<span class="tie-tag conf-${escAll(c)}">${esc(c.replace(/_/g, " "))}</span>` : "";
};

/* WHAT THE TIE IS, not what kind of company the partner is.

   Every card and every graph node reads the tie's own type first (`ptype`: "Joint venture", "Supplier")
   and the legend's short label second (ui.partner_category.short_label, through `cats`). The company
   category `kind` is the last resort. A tie with none of them shows the em dash: no word is invented. */

/* The tie's own words, for the card and the drawer: "Joint Venture (51% Mahindra,
   49% Telephonics)" carries the split, and losing it to a canonical label loses the
   only number on the card. */
export function tieKind(p, cats) {
  if (!p) return "—";
  const cat = cats && cats.categoryOf(p.rel);
  return String(p.ptype || (cat && (cat.short || cat.label)) || p.kind || "—");
}

/* The legend's short label, for a graph node sublabel that has ~22 characters. The free
   text goes second here and is trimmed: a node reading "Joint Venture (51% Mahin…"
   is worse than one reading "Joint venture". */
export function tieKindShort(p, max = 22, cats) {
  if (!p) return "—";
  const cat = cats && cats.categoryOf(p.rel);
  const t = String((cat && (cat.short || cat.label)) || p.ptype || p.kind || "—");
  return t.length > max ? `${t.slice(0, max - 1).replace(/[\s,(./-]+$/, "")}…` : t;
}

/* THREE ANSWERS TO ONE QUESTION: is this partner also the client's? Yes, no, and
   nobody has looked.

   The roster badge had two states, so "nobody has looked" rendered as a confident
   green "Direct Partner" -- and because the overlap marking (mark_shared.py) was
   wired into no pass, that was EVERY partner on the tab, including the four that
   really are shared. Rafael is KSSL's own KRAS JV partner and Mahindra Defence's;
   it drew green.

   mark_shared stamps `cid` on every tie it can identify, shared or not, so the
   ABSENCE of cid is the signal that the join has not run -- which is what
   distinguishes "checked, no overlap" from "never checked". */
export function overlapState(p) {
  const rows = (p && p.rows) || [];
  if (!p) return "unchecked";
  if (p.koel || p.shared || rows.some((r) => r.koel || r.shared)) return "shared";
  if (p.cid || rows.some((r) => r.cid)) return "direct";
  /* Checked against KSSL's (closed, 14-row) roster and NOT found on it -> a definite
     "no overlap", the norm. Distinct from "unchecked" (the join never ran). */
  if (p.overlapChecked || rows.some((r) => r.overlapChecked)) return "none";
  return "unchecked";
}

const OVERLAP_BADGE = {
  /* BLOOD RED on the shared row, and nowhere else -- see --overlap in theme.css. It was
     #dc2626 on a 12%-opacity wash, which on this ground is a pale pink that reads as
     just another chip; the operator could not find the overlaps because the marker for
     them was quieter than the labels around it. */
  shared: ["var(--overlap-bg)", "var(--overlap)", "var(--overlap-line)", "Overlapping Partner"],
  direct: ["rgba(34, 197, 94, 0.12)", "#16a34a", "rgba(34, 197, 94, 0.3)", "Direct Partner"],
  unchecked: ["rgba(120, 118, 110, 0.10)", "#6b6a63", "rgba(120, 118, 110, 0.28)", "Overlap Unchecked"],
  // read at use, after the client is set
  get none() { return ["rgba(120, 118, 110, 0.08)", "#6b6a63", "rgba(120, 118, 110, 0.2)", `No ${clientShort()} overlap`]; },
};

/* A BADGE ON EVERY CARD SAYING THE SAME THING IS NOT A BADGE. The overlap flag is an
   exception marker -- eight of forty-two ties on staging -- and rendering the other
   thirty-four as a green "Direct Partner" spent the most prominent slot on the card
   restating the norm, which is how the relationship type ended up with nowhere to go.
   The green state is the absence of a badge; `ov-direct` still exists as a class for
   the graph and for tests, it just does not print a label. */
export function overlapBadge(p, clientName) {
  const state = overlapState(p);
  /* Only a real overlap ("shared") gets a badge. "direct" and a checked "none" were
     already silent; "unchecked" joins them (2026-09-21): with the cid join dead it is
     the state of ~700 of 703 partners, so a grey "Overlap Unchecked" on nearly every
     card is exactly the "badge on every card is not a badge" this block warns against.
     The state stays honest (overlapState still returns "unchecked"); it just isn't shouted. */
  if (state !== "shared") return "";
  const [bg, fg, br, text] = OVERLAP_BADGE[state];
  const roster = clientName ? `${clientName}'s own partner roster` : "the partner roster";
  const title = state === "shared"
    ? `${(p && p.label) || "—"} is also on ${roster}.`
    : `Not yet matched against ${roster} -- whether it is shared is unknown.`;
  return `<span class="ov-badge ov-${state}" title="${escAttr(title)}" style="font-family: var(--mono); font-size: 9.5px; background: ${bg}; color: ${fg}; border: 1px solid ${br}; padding: 2px 7px; border-radius: 4px; font-weight: 700; white-space: nowrap; flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px;">${text}</span>`;
}

/* What each kind of overlap does to the client. The heading and lead of each kind are front-end code (chrome.js
   OVERLAP_KINDS); the effects under it (title, text) are DATA: the rows of ui.partner_overlap_effect, keyed by
   overlap_kind. {rival} and {client} are filled in by the caller. With no effect rows a kind keeps its heading and
   lead and draws no effects: no effect prose is written in code. */
export function overlapDefs(d) {
  const ui = (d && d.database && d.database.ui) || {};
  const out = {};
  const canon = {};
  OVERLAP_KINDS.forEach((k) => {
    out[k.kind] = { label: k.label, lead: k.lead, fx: [] };
    canon[k.kind] = k.kind;
    (k.aliases || []).forEach((a) => { canon[a] = k.kind; });
  });
  (ui.partner_overlap_effect || []).slice().sort((a, b) => (a.display_order || 0) - (b.display_order || 0)).forEach((e) => {
    const k = e && canon[e.overlap_kind];
    if (k) out[k].fx.push([e.effect_title || "", e.effect_text || ""]);
  });
  return out;
}

export function createPartners(d) {
  const { competitors, KSSL_PARTNERS, FIELDSYN, COMPSYN, TRACEIDS, sourceRegistry } = d;
  const cats = buildCategories(d);
  const { categoryOf, categoryDef } = cats;
  const CLIENT_CID = (d.client && d.client.id);

  /* Which rivals each shared company serves. Deduped per rival: the dataset carries
     one peer row per source edge, so one company can appear 2-3 times under a single
     competitor (the client lists Powerica three times). */
  let _sharedIdx = null;
  function pgSharedIndex() {
    if (_sharedIdx) return _sharedIdx;
    const m = {};
    Object.keys(competitors).forEach((cid) => {
      const c = competitors[cid];
      const keyOf = pgKeyer(c.partners);
      const seen = {};
      (c.partners || []).forEach((p) => {
        const isShared = p.koel || p.shared;
        const key = keyOf(p);
        if (!isShared || !key || seen[key]) return;
        seen[key] = 1;
        (m[key] = m[key] || []).push({ cid, name: c.name });
      });
    });
    _sharedIdx = m;
    return m;
  }
  // distinct partner companies a rival has (not raw edge rows)
  function pgDistinct(c) {
    const keyOf = pgKeyer(c.partners);
    const s = {};
    let n = 0;
    (c.partners || []).forEach((p) => {
      const k = keyOf(p);
      if (!s[k]) {
        s[k] = 1;
        n++;
      }
    });
    return n;
  }
  // deduped shared partners for one rival
  function pgSharedFor(c) {
    const keyOf = pgKeyer(c.partners);
    const seen = {};
    const out = [];
    (c.partners || []).forEach((p) => {
      const isShared = p.koel || p.shared;
      const key = keyOf(p);
      if (!isShared || !key || seen[key]) return;
      seen[key] = 1;
      out.push(p);
    });
    return out;
  }

  /* On a reverse edge (dealer -> KSSL) the description holds the brand they carry,
     not a role, and two KSSL edges just repeat the partner's own name. Printing those
     as "KSSL's own channel partner — Kirloskar" reads as noise. */
  function ovRole(p) {
    const r = ((p.koel && p.koel.role) || "").trim();
    if (!r) return "";
    const flat = (s) => s.toLowerCase().replace(/[^a-z]/g, "");
    const f = flat(r);
    if (!f) return "";
    if (flat(p.label).indexOf(f) >= 0) return ""; // repeats the partner's name
    if ("kalyanistrategicsystemskssslbharatforge".indexOf(f) >= 0 || f === "kssl" || f === "kalyani") return ""; // only names the brand
    return r;
  }

  /* ===================================================================
     GRAPH LAYOUT — one node per partner COMPANY, each on its own line.

     Two defects this replaces:
     1. A node per relationship ROW. The dataset records one edge per source, and
        for a channel partner that means three, so the client drew three separate nodes
        all labelled "Powerica Limited". Rows are merged per company here; the drawer
        still lists every row, and c.partners is untouched so counts elsewhere hold.
     2. Concentric rings with `off=(ri%2)*(PI/m)`. With three rings of equal size,
        rings 0 and 2 both got offset 0 — identical angles — so outer lines ran
        exactly through inner nodes. Every node now takes its own angle on one
        ellipse, so no two lines can coincide.
     =================================================================== */
  function pgRowRank(p) {
    return p.sig || 1;
  }
  // one entry per company; the strongest row leads and carries the rest in .rows
  function pgNodes(c) {
    const keyOf = pgKeyer(c.partners);
    const canon = keyOf.canon || {};
    const by = {};
    const order = [];
    (c.partners || []).forEach((p) => {
      const k = keyOf(p);
      const cn = canon[k] || {};
      if (!by[k]) {
        /* A single row keeps its own label: the folded canonical name turns "&" into "AND" and
           "L.L.C." into "L L C" ("Mohamed Abdulrahman AL Bahar L L C"). */
        by[k] = { ...p, key: k, rows: [p], label: p.label, countries: cn.countries || [] };
        order.push(k);
        return;
      }
      const g = by[k];
      const rows = g.rows.concat([p]);
      const lead = pgRowRank(p) > pgRowRank(g) ? { ...p } : { ...g };
      by[k] = { ...lead, key: k, rows, label: cn.name || lead.label, countries: cn.countries || [] };
    });
    const nodes = order.map((k) => by[k]);
    /* Rank so the strongest ties, and every KSSL overlap, survive the PG_MAX_NODES cap:
       the tab exists to surface defensible partners, not the 700th co-mention. */
    nodes.forEach((n) => {
      n.pgOverlap = n.rows.some((r) => r.koel || r.shared) ? 1 : 0;
      n.pgScore = pgEvidence(n);
    });
    nodes.sort((a, b) => b.pgOverlap - a.pgOverlap || b.pgScore - a.pgScore || pgRowRank(b) - pgRowRank(a));
    return nodes;
  }

  /* Evidence weight of a partner company: sourced + typed + strong-tie rows, plus a
     little for corroboration. Drives ranking under the node cap. */
  function pgEvidence(n) {
    let s = 0;
    (n.rows || []).forEach((r) => {
      if (r && r.src && /^https?:/i.test(r.src)) s += 2;
      if (r && (r.ptype || r.rel)) s += 1;
      if (/jv|joint|technolog|licen|acquir|manufactur/i.test(String((r && (r.ptype || r.rel)) || ""))) s += 1;
    });
    return s + Math.min((n.rows || []).length, 4);
  }
  // any relationship-row id -> the node that stands for its company
  function pgNodeIdFor(c, pid) {
    const nd = pgNodes(c).filter((n) => n.rows.some((r) => r.id === pid))[0];
    return nd ? nd.id : pid;
  }
  /* The thin CSV-sourced rows carry a company name where a description belongs.
     Echoing it as the programme detail reads as noise, so it is suppressed. */
  function pgThinNote(p, compName) {
    const t = (p.note || "").trim();
    if (!t) return "";
    const flat = (x) => (x || "").toLowerCase().replace(/[^a-z]/g, "");
    const f = flat(t);
    if (!f) return "";
    if (flat(p.label).indexOf(f) >= 0 || f.indexOf(flat(p.label)) >= 0) return "";
    if (flat(compName).indexOf(f) >= 0 || f.indexOf(flat(compName)) >= 0) return "";
    return t;
  }

  function layoutGraph(c) {
    // §8.2: a sparse row may serve center as null — synthesize it from the identity
    const center = c.center || { id: c.id, label: c.name };
    const nodes = [{ ...center, type: "comp", dir: c.dir, x: PG_CX, y: PG_CY }];
    const parts = pgNodes(c).sort((a, b) => b.pgOverlap - a.pgOverlap || b.pgScore - a.pgScore || pgRowRank(b) - pgRowRank(a));
    const n = parts.length;
    // Cap visual graph nodes so labels don't crowd on dense graphs (full list in sidebar)
    const displayParts = n > PG_MAX_NODES ? parts.slice(0, PG_MAX_NODES) : parts;
    const m = displayParts.length;

    displayParts.forEach((p, i) => {
      const ang = -Math.PI / 2 + i * ((2 * Math.PI) / m);
      const f = m > 7 && i % 2 ? 0.78 : 1;
      nodes.push({
        ...p,
        type: "ptr",
        ang,
        x: PG_CX + PG_RX * f * Math.cos(ang),
        y: PG_CY + PG_RY * f * Math.sin(ang),
      });
    });

    const edges = displayParts.map((p) => {
      const isShared = p.koel || p.shared || (p.rows && p.rows.some((r) => r.koel || r.shared));
      return {
        a: center.id,
        b: p.id,
        rel: p.rel,
        sig: p.sig,
        koel: !!isShared,
        shared: !!isShared,
      };
    });
    return { nodes, edges };
  }

/* Swap a failed article image for the same captioned tile a missing one gets. */
const PG_IMG_ONERROR =
  "this.parentNode.outerHTML='&lt;div style=&quot;width:100%;height:120px;border-radius:6px;"
  + "background:#f0efea;border:1px solid #e3e1d8;display:flex;align-items:center;"
  + "justify-content:center&quot;&gt;&lt;span style=&quot;font-family:var(--mono);"
  + "font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:#8a8880&quot;&gt;"
  + "Image could not be loaded&lt;/span&gt;&lt;/div&gt;'";


  /* Labels radiate outward and are anchored by hemisphere, so neighbours diverge
     instead of stacking on the same centre line. text-anchor has to travel as a
     class: a stylesheet rule beats an SVG presentation attribute. */
  function pgLabel(nd, r) {
    const cos = Math.cos(nd.ang || 0);
    const sin = Math.sin(nd.ang || 0);
    const full = nd.label || "";
    const t =
      full.length > PG_LBL_MAX
        ? `${full.slice(0, PG_LBL_MAX - 1).replace(/[\s,(./-]+$/, "")}…`
        : full;
    if (cos > 0.3) return { x: nd.x + r + 7, y: nd.y + 3.4, cls: "la-s", t, full };
    if (cos < -0.3) return { x: nd.x - r - 7, y: nd.y + 3.4, cls: "la-e", t, full };
    return {
      x: nd.x,
      y: sin > 0 ? nd.y + r + 13 : nd.y - r - 6,
      cls: "la-m",
      t,
      full,
    };
  }

  function graphSvg(c) {
    if (!c) return "";
    const centerName = esc(c.name || c.label || "—");
    const centerId = c.id || "main";

    // Direct partners for selected company
    const parts = pgNodes(c).sort((a, b) => b.pgOverlap - a.pgOverlap || b.pgScore - a.pgScore || pgRowRank(b) - pgRowRank(a));
    const m = parts.length;
    if (m === 0) return "";
    const displayParts = m > PG_MAX_NODES ? parts.slice(0, PG_MAX_NODES) : parts;

    // SVG DEFS & GRADIENTS MATCHING graph wanted.jpeg
    const defsHtml = `
      <defs>
        <!-- Deep cosmic canvas background gradient -->
        <radialGradient id="pgBgGrad" cx="50%" cy="50%" r="70%">
          <stop offset="0%" stop-color="#0e172e" />
          <stop offset="55%" stop-color="#080d1a" />
          <stop offset="100%" stop-color="#03050a" />
        </radialGradient>
        <!-- Center Spotlight Aura Glow -->
        <!-- The spotlight aura is gone: a lit canvas is the glow the brief asked
             to remove, and it was also what made the dark node fills below look
             washed out where they crossed it. -->
        <!-- Spherical 3D Node Gradients -->
        <!-- FLAT, NOT SPHERICAL. Each of these was a radial gradient running from
             white through a bright hue: that white core is what read as a glowing 3D
             bubble. One stop each now, so a node is a flat disc of one dark colour.

             Palette validated with the dataviz checker on the dark surface -- chroma
             floor, adjacent-pair CVD and normal-vision separation all pass. Two checks
             are knowingly failed and both ARE the brief: the blood red sits below the
             lightness band because it is meant to, and the red and purple fall under
             3:1 contrast, which the checker allows only where the marks carry their own
             relief. They do: every node is drawn with a stroke and directly labelled
             with its name and its role, so nothing here is identified by hue alone. -->
        <radialGradient id="grad-oem">
          <stop offset="100%" stop-color="#0f6f7d" />
        </radialGradient>
        <radialGradient id="grad-teal">
          <stop offset="100%" stop-color="#0a8f70" />
        </radialGradient>
        <radialGradient id="grad-amber">
          <stop offset="100%" stop-color="#ab7016" />
        </radialGradient>
        <radialGradient id="grad-purple">
          <stop offset="100%" stop-color="#8340b8" />
        </radialGradient>
        <radialGradient id="grad-coral">
          <stop offset="100%" stop-color="#992424" />
        </radialGradient>
      </defs>
    `;

    let svg = defsHtml;

    /* The star-dust layer is gone. Twelve bright specks scattered over the canvas
       were the last of the lit-space look, and at 0.25-0.4 opacity in five hues they
       carried no information at all -- decoration competing with the nodes. */

    // MULTI-CLUSTER CATEGORIZATION
    const clusters = {
      amber: [],  // Foreign OEMs / Global Aerospace
      purple: [], // Tech, Radar, Systems, Electronics, JVs
      coral: [],  // Overlapping & Domestic Defense
      teal: []    // Core Strategic, R&D, Unmanned
    };

    displayParts.forEach((p) => {
      const isShared = p.koel || p.shared || (p.rows && p.rows.some((r) => r.koel || r.shared));

      if (isShared) {
        clusters.coral.push({ ...p, cluster: "coral", isOverlap: true });
      } else {
        /* the cluster follows the tie's group in the legend (ui.partner_category.group_key), by the order
           the groups are listed in; a type the legend does not list goes to the least-populated cluster.
           No keyword, country or company name is read from the label. */
        const gi = cats.groups.findIndex((g) => g.key === categoryOf(p.rel).group);
        const own = ["amber", "purple", "teal"];
        const pick = gi >= 0
          ? own[gi % own.length]
          : own.reduce((minK, k) => (clusters[k].length < clusters[minK].length ? k : minK), "amber");
        clusters[pick].push({ ...p, cluster: pick, isOverlap: false });
      }
    });

    /* Cluster colours only. The slot tables that used to live here are gone: a
       fixed coordinate per slot is a layout for one node count, and it crammed
       every graph into the same upper-left band regardless of how many partners
       it had. Positions now come from pgRadialLayout, which sizes the ring from
       the canvas and the labels and keeps each cluster to its own sector. */
    const clusterConfig = {
      amber: { color: "#ab7016" },
      purple: { color: "#8340b8" },
      coral: { color: "#992424" },
      teal: { color: "#0a8f70" },
    };

    // one layout item per partner, in cluster-sector order and rank order within
    // the cluster; the strongest row of each cluster is drawn a size larger
    const items = [];
    PG_CLUSTER_ORDER.forEach((cKey) => {
      clusters[cKey].forEach((p, idx) => {
        const full = String(p.label || "");
        items.push({
          id: p.id,
          p,
          label: full,
          text: full.length > PG_LBL_MAX ? full.slice(0, PG_LBL_MAX - 1) : full,
          sub: tieKindShort(p, undefined, cats),
          r: idx === 0 ? 19 : 15,
          lead: idx === 0,
          cluster: cKey,
        });
      });
    });
    const lay = pgRadialLayout(items, null, c.name || c.label || "");
    const cx = lay.cx;
    const cy = lay.cy;
    const f1 = (v) => (Math.round(v * 10) / 10).toString();

    /* GUIDE RINGS, sized to the layout. Each ellipse drawn here is one the nodes
       actually sit on -- a ring larger than the graph only outlines the space the
       graph is failing to use. The axes span the outer ring and no further. */
    svg += `<g class="pg-bg-guides">`;
    if (lay.rings > 1) {
      svg += `  <ellipse cx="${f1(cx)}" cy="${f1(cy)}" rx="${f1(lay.rxi)}" ry="${f1(lay.ryi)}" fill="none" stroke="rgba(56, 189, 248, 0.12)" stroke-width="1.2" stroke-dasharray="3 6" />`;
    }
    svg += `  <ellipse cx="${f1(cx)}" cy="${f1(cy)}" rx="${f1(lay.rx)}" ry="${f1(lay.ry)}" fill="none" stroke="rgba(56, 189, 248, 0.09)" stroke-width="1.2" stroke-dasharray="4 8" />`;
    svg += `  <line x1="${f1(cx - lay.rx)}" y1="${f1(cy)}" x2="${f1(cx + lay.rx)}" y2="${f1(cy)}" stroke="rgba(255,255,255,0.03)" stroke-width="1" stroke-dasharray="2 6" />`;
    svg += `  <line x1="${f1(cx)}" y1="${f1(cy - lay.ry)}" x2="${f1(cx)}" y2="${f1(cy + lay.ry)}" stroke="rgba(255,255,255,0.03)" stroke-width="1" stroke-dasharray="2 6" />`;
    svg += `</g>`;

    let edgeHtml = "";
    let nodeHtml = "";

    /* One disc and one edge per relationship on file, nothing else. The satellite
       dots and the proximity "mesh" lines that used to hang off every node stood
       for no record in the dataset -- a dashed line between two partners that
       merely landed near each other reads as a tie that does not exist -- and they
       were a third of the clutter in the reported picture. */
    lay.nodes.forEach((nd) => {
      const p = nd.p;
      const cfg = clusterConfig[nd.cluster];
      const nx = f1(nd.x);
      const ny = f1(nd.y);
      /* AN OVERLAP IS THE ONE THING ON THIS GRAPH WORTH FINDING, so it is drawn as
         blood red at full strength, not as a slightly different dot.
         Two reasons it did not read as red before:
           - the edge was emitted as class="pg-edge" with no `shared` class, so
             `.pg-edge.shared{stroke:#e8483a;stroke-width:2.5px;opacity:1}` -- which
             exists in partnerships.css and is declared after the rel-* rules
             precisely so red wins -- could never match anything;
           - the only red it did get was an inline #8c2f2f (a dark maroon) drawn at
             0.50 opacity, which against this background is browner than the amber
             cluster beside it.
         The class carries the colour now; the inline stroke stays as the fallback for
         a context that renders the SVG without the stylesheet (the print report). */
      const overlapRed = "#ff2d2d";  // --overlap; an SVG stroke attribute cannot take a var()
      const strokeColor = p.isOverlap ? overlapRed : cfg.color;
      const fillColor = p.isOverlap ? overlapRed : cfg.color;

      edgeHtml += `<line class="pg-edge${p.isOverlap ? " shared" : ""}" data-a="${centerId}" data-b="${p.id}" x1="${f1(cx)}" y1="${f1(cy)}" x2="${nx}" y2="${ny}" stroke="${strokeColor}" stroke-width="${p.isOverlap ? "2.5px" : nd.lead ? "1.8px" : "1.4px"}" opacity="${p.isOverlap ? "1" : nd.lead ? "0.65" : "0.50"}" />`;

      const fullLabel = String(p.label || "");
      const labelText = esc(
        fullLabel.length > PG_LBL_MAX
          ? `${fullLabel.slice(0, PG_LBL_MAX - 1).replace(/[\s,(./-]+$/, "")}…`
          : fullLabel,
      );
      /* When several relationship rows collapsed into this one company node, say so on
         the node: distinct tie TYPES beyond the first read as "+N", so a partner that
         spans e.g. a JV and a supply deal is visibly different from a single tie. */
      const nTypes = new Set(
        (p.rows || [p]).map((r) => String(r.ptype || r.rel || "").toLowerCase().trim()).filter(Boolean),
      ).size;
      const kindText = esc(nTypes > 1 ? `${tieKindShort(p, 14, cats)} +${nTypes - 1}` : tieKindShort(p, undefined, cats));
      const lx = f1(nd.lbl.x);
      const ly = nd.lbl.y;
      const textAnchor = nd.lbl.anchor;

      // the label stays inside the node's own group: hover, dim and select key on it
      nodeHtml +=
        `<g class="pg-node ptr ${p.isOverlap ? "overlap" : "direct"} rel-${escAll(p.rel || "other")}${p.status === "ended" ? " st-ended" : ""}" data-id="${p.id}" data-cluster="${nd.cluster}">` +
        `<title>${labelText} - ${esc(tieKind(p, cats))}${p.isOverlap ? " - also on the client's own roster" : ""}${p.status === "ended" ? " (ended)" : ""}</title>` +
        `<circle class="halo" cx="${nx}" cy="${ny}" r="${f1(nd.halo)}" fill="none" stroke="${strokeColor}" stroke-width="${p.isOverlap ? "2.2" : "1.3"}" opacity="${p.isOverlap ? "0.85" : "0.35"}" />` +
        `<circle class="net-circle" cx="${nx}" cy="${ny}" r="${f1(nd.r)}" fill="${fillColor}" stroke="#cfd3da" stroke-width="1.2" stroke-opacity="0.42" />` +
        `<text class="lbl-ptr-title" x="${lx}" y="${f1(ly)}" text-anchor="${textAnchor}">${labelText}</text>` +
        (kindText ? `<text class="lbl-ptr-sub" x="${lx}" y="${f1(ly + 12)}" text-anchor="${textAnchor}">${kindText}</text>` : "") +
        `</g>`;
    });

    // CENTER OEM NODE (flat network graph circle)
    const centerHtml =
      `<g class="pg-node center-root" data-id="${centerId}">` +
      `<circle class="halo halo-oem" cx="${f1(cx)}" cy="${f1(cy)}" r="${PG_CENTER_HALO}" fill="none" stroke="rgba(160, 172, 184, 0.28)" stroke-width="1.2" stroke-dasharray="4, 6" />` +
      `<circle class="net-circle" cx="${f1(cx)}" cy="${f1(cy)}" r="${PG_CENTER_R}" fill="#0f6f7d" stroke="#cfd3da" stroke-width="1.6" stroke-opacity="0.55" />` +
      `<text class="lbl-ptr-title center-title" x="${f1(cx)}" y="${f1(cy + 40)}" text-anchor="middle">${centerName}</text>` +
      `<text class="lbl-ptr-sub center-sub" x="${f1(cx)}" y="${f1(cy + 54)}" text-anchor="middle">SELECTED OEM</text>` +
      `</g>`;

    return svg + edgeHtml + nodeHtml + centerHtml;
  }


  /* ===================================================================
     TYPE TREE -- company -> partner TYPE -> partners (owner sketch, 28 Sep 2026).

     Level 1 is the selected company with one node per relationship type it has on
     file (the dataset's own `rel` vocabulary: jv / acq / mou / tech / supply). Level 2
     is opened per type: clicking a type node fans that type's partner companies out
     around it. A company with rows of two types appears under both, since it IS both.
     Partner nodes keep the old graph's contract -- class "pg-node ptr", data-id = the
     lead row id -- so the drawer, the highlight and the zoom work unchanged.
     =================================================================== */
  /* Every category the dataset can name (lib/partnerCategories). A colour means the same thing
     here as in the legend and on the cards. */
  const PG_TYPE_ORDER = cats.list.map((c) => c.key);
  const PG_TYPE_META = Object.fromEntries(
    cats.list.map((c) => [c.key, { label: c.label, color: c.color, fill: c.fill, hue: c.group }]),
  );
  /* a tie type the legend does not list is its own group under its stored word, in the neutral colour */
  const pgTypeKey = (r) => {
    const k = categoryOf((r && r.rel) || "").key;
    if (!PG_TYPE_META[k]) {
      const n = categoryOf(k);
      PG_TYPE_META[k] = { label: (r && (r.ptype || r.rel)) || "", color: n.color, fill: n.fill, hue: "" };
      PG_TYPE_ORDER.push(k);
    }
    return k;
  };

  // type key -> partner company nodes of that type, in pgNodes rank order
  function pgTypeGroups(c) {
    const groups = {};
    pgNodes(c).forEach((n) => {
      const types = new Set((n.rows || [n]).map(pgTypeKey));
      types.forEach((t) => {
        (groups[t] = groups[t] || []).push({
          ...n,
          isOverlap: !!(n.koel || n.shared || (n.rows || []).some((r) => r.koel || r.shared)),
        });
      });
    });
    return PG_TYPE_ORDER.filter((t) => groups[t]).map((t) => ({ key: t, ...PG_TYPE_META[t], nodes: groups[t] }));
  }

  /* REGIONS: the same partner companies grouped by the partner's own country.
     A row naming two ("France / UK") puts the company under both, as a company with two
     tie types sits under both types. Spellings of one country are folded. */
  const PG_REGION_META = { color: "#7fa8c9", fill: "#23303f" };
  /* the partner's stated region, as stored (competitive_partnership.region). A company-name-to-country
     guess and a table of country spellings are not kept here: no region stated means no region. */
  function pgRegionsOf(r) {
    const raw = String((r && r.country) || "").trim();
    if (!raw) return [];
    return raw.split(/[\/,;]/).map((part) => {
      let t = part.trim();
      const par = t.match(/\(([^)]+)\)/);          // "Europe (France)" -> "France"
      if (par) t = par[1].trim();
      return t;
    }).filter(Boolean);
  }
  function pgRegionGroups(c) {
    const groups = {};
    pgNodes(c).forEach((n) => {
      const regions = new Set();
      (n.rows || [n]).forEach((r) => pgRegionsOf(r).forEach((x) => regions.add(x)));
      if (!regions.size) regions.add("Unknown");
      const leaf = PG_TYPE_META[pgTypeKey(n)];
      regions.forEach((rg) => {
        (groups[rg] = groups[rg] || []).push({
          ...n,
          isOverlap: !!(n.koel || n.shared || (n.rows || []).some((r) => r.koel || r.shared)),
          leafColor: leaf.color,
          leafFill: leaf.fill,
          leafType: pgTypeKey(n),
        });
      });
    });
    // most partners first; "Unknown" always last
    const sorted = Object.keys(groups)
      .sort((a, b) => (a === "Unknown") - (b === "Unknown") || groups[b].length - groups[a].length || a.localeCompare(b));
    return sorted.map((rg) => ({ key: rg, label: rg, ...PG_REGION_META, hue: "Steel", nodes: groups[rg] }));
  }
  // the grouping the graph is drawn in: "type" (categories) or "region"
  function pgGroups(c, mode) {
    return mode === "region" ? pgRegionGroups(c) : pgTypeGroups(c);
  }

  // the relationship type of the company a row belongs to (Regions' middle level)
  function pgLeafTypeFor(c, pid) {
    const nodeId = pgNodeIdFor(c, pid);
    const n = pgNodes(c).find((x) => x.id === nodeId);
    return n ? pgTypeKey(n) : null;
  }

  // the group a relationship row's company node sits under (its first)
  function pgTypeFor(c, pid, mode) {
    const nodeId = pgNodeIdFor(c, pid);
    const g = pgGroups(c, mode).find((grp) => grp.nodes.some((n) => n.id === nodeId));
    return g ? g.key : null;
  }

  /* STEP-BY-STEP BRANCH EXPLORER (owner reference video, 28 Sep 2026).

     view.stage:
       "root"   only the company, in the middle
       "spread" the company and one branch per relationship type
       "focus"  as spread, plus view.type's partners fanned out around it; that branch
                glows and the other branches dim
     view.anim names what just appeared ("types" | "children"), so only that pops in.

     Layout is computed around (0,0), then fitted into the page's fixed 960x540 viewBox,
     so an opened branch near an edge pulls the whole graph back into frame instead of
     running off it. Partner nodes keep the old contract -- class "pg-node pt-leaf",
     data-id = lead row id, data-type -- so the drawer, highlight and zoom still work. */
  function typeGraphSvg(c, view) {
    if (!c) return "";
    const v = view || { stage: "root" };
    const byRegion = v.mode === "region";
    const groups = pgGroups(c, v.mode);
    const stage = groups.length ? v.stage || "root" : "root";
    const focus = stage === "focus" ? groups.find((g) => g.key === v.type) || null : null;
    const f1 = (x) => (Math.round(x * 10) / 10).toString();
    const W = 960, H = 540;
    const RED = "#ff2d2d", RED_RING = "#ffb3aa";
    const EDGE = "#3a4556";
    const CORE_R = 36, TYPE_R = 26, LEAF_R = 13;

    const name = String(c.name || c.label || "");

    function wrapPartnerTitle(str, maxLen = 14) {
      const s = String(str || "").trim();
      if (s.length <= maxLen) return [s];
      const words = s.split(/\s+/);
      if (words.length <= 1) return [s.length > 18 ? s.slice(0, 17) + "…" : s];
      if (words.length <= 5) {
        let bestSplit = 1;
        let minScore = Infinity;
        for (let i = 1; i < words.length; i++) {
          const l1 = words.slice(0, i).join(" ");
          const l2 = words.slice(i).join(" ");
          const score = Math.abs(l1.length - l2.length) + (l2.length > l1.length ? 3 : 0);
          if (score < minScore) {
            minScore = score;
            bestSplit = i;
          }
        }
        const l1 = words.slice(0, bestSplit).join(" ");
        const l2 = words.slice(bestSplit).join(" ");
        if (l1.length <= 18 && l2.length <= 18) {
          return [l1, l2];
        }
      }
      const lines = [];
      let cur = "";
      for (const w of words) {
        if (!cur) {
          cur = w;
        } else if ((cur + " " + w).length <= maxLen) {
          cur += " " + w;
        } else {
          lines.push(cur);
          cur = w;
        }
      }
      if (cur) lines.push(cur);
      return lines.slice(0, 2);
    }

    const defs =
      `<defs><filter id="pgxGlow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>` +
      `<rect class="pgx-bg" x="-480" y="-270" width="1920" height="1080" fill="#000000"/>`;

    const disc = (x, y, r, fill, ring, extra) =>
      `<circle class="halo" cx="${f1(x)}" cy="${f1(y)}" r="${f1(r + 7)}" style="fill:none;stroke:${ring}" stroke-width="1.3" opacity="0.35" />` +
      `<circle class="net-circle" cx="${f1(x)}" cy="${f1(y)}" r="${f1(r)}" style="fill:${fill};stroke:${ring}" stroke-width="2" ${extra || ""} />`;

    const titleSub = (x, y, anchor, titleInput, sub, extraCls) => {
      const isLeaf = extraCls && extraCls.includes("pt-leaf-lbl");
      const isCenter = extraCls && extraCls.includes("center-title");
      const subCls = isCenter ? " center-sub" : isLeaf ? " pt-leaf-sub" : "";
      const lines = Array.isArray(titleInput) ? titleInput : [titleInput];
      const lineStep = isCenter ? 16 : 13;
      let textSvg = "";
      lines.forEach((ln, idx) => {
        textSvg += `<text class="lbl-ptr-title${extraCls || ""}" x="${f1(x)}" y="${f1(y + idx * lineStep)}" text-anchor="${anchor}">${esc(ln)}</text>`;
      });
      if (sub) {
        const subY = y + (lines.length - 1) * lineStep + (isCenter ? 16 : 13);
        textSvg += `<text class="lbl-ptr-sub${subCls}" x="${f1(x)}" y="${f1(subY)}" text-anchor="${anchor}">${esc(sub)}</text>`;
      }
      return textSvg;
    };

    // STAGE 1: ROOT
    if (stage === "root") {
      const cx = W / 2, cy = H / 2;
      const centerSvg =
        `<g class="pg-node center-root pgx-idle" data-id="${escAll(c.id || "main")}">` +
        `<title>${esc(name)} - click to spread its partner branches</title>` +
        `<circle class="halo halo-oem pgx-ring" cx="${f1(cx)}" cy="${f1(cy)}" r="${CORE_R + 12}" style="fill:none;stroke:rgba(160,172,184,0.28)" stroke-width="1.2" stroke-dasharray="4, 6" />` +
        `<circle class="net-circle" cx="${f1(cx)}" cy="${f1(cy)}" r="${CORE_R}" style="fill:#0f6f7d;stroke:#cfd3da" stroke-width="1.6" stroke-opacity="0.55" />` +
        titleSub(cx, cy + CORE_R + 22, "middle", name, v.coreSub || "", " center-title") +
        `</g>`;
      return defs + centerSvg;
    }

    // STAGE 2: SPREAD
    if (stage === "spread" || !focus) {
      const cx = W / 2, cy = H / 2 - 5;
      const n = groups.length;
      let edges = "";
      let nodes = "";
      const popT = v.anim === "types" ? " pgx-pop" : "";

      if (!byRegion) {
        // Categories mode: small fixed set of categories (usually 4-6)
        const rx = Math.min(320, 210 + Math.max(0, n - 5) * 8);
        const ry = Math.min(170, 160 + Math.max(0, n - 5) * 6);

        groups.forEach((g, i) => {
          const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
          const tx = cx + rx * Math.cos(ang);
          const ty = cy + ry * Math.sin(ang);

          edges += `<line class="pg-edge pgx-spoke${popT}" data-type="${escAttr(g.key)}" x1="${f1(cx)}" y1="${f1(cy)}" x2="${f1(tx)}" y2="${f1(ty)}" style="stroke:${EDGE};animation-delay:${i * 50}ms" />`;

          const discSvg = categoryDisc(g.key, tx, ty, TYPE_R, g.fill, g.color, "");

          nodes +=
            `<g class="pg-node pg-type${popT}" data-type="${escAttr(g.key)}" style="animation-delay:${i * 50}ms">` +
            `<title>${esc(g.label)} - click to open its partners</title>` +
            discSvg +
            titleSub(tx, ty + TYPE_R + 18, "middle", g.label, `${g.nodes.length} PARTNERS`) +
            `</g>`;
        });
      } else {
        // Regions mode: country count can vary widely (1 to 60+ countries).
        // Adapt layout across concentric rings to ensure everything stays properly fitted,
        // without overflowing canvas bounds or colliding discs and labels.
        let numRings = 1;
        if (n > 34) numRings = 3;
        else if (n > 16) numRings = 2;

        const ringNodes = [];
        if (numRings === 1) {
          ringNodes.push({
            items: groups,
            rx: Math.min(340, 240 + n * 6),
            ry: Math.min(170, 130 + n * 3),
            r: n > 12 ? 22 : 25,
            ringIdx: 0,
          });
        } else if (numRings === 2) {
          const nInner = Math.round(n * 0.38);
          const nOuter = n - nInner;
          ringNodes.push({
            items: groups.slice(nOuter),
            rx: 215,
            ry: 115,
            r: 20,
            ringIdx: 0,
          });
          ringNodes.push({
            items: groups.slice(0, nOuter),
            rx: 370,
            ry: 190,
            r: 21,
            ringIdx: 1,
          });
        } else {
          const n1 = Math.round(n * 0.22);
          const n2 = Math.round(n * 0.35);
          const n3 = n - n1 - n2;
          ringNodes.push({
            items: groups.slice(n2 + n3),
            rx: 160,
            ry: 88,
            r: 16,
            ringIdx: 0,
          });
          ringNodes.push({
            items: groups.slice(n3, n2 + n3),
            rx: 270,
            ry: 145,
            r: 17,
            ringIdx: 1,
          });
          ringNodes.push({
            items: groups.slice(0, n3),
            rx: 380,
            ry: 198,
            r: 18,
            ringIdx: 2,
          });
        }

        let globalIndex = 0;
        ringNodes.forEach((ring) => {
          const rItems = ring.items;
          const rCount = rItems.length;
          const angleOffset = ring.ringIdx === 0 && numRings > 1 ? Math.PI / rCount : 0;

          rItems.forEach((g, i) => {
            const idx = globalIndex++;
            const ang = -Math.PI / 2 + (i * 2 * Math.PI) / rCount + angleOffset;
            const tx = cx + ring.rx * Math.cos(ang);
            const ty = cy + ring.ry * Math.sin(ang);
            const nodeR = ring.r;

            edges += `<line class="pg-edge pgx-spoke${popT}" data-type="${escAttr(g.key)}" x1="${f1(cx)}" y1="${f1(cy)}" x2="${f1(tx)}" y2="${f1(ty)}" style="stroke:${EDGE};animation-delay:${idx * 30}ms" />`;

            const discSvg = countryFlagDisc(
              g.label || g.key,
              tx,
              ty,
              nodeR,
              g.color,
              "",
              `pgx-flag-${idx}-${escAttr(g.key).replace(/[^a-zA-Z0-9_-]/g, "_")}`
            );

            let lblX = tx;
            let lblY = ty + nodeR + 14;
            let textAnchor = "middle";
            const cos = Math.cos(ang);
            const sin = Math.sin(ang);

            if (numRings === 1) {
              if (n <= 10) {
                lblX = tx;
                lblY = ty + nodeR + 16;
              } else {
                if (Math.abs(cos) > 0.65) {
                  textAnchor = cos > 0 ? "start" : "end";
                  lblX = tx + (cos > 0 ? nodeR + 6 : -(nodeR + 6));
                  lblY = ty + 4;
                } else if (sin < -0.8) {
                  lblY = ty - nodeR - 6;
                } else {
                  lblY = ty + nodeR + 14;
                }
              }
            } else {
              if (ring.ringIdx < numRings - 1) {
                lblY = ty + nodeR + 12;
              } else {
                if (Math.abs(cos) > 0.65) {
                  textAnchor = cos > 0 ? "start" : "end";
                  lblX = tx + (cos > 0 ? nodeR + 6 : -(nodeR + 6));
                  lblY = ty + 4;
                } else if (sin < -0.8) {
                  lblY = ty - nodeR - 6;
                } else {
                  lblY = ty + nodeR + 14;
                }
              }
            }

            const fontSize = nodeR <= 17 ? "10px" : nodeR <= 21 ? "11.5px" : "12.5px";

            nodes +=
              `<g class="pg-node pg-type${popT}" data-type="${escAttr(g.key)}" style="animation-delay:${idx * 30}ms">` +
              `<title>${esc(g.label)} - click to open its partners</title>` +
              discSvg +
              `<text class="lbl-ptr-title" style="font-size:${fontSize};font-weight:700" x="${f1(lblX)}" y="${f1(lblY)}" text-anchor="${textAnchor}">${esc(g.label)}</text>` +
              `</g>`;
          });
        });
      }

      const centerSvg =
        `<g class="pg-node center-root" data-id="${escAll(c.id || "main")}">` +
        `<title>${esc(name)} - click to fold branches</title>` +
        `<circle class="halo halo-oem" cx="${f1(cx)}" cy="${f1(cy)}" r="${CORE_R + 12}" style="fill:none;stroke:rgba(160,172,184,0.28)" stroke-width="1.2" stroke-dasharray="4, 6" />` +
        `<circle class="net-circle" cx="${f1(cx)}" cy="${f1(cy)}" r="${CORE_R}" style="fill:#0f6f7d;stroke:#cfd3da" stroke-width="1.6" stroke-opacity="0.55" />` +
        titleSub(cx, cy + CORE_R + 22, "middle", name, v.coreSub || "", " center-title") +
        `</g>`;

      return defs + edges + nodes + centerSvg;
    }

    // STAGE 3: FOCUS
    // Shows ONLY the competitor (root), the clicked flag/category (focus), and its connected partners.
    // No other flags/categories are shown, keeping the canvas completely clean and focused.
    const rootX = 480;
    const rootY = 410;
    const rootR = 34;

    const focusX = 480;
    const focusY = 250;
    const FOCUS_R = 32;

    let edges = "";
    let nodes = "";
    const popK = v.anim === "children" ? " pgx-pop" : "";

    // 1. Focused sub-branch stem & hub connecting competitor to clicked flag
    edges += `<line class="pg-edge pgx-spoke pgx-focus" data-type="${escAttr(focus.key)}" x1="${f1(rootX)}" y1="${f1(rootY - rootR)}" x2="${f1(focusX)}" y2="${f1(focusY + FOCUS_R + 4)}" style="stroke:${focus.color || "#0ea5e9"};stroke-width:2.8px;opacity:1" />`;

    const focusDiscSvg = byRegion
      ? countryFlagDisc(
          focus.label || focus.key,
          focusX,
          focusY,
          FOCUS_R,
          "#ffffff",
          'filter="url(#pgxGlow)"',
          `pgx-flag-focus-${escAttr(focus.key).replace(/[^a-zA-Z0-9_-]/g, "_")}`
        )
      : categoryDisc(focus.key, focusX, focusY, FOCUS_R, focus.fill, "#ffffff", 'filter="url(#pgxGlow)"');

    nodes +=
      `<g class="pg-node pg-type pgx-focus" data-type="${escAttr(focus.key)}" style="cursor:pointer">` +
      `<title>${esc(focus.label)} - click to return to all ${byRegion ? "regions" : "categories"}</title>` +
      focusDiscSvg +
      `<text class="lbl-ptr-title" style="font-size:13px;font-weight:800;letter-spacing:0.04em" x="${f1(focusX)}" y="${f1(focusY + FOCUS_R + 17)}" text-anchor="middle">${esc(focus.label.toUpperCase())}</text>` +
      (byRegion ? "" : `<text class="lbl-ptr-sub" style="font-size:10px;font-weight:700;fill:${focus.color};letter-spacing:0.06em" x="${f1(focusX)}" y="${f1(focusY + FOCUS_R + 30)}" text-anchor="middle">${focus.nodes.length} PARTNERS</text>`) +
      `</g>`;

    // 3. Partner children (leaves) fanning out in expansive single arc
    const k = Math.min(focus.nodes.length, 16);
    const activeNodes = focus.nodes.slice(0, k);

    let kids = [];
    if (k === 1) {
      const ang = -Math.PI / 2;
      const x = focusX;
      const y = focusY - 150;
      const p = activeNodes[0];
      const titleLines = wrapPartnerTitle(p.label || p.name || "", 18);
      const sub = tieKindShort(p, 16, cats);
      kids.push({ p, x, y, lx: x + LEAF_R + 8, ly: y + 4, anchor: "start", titleLines, sub, ang });
    } else {
      let startAng, endAng, Rx_base, Ry_base;
      if (k <= 3) {
        startAng = -Math.PI * 0.78; endAng = -Math.PI * 0.22;
        Rx_base = 210; Ry_base = 150;
      } else if (k <= 6) {
        startAng = -Math.PI * 0.88; endAng = -Math.PI * 0.12;
        Rx_base = 235; Ry_base = 155;
      } else if (k <= 10) {
        startAng = -Math.PI * 0.95; endAng = -Math.PI * 0.05;
        Rx_base = 255; Ry_base = 165;
      } else {
        startAng = -Math.PI * 0.98; endAng = -Math.PI * 0.02;
        Rx_base = 270; Ry_base = 175;
      }

      kids = activeNodes.map((p, i) => {
        const frac = i / (k - 1);
        const ang = startAng + frac * (endAng - startAng);
        
        const x = focusX + Rx_base * Math.cos(ang);
        const y = focusY + Ry_base * Math.sin(ang);
        const cos = Math.cos(ang);
        const sin = Math.sin(ang);

        const titleLines = wrapPartnerTitle(p.label || p.name || "", 14);
        const sub = k <= 6 ? tieKindShort(p, 14, cats) : "";

        let anchor, lx, ly;
        if (Math.abs(cos) < 0.48 && sin < -0.65) {
          anchor = "middle";
          lx = x;
          const stagger = (i % 2 === 0 ? 0 : 20);
          ly = y - LEAF_R - 10 - stagger - (titleLines.length - 1) * 13;
        } else if (cos >= 0) {
          anchor = "start";
          lx = x + LEAF_R + 8;
          ly = y - (titleLines.length - 1) * 6;
        } else {
          anchor = "end";
          lx = x - LEAF_R - 8;
          ly = y - (titleLines.length - 1) * 6;
        }

        return { p, x, y, lx, ly, anchor, titleLines, sub, ang };
      });
    }

    // Label collision clearance
    const getBox = (kd) => {
      const maxLine = Math.max(...kd.titleLines.map((l) => l.length));
      const w = Math.max(maxLine * 6.8, (kd.sub || "").length * 6.0);
      const h = kd.titleLines.length * 13 + (kd.sub ? 13 : 0);
      const x0 = kd.anchor === "start" ? kd.lx : kd.anchor === "end" ? kd.lx - w : kd.lx - w / 2;
      return { x0: x0 - 2, x1: x0 + w + 2, y0: kd.ly - 9, y1: kd.ly + h };
    };

    const allCircles = kids.map((kd) => ({ x: kd.x, y: kd.y, r: LEAF_R }));
    allCircles.push({ x: focusX, y: focusY, r: FOCUS_R });

    // 1. Circle clearance
    kids.forEach((kd) => {
      for (const c of allCircles) {
        if (Math.hypot(c.x - kd.x, c.y - kd.y) < 1) continue;
        const b = getBox(kd);
        const px = Math.max(b.x0, Math.min(c.x, b.x1));
        const py = Math.max(b.y0, Math.min(c.y, b.y1));
        const dist = Math.hypot(c.x - px, c.y - py);
        if (dist < c.r + 5) {
          const push = (c.r + 5 - dist) + 2;
          if (kd.anchor === "middle") {
            kd.ly += (kd.ly >= c.y ? push : -push);
          } else if (kd.anchor === "start") {
            kd.lx += push;
          } else {
            kd.lx -= push;
          }
        }
      }
    });

    // 2. Pairwise label clearance
    for (let step = 0; step < 40; step++) {
      let moved = false;
      for (let i = 0; i < kids.length; i++) {
        for (let j = i + 1; j < kids.length; j++) {
          const b1 = getBox(kids[i]), b2 = getBox(kids[j]);
          if (b1.x0 < b2.x1 && b2.x0 < b1.x1 && b1.y0 < b2.y1 && b2.y0 < b1.y1) {
            const ovY = Math.min(b1.y1, b2.y1) - Math.max(b1.y0, b2.y0);
            const shift = ovY / 2 + 2;
            if (kids[j].ly >= kids[i].ly) {
              kids[j].ly += shift;
              kids[i].ly -= shift;
            } else {
              kids[j].ly -= shift;
              kids[i].ly += shift;
            }
            moved = true;
          }
        }
      }
      if (!moved) break;
    }

    // Render kids edges & nodes
    kids.forEach((kd, i) => {
      const { p } = kd;
      const ring = p.isOverlap ? RED_RING : p.leafColor || focus.color;
      const fill = p.isOverlap ? RED : p.leafFill || focus.fill;
      const kx = kd.x, ky = kd.y;

      edges += `<line class="pg-edge pgx-branch${p.isOverlap ? " shared" : ""}${popK}" data-a="${escAttr(focus.key)}" data-b="${escAll(p.id)}" x1="${f1(focusX)}" y1="${f1(focusY)}" x2="${f1(kx)}" y2="${f1(ky)}" style="stroke:${p.isOverlap ? RED : EDGE};stroke-width:${p.isOverlap ? "2.5px" : "1.5px"};animation-delay:${i * 30}ms" />`;

      nodes +=
        `<g class="pg-node pt-leaf${p.isOverlap ? " overlap" : ""}${popK}" data-id="${escAll(p.id)}" data-type="${escAttr(focus.key)}" style="animation-delay:${i * 30}ms">` +
        `<title>${esc(String(p.label || ""))} - ${esc(focus.label)}${p.isOverlap ? " - also on client's own roster" : ""}</title>` +
        `<circle class="pt-hit" cx="${f1(kx)}" cy="${f1(ky)}" r="${LEAF_R + 8}" fill="transparent" />` +
        disc(kx, ky, LEAF_R, fill, ring) +
        titleSub(kd.lx, kd.ly, kd.anchor, kd.titleLines, kd.sub, " pt-leaf-lbl") +
        `</g>`;
    });

    // 3. Center OEM Root node (Competitor)
    const centerSvg =
      `<g class="pg-node center-root" data-id="${escAll(c.id || "main")}" style="cursor:pointer">` +
      `<title>${esc(name)} - click to return to all ${byRegion ? "regions" : "categories"}</title>` +
      `<circle class="halo halo-oem" cx="${f1(rootX)}" cy="${f1(rootY)}" r="${rootR + 12}" style="fill:none;stroke:rgba(160,172,184,0.32)" stroke-width="1.4" stroke-dasharray="4, 6" />` +
      `<circle class="net-circle" cx="${f1(rootX)}" cy="${f1(rootY)}" r="${rootR}" style="fill:#0f6f7d;stroke:#cfd3da" stroke-width="2" stroke-opacity="0.85" />` +
      titleSub(rootX, rootY + rootR + 20, "middle", name, v.coreSub || "", " center-title") +
      `</g>`;

    return defs + edges + nodes + centerSvg;
  }

  /* the shared-partner read under the graph */
  function overlapHtml(c, cid, open, clientNameOverride) {
    const clientName = clientNameOverride || clientShort();
    const keyOf = pgKeyer(c.partners);
    const idx = pgSharedIndex();
    const shared = pgSharedFor(c);
    const dist = pgDistinct(c);
    const nm = esc(c.name);
    // roster size is only used in the prose; an older data file must not break the view
    const nRoster = (KSSL_PARTNERS || []).length;

    if (!dist) {
      return (
        '<div class="pg-ov-h"><span class="pg-ov-t clean">Overlapping partners · no network mapped</span>' +
        `<span class="pg-ov-s">No partner relationships are on file for <b>${nm}</b>, so there is nothing to ` +
        `test against ${clientName}’s own roster of ${nRoster} partners yet.</span></div>`
      );
    }
    if (!shared.length) {
      return (
        '<div class="pg-ov-h"><span class="pg-ov-t clean">Overlapping partners · none</span>' +
        `<span class="pg-ov-s">All <b>${dist}</b> of ${nm}’s mapped partners are its own. None of them appears in ` +
        `${clientName}’s roster of <b>${nRoster}</b> partners, so ${clientName} faces this rival through a separate ` +
        "channel, supply base and service network - no overlapping dealer is quoting both brands, and no red line is drawn " +
        "on the graph above.</span></div>"
      );
    }

    // rank by exposure: the more rival brands a partner carries, the weaker client's hold
    shared.sort((a, b) => (idx[keyOf(b)] || []).length - (idx[keyOf(a)] || []).length);
    const kinds = {};
    shared.forEach((p) => {
      const relKey = (p.koel && p.koel.rel) || p.rel;
      const ok = categoryOf(relKey).overlapKind;
      if (ok) kinds[ok] = 1;
    });
    const worst = shared[0];
    const worstN = (idx[keyOf(worst)] || []).length;

    /* TWO KINDS OF RED LINE, AND THEY DO NOT READ THE SAME.

       `clientTie` means the rival's partner IS the client — Saab and Paramount both
       have a direct agreement with KSSL. The shelf language ("carries KSSL and 2
       rivals", "1 of 3 brands on that shelf") describes a THIRD party serving
       several brands, and applying it here told the reader the client is a
       distributor stocking itself. */
    const direct = shared.filter((p) => p.clientTie);
    const viaThird = shared.filter((p) => !p.clientTie);
    let h =
      `<div class="pg-ov-h"><span class="pg-ov-t">◆ Overlapping partners · ${shared.length} of ${dist}</span>` +
      `<span class="pg-ov-s">` +
      (direct.length
        ? `<b>${esc(nm)}</b> has a direct agreement with <b>${clientName}</b> itself` +
          (viaThird.length
            ? `, and ${viaThird.length} of its other partners ${viaThird.length === 1 ? "is" : "are"} also ${clientName}’s`
            : "") +
          " - red above"
        : `<b>${shared.length}</b> of ${nm}’s ${dist} mapped partners ` +
          `${shared.length === 1 ? "is" : "are"} also <b>${clientName}’s</b> own - red above`) +
      (viaThird.length && worstN > 1
        ? `. Widest: <b>${esc(worst.label)}</b> carries ${clientName} and ${worstN} rivals, so ${clientName} is 1 of ${worstN + 1} brands on that shelf.`
        : direct.length
          ? "."
          : `, and ${clientName} holds no exclusivity.`) +
      "</span></div>";

    h += '<div class="pg-ov-ties">';
    shared.forEach((p) => {
      const all = (idx[keyOf(p)] || []).length;
      const also = (idx[keyOf(p)] || []).filter((r) => r.cid !== cid).map((r) => r.name);
      // both sides are almost always the same relation, so print it once
      const pRel = (p.koel && p.koel.rel) || p.rel;
      const same = (pRel || "").toLowerCase() === (p.ptype || "").toLowerCase();
      const rel = same
        ? esc((p.ptype || "partner").toLowerCase())
        : `${esc((pRel || "").toLowerCase())} to ${clientName}, ${esc((p.ptype || "").toLowerCase())} here`;
      h +=
        `<div class="pg-ov-tie" data-pid="${escAll(p.id)}" title="Open this relationship">` +
        `<span class="pg-ov-nm">${esc(p.label)}</span>` +
        `<span class="pg-ov-cnt">${clientName} + ${all} rival${all === 1 ? "" : "s"}</span>` +
        `<span class="pg-ov-use">overlapping ${rel}` +
        `${also.length ? ` · also ${esc(also.join(", "))}` : ""}</span></div>`;
    });
    h += "</div>";

    /* The "what an overlapping partner costs" read used to print HERE, under the ties.
       It is interpretation, not relationship: the canvas states WHO overlaps and on
       what terms, and the side drawer carries what that means. See overlapDefsHtml. */
    return h;
  }

  /* The interpretation half of the overlap read, for the RIGHT-HAND DRAWER.
     Which definitions appear is decided by the SAME `kinds` map the canvas builds —
     a rival whose only overlap is a distributor must not be handed the technology
     read. Returns "" when there is no overlap, so the drawer prints nothing rather
     than an empty heading. */
  function overlapDefsHtml(c, cid, clientNameOverride) {
    const clientName = clientNameOverride || clientShort();
    if (!c || !pgDistinct(c)) return "";
    const shared = pgSharedFor(c);
    if (!shared.length) return "";
    const kinds = {};
    shared.forEach((p) => {
      const relKey = (p.koel && p.koel.rel) || p.rel;
      const ok = categoryOf(relKey).overlapKind;
      if (ok) kinds[ok] = 1;
    });
    const defs = overlapDefs(d);
    const sub = (t) => cats.fill(t, c.name, clientName);
    let h = "";
    Object.keys(kinds).forEach((k) => {
      const def = defs[k];
      if (!def) return;
      h +=
        `<div class="pg-ov-kind"><b>${esc(sub(def.label))}</b>${def.lead ? `<span class="pg-ov-lead"> - ${esc(sub(def.lead))}</span>` : ""}</div>` +
        '<div class="pg-ov-defs">';
      def.fx.forEach((f) => {
        h += `<div class="pg-ov-def"><div class="pg-ov-dt">${esc(sub(f[0]))}</div><div class="pg-ov-dx">${esc(sub(f[1]))}</div></div>`;
      });
      h += "</div>";
    });
    return h;
  }

  /* competitor-level drawer: the synthesis read, or the plain relationship list for
     the rivals that carry no synthesis. */
  function compReportHtml(c, cid, clientNameOverride) {
    const clientName = clientNameOverride || clientShort();
    /* A competitor id restored from localStorage can outlive the dataset that
       held it, and then `c` is an id with no row behind it. Read the ties through
       one guarded local rather than assuming the array exists. */
    const rows = c.partners || [];
    const syn = COMPSYN ? COMPSYN[cid] : null;
    const hasSyn = syn && syn.vulns && syn.vulns.length;
    if (!hasSyn) {
      let b = "";
      /* The "Latest updates" block is gone by request. It was also a live shape bug:
         `c.updates` is an HTML STRING on 10 companies and an always-empty ARRAY on the
         other 20, and `if ([])` is true — so twenty rivals rendered the heading over
         nothing at all. Removing the block removes both. */
      b += `<div class="pg-r-sec"><span class="eyebrow">Relationships (${rows.length})</span><div class="pg-rellist">`;
      rows.forEach((p) => {
        b +=
          `<div class="pg-rel" data-pid="${escAll(p.id)}"><span class="rmark rel-${p.rel}"></span>` +
          `<span class="rtxt"><b>${esc(p.label)}</b> <span class="pg-ctag sm">${esc(p.country || "—")}</span> <span class="rtype">${esc(p.ptype || categoryOf(p.rel).label || "—")}</span>${statusTag(p)}<br>` +
          `<span class="rnote">${joinParts([p.note, p.deal !== "n/d" ? p.deal : null, p.date].map(esc))}</span></span></div>`;
      });
      b += "</div></div>";
      // a company revived from the archive has no assessment written for it; an
      // empty box under the heading is not an assessment
      if (c.assess && isVisible("parallax-read"))
        b += `<div class="pg-assess"><span class="tl">Assessment for ${clientName}</span>${c.assess}</div>`;
      b += sourcesSectionHtml(c);
      return b;
    }

    // ---- synthesis mode ----
    let h = "";
    h += `<div class="syn-thesis"><span class="stl">Read on this competitor</span><span class="stx">${esc(syn.thesis)}</span></div>`;
    h +=
      '<div class="syn-stats">' +
      `<div class="syn-stat"><div class="sv">${rows.length}</div><div class="sl">Ties</div></div>` +
      "</div>";
    h += '<div class="syn-sec-l vuln">▸ Structural weaknesses</div>';
    syn.vulns.forEach((v, i) => {
      const chips = (v.from || []).map((f) => `<span class="syn-chip">${esc(f)}</span>`).join("");
      const traceable = v.from && v.from.length ? " traceable" : "";
      h +=
        `<div class="syn-vuln${traceable}" data-vix="${i}"><div class="syn-vuln-h" data-vulnclick="${i}">` +
        `<span class="syn-vuln-n">${i + 1}</span><div><div class="syn-vuln-t">${esc(v.title)}</div><div class="syn-vuln-from">${chips}</div></div></div>` +
        `<div class="syn-vuln-b"><div class="syn-vuln-intel">${esc(v.intel)}</div></div></div>`;
    });
    if (syn.strat && syn.strat.thesis) {
      h += '<div class="syn-sec-l strat" style="margin-top:16px">▸ What their web reveals</div>';
      h +=
        `<div class="syn-strat"><div class="st">${esc(syn.strat.thesis)}</div>` +
        (syn.strat.pattern ? `<div class="sp"><b>Pattern:</b> ${esc(syn.strat.pattern)}</div>` : "") +
        (syn.strat.sowhat
          ? `<div class="sp" style="color:var(--d-txt)"><b>Read:</b> ${esc(syn.strat.sowhat)}</div>`
          : "") +
        "</div>";
    }
    h += `<button class="field-btn" style="margin-top:16px" data-fieldread="1">◆ Field-level read - patterns across all ${Object.keys(competitors).length}</button>`;
    h += sourcesSectionHtml(c);
    return h;
  }

  function sourcesSectionHtml(c) {
    if (!c) return "";
    const srcs = c.srcs && c.srcs.length ? c.srcs : c.site ? [{ label: "Company website", url: c.site }] : null;
    if (!srcs || !srcs.length) return "";
    return (
      '<div class="pg-drawer-sources" style="margin-top:24px;padding-top:16px;border-top:1px solid var(--l-line,#e0e0e0);">' +
      '<span class="eyebrow" style="display:block;margin-bottom:8px;color:var(--l-txt-3,#888888);font-size:10px;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;">Sources</span>' +
      `<div class="pg-src-links">${srcChips(srcs)}</div>` +
      '</div>'
    );
  }

  function drawerHead(c, cid) {
    const syn = COMPSYN ? COMPSYN[cid] : null;
    const hasSyn = syn && syn.vulns && syn.vulns.length;
    return hasSyn ? "Intelligence" : "Relationships";
  }

  /* one relationship row, the drawer's deepest read */
  function tieHtml(c, cid, pid, clientNameOverride, activeRelCardIndex) {
    const clientName = clientNameOverride || clientShort();
    const p = (c.partners || []).find((x) => x.id === pid);
    if (!p) return "";

    /* Every row for the same company, keyed the way the graph node is, so one click opens ALL
       its ties (a distributor that is also a rental arm and a framework partner). */
    const keyOf = pgKeyer(c.partners);
    const pk = keyOf(p);
    const rows = (c.partners || []).filter((x) => keyOf(x) === pk);
    rows.sort((x, y) => (x.id === p.id ? -1 : y.id === p.id ? 1 : (y.sig || 0) - (x.sig || 0)));
    const canon = keyOf.canon || {};
    const partnerName = rows.length > 1 ? (canon[pk] && canon[pk].name) || p.label : p.label;
    const partnerCountries = (canon[pk] && canon[pk].countries) || [];

    const real = (v) => {
      const t = typeof v === "string" ? v.trim() : v;
      return t && t !== "n/d" && t !== "null" ? t : null;
    };
    /* a verdict is a stance: threat or watch, nothing else (a stored third value draws no verdict at all) */
    const RANK = { threat: 2, watch: 1 };
    const VERDICT_STYLE = {
      threat: ["#fdecea", "#b5341f", "#f3b8ae"],
      watch: ["#fdf4dc", "#8a6212", "#ecd28a"],
    };
    const WORDS = stanceWords();   // the two stance words: threat, watch
    const pill = (text, [bg, fg, br]) =>
      `<span style="font-family: var(--mono); font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; background: ${bg}; color: ${fg}; border: 1px solid ${br}; padding: 3px 8px; border-radius: 4px; white-space: nowrap;">${esc(text)}</span>`;
    const chip = (text) =>
      `<span style="font-family: var(--mono); font-size: 10.5px; font-weight: 600; background: #f0efea; color: #3d3d39; padding: 3px 8px; border-radius: 3px; overflow-wrap: anywhere;">${esc(text)}</span>`;
    const label = (t) =>
      `<div style="font-family: var(--mono); font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #6b6a63; margin-bottom: 3px;">${t}</div>`;
    const NO = String(clientName);

    const verdicts = rows.map((r) => verdictOf(r)).filter(Boolean);
    const net = verdicts.sort((x, y) => RANK[y] - RANK[x])[0] || null;
    const types = [...new Set(rows.map((r) => real(r.ptype) || categoryOf(r.rel).label))];
    const where = partnerCountries.length ? partnerCountries : [real(p.country)].filter(Boolean);

    let h = `<div style="display: flex; flex-direction: column; gap: 14px;">`;

    // WHO <-> WHO, in one line, with the verdict for the client
    h += `<div class="tie-hero">` +
      `<div class="th-name" style="color: #161614;">${esc(c.name)} ↔ ${esc(partnerName)}</div>` +
      `<div class="th-meta" style="flex-wrap: wrap; gap: 6px;">${types.map(chip).join("")}${statusTag(p)}${confTag(p)}${where.length ? `<span>${esc(where.join(", "))}</span>` : ""}</div>` +
      `<div style="font-size: 12.5px; color: #3d3d39; line-height: 1.5; margin-top: 8px;">` +
      `${esc(partnerName)} has ${rows.length} ${rows.length === 1 ? "tie" : "ties"} with ${esc(c.name)}: ${esc(types.join("; "))}.` +
      (net && WORDS[net] ? ` Read for ${esc(NO)}: ${pill(WORDS[net], VERDICT_STYLE[net])}` : "") +
      `</div></div>`;

    rows.forEach((r, i) => {
      const cat = categoryOf(r.rel);
      const typeLabel = real(r.ptype) || cat.label;
      const verdict = verdictOf(r);
      const impact = impactText(r);
      const note = real(r.note) || pgThinNote(r, c.name);
      const srcs = (r.srcs || []).filter((x) => x && x.url);
      const facts = [
        ["Relationship", typeLabel],
        ["Territory", real(r.country)],
        ["Since", real(r.date)],
        ["Deal value", real(r.deal)],
      ].filter(([, v]) => v);

      h += `<div style="background: #ffffff; color: #161614; border: 1px solid #e2e0d8; border-radius: 8px; padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">`;
      h += `<div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">` +
        `<span style="display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700;"><span class="rmark rel-${escAll(r.rel || "other")}" style="width: 10px; height: 10px; border-radius: 50%; background: ${cat.color};"></span>${rows.length > 1 ? `${i + 1}. ` : ""}${esc(typeLabel)}${real(r.country) ? ` · ${esc(r.country)}` : ""}</span>` +
        (verdict && WORDS[verdict] ? pill(WORDS[verdict], VERDICT_STYLE[verdict]) : "") + `</div>`;

      // what this kind of tie IS, in plain words
      h += `<div>${label("What this kind of tie means")}<div style="font-size: 12.5px; color: #3d3d39; line-height: 1.55;"><b>${esc(typeLabel)}</b>: ${esc(categoryDef(r.rel, c.name))}</div></div>`;

      if (note) h += `<div>${label(`What the record says`)}<div style="font-size: 13px; color: #161614; line-height: 1.6;">${esc(note)}</div></div>`;

      h += `<div style="padding: 12px 14px; background: #f7f6f3; border: 1px solid #e2e0d8; border-radius: 6px;">${label(`What it means for ${esc(NO)}`)}` +
        `<div style="font-size: 13px; color: #161614; line-height: 1.6;">${impact ? esc(impact) : "No read on record for this tie."}</div></div>`;

      h += `<div style="display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; font-size: 12px;">` +
        facts.map(([k, v]) => `<span style="color: #6b6a63;">${esc(k)}</span><span style="color: #161614; font-weight: 600;">${esc(v)}</span>`).join("") +
        `</div>`;

      if (srcs.length) h += `<div>${label("Sources")}<div class="pg-src-links">${srcChips(srcs)}</div></div>`;
      h += `</div>`;
    });

    h += `</div>`;
    return h;
  }

  /* Field-level read: the patterns that are invisible in any single dossier. */
  function fieldReadHtml(cid) {
    if (!FIELDSYN) return "";
    const cname = (competitors[cid] && competitors[cid].name) || "competitor";
    let h = "";
    h +=
      '<div style="padding:4px 0 8px"><div style="font-size:15px;font-weight:700;margin-bottom:3px">Field-level intelligence</div>' +
      `<div style="font-size:11px;color:var(--d-txt-3);margin-bottom:14px">Patterns across all ${Object.keys(competitors).length} competitors - invisible in any single dossier.</div>`;
    (FIELDSYN.patterns || []).forEach((p, i) => {
      h +=
        `<div class="syn-strat" style="border-left-color:#3d7fbf;margin-bottom:10px"><div class="st">${i + 1}. ${esc(p.field || p.t)}</div>` +
        `<div class="sp"><b>Pattern:</b> ${esc(p.pattern || p.e)}${p.total ? ` <span style="opacity:.6">(${p.n} of ${p.total})</span>` : ""}</div>` +
        `<div class="sp" style="color:var(--d-txt)"><b>Read:</b> ${esc(p.implication || p.s)}</div></div>`;
    });
    h += `<div class="syn-strat" style="border-left-color:#3d7fbf;margin-top:6px"><div class="st">Bottom Line</div><div class="sp" style="color:var(--d-txt)">${esc(FIELDSYN.bottomLine || FIELDSYN.bottom || "")}</div></div></div>`;
    // every URL behind the corpus, grouped by company — same list pattern as above
    try {
      if (sourceRegistry && sourceRegistry.length) {
        const byCo = {};
        sourceRegistry.forEach((r) => {
          (byCo[r.company || "—"] = byCo[r.company || "—"] || []).push(r);
        });
        h += `<div class="syn-sec-l" style="margin-top:16px">▸ All tracked sources (${sourceRegistry.length})</div>`;
        Object.keys(byCo)
          .sort()
          .forEach((co) => {
            h +=
              `<div class="syn-strat" style="border-left-color:#3d7fbf;margin-bottom:8px"><div class="st">${esc(co)}</div>` +
              `<div class="src-list" style="margin:7px 0 0">${srcChips(byCo[co].map((r) => ({ label: r.label || r.url, url: r.url })))}</div></div>`;
          });
      }
    } catch (e) {
      /* the source registry is decoration here; never let it break the read */
    }
    return h;
  }

  /* Which partner nodes a vulnerability draws on. Explicit trace ids first
     (deterministic), fuzzy label match as the fallback.
     An empty list means "no explicit ids for this vulnerability", but [] is truthy,
     so the original guard disabled the fuzzy fallback and nothing ever traced —
     every one of the 44 slots the export emits is empty. */
  function traceNodeIds(c, cid, ix) {
    const syn = COMPSYN && COMPSYN[cid];
    if (!syn || !syn.vulns[ix]) return [];
    const froms = syn.vulns[ix].from || [];
    const tmap = TRACEIDS && TRACEIDS[cid] ? TRACEIDS[cid] : null;
    const tl = (tmap && tmap[ix]) || null;
    const explicit = tl && tl.length ? tl : null;
    const out = [];
    (c.partners || []).forEach((p) => {
      let hit;
      if (explicit) hit = explicit.indexOf(p.id) >= 0;
      else {
        const lbl = (p.label || "").toLowerCase();
        hit = froms.some((f) => {
          const ff = f.toLowerCase().split("/")[0].split(" ")[0];
          return ff.length > 2 && lbl.indexOf(ff) >= 0;
        });
      }
      if (hit) {
        const gid = pgNodeIdFor(c, p.id);
        if (out.indexOf(gid) < 0) out.push(gid);
      }
    });
    return out;
  }

  /* Guards the overlap logic against the ways it can go quietly wrong: an unmatched
     partner, a double-counted duplicate row, or a KSSL relation with no definition
     behind it (which would silently print the wrong consequence). */
  function selfCheck() {
    const fail = [];
    const ok = (cond, msg) => {
      if (!cond) fail.push(msg);
    };
    const idx = pgSharedIndex();
    const roster = rosterIndex(KSSL_PARTNERS);
    let flagged = 0;
    Object.keys(competitors).forEach((cid) => {
      const c = competitors[cid];
      if (c.isBf || cid === CLIENT_CID) return;
      const sh = pgSharedFor(c);
      const keyOf = pgKeyer(c.partners);
      sh.forEach((p) => {
        const k = keyOf(p);
        if (!k) return;
        flagged++;
        ok(!!rosterLookup(roster, p), `${p.label} is flagged shared but is absent from roster`);
        const rel = (p.koel && p.koel.rel) || p.rel;
        ok(!!rel, `${p.label} is flagged shared but does not say what client uses it for`);
        const hits = (idx[k] || []).filter((r) => r.cid === cid);
        ok(hits.length === 1, `${p.label} appears ${hits.length} times for ${c.name} - duplicate rows leaked`);
      });
      ok(sh.length <= pgDistinct(c), `${c.name} has more shared partners than distinct partners`);
    });
    if (fail.length && KSSL_PARTNERS && KSSL_PARTNERS.length > 0) {
      console.error("shared-partner self-check FAILED:", fail);
    }
    return fail;
  }

  /* Measures the three things the old layout got wrong, on every competitor: a line
     with no node of its own, a line passing through someone else's node, and labels
     sitting on top of each other. Geometry, not eyeballing. */
  function geomCheck() {
    const fail = [];
    const ok = (c, m) => {
      if (!c) fail.push(m);
    };
    const CH = 5.55; // mono advance at 9.5px
    let worstGap = 999;
    let worstClear = 999;
    let pairs = 0;
    let labels = 0;
    Object.keys(competitors).forEach((cid) => {
      const c = competitors[cid];
      if (c.isBf || cid === CLIENT_CID) return;
      c.id = cid;
      c.center = c.center || { id: cid, label: c.name };
      const parts = pgNodes(c);
      if (!parts.length) return;
      const { nodes, edges } = layoutGraph(c);
      const ptr = nodes.filter((n) => n.type === "ptr");
      const hub = nodes.filter((n) => n.type === "comp")[0];

      // one node per company, one edge per node
      ok(ptr.length === Math.min(parts.length, PG_MAX_NODES), `${c.name}: node count does not match its companies`);
      ok(edges.length === ptr.length, `${c.name}: ${edges.length} edges for ${ptr.length} nodes`);
      const ids = {};
      ptr.forEach((n) => {
        ids[n.id] = (ids[n.id] || 0) + 1;
      });
      ok(Object.keys(ids).length === ptr.length, `${c.name}: two nodes share an id`);
      edges.forEach((e) => ok(ids[e.b] === 1, `${c.name}: edge ${e.b} has no node of its own`));
      const lbl = {};
      ptr.forEach((n) => {
        lbl[n.label] = (lbl[n.label] || 0) + 1;
      });
      Object.keys(lbl).forEach((k) =>
        ok(lbl[k] === 1, `${c.name}: label "${k}" appears ${lbl[k]} times`),
      );
      // a line must clear every node that is not its endpoint
      ptr.forEach((e, i) => {
        const dx = e.x - hub.x;
        const dy = e.y - hub.y;
        const len = Math.hypot(dx, dy);
        ptr.forEach((o, j) => {
          if (i === j) return;
          let t = ((o.x - hub.x) * dx + (o.y - hub.y) * dy) / (len * len);
          t = Math.max(0, Math.min(1, t));
          const px = hub.x + t * dx;
          const py = hub.y + t * dy;
          const dist = Math.hypot(o.x - px, o.y - py);
          const rad = 8 + (o.sig || 1) * 1.4;
          worstClear = Math.min(worstClear, dist - rad);
          ok(
            dist > rad + 3,
            `${c.name}: the line to ${e.label} passes through ${o.label} (${dist.toFixed(1)}px from a ${rad.toFixed(1)}px node)`,
          );
          pairs++;
        });
      });
      // labels must not overlap: rectangle test on the anchored text boxes
      const boxes = ptr.map((nd) => {
        const rad = 8 + (nd.sig || 1) * 1.4;
        const L = pgLabel(nd, rad);
        const w = L.t.length * CH;
        const x0 = L.cls === "la-s" ? L.x : L.cls === "la-e" ? L.x - w : L.x - w / 2;
        const h = nd.rows && nd.rows.length > 1 ? 21 : 10;
        return { x0, x1: x0 + w, y0: L.y - 8, y1: L.y - 8 + h, t: L.t };
      });
      labels += boxes.length;
      for (let i = 0; i < boxes.length; i++)
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i];
          const b = boxes[j];
          const over = a.x0 < b.x1 - 1 && b.x0 < a.x1 - 1 && a.y0 < b.y1 - 1 && b.y0 < a.y1 - 1;
          ok(!over, `${c.name}: labels overlap - "${a.t}" and "${b.t}"`);
        }
      // everything must stay inside the viewBox
      boxes.forEach((b) =>
        ok(
          b.x0 >= 22 && b.x1 <= 722 && b.y0 >= 30 && b.y1 <= 434,
          `${c.name}: label "${b.t}" falls outside the viewBox [${b.x0.toFixed(0)}..${b.x1.toFixed(0)}]`,
        ),
      );
    });
    if (fail.length)
      console.error(
        "graph geometry self-check FAILED:",
        fail.slice(0, 14),
        fail.length > 14 ? `(+${fail.length - 14} more)` : "",
      );
    return {
      fail,
      worstAngleGapDeg: +((worstGap * 180) / Math.PI).toFixed(1),
      worstNodeClearancePx: +worstClear.toFixed(1),
      linePairsTested: pairs,
      labelsTested: labels,
    };
  }

  function allPartnersRosterHtml(c, cid, clientNameOverride) {
    if (!c) return "";
    const clientName = clientNameOverride || clientShort();
    /* Ranked (overlaps + evidence first) and capped: the roster surfaces the top
       defensible partners, not the long co-mention tail. */
    const all = pgNodes(c);
    const CAP = 40;
    const parts = all.slice(0, CAP);
    const countLabel = all.length > CAP ? `TOP ${CAP} OF ${all.length}` : `${all.length}`;

    let h = "";
    h += `<div style="padding: 16px 18px; border-bottom: 1px solid var(--l-line, #e2e0d8);">`;
    h += `  <div style="font-family: var(--mono); font-size: 11px; color: #b5341f; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;">`;
    h += `    ${esc(c.name)} ALLIANCE NETWORK (${countLabel} MAPPED PARTNERS)`;
    h += `  </div>`;
    h += `  <div style="font-size: 12px; color: #6b6a63; margin-top: 4px; line-height: 1.4;">`;
    h += `    Click on any partner card below or any node on the graph to open its full relationship detail page.`;
    h += `  </div>`;
    h += `</div>`;

    h += `<div style="display: flex; flex-direction: column; gap: 10px; padding: 16px 18px;">`;
    parts.forEach((p) => {
      const kinds = [...new Set((p.rows || [p]).map((r) => tieKind(r, cats)))];
      const kindText = kinds.map((k) => esc(k)).join(`</span><span style="background: #f0efea; padding: 2px 6px; border-radius: 3px; font-weight: 600; max-width: 100%; overflow-wrap: anywhere;">`);

      h +=
        `<div class="pg-partner-roster-card" data-pid="${escAll(p.id)}" style="padding: 14px; background: #ffffff; border: 1px solid #e2e0d8; border-radius: 8px; cursor: pointer; transition: all 0.15s ease-in-out; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">` +
        `<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: nowrap; width: 100%;">` +
        `<span style="font-size: 13.5px; font-weight: 700; color: #161614; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0;" title="${escAttr(p.label)}">${esc(p.label)}</span>` +
        `</div>` +
        /* the tag row WRAPS: a long tag ("Missiles & air defence JV partner") must not run past the card edge.
           The card is name, relationship label and the detail link only (owner request). */
        `<div style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; min-width: 0; font-family: var(--mono); font-size: 10.5px; color: #6b6a63;">` +
        `<span style="background: #f0efea; padding: 2px 6px; border-radius: 3px; font-weight: 600; max-width: 100%; overflow-wrap: anywhere;">${kindText}</span>` +
        `</div>` +
        `<div style="font-size: 11px; font-weight: 600; color: #b5341f; margin-top: 2px; display: inline-flex; align-items: center; gap: 4px;">` +
        `View Relationship Detail →` +
        `</div>` +
        `</div>`;
    });
    h += `</div>`;

    return h;
  }

  return {
    pgSharedIndex,
    pgSharedFor,
    pgDistinct,
    pgNodes,
    pgNodeIdFor,
    pgThinNote,
    layoutGraph,
    graphSvg,
    typeGraphSvg,
    pgTypeGroups,
    pgRegionGroups,
    pgGroups,
    pgTypeFor,
    pgLeafTypeFor,
    overlapHtml,
    overlapDefsHtml,
    compReportHtml,
    allPartnersRosterHtml,
    drawerHead,
    tieHtml,
    fieldReadHtml,
    traceNodeIds,
    ovRole,
    selfCheck,
    geomCheck,
  };
}
