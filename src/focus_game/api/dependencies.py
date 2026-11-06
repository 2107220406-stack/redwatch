"""FastAPI dependency container."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from focus_game.domain.service import GameDomainService
from focus_game.persistence.event_store import EventStore

from .auth import current_player_id as _authenticated_player_id


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def current_player_id(request: Request) -> str:
    return _authenticated_player_id(request)


def domain_service(request: Request) -> GameDomainService:
    return request.app.state.domain_service


def event_store(session: AsyncSession) -> EventStore:
    return EventStore(session)
