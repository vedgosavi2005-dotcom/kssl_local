/* THE LAYOUT GUARDIAN: measures the page after every render and repairs what it can.

   It is deterministic -- no model involved. It checks two things:

   1. The product is not distorted by the dock. The dock narrows the product's #root; if
      that narrowing makes any product chrome spill past its own edge or scroll
      sideways (a narrow window, a long header), the guardian switches the dock to
      overlay mode (html.pa-overlay): the product gets its full width back and the dock
      floats over it.

   2. Generated widgets fit. A widget whose content is wider than its card is widened to
      the full row; the canvas must sit inside its frame (right of the rail, left of
      the dock).

   Every finding is returned so the canvas can say what was checked and fixed. */

import { DOM } from "./product.js";

const PRODUCT_CHROME = DOM.chrome.join(", ");

export function checkProduct() {
  const root = document.querySelector(DOM.root);
  const html = document.documentElement;
  if (!root || !html.classList.contains("pa-on")) return { ok: true, issues: [] };
  const issues = [];
  const r = root.getBoundingClientRect();
  if (root.scrollWidth > root.clientWidth + 2) issues.push(`product scrolls sideways (${root.scrollWidth}px in ${root.clientWidth}px)`);
  for (const el of root.querySelectorAll(PRODUCT_CHROME)) {
    if (el.getBoundingClientRect().right > r.right + 2) issues.push(`${el.className.split(" ")[0]} spills past the product edge`);
  }
  const dock = document.querySelector(".pa-dock");
  if (dock && !html.classList.contains("pa-overlay") && r.right > dock.getBoundingClientRect().left + 2) {
    issues.push("product runs under the dock");
  }
  return { ok: issues.length === 0, issues };
}

/* returns true when it had to switch to overlay mode */
export function guardProduct() {
  const html = document.documentElement;
  if (html.classList.contains("pa-overlay")) return false;
  const { ok, issues } = checkProduct();
  if (ok) return false;
  html.classList.add("pa-overlay");
  console.info("[parallax-agent] layout guardian: overlay mode -", issues.join("; "));
  return true;
}

export function checkCanvas(canvasEl, frame) {
  const fixes = [];
  const issues = [];
  if (!canvasEl) return { fixes, issues };
  const c = canvasEl.getBoundingClientRect();
  const dock = document.querySelector(".pa-dock");
  if (Math.abs(c.left - frame.left) > 2) issues.push("canvas is not aligned to the rail");
  if (dock && c.right > dock.getBoundingClientRect().left + 2) issues.push("canvas runs under the dock");
  for (const w of canvasEl.querySelectorAll(".pa-w")) {
    const over = w.scrollWidth > w.clientWidth + 2;
    if (over && !w.classList.contains("pa-w-wide")) {
      w.classList.add("pa-w-wide");
      const title = (w.querySelector(".pa-w-title") || {}).textContent || "a widget";
      fixes.push(`widened "${title.trim().slice(0, 40)}" to the full row`);
    }
    const chart = w.querySelector(".pa-chart, .pa-d3");
    if (chart && chart.getBoundingClientRect().height < 40) issues.push("a chart rendered with no height");
  }
  return { fixes, issues };
}
