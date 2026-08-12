"""
app/db/database.py

Handles the PostgreSQL connection and provides the SQLAlchemy session
used by routes / background tasks (FastAPI dependency injection).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load variables from the .env file (DATABASE_URL, etc.)
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/mr_reviewer",
)

# echo=False in prod, set True temporarily for SQL debugging
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class that all SQLAlchemy models will inherit from (models.py)
Base = declarative_base()


def get_db():
    """
    FastAPI dependency: opens a DB session for the duration of a request
    and closes it properly at the end (even if an exception occurs).

    Usage in a route:
        @router.get("/...")
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Creates all tables declared in models.py if they don't exist yet.
    Call this once at startup (see main.py).
    Useful in dev; in prod, Alembic migrations are preferred.
    """
    from app.db import models  # noqa: F401  (ensures models are registered)
    Base.metadata.create_all(bind=engine)