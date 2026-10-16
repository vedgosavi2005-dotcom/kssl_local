/* ===================================================================
   ALLIANCE GRAPH + RELATIONSHIP DRAWER

   Every value is a stored column of competitive_partnership (one row per relationship),
   _evidence (its cards) and _relationship_detail, joined to the rival by competitor_id. One
   graph node is one partner_id. Where the partner is also one of KSSL's (client_partner), the
   dataset stamps p.koel with the client's own partner row -- see lib/overlap.js for the rule.

   Built as a factory over the dataset.
   =================================================================== */
import { esc, escAll, escAttr } from "./html.js";
import { countryFlagDisc } from "./countryFlags.js";
import { categoryDisc } from "./categorySymbols.js";
import { formatDate } from "../utils/formatDate.js";

const lc = (v) => String(v == null ? "" : v).toLowerCase();
const isShared = (p) => !!(p && (p.koel || p.shared));

/* THE GRAPH'S CATEGORIES ARE THE STORED partner_type VALUES, one branch per distinct value,
   labelled exactly as stored. The icon and colour only decide how a branch LOOKS: the type text is
   matched to one of six drawings (artwork choice, not content); a type matching none gets the
   neutral "other" drawing.

   partner_type vocabulary expected from the prompts (free text, shown as stored): Joint venture,
   Supply agreement, Technology / ToT, Licensing, Manufacturing, Distribution / reseller,
   Integration / platform, MoU, Acquisition / stake, R&D, Partnership. */
const PG_STYLE = {
  tech: { color: "#e0a020", fill: "#3a2f15" },
  supply: { color: "#5b9bd5", fill: "#1d3147" },
  jv: { color: "#3fa86a", fill: "#1d3a2b" },
  mou: { color: "#b8b8c0", fill: "#2a2a30" },
  acq: { color: "#b266c9", fill: "#3a2347" },
  other: { color: "#9aa0aa", fill: "#2a2a30" },
};
export function symbolKeyOf(typeText) {
  const t = lc(typeText);
  if (/joint|\bjv\b/.test(t)) return "jv";
  if (/acqui|stake/.test(t)) return "acq";
  if (/supply|supplier|manufactur|distribut|reseller/.test(t)) return "supply";
  if (/tech|licen|r&d|rnd|research|integrat/.test(t)) return "tech";
  if (/mou|memorandum|strategic|partnership/.test(t)) return "mou";
  return "other";
}
const NO_TYPE = "_none";
const typeKeyOf = (row) => lc(row && row.ptype).trim() || NO_TYPE;
const typeLabelOf = (row) => (row && String(row.ptype || "").trim()) || "Type not stated";

/* The tie's own words, as stored. */
export function tieKind(p) {
  return p ? String(p.ptype || "") : "";
}
export function tieKindShort(p, max = 22) {
  const t = tieKind(p);
  return t.length > max ? `${t.slice(0, max - 1).replace(/[\s,(./-]+$/, "")}\u2026` : t;
}

/* "as of YYYY": the year of the row's stored as_of_date -- what the tie is stated to be true as of. */
const asOfYear = (p) => {
  const m = /^(\d{4})/.exec(String((p && p.as_of) || ""));
  return m ? Number(m[1]) : null;
};
const asOfTag = (p) => (asOfYear(p) !== null ? `<span class="tie-tag asof">as of ${asOfYear(p)}</span>` : "");

/* relationship_confidence: the three codes below carry a tooltip and a colour; any other value
   is shown as stored. */
const CONF_TAG = {
  official: ["official", "the maker or a government publisher states it"],
  corroborated: ["corroborated", "two or more independent sources"],
  single_source: ["single source", "one source, uncorroborated"],
};
const confTag = (p) => {
  const code = lc(p && p.confidence);
  if (!code) return "";
  const c = CONF_TAG[code];
  return c
    ? `<span class="tie-tag conf-${code}" title="${esc(c[1])}">${c[0]}</span>`
    : `<span class="tie-tag">${esc(p.confidence)}</span>`;
};

/* The one badge: this partner is also on the client's own roster. */
export function overlapBadge(p, clientName) {
  if (!isShared(p)) return "";
  const who = clientName || "the client";
  const title = `${(p && p.label) || "This partner"} is also on ${who}'s own partner roster.`;
  return `<span class="ov-badge ov-shared" title="${escAttr(title)}" style="font-family: var(--mono); font-size: 9.5px; background: var(--overlap-bg); color: var(--overlap); border: 1px solid var(--overlap-line); padding: 2px 7px; border-radius: 4px; font-weight: 700; white-space: nowrap; flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px;">Overlapping Partner</span>`;
}

