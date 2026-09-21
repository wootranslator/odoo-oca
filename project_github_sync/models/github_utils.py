# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Helpers shared by both synchronization directions."""

import hashlib
import re

MAX_TITLE_LENGTH = 256
MAX_BODY_LENGTH = 60000

# Invisible marker appended to what Odoo writes on GitHub. It lets the webhook
# recognize its own echoes and link the objects Odoo created.
MARKER_RE = re.compile(r"[ \t]*<!-- odoo-sync:(task|message):(\d+) -->[ \t]*\n?")


def split_marker(body):
    """Return ``(body_without_marker, kind, record_id)``; kind/id may be None."""
    body = body or ""
    match = MARKER_RE.search(body)
    if not match:
        return body, None, None
    clean = body[: match.start()].rstrip() + body[match.end() :]
    return clean, match.group(1), int(match.group(2))


def add_marker(body, kind, record_id):
    marker = f"<!-- odoo-sync:{kind}:{record_id} -->"
    return f"{body}\n\n{marker}" if body else marker


def normalize_body(body):
    """GitHub may store CRLF line endings and trim whitespace."""
    return (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def truncate(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def content_hash(title, body, state_key):
    """Fingerprint of what is (or should be) on both sides of the sync."""
    parts = [(title or "").strip(), normalize_body(body), state_key]
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()
