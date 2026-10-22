/* The product this widget is attached to: parallax-agent/adapter/product.json, bundled at
   build time (rebuild the widget after editing it; run-local.sh does when it is newer).
   Only the parts the browser needs are imported, so prompts and data notes stay server-side. */
import { companies, frontend, routes } from "@adapter/product.json";

export const DOM = frontend.dom;
export const APP = frontend.app_state;
export const THEME = frontend.theme;
export const ROUTES = routes;
export const COMPANIES = companies;
export const LAUNCHER = frontend.launcher || {};
export const TEXT = {
  tagline: frontend.tagline,
  welcome: frontend.welcome,
  general: frontend.general_suggestions,
  pages: frontend.page_suggestions,
};

/* What the service knows from the data (GET /api/agent/status): the client's name for {client}
   in the texts above, and the companies with their colour slots, for a product whose client
   and companies are data rather than product.json entries. */
export const RUNTIME = { client: null, companies: null };
export function setRuntime(status) {
  if (!status) return;
  if (status.client && status.client.name && !String(status.client.name).includes("{")) RUNTIME.client = status.client;
  if (Array.isArray(status.companies) && status.companies.length) RUNTIME.companies = status.companies;
}
export const fillText = (s) => String(s || "")
  .replaceAll("{client}", (RUNTIME.client && RUNTIME.client.name) || "the client")
  .replaceAll("{client_short}", (RUNTIME.client && (RUNTIME.client.short || RUNTIME.client.name)) || "the client");

/* a selector list relative to the product root ("#root .x, #root .y") */
export const inRoot = (sels) => [].concat(sels).map((x) => `${DOM.root} ${x}`).join(", ");

/* obj["a.b.c"] without throwing */
export const pick = (obj, path) => String(path || "").split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);

/* The product's tokens and the layout hook, applied before the widget mounts. The hook is the
   only rule that reaches the product: it narrows the product root while the dock is open
   (classes this widget puts on <html>), so it matches nothing once the widget is gone. */
export function injectProductCss() {
  if (document.getElementById("pa-adapter-css")) return;
  const tokens = Object.entries(THEME.tokens).map(([k, v]) => `  ${k}: ${v};`).join("\n");
  const css = `:root {\n${tokens}\n}\n` +
    `html.pa-on:not(.pa-overlay) ${DOM.root} { width: calc(100% - var(--pa-dock-w)) !important; max-width: calc(100vw - var(--pa-dock-w)) !important; }\n` +
    `@media (max-width: 900px) { html.pa-on ${DOM.root} { width: 100% !important; max-width: 100vw !important; } }\n`;
  const el = document.createElement("style");
  el.id = "pa-adapter-css";
  el.textContent = css;
  document.head.appendChild(el);
}
