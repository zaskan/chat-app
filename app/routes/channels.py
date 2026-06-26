import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import get_current_user, require_admin
from app.db import get_db
from app.services.membership import is_channel_member
from app.models import Channel, ChannelMembership, User
from app.channel_ref import get_channel_by_ref
from app.websocket import manager as ws_manager

router = APIRouter(prefix="/channels", tags=["channels"])


def _validate_anonymous_user(
    db: Session, channel_id: uuid.UUID, user_id: uuid.UUID | None
) -> None:
    if user_id is None:
        return
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="anonymous_webhook_user_id: user not found",
        )
    if not is_channel_member(db, user_id, channel_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="anonymous_webhook_user_id: user must be a member of the channel",
        )


@router.get("", response_model=list[schemas.ChannelOut])
def list_channels(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[schemas.ChannelOut]:
    if current.is_admin:
        channels = db.query(Channel).order_by(Channel.name).all()
    else:
        channels = (
            db.query(Channel)
            .join(ChannelMembership)
            .filter(ChannelMembership.user_id == current.id)
            .order_by(Channel.name)
            .all()
        )
    return [schemas.ChannelOut.model_validate(c) for c in channels]


@router.post("", response_model=schemas.ChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(
    body: schemas.ChannelCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> schemas.ChannelOut:
    if db.query(Channel).filter(Channel.name == body.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel name already exists",
        )
    ch = Channel(
        name=body.name,
        allow_anonymous_webhook=body.allow_anonymous_webhook,
        anonymous_webhook_user_id=body.anonymous_webhook_user_id,
        webhook_payload_format=body.webhook_payload_format,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return schemas.ChannelOut.model_validate(ch)


@router.patch("/{channel_id_or_name}", response_model=schemas.ChannelOut)
def update_channel(
    body: schemas.ChannelUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    ch: Channel = Depends(get_channel_by_ref),
) -> schemas.ChannelOut:
    channel_id = ch.id
    if body.name is not None:
        other = db.query(Channel).filter(Channel.name == body.name, Channel.id != channel_id).first()
        if other:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Channel name already exists",
            )
        ch.name = body.name
    if body.allow_anonymous_webhook is not None:
        ch.allow_anonymous_webhook = body.allow_anonymous_webhook
    if body.anonymous_webhook_user_id is not None:
        ch.anonymous_webhook_user_id = body.anonymous_webhook_user_id
    if body.webhook_payload_format is not None:
        ch.webhook_payload_format = body.webhook_payload_format
    if ch.allow_anonymous_webhook:
        if not ch.anonymous_webhook_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="anonymous_webhook_user_id is required when allow_anonymous_webhook is true",
            )
        _validate_anonymous_user(db, ch.id, ch.anonymous_webhook_user_id)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return schemas.ChannelOut.model_validate(ch)


@router.delete("/{channel_id_or_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    ch: Channel = Depends(get_channel_by_ref),
) -> None:
    db.delete(ch)
    db.commit()


@router.get("/{channel_id_or_name}/presence", response_model=list[schemas.PresenceUser])
def channel_presence(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    ch: Channel = Depends(get_channel_by_ref),
) -> list[schemas.PresenceUser]:
    channel_id = ch.id
    if not current.is_admin and not is_channel_member(db, current.id, channel_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this channel",
        )
    rows = ws_manager.presence_for_channel(channel_id)
    return [
        schemas.PresenceUser(user_id=r["user_id"], username=str(r["username"]))
        for r in rows
    ]


@router.get("/{channel_id_or_name}/members", response_model=list[schemas.UserOut])
def list_members(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    ch: Channel = Depends(get_channel_by_ref),
) -> list[schemas.UserOut]:
    channel_id = ch.id
    users = (
        db.query(User)
        .join(ChannelMembership)
        .filter(ChannelMembership.channel_id == channel_id)
        .order_by(User.username)
        .all()
    )
    return [schemas.UserOut.model_validate(u) for u in users]


@router.post(
    "/{channel_id_or_name}/members",
    status_code=status.HTTP_204_NO_CONTENT,
)
def add_member(
    body: schemas.MembershipCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    ch: Channel = Depends(get_channel_by_ref),
) -> None:
    channel_id = ch.id
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if is_channel_member(db, body.user_id, channel_id):
        return
    db.add(ChannelMembership(user_id=body.user_id, channel_id=channel_id))
    db.commit()


@router.delete(
    "/{channel_id_or_name}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    ch: Channel = Depends(get_channel_by_ref),
) -> None:
    channel_id = ch.id
    m = (
        db.query(ChannelMembership)
        .filter(
            and_(
                ChannelMembership.channel_id == channel_id,
                ChannelMembership.user_id == user_id,
            )
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    db.delete(m)
    db.commit()
