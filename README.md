# cron-job-org-mcp

**MCP server for [cron-job.org](https://cron-job.org)** — manage HTTP cron jobs (create, list, update, delete, view history) directly from Claude Code, Claude Desktop, or any MCP-compatible client.

Stop clicking through cron-job.org dashboard. Just ask Claude:

> *"Add a cron job that pings `https://my-app.com/cron/refresh?token=X` every 2 minutes."*

> *"Show me execution history of the 'daily backup' job from last week."*

> *"Disable all jobs containing 'staging' in title — we're in maintenance."*

## Features

8 MCP tools wrapping the [cron-job.org REST API](https://docs.cron-job.org/rest-api.html):

| Tool | What it does |
|---|---|
| `list_jobs` | List all jobs on your account (optionally filter by title substring) |
| `get_job` | Full details of one job + last 5 executions |
| `create_job` | Create new job (URL, cron expression, method, body, headers, timezone) |
| `update_job` | Partial update (only changed fields sent) |
| `delete_job` | Permanently delete a job |
| `enable_job` / `disable_job` | Toggle active state |
| `get_history` | Recent execution history (success/fail, HTTP code, duration) |

Plus: **standard cron expressions** (`*/2 * * * *`, `0 8 * * 1`) are converted to cron-job.org's internal schedule dict format automatically. You can use the same cron syntax you know from crontab.

## Quick start

### 1. Install

```bash
git clone https://github.com/come2daddy13/cron-job-org-mcp
cd cron-job-org-mcp
pip install -e .
```

Or directly from git:

```bash
pip install git+https://github.com/come2daddy13/cron-job-org-mcp.git
```

### 2. Generate API key

Sign in to [cron-job.org](https://cron-job.org), then go to:

**Settings → API → Create API key** (https://console.cron-job.org/settings)

Copy the token (looks like `zaX78aqKJuIH4l4RX6njoqADn77MQNJJ`).

### 3. Configure Claude Code

Edit your Claude Code MCP config file (typically `~/.claude.json` or via Claude Code's settings UI). Add this entry:

```json
{
  "mcpServers": {
    "cron-job-org": {
      "command": "python3",
      "args": ["-m", "cron_job_org_mcp"],
      "env": {
        "CRON_JOB_ORG_API_KEY": "your-token-here",
        "CRON_JOB_ORG_DEFAULT_TIMEZONE": "Europe/Warsaw"
      }
    }
  }
}
```

See `claude_code_config_example.json` in this repo for a ready-to-paste snippet.

### 4. Restart Claude Code

After restart, the tools appear as `mcp__cron-job-org__list_jobs`, etc. Just ask Claude in plain language — it'll call the right tool.

## Usage examples

### Add a self-healing cron for your Railway/Vercel app

> *"Add a cron job 'process-queue' that GETs `https://hub.example.com/cron/process-queue?token=SECRET` every 2 minutes. Use Europe/Warsaw timezone."*

Claude → `create_job(url="https://hub.example.com/cron/process-queue?token=SECRET", title="process-queue", cron_expression="*/2 * * * *")`.

### Audit failures

> *"Show me last 10 executions of job ID 12345 — I want to see which failed and why."*

Claude → `get_history(job_id=12345, limit=10)`.

### Bulk maintenance

> *"List all jobs containing 'staging', then disable them — we're refactoring."*

Claude → `list_jobs(filter_title="staging")` → for each result: `disable_job(job_id=...)`.

### Migrate / clone

> *"Copy job 5523 but change the URL to point to the new domain and rename it."*

Claude → `get_job(5523)` → reads config → `create_job(url=new_url, title=new_title, cron_expression=...)`.

## Configuration

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CRON_JOB_ORG_API_KEY` | yes | — | API key from cron-job.org settings |
| `CRON_JOB_ORG_DEFAULT_TIMEZONE` | no | `Europe/Warsaw` | Default timezone for new jobs |
| `LOG_LEVEL` | no | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

You can put these in a `.env` file (loaded automatically), or pass them via the Claude Code config `env` block (recommended for `CRON_JOB_ORG_API_KEY`).

### Cron expression format

Standard 5-field cron: `minute hour day_of_month month day_of_week`.

Examples:

| Expression | Meaning |
|---|---|
| `*/2 * * * *` | Every 2 minutes |
| `0 8 * * 1` | Every Monday at 8:00 |
| `30 7 * * *` | Daily at 7:30 |
| `0 9-17 * * 1-5` | Every hour from 9 to 17, Mon–Fri |
| `0,15,30,45 * * * *` | Every 15 minutes |

Day-of-week: `0 = Sunday`, `1 = Monday`, ..., `6 = Saturday`.

## Rate limits (per cron-job.org)

- **Free tier**: 100 API requests/day
- **Sustaining member**: 5000/day
- Generic endpoints: max 5 req/sec
- Create job: max 1 req/sec, 5/min

The client automatically retries on `429 Too Many Requests` with backoff (`Retry-After` header respected).

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (no API key needed — uses httpx MockTransport)
pytest tests/ -v

# Lint
ruff check src/ tests/
```

### Manual smoke test (requires real API key)

```bash
# Set token in .env
cp .env.example .env
# Edit .env, add CRON_JOB_ORG_API_KEY=...

python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
from cron_job_org_mcp.api import CronJobOrgClient
c = CronJobOrgClient(os.getenv('CRON_JOB_ORG_API_KEY'))
print(c.list_jobs())
"
```

### Test MCP stdio handshake

```bash
echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python3 -m cron_job_org_mcp
```

You should see a JSON response with the server's `serverInfo` and supported tools.

## Why not [other MCP scheduler]?

There are several "MCP scheduler" servers (jolks/mcp-cron, PhialsBasement/scheduler-mcp, Q-Scheduler, etc.) — but they're all **local in-memory schedulers**: when you stop the MCP server, the jobs stop. They run on your machine.

This MCP integrates with **cron-job.org's hosted service**: jobs run 24/7 on their infrastructure, regardless of whether your Claude Code or MCP server is running. Free tier covers most personal/SaaS use cases.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

PRs welcome. Ideas:

- `bulk_create_jobs(specs)` — create multiple at once
- `clone_job(source_id, new_title, new_schedule)` — duplicate with overrides
- `search_jobs_by_url(pattern)` — filter by URL substring
- Async variant using `httpx.AsyncClient`
- Support for cron-job.org's notification settings (email on fail)

## Credits

Built by [Darek Jasion](https://github.com/come2daddy13) with Claude Opus 4.7. Inspired by the gap in the MCP ecosystem — every other "cron MCP" runs locally, none wraps the cron-job.org API.
