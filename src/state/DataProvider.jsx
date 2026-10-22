import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { datasetService } from "../api/datasetService";
import { wireDataset } from "../lib/dataset";
import { setClient, clientName } from "../lib/client.js";
import { setVisibility } from "../lib/visibility.js";
import { createGeo } from "../lib/geo";
import { createPartners } from "../lib/partners";
import { buildGapModel } from "../lib/gapModel";
import { navCounts, viewMetaFor } from "../lib/overview";
import { marketSelfCheck } from "../lib/marketOverview";
import { profileSelfCheck } from "../lib/profile";
import { logger } from "../utils/logger";
import { ReviewProvider } from "../components/review/Review";

const DataContext = createContext(null);

/* Loads the dataset once, wires it, and derives everything the panels read from it.
   The derived objects are memoised on the dataset identity, so a refetch rebuilds
   them and a re-render does not. */
function build(src) {
  /* the client first: wireDataset builds strings that name it */
  setClient(src.client);
  /* which sections the database switched on; read before anything below counts or routes */
  setVisibility(src.sectionVisibility);
  const data = wireDataset(src);
  const gapModel = buildGapModel(data);
  const geo = createGeo(data);
  const partners = createPartners(data);
  return {
    data,
    gapModel,
    geo,
    partners,
    counts: navCounts(data, gapModel),
    viewMeta: viewMetaFor(data),
  };
}

export function DataProvider({ children }) {
  const [raw, setRaw] = useState(null);
  /* another dataset shown for a while in place of this site's own: the review site's Session replay of a LIVE visit
     shows the live dataset, so the cards, order and numbering are what that person saw (components/replay/Replay.jsx).
     Set by the "kssl:dataset-override" event (detail = the payload, or null to go back). */
  const [override, setOverride] = useState(null);
  useEffect(() => {
    const on = (e) => setOverride(e.detail || null);
    window.addEventListener("kssl:dataset-override", on);
    return () => window.removeEventListener("kssl:dataset-override", on);
  }, []);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setRaw(null);
    datasetService
      .getDataset()
      .then((payload) => {
        if (cancelled) return;
        if (!payload || !payload.matchups)
          throw new Error(
            "the API answered but did not return a usable dataset (no matchups global) - check the backend's /api/dataset response",
          );
        setRaw(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err.message || err));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  /* each dataset is wired once and kept: wireDataset changes the objects it is given, so the site's own dataset is never
     wired a second time when a replay hands it back */
  const own = useMemo(() => (raw ? build(raw) : null), [raw]);
  const shown = useMemo(() => (override ? build(override) : null), [override]);
  const value = shown || own;
  // the client and the switched-on sections follow whichever dataset is on screen
  useEffect(() => {
    const src = override || raw;
    if (!src) return;
    setClient(src.client);
    setVisibility(src.sectionVisibility);
  }, [raw, override]);

  /* The three self-checks the standalone file ran on load. They assert the derived
     logic against the corpus and log only on failure — a silent console is the pass. */
  /* the page is ready: things that should appear only with it (the Ask Parallax button, src/main.jsx) wait for this */
  useEffect(() => {
    if (!value) return;
    window.__ksslDataReady = true;
    window.dispatchEvent(new Event("kssl:data-ready"));
  }, [value]);

  useEffect(() => {
    if (!value) return;
    try {
      value.partners.selfCheck();
      value.partners.geomCheck();
      value.geo.selfCheck();
      /* Both run against value.data — the WIRED dataset. That matters for the market
         one: computeTenderRealDays rewrites dl and deadline, and the served rows carry
         dl: null, for which `dl <= 0` is true and every tender buckets as closed. */
      marketSelfCheck(value.data.tenders, value.data.marketCards);
      profileSelfCheck(value.data);
      logger.info("self-checks complete", {
        globals: Object.keys(value.data).length,
        matchups: Object.keys(value.data.matchups).length,
        gaps: value.gapModel.length,
      });
    } catch (err) {
      logger.error("a self-check threw", err);
    }
  }, [value]);

  useEffect(() => {
    document.title = clientName() ? `137Parallax — ${clientName()}` : "137Parallax";
  }, [value]);

  if (error) {
    return (
      <div className="boot err">
        <div className="boot-mark">
          137<span>Parallax</span>
        </div>
        <div className="boot-msg">
          Could not load the dataset - {error}
          <br />
          <br />
          The app reads everything from <code>GET /api/dataset</code>. Start the
          backend (see the README), then retry.
        </div>
        <button
          className="boot-retry"
          onClick={() => setReloadKey((k) => k + 1)}
          type="button"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!value) {
    return (
      <div className="boot">
        <div className="boot-mark">
          137<span>Parallax</span>
        </div>
        <div className="boot-msg">137Parallax Loading</div>
      </div>
    );
  }

  return (
    <DataContext.Provider value={value}>
      <ReviewProvider initial={raw.review}>{children}</ReviewProvider>
    </DataContext.Provider>
  );
}

export function useData() {
  const value = useContext(DataContext);
  if (!value) throw new Error("useData must be used within DataProvider");
  return value;
}
