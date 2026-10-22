"""The UI agent: composes one canvas view from result sets, choosing widgets from the
catalog, their encodings, filters, click actions and the summary. One structured-output
call; spec.validate() then holds it to the real columns before rows are attached."""

import json

from . import config, prompts, reviewer, spec
from .llm import LLMError, get_llm


async def build_view(conv, question: str, title: str, brief: str, result_ids: list, emit) -> tuple:
    rids = [r for r in result_ids if r in conv.results]
    if not rids:
        raise ValueError("none of the result_ids exist; run query_data first")
    # the canvas opens now, as a frame with the title, and fills in when the view is ready
    emit({"type": "view_pending", "title": title or "Building the view"})
    emit({"type": "status", "stage": "design", "text": "Designing the view"})
    results = [conv.results[r] for r in rids]
    assumptions = [a for rs in results for a in rs.assumptions]
    payload = {
        "question": question,
        "title_hint": title,
        "brief": brief,
        "assumptions_given": assumptions,
        "results": [rs.preview() for rs in results],
    }
    raw, warnings = None, []
    try:
        turn = await get_llm().turn(
            role="ui", model=config.UI_MODEL, system=prompts.ui_system(),
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            effort=config.UI_EFFORT, max_tokens=16000, output_schema=spec.VIEW_SCHEMA)
        if turn.stop_reason != "refusal":
            raw = turn.json()
    except LLMError as exc:
        warnings.append(f"designer unavailable ({exc}); showing the data as tables")
    if raw is None:
        raw = {"title": title, "summary": "", "widgets": [], "filters": [],
               "assumptions": assumptions, "caveats": [], "followups": []}
    clean, more = spec.validate(raw, conv.results, rids)
    warnings += more
    if config.REVIEW_ENABLED and clean["widgets"] and raw.get("widgets"):
        clean, notes = await reviewer.review(question, results, clean, conv.results, rids, emit)
        warnings += notes
    if not clean.get("title"):
        clean["title"] = title
    for a in assumptions:  # categorisation assumptions are not optional reading
        if a not in clean["assumptions"]:
            clean["assumptions"].append(a)
    view = spec.hydrate(clean, conv.results, question)
    view["qa"] = {"reviewed": config.REVIEW_ENABLED,
                  "fixes": [w[len("review: "):] for w in warnings if w.startswith("review: ")]}
    conv.views.append({"id": view["id"], "title": view["title"], "question": question, "result_ids": rids})
    conv.view_specs[view["id"]] = view
    if warnings:
        print(f"[agent] view warnings: {warnings}", flush=True)
    return view, warnings
