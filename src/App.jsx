import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/layout/Layout";
import { AppStateProvider } from "./state/AppState";
import { DataProvider } from "./state/DataProvider";
import "./lib/track.js";   // usage log -> /api/track (anonymous; docs/ui_port/ACTIVITY_LOG.md)

/* DataProvider fetches and wires the dataset before anything renders, so no panel
   has to guard against a half-loaded corpus. */
export default function App() {
  return (
    <ErrorBoundary label="137Parallax" root>
      <DataProvider>
        <AppStateProvider>
          <Layout />
        </AppStateProvider>
      </DataProvider>
    </ErrorBoundary>
  );
}
