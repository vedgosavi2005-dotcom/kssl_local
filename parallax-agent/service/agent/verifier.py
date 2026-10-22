"""The answer verifier: checks every figure in the orchestrator's reply against the result
sets this answer was built from (and the page context the user was looking at). The
reply has already streamed; the verdict arrives as a `verify` event the dock shows under
the answer -- a tick when every figure traces to data, a flag naming any that do not."""

import json
import re

from . import config
from .llm import LLMError, get_llm

VERIFY_SYSTEM = """You audit an analyst's chat answer against the data it was based on. List every figure the answer states (counts, amounts, percentages, ranks, years used as facts) and check each against the result rows and stats provided (and the page context, if given). A figure passes if it appears in the data, in the platform pages read for this answer, in the platform reference facts, or follows from them by simple arithmetic (sums, differences, shares, rounding), including a statement that something is absent when a complete result shows no rows for it. Units written slightly differently (L/h vs L/hr) are not errors. It fails if the data contradicts it or nothing in the data supports it. Estimates labelled "Est." pass when the data's estimate column supports them.

Put ONLY failures in issues; a figure that passes is never listed. status: "verified" when every figure passes, "issues" when any fails, "no_figures" when the answer states none. For each failure give the claim as written and a one-line reason with the correct value if the data shows it. checked = the number of figures you checked."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["verified", "issues", "no_figures"]},
        "checked": {"type": "integer"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"}, "problem": {"type": "string"}},
                "required": ["claim", "problem"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "checked", "issues"],
    "additionalProperties": False,
}


async def verify(answer: str, results: list, page_text: str, reference: str = "", pages_read=()) -> dict:
    if not answer.strip():
        return {"status": "no_figures", "checked": 0, "issues": []}
    data = []
    for rs in results:
        p = rs.preview(n=min(rs.row_count, 120), cell_chars=160)
        data.append(p)
    payload = {"answer": answer, "results": data, "page_context": page_text[:4000],
               "platform_pages_read": "\n\n".join(pages_read)[:24000], "platform_reference_facts": reference}
    try:
        turn = await get_llm().turn(
            role="verifier", model=config.VERIFY_MODEL, system=VERIFY_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            effort="low", max_tokens=8000, output_schema=VERIFY_SCHEMA)
        if turn.stop_reason == "refusal":
            return {"status": "skipped", "checked": 0, "issues": []}
        out = turn.json()
    except LLMError as exc:
        return {"status": "skipped", "checked": 0, "issues": [], "note": str(exc)}
    # a smaller model sometimes files a passing figure under issues ("...so it passes")
    passing = re.compile(r"\b(so it passes|it passes|passes\b|no issue|no failure|is supported|are supported|both supported|is correct)\b", re.I)
    out["issues"] = [i for i in out.get("issues") or [] if not passing.search(i.get("problem", ""))]
    if out.get("status") == "issues" and not out["issues"]:
        out["status"] = "verified"
    out["results"] = len(results)
    return out