/* What the client uses the same company for: the stored client_partner strategic_role and
   client_partner_relationship.kssl_read. */
function clientUseHtml(p, clientName) {
  const k = p && p.koel;
  if (!k) return "";
  const reads = (k.relationships || []).map((r) => r.read).filter(Boolean);
  const lines = [k.role ? `<b>${esc(clientName)} uses ${esc(k.label)} for:</b> ${esc(k.role)}` : `<b>${esc(k.label)}</b> is also on ${esc(clientName)}'s partner roster.`]
    .concat(reads.map((r) => esc(r)));
  return `<div style="margin: 0 0 14px; padding: 12px 14px; background: var(--overlap-bg); border: 1px solid var(--overlap-line); border-radius: 6px; font-size: 12.5px; line-height: 1.5; color: #161614;">${lines.join("<br>")}</div>`;
}

export function createPartners(d) {
  const clientNameOf = (override) => override || (d.client && (d.client.short || d.client.name)) || "";

  /* ===================================================================
     NODES -- one entry per partner_id; the lead row carries the rest in .rows.
     Ranked: partners that overlap the client first, then the most evidence cards, then name.
     =================================================================== */
  function pgNodes(c) {
    const by = new Map();
    (c.partners || []).forEach((p) => {
      const k = p.pid || p.id;
      if (!by.has(k)) {
        by.set(k, { ...p, key: k, rows: [p], countries: p.country ? [p.country] : [] });
        return;
      }
      const g = by.get(k);
      g.rows.push(p);
      if (p.country && !g.countries.includes(p.country)) g.countries.push(p.country);
    });
    const nodes = [...by.values()];
    nodes.forEach((n) => {
      n.pgOverlap = n.rows.some(isShared) ? 1 : 0;
      n.pgEvidence = n.rows.reduce((t, r) => t + (r.evidence || []).length, 0);
      if (!n.koel) n.koel = (n.rows.find((r) => r.koel) || {}).koel;
    });
    nodes.sort((a, b) => b.pgOverlap - a.pgOverlap || b.pgEvidence - a.pgEvidence || String(a.label).localeCompare(String(b.label)));
    return nodes;
  }
  // any relationship-row id -> the node that stands for its company
  function pgNodeIdFor(c, pid) {
    const nd = pgNodes(c).filter((n) => n.rows.some((r) => r.id === pid))[0];
    return nd ? nd.id : pid;
  }

  /* ===================================================================
     GROUPS -- company -> partner TYPE -> partners, or company -> REGION -> partners.
     A company with rows of two types appears under both, since it IS both.
     =================================================================== */
  function pgTypeGroups(c) {
    const groups = new Map();
    pgNodes(c).forEach((n) => {
      const seen = new Set();
      n.rows.forEach((r) => {
        const key = typeKeyOf(r);
        if (seen.has(key)) return;
        seen.add(key);
        if (!groups.has(key)) {
          const symbol = key === NO_TYPE ? "other" : symbolKeyOf(r.ptype);
          groups.set(key, { key, label: typeLabelOf(r), symbol, ...PG_STYLE[symbol], nodes: [] });
        }
        groups.get(key).nodes.push({ ...n, isOverlap: n.rows.some(isShared) });
      });
    });
    return [...groups.values()].sort(
      (a, b) => (a.key === NO_TYPE) - (b.key === NO_TYPE) || b.nodes.length - a.nodes.length || a.label.localeCompare(b.label),
    );
  }

  /* REGIONS: the same partner companies grouped by the stored region of their relationship row. */
  const PG_REGION_META = { color: "#7fa8c9", fill: "#23303f" };
  function pgRegionGroups(c) {
    const groups = new Map();
    pgNodes(c).forEach((n) => {
      const regions = new Set(n.rows.map((r) => String(r.country || "").trim()).filter(Boolean));
      if (!regions.size) regions.add(NO_TYPE);
      const leafKey = typeKeyOf(n);
      const leaf = PG_STYLE[leafKey === NO_TYPE ? "other" : symbolKeyOf(n.ptype)];
      regions.forEach((rg) => {
        if (!groups.has(rg)) groups.set(rg, { key: rg, label: rg === NO_TYPE ? "Region not stated" : rg, ...PG_REGION_META, nodes: [] });
        groups.get(rg).nodes.push({
          ...n,
          isOverlap: n.rows.some(isShared),
          leafColor: leaf.color,
          leafFill: leaf.fill,
          leafType: leafKey,
        });
      });
    });
    return [...groups.values()].sort(
      (a, b) => (a.key === NO_TYPE) - (b.key === NO_TYPE) || b.nodes.length - a.nodes.length || a.label.localeCompare(b.label),
    );
  }
  // the grouping the graph is drawn in: "type" (categories) or "region"
  function pgGroups(c, mode) {
    return mode === "region" ? pgRegionGroups(c) : pgTypeGroups(c);
  }
  // the group a relationship row's company node sits under (its first)
  function pgTypeFor(c, pid, mode) {
    const nodeId = pgNodeIdFor(c, pid);
    const g = pgGroups(c, mode).find((grp) => grp.nodes.some((n) => n.id === nodeId));
    return g ? g.key : null;
  }

  /* STEP-BY-STEP BRANCH EXPLORER.

     view.stage:
       "root"   only the company, in the middle
       "spread" the company and one branch per group
       "focus"  as spread, plus view.type's partners fanned out around it; that branch
                glows and the other branches dim
     view.anim names what just appeared ("types" | "children"), so only that pops in.

     Layout is computed around (0,0), then fitted into the page's fixed 960x540 viewBox.
     Partner nodes: class "pg-node pt-leaf", data-id = lead row id, data-type. */
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

          const discSvg = categoryDisc(g.symbol || "other", tx, ty, TYPE_R, g.fill, g.color, "");

          nodes +=
            `<g class="pg-node pg-type${popT}" data-type="${escAttr(g.key)}" style="animation-delay:${i * 50}ms">` +
            `<title>${esc(g.label)} - click to open its partners</title>` +
            discSvg +
            titleSub(tx, ty + TYPE_R + 18, "middle", g.label, `${g.nodes.length} PARTNER${g.nodes.length === 1 ? "" : "S"}`) +
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
      : categoryDisc(focus.symbol || "other", focusX, focusY, FOCUS_R, focus.fill, "#ffffff", 'filter="url(#pgxGlow)"');

    nodes +=
      `<g class="pg-node pg-type pgx-focus" data-type="${escAttr(focus.key)}" style="cursor:pointer">` +
      `<title>${esc(focus.label)} - click to return to all ${byRegion ? "regions" : "categories"}</title>` +
      focusDiscSvg +
      `<text class="lbl-ptr-title" style="font-size:13px;font-weight:800;letter-spacing:0.04em" x="${f1(focusX)}" y="${f1(focusY + FOCUS_R + 17)}" text-anchor="middle">${esc(focus.label.toUpperCase())}</text>` +
      (byRegion ? "" : `<text class="lbl-ptr-sub" style="font-size:10px;font-weight:700;fill:${focus.color};letter-spacing:0.06em" x="${f1(focusX)}" y="${f1(focusY + FOCUS_R + 30)}" text-anchor="middle">${focus.nodes.length} PARTNER${focus.nodes.length === 1 ? "" : "S"}</text>`) +
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
      const sub = tieKindShort(p, 16);
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
        const sub = k <= 6 ? tieKindShort(p, 14) : "";

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

    // more partners than the arc holds: say so, the full list is in the drawer
    if (focus.nodes.length > k) {
      nodes += `<text class="lbl-ptr-sub" x="14" y="${H - 12}" text-anchor="start">+${focus.nodes.length - k} more in the partner list</text>`;
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

  /* ===================================================================
     THE DRAWER -- one partner company: every relationship row it has with this rival, each
     expanded into its evidence cards (competitive_partnership_evidence). A row with no evidence
     card gets one card made from its own columns.
     =================================================================== */
  const NL = String.fromCharCode(10);
  const cardsFor = (c, node, selected) => {
    const cards = [];
    const ordered = [selected, ...node.rows.filter((r) => r !== selected)];
    ordered.forEach((r) => {
      const det = r.detail || {};
      const lines = (e) => [
        r.country ? `Active in: ${r.country}` : null,
        r.ptype ? `Type: ${r.ptype}` : null,
        (e.scope || r.scope) ? `Scope: ${e.scope || r.scope}` : null,
        (e.asOf || r.as_of) ? `Recorded: ${formatDate(e.asOf || r.as_of)}` : null,
        (e.srcNote || r.srcnote) ? `Source note: ${e.srcNote || r.srcnote}` : null,
        (e.confidence || r.confidence) ? `Confidence: ${e.confidence || r.confidence}` : null,
        (e.basis || det.basis) ? `Basis for the type: "${e.basis || det.basis}"` : null,
        det.statedAsOf ? `Stated as of: ${formatDate(det.statedAsOf)}` : null,
      ].filter(Boolean);
      const base = (e) => {
        const label = (e.label || e.type || r.ptype || "").toUpperCase();
        return {
          category: [label, String(r.country || "").toUpperCase()].filter(Boolean).join(" · "),
          ago: (e.asOf || r.as_of) ? formatDate(e.asOf || r.as_of) : "",
          title: det.title || `${c.name} ↔ ${r.label}`,
          source: e.publisher || det.publisher || "",
          url: e.articleUrl || e.url || det.articleUrl || "",
        };
      };
      if ((r.evidence || []).length) {
        r.evidence.forEach((e) => {
          cards.push({ ...base(e), id: cards.length, excerpt: e.text, fullBodyText: [e.text].concat(lines(e)).filter(Boolean).join(NL) });
        });
      } else {
        const e = {};
        cards.push({ ...base(e), id: cards.length, excerpt: r.note, fullBodyText: [r.note].concat(lines(e)).filter(Boolean).join(NL) });
      }
    });
    return cards;
  }

  /* one partner company, the drawer's deepest read */
  function tieHtml(c, cid, pid, clientNameOverride, activeRelCardIndex) {
    const clientName = clientNameOf(clientNameOverride);
    const node = pgNodes(c).find((n) => n.rows.some((r) => r.id === pid));
    if (!node) return "";
    const p = node.rows.find((r) => r.id === pid);
    const cards = cardsFor(c, node, p);
    const symbol = symbolKeyOf(p.ptype);

    // A SELECTED CARD: the full read
    if (activeRelCardIndex !== null && activeRelCardIndex !== undefined && cards[activeRelCardIndex]) {
      const card = cards[activeRelCardIndex];
      let h = "";
      h += `<div style="background: #ffffff; color: #161614; padding: 24px; border: 1px solid #e2e0d8; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); display: flex; flex-direction: column; gap: 16px;">`;
      h += `  <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e0d8; padding-bottom: 14px;">`;
      h += `    <div style="display: flex; align-items: center; gap: 8px;">`;
      h += `      <span style="width: 8px; height: 8px; border-radius: 50%; background: #b5341f; display: inline-block;"></span>`;
      h += `      <span style="font-family: var(--mono); font-size: 11px; color: #b5341f; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;">`;
      h += `        ${esc([c.name, card.category, card.ago].filter(Boolean).join(" · "))}`;
      h += `      </span>`;
      h += `    </div>`;
      h += `    <button type="button" data-backrelcards="true" style="background: #f0efea; border: 1px solid #cfcdc3; color: #161614; padding: 5px 12px; border-radius: 6px; font-size: 11.5px; font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px;">`;
      h += `      ← Back`;
      h += `    </button>`;
      h += `  </div>`;
      h += `  <h2 style="font-size: 22px; font-weight: 700; color: #161614; line-height: 1.35; margin: 0;">${esc(card.title)}</h2>`;
      if (card.source || card.url) {
        h += `  <div style="font-size: 12px; color: #6b6a63; font-weight: 600;">`;
        h += card.url
          ? `    Source publisher: <a href="${escAttr(card.url)}" target="_blank" rel="noopener noreferrer" style="color: #b5341f;">${esc(card.source || card.url)} ↗</a>`
          : `    Source publisher: <span style="color: #b5341f;">${esc(card.source)}</span>`;
        h += `  </div>`;
      }
      h += `  <div style="font-size: 14px; color: #3d3d39; line-height: 1.75; white-space: pre-line;">${esc(card.fullBodyText)}</div>`;
      h += `</div>`;
      return h;
    }

    // DEFAULT VIEW: the relationship's hero, then one card per evidence row
    let h = "";
    const countries = node.countries.join(", ");
    h +=
      `<div class="tie-hero"><div class="th-name" style="color: #161614;">${esc(c.name)} ↔ ${esc(node.label)}</div>` +
      `<div class="th-meta">${p.ptype ? `<span class="tie-rel-pill"><span class="rmark rel-${symbol}"></span>${esc(p.ptype)}</span>` : ""}${asOfTag(p)}${confTag(p)}${countries ? `<span>${esc(countries)}</span>` : ""}</div></div>`;
    h += clientUseHtml(node, clientName);
    h += `<div style="font-size: 12px; color: #6b6a63; margin: 12px 0 16px 0;">Select a card below to read detailed intelligence on this relationship:</div>`;
    h += `<div style="display: flex; flex-direction: column; gap: 12px;">`;
    cards.forEach((card, idx) => {
      h +=
        `<div class="pg-news-feed-card" data-relcard="${idx}" style="display: flex; gap: 12px; padding: 14px; background: #ffffff; border: 1px solid #e2e0d8; border-radius: 8px; cursor: pointer; transition: all 0.15s ease-in-out; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">` +
          `<div style="width: 90px; height: 75px; border-radius: 6px; background: #f7f6f3; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-shrink: 0; border: 1px solid #e2e0d8;">` +
            `<span class="rmark rel-${symbol}" style="width: 10px; height: 10px; border-radius: 50%;"></span>` +
            `<span style="font-family: var(--mono); font-size: 8.5px; color: #6b6a63; font-weight: 700; margin-top: 4px; text-align: center; padding: 0 2px;">CARD ${idx + 1}</span>` +
          `</div>` +
          `<div style="display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0;">` +
            `<div style="font-family: var(--mono); font-size: 10.5px; color: #b5341f; font-weight: 600; text-transform: uppercase;">` +
              `${esc([card.category, card.ago].filter(Boolean).join(" · "))}` +
            `</div>` +
            `<div style="font-size: 13px; font-weight: 700; color: #161614; line-height: 1.35;">${esc(card.title)}</div>` +
            (card.excerpt
              ? `<div style="font-size: 11.5px; color: #6b6a63; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${esc(card.excerpt)}</div>`
              : "") +
            (card.source
              ? `<span style="font-size: 11px; color: #3d3d39; margin-top: auto;"><span class="src-dot"></span>${esc(card.source)}</span>`
              : "") +
          `</div>` +
        `</div>`;
    });
    h += `</div>`;
    return h;
  }

  function allPartnersRosterHtml(c, cid, clientNameOverride) {
    if (!c) return "";
    const clientName = clientNameOf(clientNameOverride);
    const parts = pgNodes(c);

    let h = "";
    h += `<div style="padding: 16px 18px; border-bottom: 1px solid var(--l-line, #e2e0d8);">`;
    h += `  <div style="font-family: var(--mono); font-size: 11px; color: #b5341f; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;">`;
    h += `    ${esc(c.name)} ALLIANCE NETWORK (${parts.length} MAPPED PARTNER${parts.length === 1 ? "" : "S"})`;
    h += `  </div>`;
    h += `  <div style="font-size: 12px; color: #6b6a63; margin-top: 4px; line-height: 1.4;">`;
    h += `    Click on any partner card below or any node on the graph to open its full relationship detail page.`;
    h += `  </div>`;
    h += `</div>`;

    h += `<div style="display: flex; flex-direction: column; gap: 10px; padding: 16px 18px;">`;
    parts.forEach((p) => {
      const kindText = esc(tieKind(p));
      const where = p.countries.join(", ");
      h +=
        `<div class="pg-partner-roster-card" data-pid="${escAll(p.id)}" style="padding: 14px; background: #ffffff; border: 1px solid #e2e0d8; border-radius: 8px; cursor: pointer; transition: all 0.15s ease-in-out; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">` +
        `<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: nowrap; width: 100%;">` +
        `<span style="font-size: 13.5px; font-weight: 700; color: #161614; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0;" title="${escAttr(p.label)}">${esc(p.label)}</span>` +
        `${overlapBadge(p, clientName)}` +
        `</div>` +
        (kindText || where
          ? `<div style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; min-width: 0; font-family: var(--mono); font-size: 10.5px; color: #6b6a63;">` +
            (kindText ? `<span style="background: #f0efea; padding: 2px 6px; border-radius: 3px; font-weight: 600; max-width: 100%; overflow-wrap: anywhere;">${kindText}</span>` : "") +
            (where ? `<span style="max-width: 100%; overflow-wrap: anywhere;">${kindText ? "·&nbsp;" : ""}${esc(where)}</span>` : "") +
            `</div>`
          : "") +
        (p.note
          ? `<div style="font-size: 12px; color: #4b5563; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${esc(p.note)}</div>`
          : "") +
        `<div style="font-size: 11px; font-weight: 600; color: #b5341f; margin-top: 2px; display: inline-flex; align-items: center; gap: 4px;">` +
        `View Relationship Detail →` +
        `</div>` +
        `</div>`;
    });
    h += `</div>`;

    return h;
  }

  return {
    pgNodes,
    pgNodeIdFor,
    typeGraphSvg,
    pgTypeGroups,
    pgRegionGroups,
    pgGroups,
    pgTypeFor,
    allPartnersRosterHtml,
    tieHtml,
  };
}
