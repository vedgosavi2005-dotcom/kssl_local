"""Agent settings, all from the environment (parallax-agent/.env) so a deploy can retune
without a rebuild."""

import os
import re
from pathlib import Path


def _load_dotenv() -> None:
    """parallax-agent/.env, for running outside Docker. Real environment variables win."""
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Provider: "anthropic" (Claude API, ANTHROPIC_API_KEY) or "openrouter" (Claude models via
# OpenRouter's Anthropic-compatible endpoint, OPENROUTER_API_KEY). The code path is the
# same Anthropic SDK either way; only the base URL, credential and model ids differ.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api")

# Models. Sonnet where the reasoning is (planning, SQL), Haiku where the job is narrow and
# latency matters (scope check, view composition). Any can be raised to claude-opus-5-5.
ORCHESTRATOR_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
DATA_MODEL = os.environ.get("AGENT_DATA_MODEL", "claude-sonnet-5-5")
UI_MODEL = os.environ.get("AGENT_UI_MODEL", "claude-haiku-5-5")
GUARD_MODEL = os.environ.get("AGENT_GUARD_MODEL", "claude-haiku-5-5")

ORCHESTRATOR_EFFORT = os.environ.get("AGENT_EFFORT", "low")
DATA_EFFORT = os.environ.get("AGENT_DATA_EFFORT", "medium")
UI_EFFORT = os.environ.get("AGENT_UI_EFFORT", "low")
GUARD_EFFORT = "low"
CATEGORIZE_MODEL = os.environ.get("AGENT_CATEGORIZE_MODEL", "claude-haiku-5-5")

# Quality agents: the design reviewer checks each view before it is shown; the answer
# verifier checks every figure in a reply against the query results. Each can be
# switched off (0) to save a model call.
REVIEW_ENABLED = os.environ.get("AGENT_REVIEW", "1") != "0"
REVIEW_MODEL = os.environ.get("AGENT_REVIEW_MODEL", "claude-haiku-5-5")
REVIEW_EFFORT = os.environ.get("AGENT_REVIEW_EFFORT", "low")
VERIFY_ENABLED = os.environ.get("AGENT_VERIFY", "1") != "0"
VERIFY_MODEL = os.environ.get("AGENT_VERIFY_MODEL", "claude-haiku-5-5")

# Spend cap for OpenRouter keys: the service records the key's usage the first time it
# starts and refuses new questions once it has spent this much more. 0 disables.
BUDGET_USD = float(os.environ.get("AGENT_BUDGET_USD", "20"))

# Technical detail in the UI (SQL, query timings, design-review / layout-check lines, the
# verifier's figure counts, model and budget). Off for business users; 1 for developers.
DEBUG_UI = os.environ.get("AGENT_DEBUG_UI", "0") == "1"

# Loop and payload bounds
MAX_ORCHESTRATOR_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "8"))
MAX_DATA_STEPS = int(os.environ.get("AGENT_MAX_DATA_STEPS", "8"))
MAX_ROWS = int(os.environ.get("AGENT_MAX_ROWS", "500"))          # rows kept per result set
PREVIEW_ROWS = 25                                                   # rows a model sees per result
MAX_CATEGORIZE_ROWS = 200
CONVERSATION_TTL_S = 6 * 3600
MAX_CONVERSATIONS = 200
PAGE_CONTEXT_CHARS = 6000                                           # page context sent per turn

# Database. KSSL_DSN is the product's own connection string (it can create the analytics
# views). The agent's SQL runs as parallax_agent (SELECT on analytics.* only); the service
# sets that role's password on startup: AGENT_DB_PASSWORD if given, otherwise a random one
# held in memory for the life of the process.
AGENT_DB_ROLE = "parallax_agent"
AGENT_DB_PASSWORD = os.environ.get("AGENT_DB_PASSWORD", "").strip()
ENSURE_ANALYTICS = os.environ.get("AGENT_ENSURE_ANALYTICS", "1") != "0"


def credentials_present() -> bool:
    if LLM_PROVIDER == "openrouter":
        return bool(OPENROUTER_API_KEY)
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def provider_model(model: str) -> str:
    """Claude API id -> the id the provider expects (OpenRouter: anthropic/claude-sonnet-5.5)."""
    if LLM_PROVIDER != "openrouter" or "/" in model:
        return model
    return "anthropic/" + re.sub(r"-(\d+)-(\d+)$", r"-\1.\2", model)


def supports_server_fallback(model: str) -> bool:
    """`fallbacks: "default"` is a Claude API feature (Sonnet 5.5, Opus 5.x, Fable 5.x).
    Haiku 5.5 has none, and OpenRouter does its own routing; refusals there are handled in
    code."""
    return LLM_PROVIDER == "anthropic" and model.startswith(
        ("claude-sonnet-5-5", "claude-opus-5", "claude-fable-5"))
