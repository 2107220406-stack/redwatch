"""Transactional event append, snapshot persistence, and idempotency."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from focus_game.domain.service import Decision, PlayerState

from .serialization import state_from_dict, state_to_dict
from .tables import EventRecord, IdempotencyRecord, OutboxRecord, PlayerSnapshot


class ConcurrencyConflict(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class AppendResult:
    def __init__(
        self, decision_id: str, response: dict, state: PlayerState, replayed: bool = False
    ) -> None:
        self.decision_id = decision_id
        self.response = response
        self.state = state
        self.replayed = replayed


class EventStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_state(self, player_id: str) -> tuple[PlayerState, int]:
        snapshot = await self.session.get(PlayerSnapshot, player_id)
        if snapshot is None:
            return PlayerState(player_id=player_id), 0
        return state_from_dict(snapshot.state), snapshot.aggregate_version

    async def get_idempotent_response(
        self, player_id: str, command_key: str, request: dict
    ) -> dict | None:
        request_hash = hashlib.sha256(
            json.dumps(request, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        existing = await self.session.get(
            IdempotencyRecord, {"player_id": player_id, "key": command_key}
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyConflict("idempotency key was reused with a different request")
        return existing.response

    async def append(
        self,
        *,
        player_id: str,
        expected_version: int,
        command_key: str,
        request: dict,
        decision: Decision,
    ) -> AppendResult:
        request_hash = hashlib.sha256(
            json.dumps(request, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        existing = await self.session.get(
            IdempotencyRecord, {"player_id": player_id, "key": command_key}
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyConflict("idempotency key was reused with a different request")
            state, _ = await self.load_state(player_id)
            return AppendResult(existing.decision_id, existing.response, state, replayed=True)

        snapshot = await self.session.get(PlayerSnapshot, player_id)
        current_version = snapshot.aggregate_version if snapshot else 0
        if current_version != expected_version:
            raise ConcurrencyConflict(
                f"aggregate version conflict: expected {expected_version}, got {current_version}"
            )

        response = {
            "decision_id": decision.decision_id,
            "aggregate_version": expected_version + len(decision.events),
            "message": decision.message,
            "events": [event.to_dict() for event in decision.events],
            "state": state_to_dict(decision.state),
        }
        persisted_events = tuple(
            replace(event, aggregate_version=expected_version + index)
            for index, event in enumerate(decision.events, start=1)
        )
        response["events"] = [event.to_dict() for event in persisted_events]
        for event in persisted_events:
            self.session.add(
                EventRecord(
                    event_id=event.event_id,
                    aggregate_id=event.aggregate_id,
                    aggregate_version=event.aggregate_version,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    business_date=event.business_date,
                    causation_id=event.causation_id,
                    correlation_id=event.correlation_id,
                    idempotency_key=event.idempotency_key,
                    schema_version=event.schema_version,
                    payload=event.to_dict()["payload"],
                )
            )
            self.session.add(
                OutboxRecord(
                    event_id=event.event_id, event_type=event.event_type, payload=event.to_dict()
                )
            )
        if snapshot is None:
            self.session.add(
                PlayerSnapshot(
                    player_id=player_id,
                    aggregate_version=response["aggregate_version"],
                    state=state_to_dict(decision.state),
                )
            )
        else:
            snapshot.aggregate_version = response["aggregate_version"]
            snapshot.state = state_to_dict(decision.state)
        self.session.add(
            IdempotencyRecord(
                player_id=player_id,
                key=command_key,
                request_hash=request_hash,
                decision_id=decision.decision_id,
                response=response,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise ConcurrencyConflict("event append conflicted with another writer") from exc
        return AppendResult(decision.decision_id, response, decision.state)

    async def list_events(self, player_id: str) -> Sequence[EventRecord]:
        result = await self.session.execute(
            select(EventRecord)
            .where(EventRecord.aggregate_id == player_id)
            .order_by(EventRecord.aggregate_version)
        )
        return result.scalars().all()
