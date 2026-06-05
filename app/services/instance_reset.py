"""Wipe demo data and restore seed admin (admin-only reset)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import hash_password
from app.config import settings
from app.models import AppSetting, Channel, User


def reset_instance(db: Session) -> schemas.InstanceResetOut:
    seed_username = settings.seed_admin_username

    db.query(Channel).delete(synchronize_session=False)
    db.query(AppSetting).delete(synchronize_session=False)
    db.query(User).filter(User.username != seed_username).delete(
        synchronize_session=False
    )

    admin = db.query(User).filter(User.username == seed_username).first()
    password_hash = hash_password(settings.seed_admin_password)
    if admin is None:
        admin = User(
            username=seed_username,
            password_hash=password_hash,
            is_admin=True,
        )
        db.add(admin)
    else:
        admin.password_hash = password_hash
        admin.is_admin = True

    db.commit()

    return schemas.InstanceResetOut(
        admin_username=seed_username,
        password_reset=True,
    )
