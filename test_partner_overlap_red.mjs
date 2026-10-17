/* An overlapping partner must be unmistakable on the graph, in BLOOD RED.
 *
 * WHY THIS EXISTS. mark_shared.py finally ran against production and found that one of
 * Saab's 13 mapped partners -- GA-ASI, which is General Atomics and sits on KSSL's own
 * roster -- is shared. The drawer said so ("OVERLAPPING PARTNERS 1 OF 13"), and the
 * graph did not: the node was indistinguishable from the amber "Foreign OEM" cluster
 * beside it. Two causes, both fixed and both guarded here:
 *
 *   1. the edge was emitted as class="pg-edge" with no `shared` class, so the red rule
 *      in partnerships.css could never match. The ONLY red it got was an inline
 *      #8c2f2f -- a dark maroon -- drawn at 0.50 opacity, which on this background
 *      reads browner than amber.
 *   2. the node halo was drawn at the same 0.35 opacity as every other node.
 *
 * The fixture is real production data exported from serving.competitors (Saab's and
 * Rheinmetall's ties, GA-ASI's `shared` flag included), committed beside this test so it
 * runs in CI with no database. It fails if the colour regresses AND if a future change
 * stops marking the tie.
 */
import fs from "fs";
import { createPartners } from "./src/lib/partners.js";

/* --overlap in theme.css. Raised from #e8483a on 2026-09-10: the operator reported that
   overlaps still could not be found on the page, and #e8483a against --d-bg-1 is a warm
   coral that sits inside the same hue family as the threat orange already on every other
   row. This is the ONE colour in the app that has to be findable without reading, so it
   is pinned here -- if it drifts back toward the threat palette this test says so. */
const RED = "#ff2d2d";
let fails = 0;
const ck = (name, ok, detail) => {
  console.log(`  ${name.padEnd(64)} ${ok ? "ok" : "FAIL"}${!ok && detail ? "  " + String(detail).slice(0, 120) : ""}`);
  if (!ok) fails++;
};

import { wireDataset } from "./src/lib/dataset.js";
import { setClient } from "./src/lib/client.js";
const raw = JSON.parse(fs.readFileSync(new URL("./fixtures/kssl_dataset.json", import.meta.url), "utf8"));
setClient(raw.client);
const d = wireDataset(raw);
const P = createPartners(d);

/* the rival that has a partner the client also uses (marked at wire time) */
const [rid, rival] = Object.entries(d.competitors).find(([, c]) => (c.partners || []).some((p) => p.shared || p.koel));
const ga = rival.partners.find((p) => p.shared || p.koel);
ck("the dataset marks a shared partner", !!ga, ga && ga.label);

const saabComp = { ...rival, id: rid, cid: rid };
const svg = P.graphSvg(saabComp);
ck("the graph renders", typeof svg === "string" && svg.length > 200);

// the overlapping tie's edge must carry the class the red rule keys on
const sharedEdges = (svg.match(/<line class="pg-edge shared"[^>]*>/g) || []);
ck("the overlapping tie's edge carries the `shared` class", sharedEdges.length >= 1,
   `found ${sharedEdges.length}`);
ck("... and is stroked blood red, not maroon", sharedEdges.some((e) => e.includes(RED)),
   sharedEdges[0]);
ck("... at full opacity, not 0.5", sharedEdges.some((e) => /opacity="1"/.test(e)),
   sharedEdges[0]);
ck("... and thicker than an ordinary tie", sharedEdges.some((e) => /stroke-width="2.5px"/.test(e)),
   sharedEdges[0]);

// non-overlapping ties must NOT be red -- a red that is everywhere is not a signal
const plainEdges = (svg.match(/<line class="pg-edge"[^>]*>/g) || []);
ck("ordinary ties are still drawn, and none of them is red",
   plainEdges.length >= 1 && !plainEdges.some((e) => e.includes(RED)),
   `${plainEdges.length} plain edges`);

// the node itself
ck("the overlapping node is classed `overlap`", /class="pg-node ptr overlap/.test(svg));
ck("... and its halo is drawn at full strength", /opacity="0.85"/.test(svg));
ck("its tooltip says why it is red",
   /also on the client's own roster/.test(svg));

console.log(fails ? `\n${fails} FAILED` : "\nok - an overlapping partner reads as blood red, and only an overlapping partner does");
process.exit(fails ? 1 : 0);
