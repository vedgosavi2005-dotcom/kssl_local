"""The data agent: turns an analytical question into read-only SQL over analytics.*, can
have rows categorised by a model, and reports result sets by id with findings, caveats and
assumptions. Its own message history lives only for one query_data call; the result sets it
creates persist on the conversation so later views can reuse them."""

import asyncio
import json

import psycopg2

from . import config, db, prompts
from .llm import LLMError, get_llm
from .sql_guard import SqlRejected

RUN_SQL_TOOL = {
    "name": "run_sql",
    "description": "Run one read-only SELECT (or WITH ... SELECT) against the analytics views. "
                   "Returns result_id, columns, up to 25 rows and per-column stats, or the error.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short specific title for the result set, e.g. 'Award value by year and segment (USD)'."},
            "sql": {"type": "string", "description": "A single PostgreSQL SELECT statement, no semicolon."},
        },
        "required": ["title", "sql"],
    },
}

CATEGORIZE_TOOL = {
    "name": "categorize",
    "description": "Have a language model assign each row of an existing result set to a category, "
                   "for groupings no column provides. Returns a new result set (columns of the source "
                   "plus `category` and `category_confidence`) and the assumptions behind the grouping.",
    "input_schema": {
        "type": "object",
        "properties": {
            "result_id": {"type": "string"},
            "key_column": {"type": "string", "description": "Column that identifies a row (an id or a unique name)."},
            "text_columns": {"type": "array", "items": {"type": "string"},
                             "description": "Columns whose text describes the row (title, note, summary)."},
            "instructions": {"type": "string", "description": "What the grouping should capture."},
            "categories": {"type": "array", "items": {"type": "string"},
                           "description": "Fixed category names to use, or [] to let the model define 3-7."},
        },
        "required": ["result_id", "key_column", "text_columns", "instructions", "categories"],
    },
}


def _err(tool_use_id, message):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "is_error": True, "content": message}


async def _run_sql(conv, tu, emit):
    args = tu["input"] if isinstance(tu["input"], dict) else {}
    title, sql = args.get("title"), args.get("sql")
    if not isinstance(title, str) or not isinstance(sql, str):
        return _err(tu["id"], "run_sql needs string `title` and `sql`.")
    emit({"type": "status", "stage": "query", "text": f"Querying: {title}"})
    try:
        out = await asyncio.to_thread(db.run_query, sql)
    except SqlRejected as exc:
        emit({"type": "query", "title": title, "sql": sql, "error": str(exc)})
        return _err(tu["id"], f"Rejected before running: {exc}")
    except psycopg2.Error as exc:
        msg = (getattr(exc, "pgerror", None) or str(exc)).strip().splitlines()
        msg = " ".join(msg[:3])[:600]
        emit({"type": "query", "title": title, "sql": sql, "error": msg})
        return _err(tu["id"], f"Database error: {msg}")
    rs = conv.add_result(title=title, sql=sql, columns=out["columns"], rows=out["rows"],
                         truncated=out["truncated"], ms=out["ms"])
    emit({"type": "query", "id": rs.id, "title": title, "sql": sql, "row_count": rs.row_count,
          "ms": rs.ms, "truncated": rs.truncated})
    return {"type": "tool_result", "tool_use_id": tu["id"],
            "content": json.dumps(rs.preview(), default=str)}


