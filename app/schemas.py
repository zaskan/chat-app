import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# Auth
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# User
class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=128)


class UserCreate(UserBase):
    password: str = Field(min_length=1, max_length=256)
    is_admin: bool = False


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    is_admin: bool

    model_config = {"from_attributes": True}


class PresenceUser(BaseModel):
    """User currently subscribed to a channel via WebSocket."""

    user_id: uuid.UUID
    username: str


class PasswordUpdate(BaseModel):
    password: str = Field(min_length=1, max_length=256)


# Channel
class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    allow_anonymous_webhook: bool = False
    anonymous_webhook_user_id: uuid.UUID | None = None


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    allow_anonymous_webhook: bool | None = None
    anonymous_webhook_user_id: uuid.UUID | None = None


class ChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    allow_anonymous_webhook: bool
    anonymous_webhook_user_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class MembershipCreate(BaseModel):
    user_id: uuid.UUID


# Message
class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=65535)
    parent_id: uuid.UUID | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    body: str
    created_at: datetime
    parent_id: uuid.UUID | None = None
    reply_count: int = 0


class MessagePage(BaseModel):
    items: list[MessageOut]
    has_more: bool
    next_before_id: uuid.UUID | None = None


# Instance settings (UI / branding — extend with more groups later)
_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingSettings(BaseModel):
    """Resolved branding shown to all clients (defaults applied)."""

    app_title: str = Field(default="Demo Chat", max_length=120)
    logo_mode: Literal["default", "none", "custom"] = "default"
    logo_url: str | None = Field(
        default=None,
        description="https URL, site-relative path, or data:image/*;base64,...",
    )
    sidebar_background: str = Field(
        default="#1a2744",
        description="Sidebar menu background (hex)",
    )
    sidebar_text: str | None = Field(
        default=None,
        description="Sidebar primary text color (hex); null = automatic from background",
    )

    @field_validator("sidebar_background", "sidebar_text", mode="before")
    @classmethod
    def normalize_hex(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    @field_validator("sidebar_background")
    @classmethod
    def hex_background(cls, v: str) -> str:
        if not _HEX6.match(v):
            raise ValueError("sidebar_background must be a #RRGGBB hex color")
        return v

    @field_validator("sidebar_text")
    @classmethod
    def hex_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _HEX6.match(v):
            raise ValueError("sidebar_text must be a #RRGGBB hex color")
        return v

    @field_validator("logo_url")
    @classmethod
    def logo_url_limits(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if s.startswith("data:image/"):
            if len(s) > 700_000:
                raise ValueError("Embedded image data too large (max ~700KB encoded)")
            return s
        if len(s) > 2048:
            raise ValueError("logo_url is too long")
        return s


class BrandingSettingsPatch(BaseModel):
    """Partial branding update (PATCH). Omit a field to leave it unchanged."""

    app_title: str | None = Field(default=None, max_length=120)
    logo_mode: Literal["default", "none", "custom"] | None = None
    logo_url: str | None = None
    sidebar_background: str | None = None
    sidebar_text: str | None = None

    @field_validator(
        "sidebar_background",
        "sidebar_text",
        "app_title",
        "logo_mode",
        "logo_url",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("sidebar_background")
    @classmethod
    def hex_background_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _HEX6.match(v):
            raise ValueError("sidebar_background must be a #RRGGBB hex color")
        return v

    @field_validator("sidebar_text")
    @classmethod
    def hex_text_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _HEX6.match(v):
            raise ValueError("sidebar_text must be a #RRGGBB hex color")
        return v

    @field_validator("logo_url")
    @classmethod
    def logo_url_limits_patch(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if s.startswith("data:image/"):
            if len(s) > 700_000:
                raise ValueError("Embedded image data too large (max ~700KB encoded)")
            return s
        if len(s) > 2048:
            raise ValueError("logo_url is too long")
        return s


class InstanceSettingsOut(BaseModel):
    """Full public instance settings (add nested groups as needed)."""

    branding: BrandingSettings


class InstanceSettingsMeta(BaseModel):
    """Admin read includes metadata."""

    branding: BrandingSettings
    updated_at: datetime | None = None


class InstanceSettingsPatch(BaseModel):
    """Merge patch for instance settings. Only provided sections/fields are updated."""

    branding: BrandingSettingsPatch | None = None
