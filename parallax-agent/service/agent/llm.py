"""One narrow interface to the model for all four agents, so the loops never touch SDK
details:

    turn = await get_llm().turn(role=..., model=..., system=..., messages=..., tools=..., ...)

`turn.content` is appended to the history verbatim (thinking blocks included -- the history
is append-only, which preserved thinking requires)."""

import asyncio
import json
import time
from dataclasses import dataclass, field

import anthropic

from . import config


class LLMError(RuntimeError):
    """A model call failed in a way the user should hear about in plain words."""


@dataclass
class Turn:
    content: list
    stop_reason: str
    text: str = ""
    tool_uses: list = field(default_factory=list)   # [{"id", "name", "input"}]
    model: str = ""

    def json(self):
        """The structured-output payload (output_config.format guarantees valid JSON)."""
        try:
            return json.loads(self.text)
        except (TypeError, ValueError) as exc:
            raise LLMError(f"model returned malformed JSON: {exc}") from exc


def _to_turn(msg) -> Turn:
    text = "".join(b.text for b in msg.content if b.type == "text")
    tools = [{"id": b.id, "name": b.name, "input": b.input} for b in msg.content if b.type == "tool_use"]
    return Turn(content=list(msg.content), stop_reason=msg.stop_reason or "", text=text,
                tool_uses=tools, model=getattr(msg, "model", ""))


class LLM:
    def __init__(self):
        if config.LLM_PROVIDER == "openrouter":
            # OpenRouter's Anthropic-compatible Messages endpoint; bearer auth
            self.client = anthropic.AsyncAnthropic(
                base_url=config.OPENROUTER_BASE_URL, auth_token=config.OPENROUTER_API_KEY,
                api_key=None, max_retries=3, timeout=180.0)
        else:
            self.client = anthropic.AsyncAnthropic(max_retries=3, timeout=180.0)

    async def turn(self, *, role, model, system, messages, tools=None, effort="medium",
                   max_tokens=16000, output_schema=None, on_text=None) -> Turn:
        params = {
            "model": config.provider_model(model),
            "max_tokens": max_tokens,
            # the stable prefix (tools + system) is cached explicitly; the conversation
            # tail is cached by the top-level automatic breakpoint
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "cache_control": {"type": "ephemeral"},
            "output_config": {"effort": effort},
        }
        if tools:
            params["tools"] = tools
        if output_schema:
            params["output_config"]["format"] = {"type": "json_schema", "schema": output_schema}
        if config.supports_server_fallback(model):
            # a declined request is re-run server-side on the recommended fallback model
            params["fallbacks"] = "default"
            params["betas"] = ["server-side-fallback-2026-07-01"]

        msg = None
        t0 = time.monotonic()
        # attempts: one re-issue for unparseable streamed tool JSON, and two more (with a
        # pause) when the provider cannot be reached at all -- on top of the SDK's own retries
        for attempt in range(4):
            try:
                if on_text is None:
                    msg = await self.client.beta.messages.create(**params)
                else:
                    async with self.client.beta.messages.stream(**params) as stream:
                        async for event in stream:
                            if event.type == "text":
                                await on_text(event.text)
                        msg = await stream.get_final_message()
                break
            except ValueError:
                # eager tool-input streaming produced JSON the SDK could not parse at all;
                # no tool_use block completed, so re-issuing the turn is safe (bounded)
                if attempt >= 1:
                    raise LLMError("the model's tool call could not be parsed; please retry")
            except anthropic.AuthenticationError as exc:
                raise LLMError("the model API key was rejected - check parallax-agent/.env") from exc
            except anthropic.PermissionDeniedError as exc:
                raise LLMError(f"the model API refused the request: {exc.message}") from exc
            except anthropic.RateLimitError as exc:
                raise LLMError("the model is rate-limited right now - try again in a minute") from exc
            except anthropic.APIStatusError as exc:
                raise LLMError(f"model API error {exc.status_code}: {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                if attempt >= 2 or on_text is not None and attempt >= 1:
                    raise LLMError("could not reach the model API from the agent service") from exc
                print(f"[agent] {role}: connection failed, retrying ({exc})", flush=True)
                await asyncio.sleep(2 + 3 * attempt)

        u = getattr(msg, "usage", None)
        if u is not None:
            print(f"[agent] {role:<11} {params['model']} {time.monotonic() - t0:5.1f}s stop={msg.stop_reason} in={u.input_tokens} "
                  f"cache_read={getattr(u, 'cache_read_input_tokens', 0) or 0} out={u.output_tokens}",
                  flush=True)
        return _to_turn(msg)


_llm = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
