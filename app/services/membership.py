import uuid

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import ChannelMembership


def is_channel_member(db: Session, user_id: uuid.UUID, channel_id: uuid.UUID) -> bool:
    m = (
        db.query(ChannelMembership)
        .filter(
            and_(
                ChannelMembership.user_id == user_id,
                ChannelMembership.channel_id == channel_id,
            )
        )
        .first()
    )
    return m is not None
