import logging
import pathlib
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from scripts.constants import USED_CLIPS_DB_PATH

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class UsedClip(Base):
    __tablename__ = "used_clips"

    video_id = Column(String, primary_key=True)
    clip_id = Column(String, primary_key=True)
    used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _get_session() -> Session:
    """Create the DB file/tables if missing and return a session."""
    db_path = pathlib.Path(USED_CLIPS_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)

    return sessionmaker(bind=engine)()


def get_used_clip_ids(video_id: str) -> set[str]:
    """Return the set of clip IDs already used for a given video."""
    session = _get_session()
    try:
        rows = session.query(UsedClip.clip_id).filter_by(video_id=video_id).all()
        used = {row.clip_id for row in rows}
        logger.info("Found %d used clips for video %s", len(used), video_id)
        return used
    finally:
        session.close()


def mark_clip_used(video_id: str, clip_id: str) -> None:
    """Record a clip as used in the database."""
    session = _get_session()
    try:
        record = UsedClip(
            video_id=video_id,
            clip_id=clip_id,
            used_at=datetime.now(timezone.utc),
        )
        session.merge(record)
        session.commit()
        logger.info("Marked clip '%s' as used for video '%s'", clip_id, video_id)
    except Exception as exc:
        session.rollback()
        logger.error("Failed to mark clip used: %s", exc)
        raise
    finally:
        session.close()
