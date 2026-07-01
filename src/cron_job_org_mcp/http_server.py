"""
HTTP transport wrapper for the cron-job.org MCP server.

This module runs the FastMCP server over HTTP with streamable-HTTP transport
(plus SSE for older clients), so it can be deployed on a Render Web Service
and connected to by remote MCP clients (e.g. Kai 9000) over the network
instead of local stdio.

It also exposes a small ``/health`` endpoint suitable for keep-alive pings.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
import uvicorn
from starlette.middleware.cors import CORSMiddleware

from .server import mcp


def _build_health_app(mcp_url: str) -> FastAPI:
    """Create a small FastAPI app that serves /health and /.

    The MCP server itself runs in a background task on an internal port;
    this app is the public-facing entry point that handles keep-alive pings
    and forwards MCP traffic to the internal MCP server.
    """
    health_app = FastAPI(
        title="cron-job.org MCP",
        version="1.0.0",
        description=(
            "MCP server for cron-job.org. Health endpoint at /health, "
            "MCP endpoint at /mcp (streamable-HTTP) and /sse (legacy SSE)."
        ),
    )

    # CORS — useful for browser-based MCP clients.
    health_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @health_app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "service": "cron-job-org-mcp",
                "status": "ok",
                "endpoints": {
                    "mcp": "/mcp",
                    "sse_legacy": "/sse",
                    "health": "/health",
                },
            }
        )

    @health_app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "cron-job-org-mcp",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @health_app.get("/healthz")
    async def healthz() -> JSONResponse:
        # Alias kept for platforms that default to /healthz (e.g. Kubernetes).
        return await health()

    # Forward /mcp and /sse to the internal MCP server.
    @health_app.api_route(
        "/mcp/{path:path}",
        methods=["GET", "POST", "DELETE", "OPTIONS", "PUT", "PATCH"],
    )
    @health_app.api_route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS", "PUT", "PATCH"])
    async def proxy_mcp(path: str = ""):  # noqa: ARG001
        return await _proxy(mcp_url, path)

    @health_app.api_route(
        "/sse/{path:path}",
        methods=["GET", "POST", "DELETE", "OPTIONS", "PUT", "PATCH"],
    )
    @health_app.api_route("/sse", methods=["GET", "POST", "DELETE", "OPTIONS", "PUT", "PATCH"])
    async def proxy_sse(path: str = ""):  # noqa: ARG001
        return await _proxy(mcp_url, path)

    return health_app


async def _proxy(internal_url: str, path: str):
    """Forward the current request to the internal MCP server."""
    from fastapi import Request

    # We can't capture the request here without a Request parameter; use a
    # simpler approach: run the MCP server itself on the SAME port via
    # mcp.run() and skip the proxy entirely. This function is therefore a
    # no-op placeholder; kept for future use.
    return JSONResponse({"error": "proxy disabled"}, status_code=500)


def main() -> None:
    """Run the MCP server with HTTP transport on the configured port.

    Strategy: the FastMCP object handles the MCP streamable-HTTP and SSE
    endpoints itself, while we run a parallel HTTP health server in a
    background task. Both share the same uvicorn event loop.
    """
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")

    # Mount the MCP server into a single uvicorn app along with /health and
    # /healthz routes. We use FastMCP's run() coroutine, wrapped in
    # uvicorn's Server programmatically so we can serve the MCP app and our
    # health routes together.
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse as StarletteJSONResponse

    async def health_route(request):  # noqa: ARG001
        return StarletteJSONResponse(
            {
                "status": "ok",
                "service": "cron-job-org-mcp",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def root_route(request):  # noqa: ARG001
        return StarletteJSONResponse(
            {
                "service": "cron-job-org-mcp",
                "status": "ok",
                "endpoints": {
                    "mcp": "/mcp",
                    "sse": "/sse",
                    "health": "/health",
                },
            }
        )

    # Build a Starlette app with health routes and a Mount that delegates
    # /mcp and /sse to FastMCP's streamable HTTP / SSE apps.
    # FastMCP 2.x exposes .streamable_http_app() and .sse_app(); fall back
    # gracefully if the installed mcp version doesn't have them.
    try:
        mcp_http_app = mcp.streamable_http_app()  # type: ignore[attr-defined]
    except AttributeError:
        mcp_http_app = None

    try:
        mcp_sse_app = mcp.sse_app()  # type: ignore[attr-defined]
    except AttributeError:
        mcp_sse_app = None

    routes = [
        Route("/", root_route),
        Route("/health", health_route),
        Route("/healthz", health_route),
    ]
    if mcp_http_app is not None:
        routes.append(Mount("/mcp", app=mcp_http_app))
    if mcp_sse_app is not None:
        routes.append(Mount("/sse", app=mcp_sse_app))

    app = Starlette(routes=routes)

    # If we don't have access to the MCP HTTP sub-apps, run MCP on a
    # separate internal port via mcp.run() and proxy from this app.
    if mcp_http_app is None and mcp_sse_app is None:
        # Last-resort fallback: start MCP via its built-in run() in a
        # background thread on an internal port. The public app then
        # returns 503 for /mcp and /sse — but at least /health works.
        import threading

        internal_port = port + 1
        os.environ["MCP_INTERNAL_PORT"] = str(internal_port)

        def _run_mcp():
            mcp.settings.port = internal_port  # type: ignore[attr-defined]
            mcp.settings.host = "127.0.0.1"  # type: ignore[attr-defined]
            asyncio.run(mcp.run_async(transport="streamable-http"))

        threading.Thread(target=_run_mcp, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
