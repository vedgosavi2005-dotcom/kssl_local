import { useLayoutEffect, useState } from "react";
import { LAUNCHER } from "./product.js";

/* Our own "Ask Parallax" button, for a product version without one. It is a fixed overlay
   placed beside the product's page-header actions (adapter/product.json frontend.launcher
   .anchor), styled like the product's own header buttons; nothing is inserted into the
   product's DOM. Without the anchor (a page with no header actions) it sits in the corner. */
export default function Launcher({ onOpen }) {
  const [pos, setPos] = useState(null);
  useLayoutEffect(() => {
    if (!LAUNCHER.anchor) return undefined;
    const place = () => {
      const a = document.querySelector(LAUNCHER.anchor);
      const r = a && a.getBoundingClientRect();
      const next = r && (r.width || r.height)
        ? { top: Math.round(r.top + r.height / 2), right: Math.round(window.innerWidth - r.left + (LAUNCHER.gap_px ?? 8)) }
        : null;
      setPos((p) => (p && next && p.top === next.top && p.right === next.right ? p : next));
    };
    place();
    const t = setInterval(place, 700); // pages swap their header actions as the route changes
    window.addEventListener("resize", place);
    return () => {
      clearInterval(t);
      window.removeEventListener("resize", place);
    };
  }, []);
  const label = LAUNCHER.label || "Ask Parallax";
  return (
    <button
      className={`pa-launcher${pos ? " pa-launcher-inline" : ""}`}
      onClick={onOpen}
      style={pos ? { top: pos.top, right: pos.right } : undefined}
      title="Ask Parallax Analyst about anything on the platform"
      type="button"
    >
      <span className="pa-tick" /> {label}
    </button>
  );
}
