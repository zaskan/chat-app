from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import schemas
from app.models import Message, User


def batch_reply_counts(
    db: Session, root_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not root_ids:
        return {}
    rows = (
        db.query(Message.parent_id, func.count(Message.id))
        .filter(Message.parent_id.in_(root_ids))
        .group_by(Message.parent_id)
        .all()
    )
    return {pid: int(cnt) for pid, cnt in rows if pid is not None}


def message_to_out(
    db: Session,
    msg: Message,
    *,
    reply_count: int | None = None,
) -> schemas.MessageOut:
    author = db.query(User).filter(User.id == msg.user_id).first()
    username = author.username if author else "?"
    count = reply_count if reply_count is not None else 0
    if reply_count is None and msg.parent_id is None:
        count = (
            db.query(func.count(Message.id))
            .filter(Message.parent_id == msg.id)
            .scalar()
            or 0
        )
    return schemas.MessageOut(
        id=msg.id,
        channel_id=msg.channel_id,
        user_id=msg.user_id,
        username=username,
        body=msg.body,
        created_at=msg.created_at,
        parent_id=msg.parent_id,
        reply_count=count,
    )


def resolve_thread_root(
    db: Session, channel_id: uuid.UUID, message_id: uuid.UUID
) -> Message | None:
    msg = (
        db.query(Message)
        .filter(Message.id == message_id, Message.channel_id == channel_id)
        .first()
    )
    if msg is None:
        return None
    if msg.parent_id is None:
        return msg
    return (
        db.query(Message)
        .filter(Message.id == msg.parent_id, Message.channel_id == channel_id)
        .first()
    )


def validate_reply_parent(
    db: Session, channel_id: uuid.UUID, parent_id: uuid.UUID
) -> Message:
    parent = (
        db.query(Message)
        .filter(Message.id == parent_id, Message.channel_id == channel_id)
        .first()
    )
    if parent is None:
        raise ValueError("parent_id not found in this channel")
    if parent.parent_id is not None:
        raise ValueError("parent_id must be a top-level channel message")
    return parent
