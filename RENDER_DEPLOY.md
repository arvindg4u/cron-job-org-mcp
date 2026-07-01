# Render deployment (cron-job-org-mcp)

This is a fork of [come2daddy13/cron-job-org-mcp](https://github.com/come2daddy13/cron-job-org-mcp) that adds HTTP transport support so the server can be deployed on a Render Web Service and connected to by remote MCP clients (e.g. **Kai 9000**).

The original server only runs over **stdio** (for Claude Desktop / local clients). This fork adds an `http_server` entrypoint that runs the same FastMCP server over **streamable HTTP / SSE** on the port Render assigns.

## One-click deploy on Render

1. Create a **cron-job.org API key** at <https://cron-job.org/en/members/>, if you do not have one yet.
2. Click the button below and follow the Render prompts:
   - `CRON_JOB_ORG_API_KEY` will be asked for during setup.
   - Render will build, deploy, and give you a public URL like `https://cron-job-mcp.onrender.com`.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/arvindg4u/cron-job-org-mcp)

## Manual setup

1. Create a new **Web Service** on Render pointing at this repo.
2. Runtime: `Python`
3. Build command: `pip install -e .`
4. Start command: `python -m cron_job_org_mcp.http_server`
5. Add an environment variable `CRON_JOB_ORG_API_KEY` with your cron-job.org API key.
6. Wait for the deploy. Your MCP endpoint will be the service URL itself (e.g. `https://cron-job-mcp.onrender.com/mcp`).

## Local run (HTTP mode)

```bash
export CRON_JOB_ORG_API_KEY=...
pip install -e .
PORT=8000 python -m cron_job_org_mcp.http_server
```

Then point an MCP client at `http://localhost:8000/mcp`.

## Local run (stdio mode, original behaviour)

```bash
export CRON_JOB_ORG_API_KEY=...
uvx --from . cron-job-org-mcp
```

## Connecting from Kai 9000

In Kai 9000, go to **Settings → Tools → Add MCP Server** and add:

| Field | Value |
|---|---|
| Name | `cron-job.org` |
| URL | `https://<your-render-service>.onrender.com/mcp` |
| Header (optional) | `Authorization: Bearer <any-token>` (only if you wrap the server with one) |

The server is unauthenticated by default — protect it with a secret header or by putting it behind a proxy if you need to.
