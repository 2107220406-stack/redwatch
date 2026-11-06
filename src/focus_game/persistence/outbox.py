"""Small transactional-outbox delivery primitive.

The database transaction creates the outbox row together with the domain event.
This module provides the worker-facing claim and delivery operations; deployment
can call ``deliver_pending`` from a process scheduler or a long-running worker.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import OutboxRecord

OutboxHandler = Callable[[OutboxRecord], Awaitable[None]]


async def deliver_pending(
    session: AsyncSession,
    handler: OutboxHandler,
    *,
    limit: int = 100,
) -> int:
    if limit <= 0:
        raise ValueError("limit must be positive")
    result = await session.execute(
        select(OutboxRecord)
        .where(OutboxRecord.status == "PENDING")
        .order_by(OutboxRecord.event_id)
        .limit(limit)
    )
    records = list(result.scalars().all())
    delivered = 0
    for record in records:
        record.attempts += 1
        try:
            await handler(record)
        except Exception as exc:
            record.status = "FAILED"
            record.last_error = str(exc)[:2000]
        else:
            record.status = "DELIVERED"
            record.last_error = None
            delivered += 1
    await session.commit()
    return delivered


async def retry_failed(session: AsyncSession, *, limit: int = 100) -> int:
    if limit <= 0:
        raise ValueError("limit must be positive")
    result = await session.execute(
        select(OutboxRecord)
        .where(OutboxRecord.status == "FAILED")
        .order_by(OutboxRecord.event_id)
        .limit(limit)
    )
    records = list(result.scalars().all())
    for record in records:
        record.status = "PENDING"
        record.last_error = None
    await session.commit()
    return len(records)
