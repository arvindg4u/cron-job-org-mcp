"""HTTPx wrapper na cron-job.org REST API.

Docs: https://docs.cron-job.org/rest-api.html
Base URL: https://api.cron-job.org

Auth: Bearer token (generate w https://console.cron-job.org/settings → API).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.cron-job.org"


class CronJobOrgError(Exception):
    """Generic API error."""


class CronJobOrgClient:
    """Sync client for cron-job.org REST API.

    Automatic retry on 429 (rate limit) with backoff.
    Rate limits (per docs):
      - 5 req/sec generic
      - 1 req/sec, 5/min for create (PUT /jobs)
      - 100 req/day (free tier); 5000 sustaining
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = API_BASE,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        if not api_key:
            raise ValueError("api_key is required (set CRON_JOB_ORG_API_KEY in env)")
        self.api_key = api_key
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "cron-job-org-mcp/0.1.0 (https://github.com/come2daddy13/cron-job-org-mcp)",
        }
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "CronJobOrgClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---------------------------------------------------------------------
    # Generic _request with retry/backoff
    # ---------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        max_retries: int = 3,
    ) -> Any:
        for attempt in range(1, max_retries + 1):
            try:
                resp = self._client.request(method, path, json=json_body)
            except httpx.RequestError as e:
                if attempt == max_retries:
                    raise CronJobOrgError(f"Network error: {e}") from e
                wait = 2**attempt
                log.warning("Request error %s, retry %d/%d za %ds", e, attempt, max_retries, wait)
                time.sleep(wait)
                continue

            # 429 Rate limited → backoff
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "2"))
                log.warning("Rate limited (429), retry za %ds (attempt %d/%d)", wait, attempt, max_retries)
                if attempt == max_retries:
                    raise CronJobOrgError(f"Rate limited after {max_retries} retries")
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                raise CronJobOrgError(
                    f"Forbidden (403): invalid token or IP not allowlisted. Body: {resp.text[:200]}"
                )
            if resp.status_code == 404:
                raise CronJobOrgError(f"Not found (404): {path}")
            if resp.status_code >= 400:
                raise CronJobOrgError(
                    f"HTTP {resp.status_code} on {method} {path}: {resp.text[:300]}"
                )

            # 204 No Content (delete)
            if resp.status_code == 204 or not resp.content:
                return None

            try:
                return resp.json()
            except Exception as e:
                raise CronJobOrgError(f"Invalid JSON response: {e}; body: {resp.text[:200]}") from e

        raise CronJobOrgError(f"Failed after {max_retries} retries")

    # ---------------------------------------------------------------------
    # Public API methods
    # ---------------------------------------------------------------------

    def list_jobs(self) -> list[dict]:
        """GET /jobs — list all jobs on account.

        Returns: list of job dicts with keys: jobId, enabled, title, url, lastStatus,
        lastDuration, lastExecution, schedule (dict).
        """
        data = self._request("GET", "/jobs")
        # API returns { "jobs": [...], "someExtraInfo": {...} }
        return data.get("jobs", []) if isinstance(data, dict) else []

    def get_job(self, job_id: int) -> dict:
        """GET /jobs/{id} — full job details."""
        data = self._request("GET", f"/jobs/{job_id}")
        # Returns { "jobDetails": {...} }
        return data.get("jobDetails", data) if isinstance(data, dict) else {}

    def create_job(self, job_payload: dict) -> dict:
        """PUT /jobs — create new job.

        Args:
            job_payload: dict with required keys:
              - url (str): URL to ping
              - title (str): job title
              - schedule (dict): cron-job.org schedule format
              - enabled (bool, optional, default True)
              - requestMethod (int, optional, 0=GET, 1=POST, ...)
              - extendedData (dict, optional, with headers/body)

        Returns: { "jobId": int } from response
        """
        body = {"job": job_payload}
        return self._request("PUT", "/jobs", json_body=body) or {}

    def update_job(self, job_id: int, partial: dict) -> None:
        """PATCH /jobs/{id} — partial update."""
        body = {"job": partial}
        self._request("PATCH", f"/jobs/{job_id}", json_body=body)

    def delete_job(self, job_id: int) -> None:
        """DELETE /jobs/{id}."""
        self._request("DELETE", f"/jobs/{job_id}")

    def get_history(self, job_id: int) -> list[dict]:
        """GET /jobs/{id}/history — execution history.

        Returns list of dicts with: jobLogId, jobId, identifier, date, datePlanned,
        jitter, url, duration, status, statusText, httpStatus.
        """
        data = self._request("GET", f"/jobs/{job_id}/history")
        return data.get("history", []) if isinstance(data, dict) else []

    def get_history_item(self, job_id: int, identifier: str) -> dict:
        """GET /jobs/{id}/history/{identifier} — single execution details (with response body)."""
        data = self._request("GET", f"/jobs/{job_id}/history/{identifier}")
        return data.get("jobHistoryDetails", data) if isinstance(data, dict) else {}
