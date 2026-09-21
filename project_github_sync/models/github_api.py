# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Minimal GitHub REST client used by the Odoo → GitHub synchronization."""

import logging
import time

import requests

_logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
REQUEST_TIMEOUT = 20
# Never wait more than this for a rate limit / Retry-After hint (seconds)
MAX_RETRY_AFTER = 6 * 3600


class GithubApiError(Exception):
    """Error talking to GitHub.

    ``retryable`` tells whether trying again later can succeed (network
    problems, 5xx, rate limits) or not (bad token, missing permissions,
    validation errors).
    """

    def __init__(self, message, status=None, retryable=False, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "odoo-project-github-sync",
    }


def _retry_after(response):
    """Seconds to wait according to the rate limit headers, or None."""
    headers = response.headers or {}
    try:
        if headers.get("Retry-After"):
            return min(int(headers["Retry-After"]), MAX_RETRY_AFTER)
        if headers.get("X-RateLimit-Remaining") == "0" and headers.get(
            "X-RateLimit-Reset"
        ):
            return min(
                max(int(headers["X-RateLimit-Reset"]) - int(time.time()), 0),
                MAX_RETRY_AFTER,
            )
    except ValueError:
        return None
    return None


def _error_message(response):
    try:
        data = response.json()
    except ValueError:
        data = {}
    message = data.get("message") if isinstance(data, dict) else None
    return message or (response.text or "")[:200] or "unknown error"


def github_request(token, method, path, payload=None):
    """Call the GitHub REST API and return the decoded JSON answer.

    ``path`` must start with ``/``. Raises GithubApiError on any failure.
    The token is never included in error messages or logs.
    """
    try:
        response = requests.request(
            method,
            GITHUB_API_URL + path,
            json=payload,
            headers=_headers(token),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise GithubApiError(
            f"Network error contacting GitHub: {exc.__class__.__name__}",
            retryable=True,
        ) from exc
    status = response.status_code
    if status < 300:
        try:
            return response.json()
        except ValueError:
            return {}
    message = f"GitHub answered {status}: {_error_message(response)}"
    retry_after = _retry_after(response)
    retryable = status >= 500 or status == 429 or (status == 403 and retry_after)
    _logger.warning("GitHub API %s %s failed: %s", method, path, message)
    raise GithubApiError(
        message, status=status, retryable=bool(retryable), retry_after=retry_after
    )
