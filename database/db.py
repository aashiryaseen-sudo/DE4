import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.declarative import declarative_base

load_dotenv()

SUPABASE_DB_URL = os.environ.get("DATABASE_URL")

if not SUPABASE_DB_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please set it in your .env file.")

engine = create_engine(SUPABASE_DB_URL, client_encoding="utf8", poolclass=NullPool)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    FastAPI dependency to get a database session.
    Yields a session and ensures it is always closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
