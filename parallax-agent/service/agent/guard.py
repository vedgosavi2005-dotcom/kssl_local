"""Layer one of keeping the assistant on-topic: a small model screens each message before
the orchestrator sees it. (Layer two is the orchestrator's own scope rules; layer three is
that every figure must come from a query.) It fails open -- if the screen itself errors, the
orchestrator's rules still apply."""

from . import adapter, config, prompts
from .llm import LLMError, get_llm



async def screen(question: str, recent: list) -> dict:
    client = adapter.client()
    covers, suggestions = client["coverage"], client["off_topic_suggestions"]
    earlier = "\n".join(f"- {q}" for q in recent[-3:]) or "(none)"
    content = f"Earlier questions in this conversation:\n{earlier}\n\nNew message:\n{question}"
    try:
        turn = await get_llm().turn(
            role="guard", model=config.GUARD_MODEL, system=prompts.guard_system(),
            messages=[{"role": "user", "content": content}], effort=config.GUARD_EFFORT,
            max_tokens=2048, output_schema=prompts.GUARD_SCHEMA)
    except LLMError as exc:
        print(f"[agent] guard unavailable, failing open: {exc}", flush=True)
        return {"verdict": "in_scope", "reply": "", "suggestions": []}
    if turn.stop_reason == "refusal":
        return {"verdict": "unsafe", "reply": f"I can't help with that. I cover {covers}.", "suggestions": suggestions}
    try:
        out = turn.json()
    except LLMError:
        return {"verdict": "in_scope", "reply": "", "suggestions": []}
    if out.get("verdict") not in ("in_scope", "off_topic", "unsafe"):
        out["verdict"] = "in_scope"
    if out["verdict"] != "in_scope":
        out["reply"] = out.get("reply") or f"I only cover {covers}."
        out["suggestions"] = (out.get("suggestions") or suggestions)[:3]
    return out
