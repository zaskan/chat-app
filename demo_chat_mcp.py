#!/usr/bin/env python3
"""
MCP server (stdio) that controls the Demo Chat app via its REST API.

Cursor reads `.cursor/mcp.json` and runs this process. Configure:
  DEMO_CHAT_BASE_URL  — e.g. http://127.0.0.1:8000 (default)
  DEMO_CHAT_TOKEN     — JWT from POST /api/v1/auth/login (required for most tools)

Optional for inbound-webhook style calls:
  DEMO_CHAT_WEBHOOK_USER / DEMO_CHAT_WEBHOOK_PASSWORD — HTTP Basic instead of Bearer

Log only to stderr; stdout is reserved for the MCP protocol.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "demo-chat",
    instructions=(
        "Tools call the Demo Chat REST API at DEMO_CHAT_BASE_URL (default "
        "http://127.0.0.1:8000). Set DEMO_CHAT_TOKEN to a JWT unless using "
        "webhook basic-auth env vars."
    ),
)


def _base() -> str:
    return os.environ.get("DEMO_CHAT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _token() -> str:
    return os.environ.get("DEMO_CHAT_TOKEN", "").strip()


def _request(
    method: str,
    api_path: str,
    *,
    json_body: dict | None = None,
    use_bearer: bool = True,
) -> str:
    """api_path starts with / e.g. /channels"""
    url = f"{_base()}/api/v1{api_path}"
    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    if use_bearer:
        tok = _token()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
    else:
        user = os.environ.get("DEMO_CHAT_WEBHOOK_USER", "")
        password = os.environ.get("DEMO_CHAT_WEBHOOK_PASSWORD", "")
        if user or password:
            import base64

            creds = base64.b64encode(f"{user}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return raw if raw.strip() else '{"ok":true}'
    except urllib.error.HTTPError as e:
        body = e.read().decode() or e.reason
        return json.dumps({"error": True, "status": e.code, "detail": body})
    except urllib.error.URLError as e:
        return json.dumps({"error": True, "detail": str(e.reason)})


def _seg(ref: str) -> str:
    return quote(ref.strip(), safe="")


@mcp.tool()
def demo_chat_health() -> str:
    """Check Demo Chat liveness (GET /healthz). No auth."""
    url = f"{_base()}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.read().decode() or "ok"
    except urllib.error.URLError as e:
        return json.dumps({"error": True, "detail": str(e.reason)})


@mcp.tool()
def demo_chat_list_channels() -> str:
    """List channels visible to the current user (requires DEMO_CHAT_TOKEN)."""
    if not _token():
        return json.dumps(
            {
                "error": True,
                "detail": "Set DEMO_CHAT_TOKEN to a JWT (login via /api/v1/auth/login).",
            }
        )
    return _request("GET", "/channels")


@mcp.tool()
def demo_chat_list_messages(channel_id_or_name: str, limit: int = 30) -> str:
    """
    List recent top-level messages in a channel (thread replies excluded).
    channel_id_or_name is the channel UUID or its exact name (e.g. 'general').
    """
    if not _token():
        return json.dumps({"error": True, "detail": "Set DEMO_CHAT_TOKEN."})
    lim = max(1, min(int(limit), 200))
    return _request(
        "GET",
        f"/channels/{_seg(channel_id_or_name)}/messages?limit={lim}&root_only=true",
    )


@mcp.tool()
def demo_chat_list_thread_replies(
    channel_id_or_name: str, message_id: str, limit: int = 30
) -> str:
    """
    List replies in a thread. message_id is the root (top-level) message UUID.
    """
    if not _token():
        return json.dumps({"error": True, "detail": "Set DEMO_CHAT_TOKEN."})
    lim = max(1, min(int(limit), 200))
    return _request(
        "GET",
        f"/channels/{_seg(channel_id_or_name)}/messages/{quote(message_id.strip(), safe='')}/replies?limit={lim}",
    )


def _message_json(body: str, parent_id: str | None) -> dict:
    payload: dict = {"body": body}
    if parent_id and parent_id.strip():
        payload["parent_id"] = parent_id.strip()
    return payload


@mcp.tool()
def demo_chat_send_message(
    channel_id_or_name: str, body: str, parent_id: str = ""
) -> str:
    """
    Post a message to a channel as the authenticated user (requires token).
    Optional parent_id: UUID of a top-level message to reply in that thread.
    """
    if not _token():
        return json.dumps({"error": True, "detail": "Set DEMO_CHAT_TOKEN."})
    return _request(
        "POST",
        f"/channels/{_seg(channel_id_or_name)}/messages",
        json_body=_message_json(body, parent_id),
    )


@mcp.tool()
def demo_chat_channel_presence(channel_id_or_name: str) -> str:
    """Who is connected via WebSocket (channel UUID or name)."""
    if not _token():
        return json.dumps({"error": True, "detail": "Set DEMO_CHAT_TOKEN."})
    return _request("GET", f"/channels/{_seg(channel_id_or_name)}/presence")


@mcp.tool()
def demo_chat_webhook_post_message(
    channel_id_or_name: str, body: str, parent_id: str = ""
) -> str:
    """
    Post via inbound webhook POST /webhooks/channels/.../messages.
    Uses Bearer DEMO_CHAT_TOKEN if set, else HTTP Basic from
    DEMO_CHAT_WEBHOOK_USER and DEMO_CHAT_WEBHOOK_PASSWORD, else unauthenticated
    (only works when the channel allows anonymous webhook).
    Optional parent_id: UUID of a top-level message to reply in that thread.
    """
    path = f"/webhooks/channels/{_seg(channel_id_or_name)}/messages"
    payload = _message_json(body, parent_id)
    use_bearer = bool(_token())
    if not use_bearer and not (
        os.environ.get("DEMO_CHAT_WEBHOOK_USER")
        or os.environ.get("DEMO_CHAT_WEBHOOK_PASSWORD")
    ):
        return _request("POST", path, json_body=payload, use_bearer=False)
    return _request("POST", path, json_body=payload, use_bearer=use_bearer)


if __name__ == "__main__":
    logger.info("demo-chat MCP: base=%s token_set=%s", _base(), bool(_token()))
    mcp.run(transport="stdio")
