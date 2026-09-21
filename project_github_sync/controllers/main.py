# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class GithubWebhookController(http.Controller):
    @http.route(
        "/project_github_sync/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def webhook(self):
        """Receive GitHub webhook deliveries.

        Payloads for repositories that are not linked to a project are
        acknowledged and ignored, so they never create anything in Odoo.
        Payloads for linked repositories must carry a valid HMAC signature.
        """
        httprequest = request.httprequest
        body = httprequest.get_data()
        try:
            payload = json.loads(body)
        except ValueError:
            return self._respond(400, {"status": "error", "reason": "invalid JSON"})
        if not isinstance(payload, dict):
            return self._respond(400, {"status": "error", "reason": "invalid payload"})

        env = request.env(user=SUPERUSER_ID)
        repository = payload.get("repository")
        full_name = (
            repository.get("full_name") if isinstance(repository, dict) else None
        )
        repo = env["project.github.repo"]._find_by_full_name(full_name)
        if not repo:
            return self._respond(200, {"status": "ignored", "reason": "not linked"})

        signature = httprequest.headers.get("X-Hub-Signature-256", "")
        if not repo._verify_signature(body, signature):
            _logger.warning("Invalid GitHub webhook signature for %s", repo.name)
            return self._respond(403, {"status": "error", "reason": "bad signature"})

        event = httprequest.headers.get("X-GitHub-Event", "")
        try:
            result = repo._process_webhook(event, payload)
        except ValidationError as exc:
            env.cr.rollback()
            return self._respond(400, {"status": "error", "reason": str(exc)})
        return self._respond(200, result)

    @staticmethod
    def _respond(status, data):
        return request.make_json_response(data, status=status)
