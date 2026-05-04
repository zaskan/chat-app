"""Load and persist instance-wide settings (branding, future feature flags, etc.)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import schemas
from app.models import AppSetting

INSTANCE_KEY = "instance_v1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_raw_dict(db: Session) -> dict[str, Any]:
    row = db.query(AppSetting).filter(AppSetting.key == INSTANCE_KEY).first()
    if not row or not row.value_json or not row.value_json.strip():
        return {}
    try:
        out = json.loads(row.value_json)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def _default_branding_dict() -> dict[str, Any]:
    return schemas.BrandingSettings().model_dump()


def _merge_branding(
    stored: dict[str, Any] | None,
) -> schemas.BrandingSettings:
    base = _default_branding_dict()
    if stored and isinstance(stored, dict):
        base.update({k: v for k, v in stored.items() if k in base})
    try:
        return schemas.BrandingSettings.model_validate(base)
    except Exception:
        return schemas.BrandingSettings()


def get_branding(db: Session) -> schemas.BrandingSettings:
    raw = _load_raw_dict(db)
    return _merge_branding(raw.get("branding"))


def get_public_settings(db: Session) -> schemas.InstanceSettingsOut:
    return schemas.InstanceSettingsOut(branding=get_branding(db))


def get_admin_settings(db: Session) -> schemas.InstanceSettingsMeta:
    row = db.query(AppSetting).filter(AppSetting.key == INSTANCE_KEY).first()
    return schemas.InstanceSettingsMeta(
        branding=get_branding(db),
        updated_at=row.updated_at if row else None,
    )


def _save_raw_dict(db: Session, data: dict[str, Any]) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == INSTANCE_KEY).first()
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    now = _utcnow()
    if row is None:
        row = AppSetting(key=INSTANCE_KEY, value_json=payload, updated_at=now)
        db.add(row)
    else:
        row.value_json = payload
        row.updated_at = now
    db.commit()


def patch_instance_settings(db: Session, patch: schemas.InstanceSettingsPatch) -> None:
    raw = _load_raw_dict(db)
    dirty = False
    if patch.branding is not None:
        b_patch = patch.branding.model_dump(exclude_unset=True)
        if b_patch:
            brand = raw.get("branding")
            if not isinstance(brand, dict):
                brand = {}
            else:
                brand = dict(brand)
            for k, v in b_patch.items():
                if v is None:
                    brand.pop(k, None)
                else:
                    brand[k] = v
            raw["branding"] = brand
            dirty = True
    # Extend here with other setting groups (e.g. patch.features).
    if dirty:
        _save_raw_dict(db, raw)


def replace_branding_defaults(db: Session) -> None:
    """Reset stored branding so defaults apply (admin utility)."""
    raw = _load_raw_dict(db)
    raw.pop("branding", None)
    if raw:
        _save_raw_dict(db, raw)
    else:
        row = db.query(AppSetting).filter(AppSetting.key == INSTANCE_KEY).first()
        if row:
            db.delete(row)
            db.commit()
