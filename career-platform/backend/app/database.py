from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # test each connection with a lightweight ping before use;
                          # transparently reconnects if Neon has silently dropped it
    pool_recycle=300,     # proactively recycle connections older than 5 minutes,
                          # before Neon's own idle timeout can kill them first
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()