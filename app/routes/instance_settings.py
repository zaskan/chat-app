"""Public and admin API for instance-wide settings (branding, future options)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import User, require_admin
from app.db import get_db
from app.services import instance_reset as reset_svc
from app.services import instance_settings as settings_svc

router = APIRouter(tags=["settings"])


@router.get(
    "/settings",
    response_model=schemas.InstanceSettingsOut,
    summary="Get instance settings",
    description=(
        "Returns merged instance settings (defaults + stored values). "
        "No authentication required — used before login for branding."
    ),
)
def get_instance_settings(db: Session = Depends(get_db)) -> schemas.InstanceSettingsOut:
    return settings_svc.get_public_settings(db)


@router.get(
    "/admin/settings",
    response_model=schemas.InstanceSettingsMeta,
    summary="Get instance settings (admin)",
    description="Same payload as public GET plus `updated_at` from the server.",
)
def get_instance_settings_admin(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> schemas.InstanceSettingsMeta:
    return settings_svc.get_admin_settings(db)


@router.patch(
    "/admin/settings",
    response_model=schemas.InstanceSettingsMeta,
    summary="Update instance settings (admin)",
    description=(
        "Merge patch: include only `branding` fields you want to change. "
        "Set a branding field to JSON `null` to clear an override and use the built-in default."
    ),
)
def patch_instance_settings_admin(
    body: schemas.InstanceSettingsPatch,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> schemas.InstanceSettingsMeta:
    settings_svc.patch_instance_settings(db, body)
    return settings_svc.get_admin_settings(db)


@router.delete(
    "/admin/settings/branding",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear stored branding (admin)",
    description=(
        "Remove branding overrides so built-in defaults apply. "
        "Other future setting groups are left unchanged."
    ),
)
def delete_branding_overrides(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    settings_svc.replace_branding_defaults(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/reset",
    response_model=schemas.InstanceResetOut,
    summary="Reset instance to demo defaults (admin)",
    description=(
        "Deletes all channels (messages and memberships), all non-seed users, "
        "and all server-side instance settings. Restores the seed admin user "
        "with the configured seed password."
    ),
)
def reset_instance_admin(
    body: schemas.InstanceResetRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> schemas.InstanceResetOut:
    _ = body.confirm
    return reset_svc.reset_instance(db)
