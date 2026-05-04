import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.auth_deps import get_current_user, hash_password, require_admin
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=schemas.UserOut)
def read_me(current: User = Depends(get_current_user)) -> schemas.UserOut:
    return schemas.UserOut.model_validate(current)


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[schemas.UserOut]:
    users = db.query(User).order_by(User.username).all()
    return [schemas.UserOut.model_validate(u) for u in users]


@router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> schemas.UserOut:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.UserOut.model_validate(user)


@router.patch("/me", response_model=schemas.UserOut)
def update_my_password(
    body: schemas.PasswordUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> schemas.UserOut:
    current.password_hash = hash_password(body.password)
    db.add(current)
    db.commit()
    db.refresh(current)
    return schemas.UserOut.model_validate(current)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> None:
    if user_id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()
