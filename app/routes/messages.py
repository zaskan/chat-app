import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import get_current_user, require_admin
from app.channel_ref import get_channel_by_ref
from app.db import get_db
from app.models import Channel, Message, User
from app.services.membership import is_channel_member
from app.services.message_out import (
    batch_reply_counts,
    message_to_out,
    resolve_thread_root,
    validate_reply_parent,
)

router = APIRouter(tags=["messages"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _require_channel_access(
    db: Session,
    current: User,
    channel_id: uuid.UUID,
) -> Channel:
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    if current.is_admin:
        return ch
    if not is_channel_member(db, current.id, channel_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this channel")
    return ch


def _paginate_messages(
    db: Session,
    channel_id: uuid.UUID,
    *,
    limit: int,
    before_id: uuid.UUID | None,
    parent_filter,
    include_reply_counts: bool,
) -> schemas.MessagePage:
    q = db.query(Message).filter(Message.channel_id == channel_id)
    if parent_filter is not True:
        q = q.filter(parent_filter)

    before_msg: Message | None = None
    if before_id is not None:
        before_msg = (
            db.query(Message)
            .filter(and_(Message.id == before_id, Message.channel_id == channel_id))
            .first()
        )
        if not before_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="before_id not found in this channel",
            )
        q = q.filter(Message.created_at < before_msg.created_at)

    rows = q.order_by(Message.created_at.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    items_rows = rows[:limit]
    items_rows.reverse()

    counts: dict[uuid.UUID, int] = {}
    if include_reply_counts:
        root_ids = [m.id for m in items_rows if m.parent_id is None]
        counts = batch_reply_counts(db, root_ids)

    items = [
        message_to_out(
            db,
            m,
            reply_count=counts.get(m.id, 0) if include_reply_counts else 0,
        )
        for m in items_rows
    ]
    next_before = items[0].id if has_more and items else None
    return schemas.MessagePage(
        items=items,
        has_more=has_more,
        next_before_id=next_before,
    )


@router.get("/channels/{channel_id_or_name}/messages", response_model=schemas.MessagePage)
def list_messages(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    ch: Channel = Depends(get_channel_by_ref),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    before_id: uuid.UUID | None = None,
    root_only: bool = Query(default=True),
) -> schemas.MessagePage:
    channel_id = ch.id
    _require_channel_access(db, current, channel_id)

    parent_filter = Message.parent_id.is_(None) if root_only else True
    return _paginate_messages(
        db,
        channel_id,
        limit=limit,
        before_id=before_id,
        parent_filter=parent_filter,
        include_reply_counts=root_only,
    )


@router.get(
    "/channels/{channel_id_or_name}/messages/{message_id}/replies",
    response_model=schemas.MessagePage,
)
def list_message_replies(
    message_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    ch: Channel = Depends(get_channel_by_ref),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    before_id: uuid.UUID | None = None,
) -> schemas.MessagePage:
    channel_id = ch.id
    _require_channel_access(db, current, channel_id)

    root = resolve_thread_root(db, channel_id, message_id)
    if root is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    return _paginate_messages(
        db,
        channel_id,
        limit=limit,
        before_id=before_id,
        parent_filter=Message.parent_id == root.id,
        include_reply_counts=False,
    )


@router.post(
    "/channels/{channel_id_or_name}/messages",
    response_model=schemas.MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    body: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    ch: Channel = Depends(get_channel_by_ref),
) -> schemas.MessageOut:
    channel_id = ch.id
    _require_channel_access(db, current, channel_id)

    parent_id: uuid.UUID | None = None
    if body.parent_id is not None:
        try:
            validate_reply_parent(db, channel_id, body.parent_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        parent_id = body.parent_id

    msg = Message(
        channel_id=channel_id,
        user_id=current.id,
        body=body.body,
        parent_id=parent_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    from app.websocket import broadcast_message_created

    broadcast_message_created(db, msg)

    return message_to_out(db, msg)


@router.delete(
    "/channels/{channel_id_or_name}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_message(
    message_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
    ch: Channel = Depends(get_channel_by_ref),
) -> None:
    channel_id = ch.id
    msg = (
        db.query(Message)
        .filter(
            and_(Message.id == message_id, Message.channel_id == channel_id)
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    db.delete(msg)
    db.commit()
