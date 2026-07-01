"""
HTTP/SSE transport wrapper for the cron-job.org MCP server.

This module runs the FastMCP server over HTTP with SSE transport, so it can be
deployed on a Render Web Service and connected to by remote MCP clients
(e.g. Kai 9000) over the network instead of local stdio.
"""
from __future__ import annotations

import os

from .server import mcp


def main() -> None:
    """Run the MCP server with HTTP/SSE transport on the configured port."""
    # Render injects PORT; default to 8000 for local debugging.
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")

    # FastMCP 2.x supports the streamable HTTP transport, which is the modern
    # MCP-over-HTTP standard. Falls back to SSE if streamable-http is not
    # available in the installed mcp version.
    try:
        mcp.run(transport="streamable-http", host=host, port=port)
    except ValueError:
        mcp.run(transport="sse", host=host, port=port)


if __name__ == "__main__":
    main()
