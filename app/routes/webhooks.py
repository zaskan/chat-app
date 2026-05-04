import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import authenticate_user, decode_token, get_user_by_id
from app.channel_ref import get_channel_by_ref
from app.db import get_db
from app.services.membership import is_channel_member
from app.models import Channel, Message, User
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


@router.post(
    "/channels/{channel_id_or_name}/messages",
    response_model=schemas.MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def webhook_post_message(
    body: schemas.MessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    basic_creds: HTTPBasicCredentials | None = Depends(basic_scheme),
    ch: Channel = Depends(get_channel_by_ref),
) -> schemas.MessageOut:
    channel_id = ch.id

    user = _resolve_webhook_user(request, db, basic_creds)
    if user is not None:
        if not user.is_admin and not is_channel_member(db, user.id, channel_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of this channel",
            )
        msg = Message(
            channel_id=channel_id,
            user_id=user.id,
            body=body.body,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        broadcast_message_created(db, msg)
        author = db.query(User).filter(User.id == msg.user_id).first()
        return schemas.MessageOut(
            id=msg.id,
            channel_id=msg.channel_id,
            user_id=msg.user_id,
            username=author.username if author else "?",
            body=msg.body,
            created_at=msg.created_at,
        )

    if ch.allow_anonymous_webhook and ch.anonymous_webhook_user_id:
        if not is_channel_member(db, ch.anonymous_webhook_user_id, channel_id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Misconfigured anonymous webhook user (not a member)",
            )
        msg = Message(
            channel_id=channel_id,
            user_id=ch.anonymous_webhook_user_id,
            body=body.body,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        broadcast_message_created(db, msg)
        author = db.query(User).filter(User.id == msg.user_id).first()
        return schemas.MessageOut(
            id=msg.id,
            channel_id=msg.channel_id,
            user_id=msg.user_id,
            username=author.username if author else "?",
            body=msg.body,
            created_at=msg.created_at,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (Bearer token or Basic auth), or enable anonymous webhook with an attribution user",
        headers={"WWW-Authenticate": 'Bearer realm="api", Basic realm="api"'},
    )
