import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fetchTrending } from "./src/lib/pulseFetch.js";

const apiTarget = process.env.KSSL_API_TARGET || "http://127.0.0.1:8600";
const reviewApiTarget = process.env.KSSL_API_TARGET || "http://127.0.0.1:8601";

/* KSSL_Deploy frontend. Dev proxies /api to the FastAPI backend on :8600;
   the production build fetches /api relative to its own origin, so any static
   server that also routes /api to the backend serves it unchanged. */

/* Serve only the live company-pulse endpoint from the dev and preview servers. The
   dataset always comes from the PostgreSQL-backed API; a checked-in snapshot would
   make an empty database look populated. */
async function apiMiddleware(req, res, next) {
  if (req.url && req.url.startsWith("/api/img")) {
    /* Image proxy: many publishers block hotlinking (Referer/UA checks), so an
       og:image that renders fine on the source 403s in an <img> here. Fetching it
       server-side with a browser UA and no referer bypasses that; the browser then
       loads it from our own origin. Mirrors the backend /api/img on staging/prod. */
    try {
      const src = new URL(req.url, "http://localhost").searchParams.get("u") || "";
      if (!/^https?:\/\//i.test(src)) { res.statusCode = 400; return res.end("bad url"); }
      const upstream = await fetch(src, {
        headers: { "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "accept": "image/*,*/*" },
        redirect: "follow",
        signal: AbortSignal.timeout(12000),
      });
      const ct = upstream.headers.get("content-type") || "";
      if (!upstream.ok || !/^image\//i.test(ct)) { res.statusCode = 404; return res.end("not an image"); }
      const buf = Buffer.from(await upstream.arrayBuffer());
      res.setHeader("Content-Type", ct);
      res.setHeader("Cache-Control", "public, max-age=86400");
      return res.end(buf);
    } catch (e) {
      res.statusCode = 404;
      return res.end("img fetch failed");
    }
  }
  if (req.url && req.url.startsWith("/api/dataset")) {
    return next(); // forwarded to the FastAPI backend by the /api proxy
  }
  /* Exact path match: no sub-path of /api/pulse is served here (there is no stock lane). */
  if (req.url && new URL(req.url, "http://localhost").pathname === "/api/pulse") {
    try {
      const q = new URL(req.url, "http://localhost").searchParams;
      const name = q.get("name") || "";
      const product = q.get("product") || "";
      /* Decision: live Google News headlines stay (not from the DB, not reviewed). There is no
         stock lane. The query is the request's own name/product -- no default is injected. */
      const data = { trending: await fetchTrending(name, product), fetchedAt: new Date().toISOString() };
      res.setHeader("Content-Type", "application/json");
      res.setHeader("Cache-Control", "public, max-age=300"); // 5 min
      return res.end(JSON.stringify(data));
    } catch (e) {
      res.statusCode = 200; // never break the page on a data-source hiccup
      res.setHeader("Content-Type", "application/json");
      return res.end(JSON.stringify({ trending: [], error: String((e && e.message) || e) }));
    }
  }
  return next();
}

/* `vite --mode review` (npm run dev:review): the review copy on 127.0.0.1:5180, proxying /api to
   the review backend (KSSL_VIEW=review, :8601). VITE_REVIEW=1 is defined here (no .env file), so
   src/components/review/Review.jsx renders its controls; every other mode renders nothing there. */
export default defineConfig(({ mode }) => {
  const review = mode === "review";
  return {
  define: review ? { "import.meta.env.VITE_REVIEW": JSON.stringify("1") } : {},
  plugins: [
    react(),
    {
      name: "api-local",
      configureServer(server) {
        server.middlewares.use(apiMiddleware);
      },
      configurePreviewServer(server) {
        server.middlewares.use(apiMiddleware);
      },
    },
  ],
  /* `preview` serves the BUILT bundle. It needs the same proxy as `server`, or the
     only way to test the real artefact is to deploy it. */
  preview: {
    port: 5179,
    host: true,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
  server: {
    port: review ? 5180 : 5178,
    host: review ? "127.0.0.1" : true,
    strictPort: true,
    proxy: {
      "/api": {
        target: review ? reviewApiTarget : apiTarget,
        changeOrigin: true,
      },
    },
  },
  };
});
