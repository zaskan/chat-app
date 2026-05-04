"""REST API v1 — aggregated routers (same pattern as itsm-app)."""

from __future__ import annotations

from fastapi import APIRouter

from app.routes import auth, channels, instance_settings, messages, users, webhooks
from app.websocket import router as ws_router

router = APIRouter(prefix="/api/v1", tags=["api-v1"])

router.include_router(auth.router)
router.include_router(instance_settings.router)
router.include_router(users.router)
router.include_router(channels.router)
router.include_router(messages.router)
router.include_router(webhooks.router)
router.include_router(ws_router)
