"""HTTP surface of the agent:

  GET    /api/agent/status                   enabled?, provider, models, db, budget
  POST   /api/agent/chat                     {conversation_id?, message, page?} -> text/event-stream
  DELETE /api/agent/conversation/{id}        forget a conversation (memory and History)
  GET    /api/agent/conversations             History: saved conversations
  GET    /api/agent/conversations/{id}        one conversation's transcript and views
  PUT    /api/agent/conversations/{id}/transcript   the dock's transcript, after each answer
  POST   /api/agent/views/{view_id}/save      save (pin) a view; its id is the share id
  GET    /api/agent/views                     saved views
  GET    /api/agent/views/{id}                one saved view (what a share link opens)
  DELETE /api/agent/views/{id}
"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import adapter, budget, config, db, orchestrator, product_ui, state, store

router = APIRouter(prefix="/api/agent")


def startup() -> None:
    db.ensure_analytics()
    if db.status()["ready"]:
        try:
            db.schema_catalog()   # warm the catalogue the data agent is prompted with
            db.companies()
        except Exception as exc:
            print(f"[agent] catalogue warm-up failed: {exc}", flush=True)
    product_ui.warm()             # what the product's pages show (from its own /api/dataset)
    store.ensure()                # saved conversations and views


@router.get("/status")
async def status():
    return {
        "enabled": config.credentials_present() and db.status()["ready"],
        "credentials": config.credentials_present(),
        "debug_ui": config.DEBUG_UI,
        "provider": config.LLM_PROVIDER,
        "models": {"orchestrator": config.ORCHESTRATOR_MODEL, "data": config.DATA_MODEL,
                   "ui": config.UI_MODEL, "guard": config.GUARD_MODEL},
        "db": db.status(),
        "pages_index": product_ui.status(),
        "history": store.ready(),
        "budget": await budget.status(),
        # for the widget: whom to highlight and each company's fixed chart colour
        "client": {"name": adapter.client().get("name"), "short": adapter.client().get("short_name")},
        "companies": [{k: c.get(k) for k in ("id", "name", "client", "color_slot", "color_match")} for c in adapter.companies()],
    }


def _sse(ev: dict) -> str:
    if ev.get("type") == "ping":
        return ": ping\n\n"
    return f"data: {json.dumps(ev, default=str)}\n\n"


@router.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "body must be JSON"})
    message = str(body.get("message") or "").strip()[:2000]
    if not message:
        return JSONResponse(status_code=400, content={"error": "message is required"})
    if not config.credentials_present():
        return JSONResponse(status_code=503, content={"error": "no model credentials configured in parallax-agent/.env"})
    if not db.status()["ready"]:
        return JSONResponse(status_code=503, content={"error": f"analytics database unavailable: {db.status()['error']}"})

    cid = body.get("conversation_id")
    conv = state.get(cid)
    if conv is None and cid:
        # not in memory (the service restarted, or reopened from History): restore it
        restored = await asyncio.to_thread(store.load, cid)
        if restored is not None:
            conv = state.register(restored)
    if conv is None:
        conv = state.get_or_create(None)
    if conv.lock.locked():
        return JSONResponse(status_code=409, content={"error": "still answering the previous message"})
    page = body.get("page") if isinstance(body.get("page"), dict) else {}
    spend = await budget.status()

    async def stream():
        async with conv.lock:
            yield _sse({"type": "meta", "conversation_id": conv.id})
            if spend.get("exhausted"):
                yield _sse({"type": "notice", "kind": "budget", "suggestions": [],
                            "text": f"The testing budget of ${spend['budget_usd']:.0f} is used up "
                                    f"(${spend['spent_usd']:.2f} spent). Raise AGENT_BUDGET_USD in "
                                    "parallax-agent/.env to continue."})
                yield _sse({"type": "done"})
                return
            async for ev in orchestrator.run(conv, message, page):
                if ev.get("type") == "done":
                    budget.mark_stale()
                    ev = {**ev, "budget": await budget.status(max_age_s=0)}
                    try:
                        await asyncio.to_thread(store.save_memory, conv)
                    except Exception as exc:
                        print(f"[agent] could not save the conversation: {exc}", flush=True)
                yield _sse(ev)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/conversation/{conv_id}")
async def forget(conv_id: str):
    state.drop(conv_id)
    await asyncio.to_thread(store.delete_conversation, conv_id)
    return {"ok": True}


@router.get("/conversations")
async def conversations():
    return {"conversations": await asyncio.to_thread(store.list_conversations)}


@router.get("/conversations/{conv_id}")
async def conversation(conv_id: str):
    c = await asyncio.to_thread(store.get_conversation, conv_id)
    return c if c else JSONResponse(status_code=404, content={"error": "no such conversation"})


@router.put("/conversations/{conv_id}/transcript")
async def transcript(conv_id: str, request: Request):
    body = await request.json()
    msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
    await asyncio.to_thread(store.save_transcript, conv_id, str(body.get("title") or ""), msgs[-200:])
    return {"ok": True}


@router.post("/views/{view_id}/save")
async def save_view(view_id: str, request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = {}
    spec, owner = None, body.get("conversation_id")
    conv = state.get(owner) or (await asyncio.to_thread(store.load, owner) if owner else None)
    if conv is not None:
        spec = conv.view_specs.get(view_id)
    if spec is None and isinstance(body.get("spec"), dict) and body["spec"].get("id") == view_id:
        spec = body["spec"]  # a view the server no longer holds; the browser still has it
    if spec is None:
        return JSONResponse(status_code=404, content={"error": "no such view"})
    await asyncio.to_thread(store.save_view, spec, owner)
    return {"id": view_id}


@router.get("/views")
async def saved_views():
    return {"views": await asyncio.to_thread(store.list_views)}


@router.get("/views/{view_id}")
async def saved_view(view_id: str):
    v = await asyncio.to_thread(store.get_view, view_id)
    return v if v else JSONResponse(status_code=404, content={"error": "no such view"})


@router.delete("/views/{view_id}")
async def delete_saved_view(view_id: str):
    await asyncio.to_thread(store.delete_view, view_id)
    return {"ok": True}
