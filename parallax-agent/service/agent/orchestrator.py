"""The orchestrator: screens the message, then runs the tool loop that talks to the user,
delegates to the data and UI agents, and drives navigation. Everything it does reaches the
browser as events (see EVENTS below) through an asyncio queue, so the SSE response streams
while the loop runs.

EVENTS (each a dict with "type"):
  status      {stage, text}                 progress line ("Querying: ...")
  text        {text}                        a delta of the assistant's reply
  text_break  {}                            a new paragraph between loop steps
  query       {id?, title, sql, row_count?, ms?, error?, kind?}   SQL that ran (or failed)
  navigate    {pillar, view, payload, label, focus}   focus = block to scroll to and highlight
  view        {spec, reopened?}             a hydrated view for the canvas (spec.qa = review fixes);
                                            reopened = an earlier view shown again
  verify      {status, checked, issues}     the answer verifier's check of the reply's figures
  notice      {kind, text, suggestions}     off_topic | unsafe | refusal | budget | limit
  error       {text}
  done        {}
"""

import asyncio
import functools
import json
import re

from . import adapter, config, data_agent, db, guard, navigation, product_ui, prompts, ui_agent, verifier
from .llm import LLMError, get_llm
from .pages import PAGES

_PILLARS = sorted({p for p, _ in PAGES})
_VIEWS = sorted({v for _, v in PAGES})
_PAYLOAD_KEYS = list(dict.fromkeys(k for page in PAGES.values() for k in page["payload"]))
_T = adapter.manifest()["tools"]
_NEWS_PANEL = (adapter.manifest()["product_api"].get("news_block") or {}).get("focus") or "news"

