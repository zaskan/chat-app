import unittest
import uuid

from fastapi import HTTPException

from app import schemas
from app.services.itsm_webhook import format_itsm_event_message, resolve_webhook_message


class ItsmWebhookTests(unittest.TestCase):
    def test_incident_created_message(self) -> None:
        payload = {
            "event": "incident.created",
            "incident": {
                "public_id": "INC-42",
                "title": "Apache down",
                "severity": "high",
            },
        }
        self.assertEqual(
            format_itsm_event_message(payload),
            "[incident.created] INC-42 — Apache down (high)",
        )

    def test_request_submitted_message(self) -> None:
        payload = {
            "event": "request.submitted",
            "request": {"public_id": "REQ-7", "name": "New VM"},
        }
        self.assertEqual(
            format_itsm_event_message(payload),
            "[request.submitted] REQ-7 — New VM",
        )

    def test_unknown_event_returns_none(self) -> None:
        self.assertIsNone(format_itsm_event_message({"event": "incident.closed"}))

    def test_body_format_requires_body(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            resolve_webhook_message("body", {"event": "incident.created"})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_body_format_accepts_plain_body(self) -> None:
        msg = resolve_webhook_message("body", {"body": "hello"})
        self.assertEqual(msg.body, "hello")

    def test_itsm_format_accepts_structured_event(self) -> None:
        msg = resolve_webhook_message(
            "itsm",
            {
                "event": "incident.created",
                "incident": {"public_id": "INC-1", "title": "Test"},
            },
        )
        self.assertEqual(msg.body, "[incident.created] INC-1 — Test (medium)")

    def test_itsm_format_prefers_explicit_body(self) -> None:
        msg = resolve_webhook_message(
            "itsm",
            {
                "body": "override",
                "event": "incident.created",
                "incident": {"public_id": "INC-1", "title": "Test"},
            },
        )
        self.assertEqual(msg.body, "override")

    def test_itsm_format_skips_unknown_event(self) -> None:
        self.assertIsNone(
            resolve_webhook_message("itsm", {"event": "incident.closed"})
        )

    def test_itsm_format_parent_id(self) -> None:
        parent = uuid.uuid4()
        msg = resolve_webhook_message("itsm", {"body": "reply", "parent_id": str(parent)})
        self.assertEqual(msg.parent_id, parent)


if __name__ == "__main__":
    unittest.main()
