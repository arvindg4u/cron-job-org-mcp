"""Test CronJobOrgClient via httpx MockTransport (no real API calls)."""

import json

import httpx
import pytest

from cron_job_org_mcp.api import CronJobOrgClient, CronJobOrgError


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_init_requires_api_key():
    with pytest.raises(ValueError):
        CronJobOrgClient(api_key="")


def test_list_jobs_returns_jobs_array():
    def handler(req):
        assert req.method == "GET"
        assert req.url.path == "/jobs"
        assert req.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={"jobs": [{"jobId": 1, "title": "test", "enabled": True}]},
        )

    c = CronJobOrgClient("test-token", transport=_mock_transport(handler))
    jobs = c.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["jobId"] == 1


def test_get_job_unwraps_jobDetails():
    def handler(req):
        assert req.url.path == "/jobs/42"
        return httpx.Response(200, json={"jobDetails": {"jobId": 42, "title": "hello"}})

    c = CronJobOrgClient("t", transport=_mock_transport(handler))
    j = c.get_job(42)
    assert j["jobId"] == 42
    assert j["title"] == "hello"


def test_create_job_wraps_in_job_key():
    captured = {}

    def handler(req):
        assert req.method == "PUT"
        assert req.url.path == "/jobs"
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"jobId": 99})

    c = CronJobOrgClient("t", transport=_mock_transport(handler))
    result = c.create_job({"url": "https://x", "title": "T"})
    assert result["jobId"] == 99
    assert captured["body"] == {"job": {"url": "https://x", "title": "T"}}


def test_delete_job_no_content():
    def handler(req):
        assert req.method == "DELETE"
        assert req.url.path == "/jobs/7"
        return httpx.Response(204)

    c = CronJobOrgClient("t", transport=_mock_transport(handler))
    assert c.delete_job(7) is None


def test_403_raises_forbidden_error():
    def handler(req):
        return httpx.Response(403, text="invalid token")

    c = CronJobOrgClient("bad", transport=_mock_transport(handler))
    with pytest.raises(CronJobOrgError, match="Forbidden"):
        c.list_jobs()


def test_404_raises_not_found():
    def handler(req):
        return httpx.Response(404, json={"error": "not found"})

    c = CronJobOrgClient("t", transport=_mock_transport(handler))
    with pytest.raises(CronJobOrgError, match="Not found"):
        c.get_job(999999)


def test_get_history_returns_array():
    def handler(req):
        assert req.url.path == "/jobs/5/history"
        return httpx.Response(
            200,
            json={"history": [{"identifier": "abc", "httpStatus": 200, "duration": 250}]},
        )

    c = CronJobOrgClient("t", transport=_mock_transport(handler))
    h = c.get_history(5)
    assert len(h) == 1
    assert h[0]["httpStatus"] == 200


def test_update_job_patches_with_wrapper():
    captured = {}

    def handler(req):
        assert req.method == "PATCH"
        assert req.url.path == "/jobs/12"
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200)

    c = CronJobOrgClient("t", transport=_mock_transport(handler))
    c.update_job(12, {"enabled": False})
    assert captured["body"] == {"job": {"enabled": False}}
