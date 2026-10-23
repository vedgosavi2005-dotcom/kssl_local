"""The one place that calls the model. Today: the Claude Code CLI (no API key on this machine).
An Anthropic SDK path can replace `call_model` without touching the runner: same arguments, same
ModelResult."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

CLI = "claude"
TIMEOUT_S = 900


class ModelError(RuntimeError):
    pass


@dataclass
class ModelResult:
    text: str                       # the model's reply (the JSON envelope, as text)
    tokens_in: int = 0              # input + cache read + cache creation
    tokens_out: int = 0
    cost_usd: float | None = None
    seconds: float = 0.0            # wall time of the call
    api_ms: int | None = None
    meta: dict = field(default_factory=dict)


def build_args(model: str, system: str, web_search: bool) -> list[str]:
    return [
        CLI, "-p", "--model", model, "--system-prompt", system, "--output-format", "json",
        "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "project",
        "--exclude-dynamic-system-prompt-sections",
        "--tools", "WebSearch,WebFetch" if web_search else "",
    ] + (["--allowedTools", "WebSearch,WebFetch"] if web_search else [])      # -p cannot ask: pre-approve the two web tools


def parse_cli_output(stdout: str) -> ModelResult:
    try:
        env = json.loads(stdout)
    except ValueError as e:
        raise ModelError(f"claude CLI did not return JSON: {stdout[:300]!r}") from e
    if isinstance(env, list):  # some CLI versions return the event list
        env = next((e for e in reversed(env) if isinstance(e, dict) and e.get("type") == "result"), {})
    if env.get("is_error") or env.get("subtype", "success") != "success":
        raise ModelError(f"claude CLI error: {str(env.get('result') or env.get('subtype') or env)[:400]}")
    u = env.get("usage") or {}
    return ModelResult(
        text=env.get("result") or "",
        tokens_in=sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        tokens_out=int(u.get("output_tokens") or 0),
        cost_usd=env.get("total_cost_usd"),
        api_ms=env.get("duration_api_ms"),
        meta={**{k: env.get(k) for k in ("num_turns", "stop_reason", "terminal_reason", "session_id", "duration_ms")},
              "usage": u, "model_usage": env.get("modelUsage")},
    )


# Transient API faults are retried here, not logged as failed runs (owner 2026-10-24: "processing must produce no errors").
# A usage / credit limit is NOT transient: it is raised at once, so the runner stops cleanly (scripts/flood_run, backend/routine).
TRANSIENT = re.compile(r"connection closed|connection reset|econnreset|socket hang up|overloaded|5\d\d|internal server error|"
                       r"bad gateway|service unavailable|timed out|timeout", re.I)
RETRY_WAITS = (20, 60)          # seconds before the 2nd and 3rd attempt


def is_transient(msg: str) -> bool:
    return bool(TRANSIENT.search(msg or "")) and not re.search(r"usage limit|hit your .*limit|credit balance", msg or "", re.I)


def call_model(system: str, prompt: str, model: str, web_search: bool = False) -> ModelResult:
    """Run one prompt, retrying transient API faults (RETRY_WAITS). Raises ModelError on any other failure, or when retries run out."""
    for wait in (*RETRY_WAITS, None):
        try:
            return _call_once(system, prompt, model, web_search)
        except ModelError as e:
            if wait is None or not is_transient(str(e)):
                raise
            time.sleep(wait)
    raise ModelError("unreachable")


def _call_once(system: str, prompt: str, model: str, web_search: bool = False) -> ModelResult:
    """Run one prompt once. Raises ModelError on any failure."""
    # a neutral working directory, so no project CLAUDE.md / settings leak into the call
    cwd = Path(tempfile.gettempdir()) / "kssl_claude_cwd"
    cwd.mkdir(exist_ok=True)
    t0 = time.monotonic()
    try:
        p = subprocess.run(build_args(model, system, web_search), input=prompt, capture_output=True, text=True,
                           encoding="utf-8", timeout=TIMEOUT_S, cwd=cwd)
    except FileNotFoundError as e:
        raise ModelError("the 'claude' CLI is not on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise ModelError(f"claude CLI timed out after {TIMEOUT_S}s") from e
    secs = round(time.monotonic() - t0, 1)
    if p.returncode != 0 and not p.stdout.strip():
        raise ModelError(f"claude CLI exit {p.returncode}: {(p.stderr or '').strip()[:400]}")
    res = parse_cli_output(p.stdout)
    res.seconds = secs
    return res
