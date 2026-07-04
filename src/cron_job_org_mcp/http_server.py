"""
HTTP transport wrapper for the cron-job.org MCP server.

This module runs the FastMCP server over HTTP with streamable-HTTP transport,
deployable on a Render Web Service and connectable by remote MCP clients
(e.g. Claude Code, Claude Desktop) over the network instead of local stdio.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

from .server import mcp


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")

    # Build the FastMCP streamable-HTTP app (routes at /mcp, /messages/).
    mcp_app = mcp.http_app(transport="streamable-http")

    # Health / info routes live on the parent app.
    async def health_route(request):  # noqa: ARG001
        return JSONResponse(
            {
                "status": "ok",
                "service": "cron-job-org-mcp",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def root_route(request):  # noqa: ARG001
        return JSONResponse(
            {
                "service": "cron-job-org-mcp",
                "status": "ok",
                "endpoints": {
                    "mcp": "/mcp",
                    "health": "/health",
                },
            }
        )

    # The MCP app's lifespan manages the streamable-HTTP session manager.
    # Delegate to it from the parent so mounted routes work correctly.
    mcp_lifespan = mcp_app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: Starlette) -> AsyncGenerator[None, None]:
        async with mcp_lifespan(app):
            yield

    app = Starlette(
        routes=[
            Route("/", root_route),
            Route("/health", health_route),
            Route("/healthz", health_route),
            Mount("/", app=mcp_app),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["*"],
            ),
        ],
        lifespan=combined_lifespan,
    )

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
