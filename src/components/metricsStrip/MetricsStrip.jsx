import { useEffect, useRef, useState } from "react";
import { srcChips } from "../../lib/html";

/* Count-up on the numeric value. The original animated by writing into the text node
   directly; here it is state, so React still owns the DOM. Non-numeric values (—, a
   date) skip the animation and render as-is.

   The tween used to count a fixed 28 requestAnimationFrame ticks. rAF is not a clock:
   the browser throttles or stops it outright when the page is not being painted, so
   the count stalled around a fifth of the way up and STAYED there — the tiles read
   15 / 4 / 4 / 1 / 0 / 1 against real values of 71 / 18 / 19 / 5 / 3 / 7, six numbers
   on screen the data never contained. It is now driven by the clock, and a timer
   independent of rAF snaps it onto the exact target no matter what the frame loop
   did. A partial value can no longer be the last thing on screen. */
const DURATION_MS = 620;

function CountUp({ text }) {
  const label = String(text);
  const target = parseFloat(label.replace(/,/g, ""));
  const hasComma = label.includes(",");
  const isNum = !Number.isNaN(target);
  const final = isNum ? (hasComma ? target.toLocaleString("en-IN") : String(target)) : label;
  const [shown, setShown] = useState(final);
  const frame = useRef(0);
  const timer = useRef(0);

  useEffect(() => {
    if (!isNum) {
      setShown(label);
      return undefined;
    }
    const reduced =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setShown(final);
      return undefined;
    }
    let done = false;
    const settle = () => {
      if (done) return;
      done = true;
      setShown(final);
    };
    const t0 = Date.now();
    const tick = () => {
      const p = Math.min(1, (Date.now() - t0) / DURATION_MS);
      if (p >= 1) {
        settle();
        return;
      }
      const value = Math.round(target * p);
      setShown(hasComma ? value.toLocaleString("en-IN") : String(value));
      frame.current = requestAnimationFrame(tick);
    };
    setShown(hasComma ? (0).toLocaleString("en-IN") : "0");
    frame.current = requestAnimationFrame(tick);
    // the safety net: timers still fire where rAF is throttled or suspended
    timer.current = setTimeout(settle, DURATION_MS + 80);
    return () => {
      cancelAnimationFrame(frame.current);
      clearTimeout(timer.current);
      // a cancelled tween must never leave its partial value behind
      settle();
    };
  }, [target, hasComma, label, isNum, final]);

  return <>{shown}</>;
}

/* Each tile is a door into the feed — except where `inert` is set. The Market overview
   is a tender report with its own tabs and filter, so its tiles have no feed to open;
   they render as a readout with no button role, no focus stop and no "→" affordance,
   because a control that looks live and does nothing is worse than a plain number. */
export default function MetricsStrip({ metrics, active, onPick, inert = false }) {
  return (
    <div className="metrics" id="metrics">
      {metrics.map((m) =>
        /* TWO TILES HELD OPEN, EMPTIED — and emptied HERE, at the point of display.
           "Analytical lenses" and "All signals" are off the strip at the operator's
           request. The slot stays: the strip is a CSS grid of equal columns, so dropping
           two of five would stretch the remaining three and move every number the reader
           had learned the position of. It renders as an empty cell with no button role,
           no focus stop and no hover — there is nothing in it to open, and a control that
           looks live and does nothing is worse than an empty space.

           metricsFor still MEASURES both. That matters: "All signals" is the served card
           count, which the report and the strip's own unbound-tile warning read, and
           test_market_tiles.mjs holds metricsFor to producing it. Blanking it upstream
           broke that test — correctly. Presentation belongs here. */
        m.blank ? (
          <div className="metric metric-blank" key={m.key || m.act} />
        ) : (
        <div
          className={`metric${active === m.act ? " on" : ""}${inert ? " inert" : ""}`}
          key={m.key || m.act}
          onClick={inert ? undefined : () => onPick(m, m.act)}
          role={inert ? undefined : "button"}
          tabIndex={inert ? undefined : 0}
          onKeyDown={
            inert
              ? undefined
              : (e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onPick(m, m.act);
                  }
                }
          }
        >
          {/* The tile's coloured dot is off at the operator's request. It was the last
              of the red/orange dots -- the card and pillar ones went in the previous
              round -- and it said the same thing the tile's own words already say:
              "Competitive threats" is not more legible for having a red circle in front
              of it. `m.dot` is still served and still on the metric; nothing else reads
              it, so restoring the dot is restoring this one span. */}
          <span className="ml">{m.l}</span>
          <span className="mv">
            <CountUp text={m.v} />
            {m.unit ? <span className="unit">{m.unit}</span> : null}
            {m.delta ? <span className="delta up">{m.delta}</span> : null}
          </span>
          {/* THE DESCRIPTIVE SUBLINE IS OFF; THE WARNING ONE IS NOT.
              "rivals scaling in KSSL space", "trajectory / consolidation" and the rest are
              served flavour text and are hidden at the operator's request. The sublines
              metricsFor marks `warn` are a different thing entirely -- they are the
              sentence that says a tile's "—" is an absent measurement, or that two tiles
              reading the same number are not two findings. Hiding those would let an
              unmeasured tile pass for a measured one, which is the one thing this strip
              has already been wrong about. They still print. */}
          <span className="msub">
            {m.warn ? m.sub : null}{" "}
            <span
              dangerouslySetInnerHTML={{
                __html: srcChips(m.src ? [{ label: "source", url: m.src }] : null, "nofilter"),
              }}
            />
          </span>
        </div>
        ),
      )}
    </div>
  );
}
