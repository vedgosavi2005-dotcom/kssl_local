"""Resolve a navigate request to a target the frontend can open exactly.

The orchestrator may say "Caterpillar" where the page needs cid=CATERPIL, or a shortened
tender title where the Tender page matches on the full one. Every payload value is checked
against the database (adapter/navigation.py knows how, per payload key), so the page opens
on the right item or the model gets a clear error listing valid choices -- never a silent
landing on the wrong record."""

from . import adapter, db
from .pages import PAGES


class NavError(ValueError):
    pass


def resolve(pillar: str, view: str, payload: dict) -> dict:
    page = PAGES.get((pillar, view))
    if page is None:
        valid = ", ".join(f"{p}/{v}" for p, v in PAGES)
        raise NavError(f"{pillar}/{view} is not a page. Pages: {valid}.")
    payload = {k: v for k, v in (payload or {}).items() if v not in (None, "") and k in page["payload"]}
    try:
        return adapter.module("navigation").resolve(pillar, view, payload, db.fetch, adapter.manifest())
    except NavError:
        raise
    except ValueError as exc:
        raise NavError(str(exc)) from exc