async def _categorize(conv, tu, emit):
    args = tu["input"] if isinstance(tu["input"], dict) else {}
    rs = conv.results.get(args.get("result_id"))
    if rs is None:
        return _err(tu["id"], f"Unknown result_id {args.get('result_id')!r}.")
    cols = rs.column_names()
    key = args.get("key_column")
    text_cols = [c for c in (args.get("text_columns") or []) if c in cols]
    if key not in cols or not text_cols:
        return _err(tu["id"], f"key_column and text_columns must be columns of {rs.id}: {cols}")
    instructions = str(args.get("instructions") or "")[:1000]
    fixed = [str(c) for c in (args.get("categories") or [])][:12]
    emit({"type": "status", "stage": "categorize", "text": f"Categorising {rs.row_count} rows"})

    items, seen = [], set()
    for r in rs.records()[: config.MAX_CATEGORIZE_ROWS]:
        k = str(r[key])
        if k in seen:
            continue
        seen.add(k)
        items.append({"key": k, "text": " | ".join(f"{c}: {str(r[c])[:300]}" for c in text_cols if r.get(c))})
    try:
        turn = await get_llm().turn(
            role="categorize", model=config.CATEGORIZE_MODEL, system=prompts.categorize_system(),
            messages=[{"role": "user", "content": json.dumps(
                {"instruction": instructions, "categories": fixed, "rows": items})}],
            effort="low", max_tokens=16000, output_schema=prompts.CATEGORIZE_SCHEMA)
        out = turn.json()
    except LLMError as exc:
        return _err(tu["id"], f"Categorisation failed: {exc}")

    mapping = {str(a["key"]): (a["category"], a["confidence"]) for a in out.get("assignments", [])}
    ki = cols.index(key)
    rows = [r + list(mapping.get(str(r[ki]), ("Unclassified", "low"))) for r in rs.rows]
    assumptions = list(out.get("assumptions") or []) + [
        f"{c['name']}: {c['definition']}" for c in out.get("categories") or []]
    new = conv.add_result(
        title=f"{rs.title}, categorised", columns=rs.columns + [
            {"name": "category", "type": "text"}, {"name": "category_confidence", "type": "text"}],
        rows=rows, sql=f"{rs.sql}\n-- then categorised by a language model: {instructions}",
        assumptions=assumptions)
    emit({"type": "query", "id": new.id, "title": new.title, "sql": new.sql, "row_count": new.row_count,
          "ms": 0, "kind": "categorize"})
    counts = {}
    for r in rows:
        counts[r[-2]] = counts.get(r[-2], 0) + 1
    # the crosstab most questions want next ("mix per competitor"), so nothing has to
    # query the categorised rows -- they live here, not in the database
    by = next((c for c in ("company", "competitor", "comp_id", "rival_company", "name") if c in cols), None)
    crosstab = {}
    if by:
        bi = cols.index(by)
        for r in rows:
            crosstab.setdefault(str(r[bi]), {}).setdefault(r[-2], 0)
            crosstab[str(r[bi])][r[-2]] += 1
    return {"type": "tool_result", "tool_use_id": tu["id"],
            "content": json.dumps({**new.preview(), "category_counts": counts,
                                   **({f"counts_by_{by}": crosstab} if by else {}),
                                   "note": f"{new.id} exists only in this analysis, not in the database: do not SELECT "
                                           "from it. Report it as a result set; the canvas groups and counts its rows."},
                                  default=str)}


async def answer(conv, question: str, purpose: str, emit) -> dict:
    """Run the data agent to completion; return its report with result previews."""
    system = prompts.data_system(await asyncio.to_thread(db.schema_catalog))
    messages = [{"role": "user", "content": f"Question: {question}\nPurpose: {purpose}"}]
    created = []
    report = None
    for _ in range(config.MAX_DATA_STEPS):
        turn = await get_llm().turn(
            role="data", model=config.DATA_MODEL, system=system, messages=messages,
            tools=[RUN_SQL_TOOL, CATEGORIZE_TOOL], effort=config.DATA_EFFORT, max_tokens=16000,
            output_schema=prompts.DATA_REPORT_SCHEMA)
        messages.append({"role": "assistant", "content": turn.content})
        if turn.stop_reason == "refusal":
            break
        if not turn.tool_uses:
            try:
                report = turn.json()
            except LLMError:
                report = None
            break
        tool_results = []
        for tu in turn.tool_uses:
            before = set(conv.results)
            if tu["name"] == "run_sql":
                tool_results.append(await _run_sql(conv, tu, emit))
            elif tu["name"] == "categorize":
                tool_results.append(await _categorize(conv, tu, emit))
            else:
                tool_results.append(_err(tu["id"], f"Unknown tool {tu['name']}."))
            created += [rid for rid in conv.results if rid not in before]
        messages.append({"role": "user", "content": tool_results})

    if report is None:
        # step limit, refusal or malformed report: hand back whatever ran, flagged
        report = {"answerable": bool(created),
                  "results": [{"result_id": rid, "role": "primary" if i == 0 else "supporting",
                               "description": conv.results[rid].title} for i, rid in enumerate(created)],
                  "findings": [], "caveats": ["The analysis stopped early; results may be incomplete."],
                  "assumptions": []}

    results = []
    for r in report.get("results") or []:
        rs = conv.results.get(r.get("result_id"))
        if rs is None:
            continue
        p = rs.preview(n=40)  # the orchestrator sees small results whole; it quotes their numbers
        results.append({**p, "role": r.get("role", "supporting"), "description": r.get("description", "")})
    assumptions = list(report.get("assumptions") or [])
    for r in results:
        assumptions += r.get("assumptions", [])
    return {"answerable": bool(report.get("answerable", True)) and bool(results),
            "results": results, "findings": report.get("findings") or [],
            "caveats": report.get("caveats") or [], "assumptions": assumptions}
