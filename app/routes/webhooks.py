import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import authenticate_user, decode_token, get_user_by_id
from app.channel_ref import get_channel_by_ref
from app.db import get_db
from app.models import Channel, Message, User
from app.services.itsm_webhook import resolve_webhook_message
from app.services.membership import is_channel_member
from app.services.message_out import message_to_out, validate_reply_parent
from app.websocket import broadcast_message_created

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
basic_scheme = HTTPBasic(auto_error=False)


def _resolve_webhook_user(
    request: Request,
    db: Session,
    basic_creds: HTTPBasicCredentials | None,
) -> User | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            )
        sub = decode_token(token)
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired bearer token",
            )
        try:
            uid = uuid.UUID(sub)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token subject",
            )
        user = get_user_by_id(db, uid)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found for token",
            )
        return user

    if basic_creds is not None and (
        basic_creds.username or basic_creds.password
    ):
        user = authenticate_user(db, basic_creds.username, basic_creds.password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid basic credentials",
            )
        return user

    return None


def _resolve_parent_id(
    db: Session, channel_id: uuid.UUID, body: schemas.MessageCreate
) -> uuid.UUID | None:
    if body.parent_id is None:
        return None
    try:
        validate_reply_parent(db, channel_id, body.parent_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return body.parent_id


def _post_webhook_message(
    db: Session,
    channel_id: uuid.UUID,
    user_id: uuid.UUID,
    body: schemas.MessageCreate,
) -> schemas.MessageOut:
    msg = Message(
        channel_id=channel_id,
        user_id=user_id,
        body=body.body,
        parent_id=_resolve_parent_id(db, channel_id, body),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    broadcast_message_created(db, msg)
    return message_to_out(db, msg)


async def _read_webhook_payload(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        ) from exc
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook body must be a JSON object",
        )
    return raw


@router.post(
    "/channels/{channel_id_or_name}/messages",
    response_model=schemas.MessageOut,
    responses={
        204: {
            "description": "ITSM event recognized but unsupported; no message created"
        },
    },
    status_code=status.HTTP_201_CREATED,
)
async def webhook_post_message(
    request: Request,
    db: Session = Depends(get_db),
    basic_creds: HTTPBasicCredentials | None = Depends(basic_scheme),
    ch: Channel = Depends(get_channel_by_ref),
) -> schemas.MessageOut | Response:
    channel_id = ch.id
    raw = await _read_webhook_payload(request)
    body = resolve_webhook_message(ch.webhook_payload_format, raw)
    if body is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    user = _resolve_webhook_user(request, db, basic_creds)
    if user is not None:
        if not user.is_admin and not is_channel_member(db, user.id, channel_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of this channel",
            )
        return _post_webhook_message(db, channel_id, user.id, body)

    if ch.allow_anonymous_webhook and ch.anonymous_webhook_user_id:
        if not is_channel_member(db, ch.anonymous_webhook_user_id, channel_id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Misconfigured anonymous webhook user (not a member)",
            )
        return _post_webhook_message(
            db, channel_id, ch.anonymous_webhook_user_id, body
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (Bearer token or Basic auth), or enable anonymous webhook with an attribution user",
        headers={"WWW-Authenticate": 'Bearer realm="api", Basic realm="api"'},
    )
