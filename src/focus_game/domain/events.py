"""Immutable, serializable domain event contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, ClassVar, TypeVar

from .models import (
    require_aware_datetime,
    require_non_empty_id,
    require_non_negative_integer,
)


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    aggregate_id: str
    aggregate_version: int
    occurred_at: datetime
    business_date: date
    causation_id: str | None
    correlation_id: str
    idempotency_key: str
    payload: Mapping[str, Any]
    event_type: str = field(default="DomainEvent", kw_only=True)
    schema_version: int = field(default=1, kw_only=True)

    event_registry: ClassVar[dict[str, type[DomainEvent]]] = {}
    quantity_key: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        require_non_empty_id(self.event_id, "event_id")
        require_non_empty_id(self.aggregate_id, "aggregate_id")
        require_non_empty_id(self.correlation_id, "correlation_id")
        require_non_empty_id(self.idempotency_key, "idempotency_key")
        if self.causation_id is not None:
            require_non_empty_id(self.causation_id, "causation_id")
        require_non_negative_integer(self.aggregate_version, "aggregate_version")
        require_aware_datetime(self.occurred_at, "occurred_at")
        if not isinstance(self.business_date, date) or isinstance(self.business_date, datetime):
            raise TypeError("business_date must be a date")
        require_non_empty_id(self.event_type, "event_type")
        require_non_negative_integer(self.schema_version, "schema_version")
        if self.schema_version == 0:
            raise ValueError("schema_version must be positive")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        normalized_payload = dict(self.payload)
        _validate_json_value(normalized_payload)
        quantity_key = type(self).quantity_key
        if quantity_key is not None:
            if quantity_key not in normalized_payload:
                raise ValueError(f"payload must contain {quantity_key}")
            require_non_negative_integer(normalized_payload[quantity_key], quantity_key)
        object.__setattr__(self, "payload", normalized_payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version,
            "occurred_at": self.occurred_at.isoformat(),
            "business_date": self.business_date.isoformat(),
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "schema_version": self.schema_version,
            "payload": _serialize_json_value(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DomainEvent:
        if not isinstance(data, Mapping):
            raise TypeError("event data must be a mapping")
        event_type = data.get("event_type")
        if not isinstance(event_type, str) or event_type not in cls.event_registry:
            raise ValueError(f"unknown event_type: {event_type!r}")
        try:
            occurred_at = datetime.fromisoformat(data["occurred_at"])
            business_date = date.fromisoformat(data["business_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("event timestamps must be valid ISO 8601 values") from exc
        event_cls = cls.event_registry[event_type]
        return event_cls(
            event_id=data.get("event_id"),
            aggregate_id=data.get("aggregate_id"),
            aggregate_version=data.get("aggregate_version"),
            occurred_at=occurred_at,
            business_date=business_date,
            causation_id=data.get("causation_id"),
            correlation_id=data.get("correlation_id"),
            idempotency_key=data.get("idempotency_key"),
            payload=data.get("payload"),
            event_type=event_type,
            schema_version=data.get("schema_version", 1),
        )


_EventT = TypeVar("_EventT", bound=type[DomainEvent])


def _register(event_cls: _EventT) -> _EventT:
    DomainEvent.event_registry[event_cls.event_type] = event_cls
    return event_cls


@_register
@dataclass(frozen=True)
class SessionStarted(DomainEvent):
    event_type: str = field(default="SessionStarted", kw_only=True)


@_register
@dataclass(frozen=True)
class PatrolObservationRecorded(DomainEvent):
    event_type: str = field(default="PatrolObservationRecorded", kw_only=True)


@_register
@dataclass(frozen=True)
class ViolationEvidenceAccumulated(DomainEvent):
    event_type: str = field(default="ViolationEvidenceAccumulated", kw_only=True)


@_register
@dataclass(frozen=True)
class StarDeducted(DomainEvent):
    event_type: str = field(default="StarDeducted", kw_only=True)


@_register
@dataclass(frozen=True)
class SessionExpelled(DomainEvent):
    event_type: str = field(default="SessionExpelled", kw_only=True)


@_register
@dataclass(frozen=True)
class SessionCompleted(DomainEvent):
    event_type: str = field(default="SessionCompleted", kw_only=True)


@_register
@dataclass(frozen=True)
class SessionExited(DomainEvent):
    event_type: str = field(default="SessionExited", kw_only=True)


@_register
@dataclass(frozen=True)
class PardonGranted(DomainEvent):
    event_type: str = field(default="PardonGranted", kw_only=True)


@_register
@dataclass(frozen=True)
class PardonPurchased(DomainEvent):
    event_type: str = field(default="PardonPurchased", kw_only=True)


@_register
@dataclass(frozen=True)
class DungeonEntered(DomainEvent):
    event_type: str = field(default="DungeonEntered", kw_only=True)


@_register
@dataclass(frozen=True)
class FocusProgressCredited(DomainEvent):
    event_type: str = field(default="FocusProgressCredited", kw_only=True)
    quantity_key: ClassVar[str] = "seconds"


@_register
@dataclass(frozen=True)
class FocusProgressDebited(DomainEvent):
    event_type: str = field(default="FocusProgressDebited", kw_only=True)
    quantity_key: ClassVar[str] = "seconds"


@_register
@dataclass(frozen=True)
class HonorLevelReached(DomainEvent):
    event_type: str = field(default="HonorLevelReached", kw_only=True)


@_register
@dataclass(frozen=True)
class CurrencyCredited(DomainEvent):
    event_type: str = field(default="CurrencyCredited", kw_only=True)
    quantity_key: ClassVar[str] = "amount"


@_register
@dataclass(frozen=True)
class CurrencyDebited(DomainEvent):
    event_type: str = field(default="CurrencyDebited", kw_only=True)
    quantity_key: ClassVar[str] = "amount"


@_register
@dataclass(frozen=True)
class DailyCheckinClaimed(DomainEvent):
    event_type: str = field(default="DailyCheckinClaimed", kw_only=True)


@_register
@dataclass(frozen=True)
class AbsencePenaltyApplied(DomainEvent):
    event_type: str = field(default="AbsencePenaltyApplied", kw_only=True)


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (datetime, date, Enum)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("payload mapping keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(item)
        return
    raise ValueError(f"payload contains non-JSON-compatible value: {type(value).__name__}")


def _serialize_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("payload datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serialize_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialize_json_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_json_value(item) for item in value]
    return value
