import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import get_current_user, require_admin
from app.db import get_db
from app.services.membership import is_channel_member
from app.channel_ref import get_channel_by_ref
from app.models import Channel, Message, User

router = APIRouter(tags=["messages"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _message_out(db: Session, msg: Message) -> schemas.MessageOut:
    author = db.query(User).filter(User.id == msg.user_id).first()
    username = author.username if author else "?"
    return schemas.MessageOut(
        id=msg.id,
        channel_id=msg.channel_id,
        user_id=msg.user_id,
        username=username,
        body=msg.body,
        created_at=msg.created_at,
    )


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


@router.get("/channels/{channel_id_or_name}/messages", response_model=schemas.MessagePage)
def list_messages(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    ch: Channel = Depends(get_channel_by_ref),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    before_id: uuid.UUID | None = None,
) -> schemas.MessagePage:
    channel_id = ch.id
    _require_channel_access(db, current, channel_id)

    q = db.query(Message).filter(Message.channel_id == channel_id)
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

    rows = (
        q.order_by(Message.created_at.desc()).limit(limit + 1).all()
    )
    has_more = len(rows) > limit
    items_rows = rows[:limit]
    items_rows.reverse()

    items = [_message_out(db, m) for m in items_rows]
    next_before = items[0].id if has_more and items else None
    return schemas.MessagePage(
        items=items,
        has_more=has_more,
        next_before_id=next_before,
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
    msg = Message(channel_id=channel_id, user_id=current.id, body=body.body)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    from app.websocket import broadcast_message_created

    broadcast_message_created(db, msg)

    return _message_out(db, msg)


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
