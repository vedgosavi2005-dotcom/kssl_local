"""Parallax Analyst service: the agent API plus a thin gateway in front of the product.

The product is not modified. This service:
  - serves the product's built frontend (PRODUCT_DIST, the demo's dist/) with two tags
    added to index.html -- the chat widget's stylesheet and script;
  - forwards every other /api/* request to the product backend (PRODUCT_API) untouched;
  - answers /api/agent/* itself.

Open the product here (http://localhost:8098 by default) to get the chatbot; open it on
its own port (8097 under Docker) to get it exactly as shipped. Delete parallax-agent/ and
nothing in the product changes.
"""

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import adapter
from agent.routes import router as agent_router, startup as agent_startup

HERE = Path(__file__).resolve().parent
PRODUCT_DIST = Path(os.environ.get("PRODUCT_DIST") or HERE.parent.parent / "dist").resolve()
PRODUCT_API = os.environ.get("PRODUCT_API", "http://127.0.0.1:8600").rstrip("/")
# Some product versions answer a few /api paths from their web server rather than their API
# (adapter/product.json product_api.web_routes, e.g. /api/img, /api/pulse); PRODUCT_WEB is
# where that server runs.
PRODUCT_WEB = os.environ.get("PRODUCT_WEB", "").rstrip("/")
WIDGET_DIST = Path(os.environ.get("WIDGET_DIST", HERE / "static")).resolve()
# On a public deployment, forward only the product API paths its pages call (comma-separated
# prefixes, e.g. "/api/dataset,/api/pulse,/api/img"); the product's operator endpoints stay
# unreachable. Empty: forward everything (local use).
PRODUCT_API_ALLOW = [p.strip() for p in os.environ.get("PRODUCT_API_ALLOW", "").split(",") if p.strip()]

INJECT = ('<link rel="stylesheet" href="/parallax-agent/widget.css">'
          '<script type="module" src="/parallax-agent/widget.js"></script>')

app = FastAPI(title="Parallax Analyst", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(agent_router)
app.mount("/parallax-agent", StaticFiles(directory=WIDGET_DIST, check_dir=False), name="widget")
if (PRODUCT_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=PRODUCT_DIST / "assets"), name="assets")

_client: httpx.AsyncClient = None
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "host", "content-length"}


@app.on_event("startup")
async def _startup():
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))
    import asyncio
    await asyncio.to_thread(agent_startup)
    print(f"[gateway] product dist: {PRODUCT_DIST}  product api: {PRODUCT_API}  widget: {WIDGET_DIST}", flush=True)


@app.on_event("shutdown")
async def _shutdown():
    if _client:
        await _client.aclose()


def upstream_for(path: str) -> str:
    """the product's API, or its web server for the paths the adapter names"""
    if PRODUCT_WEB and any(path == r or path.startswith(r.rstrip("/") + "/")
                           for r in adapter.manifest()["product_api"].get("web_routes") or []):
        return PRODUCT_WEB
    return PRODUCT_API


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def product_api(path: str, request: Request):
    """Everything under /api that is not /api/agent goes to the product as-is (bodies, headers
    such as a CSRF header, and gzip encoding passed through untouched): its API, or its web
    server for the paths the adapter names."""
    if PRODUCT_API_ALLOW and not any(f"/api/{path}" == a or f"/api/{path}".startswith(a.rstrip("/") + "/") for a in PRODUCT_API_ALLOW):
        return JSONResponse(status_code=404, content={"error": "not found"})
    url = f"{upstream_for('/api/' + path)}/api/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    try:
        upstream = await _client.send(
            _client.build_request(request.method, url, params=request.query_params,
                                  headers=headers, content=await request.body()),
            stream=True)
    except httpx.HTTPError as exc:
        return JSONResponse(status_code=502, content={"error": f"product unreachable at {url.split('/api/')[0]}: {exc}"})
    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP}

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(body(), status_code=upstream.status_code, headers=out_headers)


def _index() -> Response:
    index = PRODUCT_DIST / "index.html"
    if not index.is_file():
        return HTMLResponse(f"<h1>Product build not found</h1><p>Expected {index}</p>", status_code=500)
    html = index.read_text(encoding="utf-8")
    # the widget keeps fixed file names, so stamp them with the build time: a rebuilt
    # widget is fetched fresh instead of served from the browser's heuristic cache
    try:
        version = int((WIDGET_DIST / "widget.js").stat().st_mtime)
    except OSError:
        version = 0
    tags = INJECT.replace("widget.css", f"widget.css?v={version}").replace("widget.js", f"widget.js?v={version}")
    html = html.replace("</head>", tags + "</head>", 1) if "</head>" in html else html + tags
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/{path:path}")
async def product_page(path: str):
    """Static files from the product build; any other path is the SPA (hash routing)."""
    if path:
        f = (PRODUCT_DIST / path).resolve()
        if f.is_file() and f.is_relative_to(PRODUCT_DIST) and f.name != "index.html":
            return FileResponse(f)
    return _index()
