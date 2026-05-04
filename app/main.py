from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth_deps import hash_password
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import User
from app.routes import api_v1, ui


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = db.query(User).count()
        if n == 0:
            admin = User(
                username=settings.seed_admin_username,
                password_hash=hash_password(settings.seed_admin_password),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(
    title="Demo Chat",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

_origins = [
    o.strip() for o in settings.cors_origins.split(",") if o.strip()
] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_v1.router)

static_dir = Path(ui.STATIC_DIR)
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
