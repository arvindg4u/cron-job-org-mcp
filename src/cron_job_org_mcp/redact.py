"""Hide secrets in what the tools return, put them back when a caller sends *** in.

Job URLs often carry secrets (`?token=…`). Without masking, list_jobs/get_job
would print them into the MCP client's transcript and logs. Masking is for
display only: cron-job.org always gets the real values.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote_plus, urlsplit

MASK = "***"

_SECRET_PARTS = (
    "token", "secret", "passw", "pwd", "key", "auth", "signature", "hmac",
    "credential", "cookie", "session", "jwt",
)
_SECRET_NAMES = {"pass", "pw", "sig"}

# name=value in a query string, form body or free text
_PAIR = re.compile(r"([\w.%\[\]-]+)=([^&;#\s\"'<>]*)")
# "name": "value" or "name": 123 in a JSON body
_JSON_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"(\s*:\s*)("(?:[^"\\]|\\.)*"|-?\d[\d.eE+-]*)')
# scheme://user:password@
_USERINFO = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^/?#@:\s]*):([^/?#@\s]*)@")
# "Bearer …" and the like, whatever the header is called
_AUTH_VALUE = re.compile(r"(?i)(bearer|basic|digest|token)\s+\S")


def is_secret_name(name: str) -> bool:
    n = name.lower()
    return n in _SECRET_NAMES or any(part in n for part in _SECRET_PARTS)


def mask_secrets(text: str) -> str:
    """Replace secret values in a URL, form or JSON body with ***."""
    if not text:
        return text
    text = _USERINFO.sub(lambda m: f"{m[1]}:{MASK}@" if m[2] else m[0], text)
    text = _JSON_PAIR.sub(
        lambda m: f'"{m[1]}"{m[2]}"{MASK}"' if is_secret_name(m[1]) and m[3] != '""' else m[0],
        text,
    )
    return _PAIR.sub(
        lambda m: f"{m[1]}={MASK}" if m[2] and is_secret_name(unquote_plus(m[1])) else m[0],
        text,
    )


def has_mask(text: str) -> bool:
    """True if text carries a *** in a place mask_secrets puts one."""
    if not text:
        return False
    return (
        any(m[2] == MASK for m in _USERINFO.finditer(text))
        or any(m[3] == f'"{MASK}"' and is_secret_name(m[1]) for m in _JSON_PAIR.finditer(text))
        or any(m[2] == MASK and is_secret_name(unquote_plus(m[1])) for m in _PAIR.finditer(text))
    )


def mask_headers(headers: Any) -> Any:
    """Hide values of auth-like headers. cron-job.org sends [] for no headers: passed through."""
    if not isinstance(headers, dict):
        return headers
    return {
        name: MASK if value and (is_secret_name(name) or _AUTH_VALUE.match(str(value))) else value
        for name, value in headers.items()
    }


def headers_have_mask(headers: Any) -> bool:
    return isinstance(headers, dict) and MASK in headers.values()


def same_origin(url_a: str, url_b: str) -> bool:
    return _origin(url_a) == _origin(url_b)


def _origin(url: str) -> tuple:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, parts.hostname, parts.port or {"http": 80, "https": 443}.get(scheme)


def restore_url(new_url: str, current_url: str) -> str:
    """Put current_url's secrets back where new_url has ***.

    Only for the same scheme, host and port, so a hidden token is never sent
    to an address the job didn't call before. Repeated params match by position.
    """
    if not has_mask(new_url):
        return new_url
    if not same_origin(new_url, current_url):
        raise ValueError(
            "url has masked values (***), but its scheme, host or port differ from the job's "
            "current URL. Masked values are restored only for the same address: pass the full URL."
        )

    current_user = _USERINFO.search(current_url)

    def userinfo(m: re.Match) -> str:
        if m[2] != MASK:
            return m[0]
        if not current_user or current_user[1] != m[1] or not current_user[2]:
            raise ValueError("Can't restore the password in user:***@: pass the full URL.")
        return f"{m[1]}:{current_user[2]}@"

    real: dict[str, list[str]] = {}
    for m in _PAIR.finditer(current_url):
        real.setdefault(unquote_plus(m[1]), []).append(m[2])
    seen: dict[str, int] = {}

    def pair(m: re.Match) -> str:
        name = unquote_plus(m[1])
        i = seen.get(name, 0)
        seen[name] = i + 1
        if m[2] != MASK or not is_secret_name(name):
            return m[0]
        values = real.get(name, [])
        if i >= len(values) or values[i] in ("", MASK):
            raise ValueError(
                f"Can't restore {name}=***: the job's current URL has no such value. "
                "Pass the full URL."
            )
        return f"{m[1]}={values[i]}"

    return _PAIR.sub(pair, _USERINFO.sub(userinfo, new_url, count=1))


def restore_headers(new_headers: dict, current_headers: Any) -> dict:
    """Swap *** header values for the job's current ones (names match case-insensitively)."""
    current = (
        {k.lower(): v for k, v in current_headers.items()}
        if isinstance(current_headers, dict)
        else {}
    )
    restored = {}
    for name, value in new_headers.items():
        if value == MASK:
            value = current.get(name.lower())
            if not value or value == MASK:
                raise ValueError(
                    f"Can't restore header {name}: ***, the job has no such header. "
                    "Pass the real value."
                )
        restored[name] = value
    return restored
