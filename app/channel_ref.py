"""Resolve a channel from a path or payload segment: UUID or exact channel name."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Channel


def parse_channel_ref(db: Session, ref: str) -> Channel | None:
    """Look up channel by UUID string, else by exact ``Channel.name`` (unique)."""
    ref = (ref or "").strip()
    if not ref:
        return None
    try:
        uid = uuid.UUID(ref)
        ch = db.query(Channel).filter(Channel.id == uid).first()
        if ch is not None:
            return ch
    except ValueError:
        pass
    return db.query(Channel).filter(Channel.name == ref).first()


def get_channel_by_ref(
    channel_id_or_name: str,
    db: Session = Depends(get_db),
) -> Channel:
    ch = parse_channel_ref(db, channel_id_or_name)
    if ch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    return ch
