"""The platform's pages as navigation targets, from the adapter (adapter/product.json
"pages"): a mirror of the frontend's route table and of the `pending` payload each page
reads on mount. Keep it in step with the product: check_product.py compares it against
the product's route table and page code."""

from . import adapter

_M = adapter.manifest()

PAGES = {(p["pillar"], p["view"]): {"label": p["label"], "blocks": p.get("blocks") or [], "payload": p.get("payload") or {}}
         for p in _M["pages"]}

SECTIONS = set(_M["routes"].get("report_sections") or [])
LANE_OF_FEED = {p["view"]: p["feed_lane"] for p in _M["pages"] if p.get("feed_lane")}


def page_map_text() -> str:
    lines = []
    for (pillar, view), meta in PAGES.items():
        keys = ", ".join(f"{k} = {v}" for k, v in meta["payload"].items()) or "no payload"
        blocks = "; ".join(meta.get("blocks") or []) or "the page as a whole"
        lines.append(f"- {pillar} / {view}: {meta['label']}. Payload: {keys}. Blocks to focus: {blocks}.")
    return "\n".join(lines)
