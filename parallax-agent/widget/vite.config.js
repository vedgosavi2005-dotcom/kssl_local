import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* The widget is built into the agent service's static folder and served at
   /parallax-agent/. One entry script + one stylesheet (the two tags the gateway
   injects into the product's index.html); ECharts is a lazy chunk loaded with the
   first chart, so the dock itself loads fast. */
export default defineConfig({
  plugins: [react()],
  // the product adapter (product.json): which product, pages, selectors, theme
  resolve: { alias: { "@adapter": fileURLToPath(new URL("../adapter", import.meta.url)) } },
  base: "/parallax-agent/",
  build: {
    outDir: "../service/static",
    emptyOutDir: true,
    cssCodeSplit: false,
    chunkSizeWarningLimit: 700, // ECharts is one lazy chunk, loaded with the first chart
    rollupOptions: {
      input: "src/main.jsx",
      output: {
        entryFileNames: "widget.js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: (a) => (a.name && a.name.endsWith(".css") ? "widget.css" : "assets/[name]-[hash][extname]"),
      },
    },
  },
});
