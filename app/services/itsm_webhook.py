"""Map itsm-app outbound webhook payloads to chat message bodies."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status

from app import schemas

BODY_FORMAT = "body"
ITSM_FORMAT = "itsm"


def format_itsm_event_message(payload: dict[str, Any]) -> str | None:
    """Return a channel message body for a supported itsm-app event, or None."""
    event = payload.get("event")
    if event == "incident.created":
        incident = payload.get("incident") or {}
        public_id = incident.get("public_id") or "?"
        title = incident.get("title") or "Untitled"
        severity = incident.get("severity") or "medium"
        return f"[incident.created] {public_id} — {title} ({severity})"
    if event == "request.submitted":
        request = payload.get("request") or {}
        public_id = request.get("public_id") or "?"
        title = request.get("name") or request.get("title") or "Service request"
        return f"[request.submitted] {public_id} — {title}"
    return None


def _parse_parent_id(raw: dict[str, Any]) -> uuid.UUID | None:
    parent_id = raw.get("parent_id")
    if parent_id is None:
        return None
    try:
        return uuid.UUID(str(parent_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid parent_id",
        ) from exc


def resolve_webhook_message(
    payload_format: str,
    raw: dict[str, Any],
) -> schemas.MessageCreate | None:
    """
    Normalize inbound webhook JSON to MessageCreate.

    Returns None when an itsm-style payload is recognized but the event type is
    unsupported (no channel message should be created).
    """
    fmt = payload_format or BODY_FORMAT

    body_text = raw.get("body")
    if isinstance(body_text, str) and body_text.strip():
        return schemas.MessageCreate(
            body=body_text.strip(),
            parent_id=_parse_parent_id(raw),
        )

    if fmt == BODY_FORMAT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing or empty "body" field',
        )

    if raw.get("event") is not None:
        message = format_itsm_event_message(raw)
        if message is None:
            return None
        return schemas.MessageCreate(
            body=message,
            parent_id=_parse_parent_id(raw),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Expected "body" or itsm-app event payload (event, incident/request)',
    )
