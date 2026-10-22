"""Spend cap for an OpenRouter key.

OpenRouter reports a key's lifetime usage (GET /api/v1/key). The first time the service
starts it records that figure as a baseline in .local/spend-baseline.json; afterwards it
refuses new questions once usage exceeds baseline + AGENT_BUDGET_USD. Delete the baseline
file to start a fresh budget. The Claude API provider has no equivalent endpoint, so the
cap applies to OpenRouter only (set spend limits in the Anthropic Console instead)."""

import json
import time
from pathlib import Path

import httpx

from . import config

BASELINE_FILE = Path(__file__).resolve().parents[2] / ".local" / "spend-baseline.json"
_cache = {"usage": None, "at": 0.0, "baseline": None}


async def _fetch_usage():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{config.OPENROUTER_BASE_URL}/v1/key",
                             headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
        r.raise_for_status()
        return float(r.json()["data"]["usage"])


def _baseline(current: float) -> float:
    if _cache["baseline"] is not None:
        return _cache["baseline"]
    try:
        _cache["baseline"] = float(json.loads(BASELINE_FILE.read_text())["usage"])
    except (OSError, ValueError, KeyError):
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(json.dumps({"usage": current, "recorded": time.strftime("%Y-%m-%d %H:%M:%S")}))
        _cache["baseline"] = current
    return _cache["baseline"]


async def status(max_age_s: float = 30) -> dict:
    """{"tracked", "spent_usd", "budget_usd", "exhausted"}; never raises."""
    if config.LLM_PROVIDER != "openrouter" or config.BUDGET_USD <= 0 or not config.OPENROUTER_API_KEY:
        return {"tracked": False, "spent_usd": None, "budget_usd": None, "exhausted": False}
    try:
        if _cache["usage"] is None or time.time() - _cache["at"] > max_age_s:
            _cache["usage"] = await _fetch_usage()
            _cache["at"] = time.time()
        spent = max(0.0, _cache["usage"] - _baseline(_cache["usage"]))
        return {"tracked": True, "spent_usd": round(spent, 4), "budget_usd": config.BUDGET_USD,
                "exhausted": spent >= config.BUDGET_USD}
    except Exception as exc:  # a usage-endpoint hiccup must not take the chat down
        return {"tracked": False, "spent_usd": None, "budget_usd": config.BUDGET_USD,
                "exhausted": False, "error": str(exc)}


def mark_stale() -> None:
    _cache["at"] = 0.0
