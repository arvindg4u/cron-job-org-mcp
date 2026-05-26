"""FastMCP server dla cron-job.org.

Uruchom: python -m cron_job_org_mcp
Wymaga: env var CRON_JOB_ORG_API_KEY

Tools (8):
  list_jobs, get_job, create_job, update_job, delete_job,
  enable_job, disable_job, get_history
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

from .api import CronJobOrgClient, CronJobOrgError
from .schedule import cron_to_dict, dict_to_cron

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DEFAULT_TIMEZONE = os.getenv("CRON_JOB_ORG_DEFAULT_TIMEZONE", "Europe/Warsaw")

mcp = FastMCP(
    name="cron-job-org",
    instructions=(
        "MCP server for cron-job.org. Manage HTTP cron jobs: create, list, update, "
        "delete, enable/disable, view history. Use standard 5-field cron expressions "
        "(e.g. '*/2 * * * *', '0 8 * * 1'). Default timezone: Europe/Warsaw."
    ),
)


def _get_client() -> CronJobOrgClient:
    """Lazy-init client (raises if no API key)."""
    key = os.getenv("CRON_JOB_ORG_API_KEY", "").strip()
    if not key:
        raise CronJobOrgError(
            "CRON_JOB_ORG_API_KEY not set in env. Generate at "
            "https://console.cron-job.org/settings → API → Create API key."
        )
    return CronJobOrgClient(api_key=key)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_jobs(filter_title: str = "") -> list[dict]:
    """List all cron jobs on the cron-job.org account.

    Args:
        filter_title: optional substring (case-insensitive) to filter by job title.

    Returns:
        List of jobs with: id, title, url, enabled, schedule (cron expr), last_status,
        last_execution, last_duration_ms.
    """
    with _get_client() as c:
        jobs = c.list_jobs()
    if filter_title:
        f = filter_title.lower()
        jobs = [j for j in jobs if f in (j.get("title", "") or "").lower()]
    return [
        {
            "id": j.get("jobId"),
            "title": j.get("title", ""),
            "url": j.get("url", ""),
            "enabled": j.get("enabled", False),
            "schedule": dict_to_cron(j.get("schedule") or {}),
            "last_status": j.get("lastStatus"),
            "last_execution": j.get("lastExecution"),
            "last_duration_ms": j.get("lastDuration"),
        }
        for j in jobs
    ]


@mcp.tool()
def get_job(job_id: int) -> dict:
    """Get full details of a specific cron job, including last execution history.

    Args:
        job_id: numeric ID of the job (from list_jobs).

    Returns:
        Job details: id, title, url, enabled, schedule (cron expr + raw), method,
        timezone, headers, body, last_status, last_execution, last_duration_ms.
        Plus last 5 history items.
    """
    with _get_client() as c:
        details = c.get_job(job_id)
        try:
            history = c.get_history(job_id)[:5]
        except Exception as e:
            log.warning("Could not fetch history for %d: %s", job_id, e)
            history = []

    schedule_dict = details.get("schedule") or {}
    extended = details.get("extendedData") or {}
    return {
        "id": details.get("jobId"),
        "title": details.get("title", ""),
        "url": details.get("url", ""),
        "enabled": details.get("enabled", False),
        "schedule_cron": dict_to_cron(schedule_dict),
        "schedule_raw": schedule_dict,
        "timezone": schedule_dict.get("timezone"),
        "request_method": details.get("requestMethod", 0),
        "headers": extended.get("headers", {}),
        "body": extended.get("body", ""),
        "last_status": details.get("lastStatus"),
        "last_execution": details.get("lastExecution"),
        "last_duration_ms": details.get("lastDuration"),
        "history_recent": history,
    }


@mcp.tool()
def create_job(
    url: str,
    title: str,
    cron_expression: str,
    enabled: bool = True,
    method: str = "GET",
    body: str = "",
    headers: Optional[dict] = None,
    timezone: str = "",
) -> dict:
    """Create a new cron job.

    Args:
        url: full URL to ping (must include https://).
        title: human-readable name for the job.
        cron_expression: standard 5-field cron (e.g. '*/2 * * * *' for every 2 min,
            '0 8 * * 1' for Monday 8:00, '30 7 * * *' for daily 7:30).
        enabled: start active? Default True.
        method: HTTP method — GET, POST, PUT, DELETE, etc. Default GET.
        body: request body (only for POST/PUT/PATCH).
        headers: dict of extra HTTP headers (e.g. {"X-Custom-Token": "..."}).
        timezone: IANA tz (e.g. 'Europe/Warsaw'). Default: env CRON_JOB_ORG_DEFAULT_TIMEZONE or 'Europe/Warsaw'.

    Returns:
        Created job: id, title, url, schedule, enabled.
    """
    tz = timezone or DEFAULT_TIMEZONE
    schedule = cron_to_dict(cron_expression, timezone=tz)

    method_map = {"GET": 0, "POST": 1, "OPTIONS": 2, "HEAD": 3, "PUT": 4, "DELETE": 5, "TRACE": 6, "CONNECT": 7, "PATCH": 8}
    request_method = method_map.get(method.upper(), 0)

    extended: dict[str, Any] = {}
    if headers:
        extended["headers"] = headers
    if body:
        extended["body"] = body

    payload: dict[str, Any] = {
        "url": url,
        "title": title,
        "enabled": enabled,
        "saveResponses": True,
        "schedule": schedule,
        "requestMethod": request_method,
    }
    if extended:
        payload["extendedData"] = extended

    with _get_client() as c:
        resp = c.create_job(payload)

    new_id = resp.get("jobId") if isinstance(resp, dict) else None
    return {
        "id": new_id,
        "title": title,
        "url": url,
        "schedule": cron_expression,
        "enabled": enabled,
        "timezone": tz,
    }


@mcp.tool()
def update_job(
    job_id: int,
    url: str = "",
    title: str = "",
    cron_expression: str = "",
    enabled: Optional[bool] = None,
    method: str = "",
    body: Optional[str] = None,
    headers: Optional[dict] = None,
    timezone: str = "",
) -> dict:
    """Partial update of an existing cron job. Only non-empty/non-None fields are applied.

    Args:
        job_id: ID of the job to update.
        url: new URL (empty string = no change).
        title: new title.
        cron_expression: new cron expression (will be converted to schedule dict).
        enabled: True/False to enable/disable. None = no change.
        method: new HTTP method.
        body: new request body. None = no change, "" = clear.
        headers: new headers dict. None = no change.
        timezone: new timezone (if cron_expression provided, defaults to existing or 'Europe/Warsaw').

    Returns: { id, updated_fields: [...] }
    """
    partial: dict[str, Any] = {}
    updated_fields: list[str] = []

    if url:
        partial["url"] = url
        updated_fields.append("url")
    if title:
        partial["title"] = title
        updated_fields.append("title")
    if enabled is not None:
        partial["enabled"] = enabled
        updated_fields.append("enabled")
    if method:
        method_map = {"GET": 0, "POST": 1, "OPTIONS": 2, "HEAD": 3, "PUT": 4, "DELETE": 5, "TRACE": 6, "CONNECT": 7, "PATCH": 8}
        partial["requestMethod"] = method_map.get(method.upper(), 0)
        updated_fields.append("method")
    if cron_expression:
        tz = timezone or DEFAULT_TIMEZONE
        partial["schedule"] = cron_to_dict(cron_expression, timezone=tz)
        updated_fields.append("schedule")

    extended: dict[str, Any] = {}
    if body is not None:
        extended["body"] = body
        updated_fields.append("body")
    if headers is not None:
        extended["headers"] = headers
        updated_fields.append("headers")
    if extended:
        partial["extendedData"] = extended

    if not partial:
        return {"id": job_id, "updated_fields": [], "message": "no fields to update"}

    with _get_client() as c:
        c.update_job(job_id, partial)

    return {"id": job_id, "updated_fields": updated_fields, "ok": True}


@mcp.tool()
def delete_job(job_id: int) -> dict:
    """Delete a cron job permanently.

    Args:
        job_id: ID of the job to delete.

    Returns: { id, deleted: True }
    """
    with _get_client() as c:
        c.delete_job(job_id)
    return {"id": job_id, "deleted": True}


@mcp.tool()
def enable_job(job_id: int) -> dict:
    """Enable (activate) a cron job. Shortcut for update_job(enabled=True)."""
    with _get_client() as c:
        c.update_job(job_id, {"enabled": True})
    return {"id": job_id, "enabled": True}


@mcp.tool()
def disable_job(job_id: int) -> dict:
    """Disable (pause) a cron job — keeps config but stops executions."""
    with _get_client() as c:
        c.update_job(job_id, {"enabled": False})
    return {"id": job_id, "enabled": False}


@mcp.tool()
def get_history(job_id: int, limit: int = 10) -> list[dict]:
    """Get recent execution history for a job.

    Args:
        job_id: ID of the job.
        limit: max number of recent items (default 10).

    Returns:
        List of executions: {identifier, date, http_status, duration_ms, status_text, ok}
        Sorted newest first.
    """
    with _get_client() as c:
        history = c.get_history(job_id)
    items = history[:limit] if limit > 0 else history
    return [
        {
            "identifier": h.get("identifier"),
            "date": h.get("date"),
            "http_status": h.get("httpStatus"),
            "duration_ms": h.get("duration"),
            "status_text": h.get("statusText", ""),
            "ok": h.get("httpStatus", 0) == 200 and h.get("status", 0) == 1,
        }
        for h in items
    ]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Run MCP server via stdio (default for Claude Code / Claude Desktop)."""
    mcp.run()


if __name__ == "__main__":
    main()
