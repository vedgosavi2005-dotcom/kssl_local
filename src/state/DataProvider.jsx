import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { datasetService } from "../api/datasetService";
import { wireDataset } from "../lib/dataset";
import { createGeo } from "../lib/geo";
import { createPartners } from "../lib/partners";
import { navCounts, viewMetaFor } from "../lib/overview";
import { profileSelfCheck } from "../lib/profile";
import { logger } from "../utils/logger";
import { ReviewProvider } from "../components/review/Review";

const DataContext = createContext(null);

/* Loads the dataset once, wires it, and derives everything the panels read from it.
   The derived objects are memoised on the dataset identity, so a refetch rebuilds
   them and a re-render does not. */
export function DataProvider({ children }) {
  const [raw, setRaw] = useState(null);
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

  const value = useMemo(() => {
    if (!raw) return null;
    const data = wireDataset(raw);
    const geo = createGeo(data);
    const partners = createPartners(data);
    return {
      data,
      geo,
      partners,
      counts: navCounts(data),
      viewMeta: viewMetaFor(data),
    };
  }, [raw]);

  /* Every roster row must build a named profile; logs only on failure. */
  useEffect(() => {
    if (!value) return;
    try {
      if (Object.keys(value.data.competitors || {}).length > 0) profileSelfCheck(value.data);
    } catch (err) {
      logger.error("a self-check threw", err);
    }
  }, [value]);

  if (error) {
    return (
      <div className="boot err">
        <div className="boot-mark">
          137<span>Parallax</span>
        </div>
        <div className="boot-msg">
          Could not load the KSSL dataset - {error}
          <br />
          <br />
          The app reads everything from <code>GET /api/dataset</code>. Start the
          backend: <code>cd KSSL_Deploy &amp;&amp; docker compose up -d</code> (or run
          <code>uvicorn app:app --port 8600</code> in <code>backend/</code>), then retry.
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
        <div className="boot-msg">Loading competitive intelligence from the API…</div>
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
