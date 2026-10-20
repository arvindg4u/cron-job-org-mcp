"""MCP tools against a fake cron-job.org API (httpx MockTransport, no real calls)."""

import json

import httpx
import pytest

from cron_job_org_mcp import server
from cron_job_org_mcp.api import CronJobOrgClient

JOB_ID = 8683148
SECRET = "R3AL-cr0n-t0ken"
HUB_URL = f"https://hub.example.com/cron/leads-watch?token={SECRET}&hours=24"
HUB_URL_MASKED = "https://hub.example.com/cron/leads-watch?token=***&hours=24"


def job_details(**overrides):
    """jobDetails as GET /jobs/{id} returns it."""
    job = {
        "jobId": JOB_ID,
        "enabled": True,
        "title": "Hub Leads Watch",
        "saveResponses": True,
        "url": HUB_URL,
        "lastStatus": 1,
        "lastDuration": 412,
        "lastExecution": 1792494420,
        "nextExecution": 1792498020,
        "type": 0,
        "requestTimeout": 30,
        "redirectSuccess": False,
        "folderId": 0,
        "schedule": {
            "timezone": "Europe/Warsaw",
            "expiresAt": 0,
            "hours": [-1],
            "mdays": [-1],
            "minutes": [7],
            "months": [-1],
            "wdays": [-1],
        },
        "requestMethod": 0,
        "auth": {"enable": False, "user": "", "password": ""},
        "notification": {"onFailure": False, "onSuccess": False, "onDisable": True},
        "extendedData": {"headers": [], "body": ""},
    }
    job.update(overrides)
    return job


def history_item(**overrides):
    """One entry of GET /jobs/{id}/history."""
    item = {
        "jobLogId": 7781234567,
        "jobId": JOB_ID,
        "identifier": "8683148-1-2-7781234567",
        "date": 1792494420,
        "datePlanned": 1792494420,
        "jitter": 312,
        "url": HUB_URL,
        "duration": 412,
        "status": 1,
        "statusText": "OK",
        "httpStatus": 202,
        "headers": None,
        "body": None,
        "stats": {
            "nameLookup": 1200,
            "connect": 15000,
            "appConnect": 40000,
            "preTransfer": 40100,
            "startTransfer": 411000,
            "total": 412000,
        },
    }
    item.update(overrides)
    return item


class FakeApi:
    def __init__(self):
        self.job = job_details()
        self.history = [history_item()]
        self.sent = []  # (method, path, body) of every write

    def handler(self, req):
        path = req.url.path
        if req.method == "GET" and path == "/jobs":
            listed = {
                k: v
                for k, v in self.job.items()
                if k not in ("auth", "notification", "extendedData")
            }
            return httpx.Response(200, json={"jobs": [listed], "someFailed": False})
        if req.method == "GET" and path == f"/jobs/{JOB_ID}":
            return httpx.Response(200, json={"jobDetails": self.job})
        if req.method == "GET" and path == f"/jobs/{JOB_ID}/history":
            return httpx.Response(200, json={"history": self.history, "predictions": []})
        if req.method == "PATCH" and path == f"/jobs/{JOB_ID}":
            self.sent.append((req.method, path, json.loads(req.content)))
            return httpx.Response(200, json={})
        if req.method == "PUT" and path == "/jobs":
            self.sent.append((req.method, path, json.loads(req.content)))
            return httpx.Response(200, json={"jobId": 99})
        return httpx.Response(404, json={})


@pytest.fixture(autouse=True)
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(
        server,
        "_get_client",
        lambda: CronJobOrgClient("test-key", transport=httpx.MockTransport(fake.handler)),
    )
    return fake


def secret_headers():
    return {"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"}


# --- list_jobs / get_job: no secrets out -------------------------------------


def test_list_jobs_masks_token_in_url():
    assert server.list_jobs()[0]["url"] == HUB_URL_MASKED


def test_get_job_returns_no_secret_anywhere(api):
    api.job = job_details(
        extendedData={"headers": secret_headers(), "body": f'{{"password": "{SECRET}"}}'}
    )
    assert SECRET not in json.dumps(server.get_job(JOB_ID))


