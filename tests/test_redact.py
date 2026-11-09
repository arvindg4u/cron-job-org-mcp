"""Masking secrets in what the tools return, and putting them back on update."""

import pytest

from cron_job_org_mcp.redact import (
    has_mask,
    mask_headers,
    mask_secrets,
    restore_headers,
    restore_url,
)


@pytest.mark.parametrize(
    "raw, masked",
    [
        (
            "https://hub.example.com/cron/refresh?token=s3cr3t",
            "https://hub.example.com/cron/refresh?token=***",
        ),
        (
            "https://h.example.com/x?hours=24&token=abc&open=1",
            "https://h.example.com/x?hours=24&token=***&open=1",
        ),
        ("https://h.example.com/x?TOKEN=abc", "https://h.example.com/x?TOKEN=***"),
        ("https://h.example.com/x?access%5Ftoken=abc", "https://h.example.com/x?access%5Ftoken=***"),
        ("https://h.example.com/x?token=a&token=b", "https://h.example.com/x?token=***&token=***"),
        ("https://h.example.com/x?a=1;token=b", "https://h.example.com/x?a=1;token=***"),
        ("https://h.example.com/x?token=abc#top", "https://h.example.com/x?token=***#top"),
        ("https://user:pa55@h.example.com/x", "https://user:***@h.example.com/x"),
        ("https://h.example.com/x?token=", "https://h.example.com/x?token="),
        ("https://h.example.com/x?id=5&page=2&hours=24", "https://h.example.com/x?id=5&page=2&hours=24"),
        ("https://h.example.com/x", "https://h.example.com/x"),
    ],
)
def test_mask_secrets_in_url(raw, masked):
    assert mask_secrets(raw) == masked


@pytest.mark.parametrize(
    "name",
    [
        "token", "access_token", "api_key", "apikey", "key", "secret", "client_secret",
        "password", "passwd", "pass", "pwd", "auth", "sig", "signature", "hmac", "session", "jwt",
    ],
)
def test_mask_secrets_covers_common_secret_names(name):
    assert mask_secrets(f"https://h.example.com/x?{name}=v4lue") == f"https://h.example.com/x?{name}=***"


@pytest.mark.parametrize(
    "raw, masked",
    [
        ('{"password": "p4ss", "user": "darek"}', '{"password": "***", "user": "darek"}'),
        ('{"api_key": 12345}', '{"api_key": "***"}'),
        ('{"use_auth": true}', '{"use_auth": true}'),
        ("a=1&token=xyz", "a=1&token=***"),
        (
            '{"callback": "https://h.example.com/x?token=abc"}',
            '{"callback": "https://h.example.com/x?token=***"}',
        ),
        ("hello world", "hello world"),
        ("", ""),
    ],
)
def test_mask_secrets_in_body(raw, masked):
    assert mask_secrets(raw) == masked


def test_mask_headers_hides_secret_values_and_keeps_the_rest():
    headers = {
        "Authorization": "Bearer abc",
        "X-Api-Key": "k3y",
        "Cookie": "sid=1",
        "X-Upstream": "Bearer xyz",
        "Content-Type": "application/json",
    }
    assert mask_headers(headers) == {
        "Authorization": "***",
        "X-Api-Key": "***",
        "Cookie": "***",
        "X-Upstream": "***",
        "Content-Type": "application/json",
    }


def test_mask_headers_passes_empty_list_through():
    # cron-job.org returns "headers": [] for a job without headers
    assert mask_headers([]) == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("https://h.example.com/x?token=***&hours=24", True),
        ("https://user:***@h.example.com/x", True),
        ('{"password": "***"}', True),
        ("https://h.example.com/x?token=abc", False),
        ("https://h.example.com/x?q=***", False),
        ("", False),
    ],
)
def test_has_mask(text, expected):
    assert has_mask(text) is expected


def test_restore_url_puts_back_current_secret():
    assert (
        restore_url(
            "https://hub.example.com/cron/leads-watch?token=***&hours=48",
            "https://hub.example.com/cron/leads-watch?token=R3AL&hours=24",
        )
        == "https://hub.example.com/cron/leads-watch?token=R3AL&hours=48"
    )


def test_restore_url_matches_repeated_params_by_position():
    assert (
        restore_url("https://h.example.com/x?token=NEW&token=***", "https://h.example.com/x?token=A&token=B")
        == "https://h.example.com/x?token=NEW&token=B"
    )


def test_restore_url_restores_userinfo_password():
    assert (
        restore_url("https://u:***@h.example.com/x", "https://u:pw@h.example.com/x")
        == "https://u:pw@h.example.com/x"
    )


def test_restore_url_keeps_url_without_masks():
    assert (
        restore_url("https://other.example.net/x?token=N3W", "https://h.example.com/x?token=OLD")
        == "https://other.example.net/x?token=N3W"
    )


@pytest.mark.parametrize(
    "new_url",
    [
        "https://evil.example.net/cron/refresh?token=***",
        "http://hub.example.com/cron/refresh?token=***",
        "https://hub.example.com:8443/cron/refresh?token=***",
    ],
)
def test_restore_url_refuses_other_scheme_host_or_port(new_url):
    with pytest.raises(ValueError):
        restore_url(new_url, "https://hub.example.com/cron/refresh?token=R3AL")


def test_restore_url_refuses_param_missing_from_current_url():
    with pytest.raises(ValueError):
        restore_url("https://h.example.com/x?key=***", "https://h.example.com/x?token=R3AL")


def test_restore_url_refuses_password_of_other_user():
    with pytest.raises(ValueError):
        restore_url("https://admin:***@h.example.com/x", "https://u:pw@h.example.com/x")


def test_restore_headers_puts_back_masked_values_only():
    assert restore_headers(
        {"Authorization": "***", "Content-Type": "text/plain"},
        {"authorization": "Bearer R3AL", "Content-Type": "application/json"},
    ) == {"Authorization": "Bearer R3AL", "Content-Type": "text/plain"}


def test_restore_headers_refuses_header_missing_from_job():
    with pytest.raises(ValueError):
        restore_headers({"X-Api-Key": "***"}, [])
