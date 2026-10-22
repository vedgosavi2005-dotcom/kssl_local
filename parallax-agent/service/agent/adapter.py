"""The product adapter: everything that ties Parallax Analyst to one version of the product.

It lives in parallax-agent/adapter/ (ADAPTER_DIR overrides): product.json (client, companies,
pages and blocks, routes, DOM selectors, theme, prompt facts), analytics.sql (the database
views the agents query), ui_index.py (the product's /api/dataset -> searchable page blocks),
navigation.py (page payloads -> exact database values) and scenarios.py (the live test
suite). The rest of the service is product-agnostic. To attach the chatbot to a new
product version, change only that folder; see PORTING.md and check_product.py."""

import importlib.util
import json
import os
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(os.environ.get("ADAPTER_DIR") or Path(__file__).resolve().parents[2] / "adapter").resolve()


@lru_cache(maxsize=None)
def manifest() -> dict:
    return json.loads((DIR / "product.json").read_text(encoding="utf-8"))


def path(name: str) -> Path:
    return DIR / name


@lru_cache(maxsize=None)
def module(name: str):
    """adapter/<name>.py, loaded once."""
    spec = importlib.util.spec_from_file_location(f"parallax_adapter_{name}", DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def client() -> dict:
    """The manifest's client texts, with {slots} filled from the live data facts (so a product
    whose client is data can say "{client_name}" in product.json)."""
    c = manifest()["client"]
    facts = _facts()
    return {k: fill(v, facts) if isinstance(v, str) else [fill(x, facts) if isinstance(x, str) else x for x in v]
            if isinstance(v, list) else v for k, v in c.items()}


def companies() -> list:
    """The tracked companies: listed in product.json, or read from the data when it says
    "companies": "from_data" (ids, names, aliases and colour slots from the analytics views)."""
    listed = manifest()["companies"]
    if listed == "from_data":
        from . import db  # db imports this module
        try:
            return db.company_list()
        except Exception as exc:
            print(f"[agent] company list unavailable: {exc}", flush=True)
            return []
    return listed


def _facts() -> dict:
    from . import db
    try:
        return db.facts() if db.status()["ready"] else {}
    except Exception:
        return {}


def client_company() -> dict:
    return next((c for c in companies() if c.get("client")), {"id": client()["name"], "name": client()["name"]})


def rivals() -> list:
    return [c for c in companies() if not c.get("client")]


_SLOT = re.compile(r"\{(\w+)\}")


def fill(text: str, facts: dict) -> str:
    """Put live figures ({products}, {awards}...) into manifest text; unknown names stay as written."""
    return _SLOT.sub(lambda m: str(facts[m.group(1)]) if m.group(1) in facts else m.group(0), text)
