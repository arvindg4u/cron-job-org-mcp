"""
HTTP transport wrapper for the cron-job.org MCP server.

This module runs the FastMCP server over HTTP with streamable-HTTP transport
(plus SSE for older clients), so it can be deployed on a Render Web Service
and connected to by remote MCP clients (e.g. Kai 9000) over the network
instead of local stdio.

It also exposes a small ``/health`` endpoint suitable for keep-alive pings.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from .server import mcp


def _build_health_app() -> FastAPI:
    """Create a small FastAPI app that hosts the MCP server and a /health route."""
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

    # Mount the MCP streamable-HTTP app under /mcp and SSE under /sse.
    health_app.mount("/mcp", mcp.streamable_http_app())
    health_app.mount("/sse", mcp.sse_app())

    return health_app


def main() -> None:
    """Run the MCP server with HTTP transport on the configured port."""
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")

    import uvicorn

    app = _build_health_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