@functools.lru_cache(maxsize=1)
def tools() -> list:
    """The orchestrator's tools; built on first use, when the client's name is known."""
    _CLIENT = adapter.client()["name"]
    _T = {k: adapter.fill(v, adapter._facts()) for k, v in adapter.manifest()["tools"].items()}   # {slots} from the data
    return [
    {
        "name": "query_data",
        "description": "Ask the data analyst an analytical question. It writes and runs SQL against the "
                       "platform database and returns result sets (result_id, columns, sample rows, stats) "
                       "with findings, caveats and assumptions. Several related asks can go in one question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The precise question with entities, filters, time window and breakdown, e.g. 'Total award value in USD by year and segment, 2022-2026'."},
                "purpose": {"type": "string", "description": "How the answer will be used, e.g. 'stacked bar chart of segments over time' or 'single figure for the reply'."},
            },
            "required": ["question", "purpose"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "search_platform",
        "description": f"Search what the platform's pages show ({_T['search_covers']}). "
                       "Returns matching blocks with where they live in the platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": f"What to find, in plain words, e.g. {_T['search_examples']}."},
                "kind": {"type": "string", "enum": ["any"] + product_ui.kinds()},
            },
            "required": ["query"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "read_platform",
        "description": "Read the full content of a block found with search_platform, plus the page and section to "
                       "navigate to (navigate_to) so the user can see it.",
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "live_news",
        "description": "Today's live headlines about one company, exactly as the platform's profile page shows them in "
                       f"its {_NEWS_PANEL} panel (fetched live; not stored data). Use for 'latest / recent news' questions "
                       "and to add current context to an answer.",
        "input_schema": {
            "type": "object",
            "properties": {"company": {"type": "string", "description": f"Company name, e.g. '{_T['company_example']}'."}},
            "required": ["company"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "show_insight",
        "description": "Build a visual view (KPI tiles, charts, tables, filters) on the canvas beside the chat "
                       "from result sets returned by query_data. Call again with a new brief to change a view.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "View title, e.g. 'Contract awards by segment, 2022-2026'."},
                "brief": {"type": "string", "description": f"What the view must make clear: the comparison, emphasis (e.g. highlight {_CLIENT}), preferred chart if the user asked for one, which result to lead with."},
                "result_ids": {"type": "array", "items": {"type": "string"}, "description": "result_ids from query_data to visualise."},
            },
            "required": ["title", "brief", "result_ids"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "reopen_view",
        "description": "Show again, unchanged, a view generated earlier in this conversation (ids are listed in "
                       "<session_views>). Use it when the user wants to go back to an earlier chart; to change an "
                       "earlier view, call show_insight with its result_ids and a new brief instead.",
        "input_schema": {
            "type": "object",
            "properties": {"view_id": {"type": "string"}},
            "required": ["view_id"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "navigate",
        "description": "Open a platform page behind the canvas, optionally on a specific item. See the page list "
                       "in the system prompt for each page's payload keys.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pillar": {"type": "string", "enum": _PILLARS},
                "view": {"type": "string", "enum": _VIEWS},
                "payload": {
                    "type": "object",
                    "properties": {k: {"type": "string"} for k in _PAYLOAD_KEYS},
                    "description": "Only the keys the page takes; {} for none.",
                },
                "label": {"type": "string", "description": f"What is being opened, for the user, e.g. '{_T['company_example']} profile'."},
                "focus": {"type": "string", "description": "Optional: the section heading or item text to scroll to and highlight once the page is open, "
                                                           f"e.g. {_T['focus_examples']}. \"\" for the top of the page."},
            },
            "required": ["pillar", "view", "payload", "label"],
        },
        "eager_input_streaming": True,
    },
    ]


_END = object()
_system_cache = {}


def _system() -> str:
    if "orch" not in _system_cache:
        _system_cache["orch"] = prompts.orchestrator_system(db.companies())
    return _system_cache["orch"]


def _clip(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _page_block(page: dict) -> str:
    """The user's current page as context. It comes from the browser, so it is treated as
    data: strings only, bounded in size."""
    if not isinstance(page, dict) or not page:
        return ""
    lines = []
    if page.get("pillar") or page.get("view"):
        lines.append(f"Page: {_clip(page.get('pillar'), 40)} / {_clip(page.get('view'), 40)}"
                     f" ({_clip(page.get('viewTitle'), 80)})")
    if page.get("selection"):
        lines.append(f"Selected item: {_clip(page.get('selection'), 200)}")
    if page.get("canvas"):
        lines.append(f"The canvas currently shows the view: {_clip(page.get('canvas'), 200)}")
    blocks = [_clip(b, 80) for b in (page.get("blocks") or []) if isinstance(b, str)][:40]
    if blocks:
        lines.append("Sections on this page (navigate focus targets): " + "; ".join(blocks))
    report = page.get("report")
    if isinstance(report, dict):
        body = [_clip(report.get("title"), 200), _clip(report.get("subtitle"), 300)]
        for sec in (report.get("sections") or [])[:20]:
            if not isinstance(sec, dict):
                continue
            body.append(f"## {_clip(sec.get('h'), 120)}")
            for row in (sec.get("rows") or [])[:40]:
                if isinstance(row, list) and len(row) >= 2:
                    body.append(f"- {_clip(row[0], 80)}: {_clip(row[1], 300)}")
                else:
                    body.append(f"- {_clip(row, 300)}")
        text = "\n".join(b for b in body if b)
        lines.append("What the page shows:\n" + _clip(text, config.PAGE_CONTEXT_CHARS))
    if not lines:
        return ""
    return "<page_context>\n" + "\n".join(lines) + "\n</page_context>\n\n"


def _session_block(conv) -> str:
    """What this conversation has already produced, so a follow-up can reuse it: the views
    on file (reopen_view) and the result sets behind them (show_insight / new query)."""
    if not conv.views:
        return ""
    lines = [f"- {v['id']}: \"{_clip(v['title'], 100)}\" (asked: \"{_clip(v.get('question'), 90)}\"; data: "
             f"{', '.join(v['result_ids'])})" for v in conv.views[-8:]]
    return "<session_views>\n" + "\n".join(lines) + "\n</session_views>\n\n"


def _pending_tool_uses(conv) -> list:
    """tool_use ids in the last assistant message that have no tool_result yet."""
    if not conv.messages or conv.messages[-1]["role"] != "assistant":
        return []
    out = []
    for b in conv.messages[-1]["content"]:
        btype = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
        if btype == "tool_use":
            out.append(b.get("id") if isinstance(b, dict) else b.id)
    return out


def _close_dangling(conv, reason: str) -> None:
    """Keep the history valid: every tool_use must be answered before the next user turn."""
    ids = _pending_tool_uses(conv)
    if ids:
        conv.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": i, "is_error": True, "content": reason} for i in ids]})


async def _dispatch(conv, tu, question, emit) -> dict:
    name, args = tu["name"], tu["input"] if isinstance(tu["input"], dict) else {}

    def err(msg):
        return {"type": "tool_result", "tool_use_id": tu["id"], "is_error": True, "content": msg}

    try:
        if name == "query_data":
            q, purpose = args.get("question"), args.get("purpose", "")
            if not isinstance(q, str) or not q.strip():
                return err("query_data needs a non-empty `question` string.")
            emit({"type": "status", "stage": "plan", "text": "Working out the analysis"})
            report = await data_agent.answer(conv, q, str(purpose), emit)
            return {"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(report, default=str)}

        if name == "show_insight":
            rids = args.get("result_ids")
            if not isinstance(rids, list) or not all(isinstance(r, str) for r in rids):
                return err("show_insight needs `result_ids` as a list of strings.")
            view, warnings = await ui_agent.build_view(
                conv, question, str(args.get("title") or ""), str(args.get("brief") or ""), rids, emit)
            emit({"type": "view", "spec": view})
            return {"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps({
                "shown": True, "view_title": view["title"], "result_ids": sorted(view["data"]),
                "widgets": [f"{w['type']}: {w['title']}" for w in view["widgets"]],
                "summary": view["summary"], "notes": warnings[:5]})}

        if name == "search_platform":
            q = args.get("query")
            if not isinstance(q, str) or not q.strip():
                return err("search_platform needs a `query` string.")
            emit({"type": "status", "stage": "read", "text": "Looking through the platform"})
            hits = await asyncio.to_thread(product_ui.search, q, str(args.get("kind") or ""))
            # what the answer may quote from these snippets, so the verifier can confirm it too
            if hits:
                conv.turn_reads.append("[platform search results]\n" + "\n".join(f"{h['title']} ({h['where']}): {h['snippet']}" for h in hits))
            return {"type": "tool_result", "tool_use_id": tu["id"],
                    "content": json.dumps({"results": hits} if hits else {"results": [], "note": "Nothing on the pages matches; try other words or query_data."})}

        if name == "read_platform":
            doc = await asyncio.to_thread(product_ui.read, str(args.get("doc_id") or ""))
            if doc is None:
                return err("Unknown doc_id; use one returned by search_platform.")
            emit({"type": "status", "stage": "read", "text": f"Reading: {doc['title'][:70]}"})
            conv.turn_reads.append(f"[{doc['title']}]\n{doc['content']}")
            return {"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(doc, default=str)}

        if name == "live_news":
            emit({"type": "status", "stage": "read", "text": "Checking the latest news"})
            try:
                out = await asyncio.to_thread(product_ui.live_news, str(args.get("company") or ""))
            except Exception as exc:
                return err(f"The live news panel could not be reached: {exc}")
            conv.turn_reads.append("[live headlines]\n" + json.dumps(out, default=str))
            return {"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(out, default=str)}

        if name == "reopen_view":
            spec = conv.view_specs.get(str(args.get("view_id") or ""))
            if spec is None:
                ids = ", ".join(f"{v['id']} ({v['title']})" for v in conv.views) or "none"
                return err(f"No such view. Views in this conversation: {ids}.")
            emit({"type": "view", "spec": spec, "reopened": True})
            return {"type": "tool_result", "tool_use_id": tu["id"],
                    "content": f"Reopened the view '{spec['title']}' on the canvas."}

        if name == "navigate":
            pillar, view = args.get("pillar"), args.get("view")
            payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            try:
                target = await asyncio.to_thread(navigation.resolve, pillar, view, payload)
            except navigation.NavError as exc:
                return err(str(exc))
            label = str(args.get("label") or PAGES[(pillar, view)]["label"])
            focus = _clip(args.get("focus") or "", 120).strip()
            emit({"type": "navigate", "pillar": pillar, "view": view, "payload": target, "label": label,
                  "focus": focus})
            return {"type": "tool_result", "tool_use_id": tu["id"],
                    "content": f"Opened {label} ({pillar}/{view}) with {json.dumps(target)}"
                               + (f", scrolled to and highlighted '{focus}'" if focus else "")
                               + ". The canvas closes so the user sees the page, unless you also show a view."}

        return err(f"Unknown tool {name}.")
    except (ValueError, LLMError) as exc:
        return err(str(exc))


async def _orchestrator_turn(system, messages, on_text):
    return await get_llm().turn(
        role="orchestrator", model=config.ORCHESTRATOR_MODEL, system=system,
        messages=messages, tools=tools(), effort=config.ORCHESTRATOR_EFFORT,
        max_tokens=16000, on_text=on_text)


async def _run(conv, question: str, page: dict, emit) -> None:
    emit({"type": "status", "stage": "guard", "text": "Reading the question"})
    system = await asyncio.to_thread(_system)
    _close_dangling(conv, "interrupted")
    user_msg = {"role": "user", "content": _page_block(page) + _session_block(conv) + question}

    # The scope check and the orchestrator's first step run side by side; the first step's
    # output is held back until the check passes, and thrown away (never added to the
    # history) when it does not.
    held = []

    async def hold_text(delta):
        held.append(delta)

    guard_task = asyncio.create_task(guard.screen(question, conv.recent_questions))
    first_task = asyncio.create_task(_orchestrator_turn(system, conv.messages + [user_msg], hold_text))
    try:
        verdict = await guard_task
    except BaseException:
        first_task.cancel()
        raise
    if verdict["verdict"] != "in_scope":
        first_task.cancel()
        emit({"type": "notice", "kind": verdict["verdict"], "text": verdict["reply"],
              "suggestions": verdict.get("suggestions", [])})
        return
    emit({"type": "status", "stage": "plan", "text": "Planning"})
    turn = await first_task
    results_before = set(conv.results)
    conv.recent_questions.append(question)
    conv.messages.append(user_msg)
    conv.turn_reads = []
    wrote = bool(held)
    for delta in held:
        emit({"type": "text", "text": delta})

    async def on_text(delta):
        nonlocal wrote
        wrote = True
        emit({"type": "text", "text": delta})

    for step in range(config.MAX_ORCHESTRATOR_STEPS + 1):
        last_step = step == config.MAX_ORCHESTRATOR_STEPS
        if step:
            if wrote:
                emit({"type": "text_break"})
            emit({"type": "status", "stage": "plan", "text": "Writing the answer" if last_step else "Thinking"})
            turn = await _orchestrator_turn(system, conv.messages, on_text)
        conv.messages.append({"role": "assistant", "content": turn.content})

        if turn.stop_reason == "refusal":
            _close_dangling(conv, "declined")
            emit({"type": "notice", "kind": "refusal",
                  "text": adapter.client()["refusal"],
                  "suggestions": []})
            return
        if not turn.tool_uses:
            fresh = [conv.results[r] for r in conv.results if r not in results_before]
            # nothing to check when no data was fetched and the reply states no figures
            # (navigation, refusals, clarifying questions)
            if config.VERIFY_ENABLED and turn.text.strip() and (fresh or conv.turn_reads or re.search(r"\d", turn.text)):
                used = fresh or ([] if conv.turn_reads else [conv.results[r] for r in list(conv.results)[-3:]])
                emit({"type": "status", "stage": "verify", "text": "Checking the figures"})
                reference = prompts.reference_facts(await asyncio.to_thread(db.schema_catalog), await asyncio.to_thread(db.companies))
                v = await verifier.verify(turn.text, used, _page_block(page), reference, conv.turn_reads)
                emit({"type": "verify", **v})
            return
        if turn.stop_reason == "max_tokens":
            _close_dangling(conv, "The tool call was cut off (output limit). Retry with a shorter request.")
            continue
        if last_step:
            _close_dangling(conv, "Step limit reached. Answer now with what you have.")
            emit({"type": "notice", "kind": "limit", "text": "That took more steps than allowed; "
                  "the answer may be partial.", "suggestions": []})
            return
        results = await asyncio.gather(*(_dispatch(conv, tu, question, emit) for tu in turn.tool_uses))
        conv.messages.append({"role": "user", "content": list(results)})
        if step == config.MAX_ORCHESTRATOR_STEPS - 1:
            conv.messages.append({"role": "user", "content": "(Step limit reached: answer now without further tools.)"})


async def run(conv, question: str, page: dict):
    """Async generator of events for one user message."""
    queue: asyncio.Queue = asyncio.Queue()
    shown = {"view": False, "nav": False}

    def emit(ev):
        if ev.get("type") == "view":
            shown["view"] = True
        elif ev.get("type") == "navigate":
            shown["nav"] = True
        queue.put_nowait(ev)

    async def runner():
        try:
            await _run(conv, question, page, emit)
        except LLMError as exc:
            print(f"[agent] answer failed: {exc}", flush=True)
            if shown["view"] or shown["nav"]:
                # the work the user can see is done; only the written reply is missing
                emit({"type": "notice", "kind": "partial", "suggestions": [],
                      "text": ("The view is ready on the canvas. " if shown["view"] else "The page is open. ")
                              + "The written summary could not be finished because the connection to the AI "
                                "service dropped; ask again if you need it."})
            else:
                emit({"type": "error", "retry": True,
                      "text": "I couldn't reach the AI service just now, so there is no answer yet. Please try again in a moment."})
        except Exception as exc:  # report, keep the service up
            print(f"[agent] orchestrator crashed: {type(exc).__name__}: {exc}", flush=True)
            emit({"type": "error", "retry": True, "text": "Something went wrong while answering. Please try again."})
        finally:
            _close_dangling(conv, "interrupted")
            emit({"type": "done"})
            queue.put_nowait(_END)

    task = asyncio.create_task(runner())
    try:
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield {"type": "ping"}
                continue
            if ev is _END:
                break
            yield ev
    finally:
        if not task.done():
            task.cancel()
