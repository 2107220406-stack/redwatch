"""SQLAlchemy tables. Domain objects never import this module."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EventRecord(Base):
    __tablename__ = "event_records"
    __table_args__ = (UniqueConstraint("aggregate_id", "aggregate_version"),)

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date)
    causation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (PrimaryKeyConstraint("player_id", "key"),)

    player_id: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64))
    decision_id: Mapped[str] = mapped_column(String(80))
    response: Mapped[dict] = mapped_column(JSON)


class PlayerSnapshot(Base):
    __tablename__ = "player_snapshots"

    player_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(JSON)


class OutboxRecord(Base):
    __tablename__ = "outbox_records"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
