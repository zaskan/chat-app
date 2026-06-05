import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.auth_deps import decode_token, get_user_by_id
from app.channel_ref import parse_channel_ref
from app.db import SessionLocal
from app.services.membership import is_channel_member
from app.models import Message, User
from app.services.message_out import message_to_out, validate_reply_parent

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self._channel_sockets: dict[uuid.UUID, set[WebSocket]] = {}
        self._socket_channels: dict[WebSocket, set[uuid.UUID]] = {}
        self._ws_user: dict[WebSocket, tuple[uuid.UUID, str]] = {}
        self._presence_counts: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
        self._presence_names: dict[uuid.UUID, dict[uuid.UUID, str]] = {}

    def bind_user(self, ws: WebSocket, user_id: uuid.UUID, username: str) -> None:
        self._ws_user[ws] = (user_id, username)

    def register(
        self,
        channel_id: uuid.UUID,
        ws: WebSocket,
        user_id: uuid.UUID,
        username: str,
    ) -> None:
        s = self._channel_sockets.setdefault(channel_id, set())
        new_sub = ws not in s
        s.add(ws)
        if ws not in self._socket_channels:
            self._socket_channels[ws] = set()
        self._socket_channels[ws].add(channel_id)
        if new_sub:
            pc = self._presence_counts.setdefault(channel_id, {})
            pc[user_id] = pc.get(user_id, 0) + 1
            pn = self._presence_names.setdefault(channel_id, {})
            pn[user_id] = username

    def unregister_channel(self, channel_id: uuid.UUID, ws: WebSocket) -> None:
        self._dec_presence(channel_id, ws)
        s = self._channel_sockets.get(channel_id)
        if s and ws in s:
            s.discard(ws)
            if not s:
                del self._channel_sockets[channel_id]
        chans = self._socket_channels.get(ws)
        if chans is not None:
            chans.discard(channel_id)
            if not chans:
                del self._socket_channels[ws]

    def _dec_presence(self, channel_id: uuid.UUID, ws: WebSocket) -> None:
        info = self._ws_user.get(ws)
        if not info:
            return
        user_id, _ = info
        d = self._presence_counts.get(channel_id)
        if not d or user_id not in d:
            return
        d[user_id] -= 1
        if d[user_id] <= 0:
            del d[user_id]
            pn = self._presence_names.get(channel_id)
            if pn and user_id in pn:
                del pn[user_id]
        if channel_id in self._presence_counts and not self._presence_counts[channel_id]:
            del self._presence_counts[channel_id]
            self._presence_names.pop(channel_id, None)

    def unregister(self, ws: WebSocket) -> None:
        chans = list(self._socket_channels.pop(ws, set()))
        for cid in chans:
            self._dec_presence(cid, ws)
            s = self._channel_sockets.get(cid)
            if s and ws in s:
                s.discard(ws)
                if not s:
                    del self._channel_sockets[cid]
        self._ws_user.pop(ws, None)

    def presence_for_channel(self, channel_id: uuid.UUID) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        counts = self._presence_counts.get(channel_id, {})
        names = self._presence_names.get(channel_id, {})
        for uid, n in counts.items():
            if n > 0:
                out.append(
                    {"user_id": uid, "username": names.get(uid, "?")}
                )
        out.sort(key=lambda x: str(x["username"]))
        return out

    async def broadcast(
        self, channel_id: uuid.UUID, message: dict[str, Any]
    ) -> None:
        targets = list(self._channel_sockets.get(channel_id, ()))
        text = json.dumps(message)
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                self.unregister(ws)


manager = ConnectionManager()

_AGENT_DBG_LOG = "/home/rafsanch/Documents/chat-app/.cursor/debug-b69983.log"


def _agent_dbg(payload: dict[str, Any]) -> None:
    """Append NDJSON for local debug sessions (no-op if path unavailable, e.g. in-cluster)."""
    try:
        payload.setdefault("timestamp", int(time.time() * 1000))
        payload.setdefault("sessionId", "b69983")
        with open(_AGENT_DBG_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except OSError:
        pass


def broadcast_message_created(db: Session, msg: Message) -> None:
    out = message_to_out(db, msg)
    payload = {
        "type": "message_created",
        "payload": out.model_dump(mode="json"),
    }

    async def _send() -> None:
        await manager.broadcast(msg.channel_id, payload)
        if msg.parent_id is not None:
            from sqlalchemy import func

            reply_count = (
                db.query(func.count(Message.id))
                .filter(Message.parent_id == msg.parent_id)
                .scalar()
                or 0
            )
            thread_payload = {
                "type": "thread_updated",
                "channel_id": str(msg.channel_id),
                "root_id": str(msg.parent_id),
                "reply_count": reply_count,
            }
            await manager.broadcast(msg.channel_id, thread_payload)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send())
    except RuntimeError:
        asyncio.run(_send())