def test_get_job_shows_masked_url_and_headers(api):
    api.job = job_details(extendedData={"headers": secret_headers(), "body": ""})
    result = server.get_job(JOB_ID)
    assert result["url"] == HUB_URL_MASKED
    assert result["headers"] == {"Authorization": "***", "Content-Type": "application/json"}


def test_get_job_summarizes_recent_history():
    assert server.get_job(JOB_ID)["history_recent"] == [
        {
            "identifier": "8683148-1-2-7781234567",
            "date": 1792494420,
            "http_status": 202,
            "duration_ms": 412,
            "status_text": "OK",
            "ok": True,
        }
    ]


# --- get_history: ok follows cron-job.org's verdict --------------------------


@pytest.mark.parametrize(
    "http_status, status, ok",
    [
        (202, 1, True),  # hub endpoints answer 202 Accepted
        (200, 1, True),
        (301, 1, True),  # redirectSuccess on → cron-job.org counts it as OK
        (200, 6, False),  # too much response data → failed for cron-job.org
        (500, 4, False),
    ],
)
def test_get_history_ok_follows_cron_job_org_status(api, http_status, status, ok):
    api.history = [history_item(httpStatus=http_status, status=status)]
    assert server.get_history(JOB_ID)[0]["ok"] is ok


# --- update_job: masked values never overwrite real ones ---------------------


def test_update_job_restores_masked_token(api):
    server.update_job(JOB_ID, url="https://hub.example.com/cron/leads-watch?token=***&hours=48")
    assert api.sent == [
        (
            "PATCH",
            f"/jobs/{JOB_ID}",
            {"job": {"url": f"https://hub.example.com/cron/leads-watch?token={SECRET}&hours=48"}},
        )
    ]


def test_update_job_sends_full_url_as_given(api):
    new_url = "https://hub.example.com/cron/leads-watch?token=N3W-t0ken&hours=24"
    server.update_job(JOB_ID, url=new_url)
    assert api.sent == [("PATCH", f"/jobs/{JOB_ID}", {"job": {"url": new_url}})]


def test_update_job_refuses_masked_token_for_other_host(api):
    with pytest.raises(ValueError):
        server.update_job(JOB_ID, url="https://evil.example.net/steal?token=***")
    assert api.sent == []


def test_update_job_restores_masked_header(api):
    api.job = job_details(extendedData={"headers": secret_headers(), "body": ""})
    server.update_job(JOB_ID, headers={"Authorization": "***", "Content-Type": "text/plain"})
    assert api.sent == [
        (
            "PATCH",
            f"/jobs/{JOB_ID}",
            {
                "job": {
                    "extendedData": {
                        "headers": {"Authorization": f"Bearer {SECRET}", "Content-Type": "text/plain"}
                    }
                }
            },
        )
    ]


def test_update_job_refuses_masked_header_for_other_host(api):
    api.job = job_details(extendedData={"headers": secret_headers(), "body": ""})
    with pytest.raises(ValueError):
        server.update_job(JOB_ID, url="https://evil.example.net/x", headers={"Authorization": "***"})
    assert api.sent == []


def test_update_job_refuses_masked_body(api):
    with pytest.raises(ValueError):
        server.update_job(JOB_ID, body='{"password": "***"}')
    assert api.sent == []


# --- create_job: real values in, masked out ----------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"url": "https://hub.example.com/cron/refresh?token=***"},
        {"url": "https://hub.example.com/cron/refresh", "headers": {"Authorization": "***"}},
        {"url": "https://hub.example.com/cron/refresh", "body": "token=***"},
    ],
)
def test_create_job_refuses_masked_values(api, kwargs):
    with pytest.raises(ValueError):
        server.create_job(title="Kopia", cron_expression="0 7 * * *", **kwargs)
    assert api.sent == []


def test_create_job_sends_real_url(api):
    server.create_job(url=HUB_URL, title="Hub Leads Watch 2", cron_expression="7 * * * *")
    assert api.sent[0][2]["job"]["url"] == HUB_URL


def test_create_job_returns_masked_url():
    result = server.create_job(url=HUB_URL, title="Hub Leads Watch 2", cron_expression="7 * * * *")
    assert result["url"] == HUB_URL_MASKED
