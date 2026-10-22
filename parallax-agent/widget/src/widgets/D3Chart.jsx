import { useEffect, useLayoutEffect, useRef, useState } from "react";

let implPromise = null;
const loadImpl = () => (implPromise ||= import("./d3-impl.js"));

/* Host for the D3 renderers: lazy-loads D3, redraws on data or size change. */
export default function D3Chart({ widget, rows, height, onMark }) {
  const el = useRef(null);
  const [width, setWidth] = useState(0);
  const [failed, setFailed] = useState("");

  useLayoutEffect(() => {
    if (!el.current) return undefined;
    setWidth(Math.floor(el.current.clientWidth)); // measured now; the observer follows resizes
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!width || !el.current) return undefined;
    let cleanup = null;
    let cancelled = false;
    loadImpl()
      .then((impl) => {
        if (cancelled || !el.current) return;
        el.current.replaceChildren();
        const fn = widget.type === "network" ? impl.renderNetwork : impl.renderTreemap;
        cleanup = fn(el.current, widget, rows, width, height, onMark);
        setFailed("");
      })
      .catch((e) => setFailed(String(e && e.message ? e.message : e)));
    return () => {
      cancelled = true;
      if (cleanup) cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widget, rows, width, height]);

  if (failed) return <div className="pa-w-empty">Chart could not render: {failed}</div>;
  return <div className="pa-d3" ref={el} style={{ height }} />;
}