def broadcast_channel_history_cleared(channel_id: uuid.UUID, deleted_count: int) -> None:
    payload = {
        "type": "channel_history_cleared",
        "channel_id": str(channel_id),
        "deleted_count": deleted_count,
    }

    async def _send() -> None:
        await manager.broadcast(channel_id, payload)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send())
    except RuntimeError:
        asyncio.run(_send())


def _can_access_channel(db: Session, user: User, channel_id: uuid.UUID) -> bool:
    if user.is_admin:
        return True
    return is_channel_member(db, user.id, channel_id)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
) -> None:
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    sub = decode_token(token)
    if sub is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        uid = uuid.UUID(sub)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db = SessionLocal()
    try:
        user = get_user_by_id(db, uid)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    finally:
        db.close()

    await websocket.accept()
    db_bind = SessionLocal()
    try:
        u_bind = get_user_by_id(db_bind, uid)
        if u_bind:
            manager.bind_user(websocket, u_bind.id, u_bind.username)
    finally:
        db_bind.close()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "code": "bad_json",
                            "message": "Invalid JSON",
                        }
                    )
                )
                continue

            typ = data.get("type")
            db = SessionLocal()
            try:
                user = get_user_by_id(db, uid)
                if user is None:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "unauthorized",
                                "message": "User not found",
                            }
                        )
                    )
                    break

                if typ == "subscribe":
                    cid_raw = data.get("channel_id") or data.get("channel_name")
                    if cid_raw is None:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "bad_channel",
                                    "message": "channel_id or channel_name required",
                                }
                            )
                        )
                        continue
                    ch_sub = parse_channel_ref(db, str(cid_raw))
                    if ch_sub is None:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "bad_channel",
                                    "message": "Channel not found",
                                }
                            )
                        )
                        continue
                    cid = ch_sub.id
                    if not _can_access_channel(db, user, cid):
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "forbidden",
                                    "message": "Cannot subscribe to this channel",
                                }
                            )
                        )
                        continue
                    manager.register(cid, websocket, user.id, user.username)
                    pres_rows = manager.presence_for_channel(cid)
                    presence_out = [
                        {
                            "user_id": str(r["user_id"]),
                            "username": str(r["username"]),
                        }
                        for r in pres_rows
                    ]
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "subscribed",
                                "channel_id": str(cid),
                                "presence": presence_out,
                            }
                        )
                    )
                    _agent_dbg(
                        {
                            "location": "websocket.py:subscribe",
                            "message": "subscribed with presence snapshot",
                            "data": {
                                "channel_id": str(cid),
                                "presence_count": len(presence_out),
                            },
                            "hypothesisId": "H6",
                        }
                    )

                elif typ == "send_message":
                    cid_raw = data.get("channel_id") or data.get("channel_name")
                    body = data.get("body")
                    parent_raw = data.get("parent_id")
                    if cid_raw is None:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "bad_channel",
                                    "message": "channel_id or channel_name required",
                                }
                            )
                        )
                        continue
                    ch_msg = parse_channel_ref(db, str(cid_raw))
                    if ch_msg is None:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "bad_channel",
                                    "message": "Channel not found",
                                }
                            )
                        )
                        continue
                    cid = ch_msg.id
                    if not isinstance(body, str) or not body.strip():
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "bad_body",
                                    "message": "body must be a non-empty string",
                                }
                            )
                        )
                        continue
                    if not _can_access_channel(db, user, cid):
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "forbidden",
                                    "message": "Cannot post to this channel",
                                }
                            )
                        )
                        continue
                    parent_id: uuid.UUID | None = None
                    if parent_raw is not None:
                        try:
                            parent_id = uuid.UUID(str(parent_raw))
                        except ValueError:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "code": "bad_parent",
                                        "message": "parent_id must be a valid UUID",
                                    }
                                )
                            )
                            continue
                        try:
                            validate_reply_parent(db, cid, parent_id)
                        except ValueError as exc:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "code": "bad_parent",
                                        "message": str(exc),
                                    }
                                )
                            )
                            continue
                    msg = Message(
                        channel_id=cid,
                        user_id=user.id,
                        body=body.strip(),
                        parent_id=parent_id,
                    )
                    db.add(msg)
                    db.commit()
                    db.refresh(msg)
                    broadcast_message_created(db, msg)
                elif typ == "unsubscribe":
                    cid_raw = data.get("channel_id") or data.get("channel_name")
                    if cid_raw is None:
                        continue
                    ch_un = parse_channel_ref(db, str(cid_raw))
                    if ch_un is None:
                        continue
                    cid = ch_un.id
                    manager.unregister_channel(cid, websocket)
                    await websocket.send_text(
                        json.dumps({"type": "unsubscribed", "channel_id": str(cid)})
                    )
                else:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "unknown_type",
                                "message": f"Unknown type: {typ}",
                            }
                        )
                    )
            finally:
                db.close()
    except WebSocketDisconnect:
        manager.unregister(websocket)
