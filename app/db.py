from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_schema_migrations() -> None:
    """Apply lightweight column additions for existing DBs (create_all is not enough)."""
    insp = inspect(engine)
    if not insp.has_table("messages"):
        return
    cols = {c["name"] for c in insp.get_columns("messages")}
    if "parent_id" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE messages ADD COLUMN parent_id TEXT "
                    "REFERENCES messages(id) ON DELETE CASCADE"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_messages_parent_id "
                    "ON messages (parent_id)"
                )
            )
