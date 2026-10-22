/* Parallax Analyst widget: mounted into the product page by the agent gateway, in its
   own root beside the product's #root. Nothing in the product's code knows it exists. */
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { injectProductCss } from "./product.js";
import "./styles.css";

function mount() {
  if (document.getElementById("pa-root")) return;
  injectProductCss();
  const host = document.createElement("div");
  host.id = "pa-root";
  document.body.appendChild(host);
  createRoot(host).render(<App />);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
else mount();
