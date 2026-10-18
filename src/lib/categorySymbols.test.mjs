import assert from "node:assert/strict";
import test from "node:test";
import { categorySymbolSvg, categoryDisc } from "./categorySymbols.js";
import { createPartners } from "./partners.js";

test("categorySymbolSvg: generates valid vector markup for all known category keys", () => {
  const categories = ["tech", "supply", "jv", "mou", "acq", "other"];
  for (const cat of categories) {
    const svg = categorySymbolSvg(cat, 100, 100, 24, "#48c774", "rgba(72, 199, 116, 0.2)");
    assert.ok(svg && typeof svg === "string", `Category ${cat} should return non-empty SVG string`);
    assert.ok(svg.length > 20, `Category ${cat} SVG should have substantial content`);

    // Verify key characteristics per category
    if (cat === "tech") {
      assert.ok(svg.includes("<rect"), "tech should render processor rects");
      assert.ok(svg.includes("<line"), "tech should render pin leads");
    } else if (cat === "supply") {
      assert.ok(svg.includes("<polygon"), "supply should render isometric 3D cargo facets");
    } else if (cat === "jv") {
      assert.ok(svg.includes("<circle"), "jv should render alliance rings");
      assert.ok(svg.includes("<path"), "jv should render alliance clasp");
    } else if (cat === "mou") {
      assert.ok(svg.includes("<path"), "mou should render charter document outline and corner");
      assert.ok(svg.includes("<circle"), "mou should render wax seal");
    } else if (cat === "acq") {
      assert.ok(svg.includes("<circle"), "acq should render bullseye concentric circles");
      assert.ok(svg.includes("<line"), "acq should render crosshairs");
    } else if (cat === "other") {
      assert.ok(svg.includes("<circle") && svg.includes("<line"), "other should render constellation nodes and spokes");
    }
  }
});

test("categoryDisc: wraps symbol in halo, net-circle, and pg-cat-symbol group", () => {
  const disc = categoryDisc("tech", 200, 150, 24, "rgba(99,102,241,0.2)", "#6366f1", 'data-test="node"');
  assert.ok(disc.includes('class="halo"'), "Disc should contain halo circle");
  assert.ok(disc.includes('class="net-circle"'), "Disc should contain net-circle");
  assert.ok(disc.includes('data-test="node"'), "Disc should forward extra attributes to net-circle");
  assert.ok(disc.includes('class="pg-cat-symbol"'), "Disc should contain pg-cat-symbol wrapper");
  assert.ok(disc.includes('pointer-events="none"'), "Symbol should not intercept mouse clicks on node");
});

test("typeGraphSvg integration: renders categoryDisc with symbols in Categories mode", () => {
  const mockData = {
    competitors: {},
    KSSL_PARTNERS: [
      { id: "p1", label: "Alpha Cyber", rel: "tech", role: "AI Guidance", country: "India" },
      { id: "p2", label: "Beta Logistics", rel: "supply", role: "Armor Components", country: "Israel" },
      { id: "p3", label: "Gamma Dynamics", rel: "jv", role: "Aviation Systems", country: "USA" }
    ],
    REL_LABEL: {},
    FIELDSYN: {},
    COMPSYN: {},
    TRACEIDS: {},
    sourceRegistry: {},
  };

  const partners = createPartners(mockData);
  const ksslCo = {
    id: "KSSL",
    name: "KSSL",
    dir: "client",
    partners: mockData.KSSL_PARTNERS,
  };

  // 1. Stage "spread" renders category branch nodes with vector symbols
  const spreadSvg = partners.typeGraphSvg(ksslCo, { stage: "spread", mode: "cat" });
  assert.ok(spreadSvg.includes('class="pg-cat-symbol"'), "Rendered spread SVG should include pg-cat-symbol");
  assert.ok(spreadSvg.includes("Technology / licence"), "Rendered spread SVG should contain the technology category");
  assert.ok(spreadSvg.includes("Supply / customer"), "Rendered spread SVG should contain Supply / customer category");
  assert.ok(spreadSvg.includes("Joint venture"), "Rendered spread SVG should contain Joint venture category");
  assert.ok(spreadSvg.includes('class="lbl-ptr-title center-title"'), "Rendered spread SVG should include center-title");

  // 2. Stage "focus" on "tech" renders the tech partners as leaf nodes
  const focusSvg = partners.typeGraphSvg(ksslCo, { stage: "focus", mode: "cat", type: "technology-partner" });
  assert.ok(focusSvg.includes('class="pg-cat-symbol"'), "Rendered focus SVG should include pg-cat-symbol");
  assert.ok(focusSvg.includes("Alpha Cyber"), "Rendered focus SVG should contain partner Alpha Cyber under tech");
  assert.ok(focusSvg.includes("pt-leaf"), "Rendered focus SVG should include pt-leaf nodes");
  assert.ok(focusSvg.includes("pt-leaf-sub"), "Rendered focus SVG should include pt-leaf-sub subtitles");
});

test("typeGraphSvg: dense sub-branches spread radially rather than clustering in a column", () => {
  const densePartners = Array.from({ length: 14 }, (_, i) => ({
    id: `dense_${i}`,
    label: `Partner Company ${i + 1}`,
    rel: "other",
    role: "Defense Systems",
    country: "India",
  }));

  const mockData = {
    competitors: {},
    KSSL_PARTNERS: densePartners,
    REL_LABEL: {},
    FIELDSYN: {},
    COMPSYN: {},
    TRACEIDS: {},
    sourceRegistry: {},
  };

  const partners = createPartners(mockData);
  const co = { id: "test_co", name: "Test Corp", partners: densePartners };
  const svg = partners.typeGraphSvg(co, { stage: "focus", mode: "cat", type: "other" });

  // Extract all cx coordinates of pt-leaf nodes
  const leafCircles = Array.from(svg.matchAll(/class="pg-node pt-leaf[^"]*"[^>]*>[\s\S]*?<circle class="net-circle" cx="([^"]+)" cy="([^"]+)"/g));
  assert.equal(leafCircles.length, 14, "Should render all 14 partner leaf nodes");

  const xCoords = leafCircles.map((m) => parseFloat(m[1]));
  const yCoords = leafCircles.map((m) => parseFloat(m[2]));

  // In the old bug, all 14 nodes had identical x coordinates (a single vertical line)
  const uniqueX = new Set(xCoords.map((x) => Math.round(x)));
  const uniqueY = new Set(yCoords.map((y) => Math.round(y)));

  assert.ok(uniqueX.size >= 6, `X coordinates should vary widely in radial fan (found ${uniqueX.size} unique values)`);
  assert.ok(uniqueY.size >= 6, `Y coordinates should vary widely in radial fan (found ${uniqueY.size} unique values)`);
});

