from datetime import UTC, date, datetime

import pytest

from focus_game.domain.events import (
    CurrencyCredited,
    DomainEvent,
    FocusProgressDebited,
    PatrolObservationRecorded,
    SessionStarted,
)


def event_kwargs() -> dict[str, object]:
    return {
        "event_id": "event-1",
        "aggregate_id": "session-1",
        "aggregate_version": 1,
        "occurred_at": datetime(2026, 8, 1, 9, tzinfo=UTC),
        "business_date": date(2026, 8, 1),
        "causation_id": None,
        "correlation_id": "corr-1",
        "idempotency_key": "command-1",
        "payload": {"session_id": "session-1"},
    }


def test_event_round_trips_with_type_and_timezone_preserved() -> None:
    original = SessionStarted(**event_kwargs())

    serialized = original.to_dict()
    restored = DomainEvent.from_dict(serialized)

    assert serialized["event_type"] == "SessionStarted"
    assert serialized["occurred_at"] == "2026-08-01T09:00:00+00:00"
    assert serialized["business_date"] == "2026-08-01"
    assert isinstance(restored, SessionStarted)
    assert restored == original


def test_event_payload_is_json_compatible() -> None:
    event = PatrolObservationRecorded(
        payload={
            "captured_at": datetime(2026, 8, 1, 17, tzinfo=UTC),
            "business_date": date(2026, 8, 2),
        },
        **{key: value for key, value in event_kwargs().items() if key != "payload"},
    )

    payload = event.to_dict()["payload"]

    assert payload == {
        "captured_at": "2026-08-01T17:00:00+00:00",
        "business_date": "2026-08-02",
    }


def test_events_reject_empty_ids_naive_times_and_negative_amounts() -> None:
    with pytest.raises(ValueError, match="event_id"):
        SessionStarted(**{**event_kwargs(), "event_id": " "})
    with pytest.raises(ValueError, match="timezone-aware"):
        SessionStarted(**{**event_kwargs(), "occurred_at": datetime(2026, 8, 1, 9)})
    with pytest.raises(ValueError, match="non-negative integer"):
        CurrencyCredited(**{**event_kwargs(), "payload": {"amount": -1}})
    with pytest.raises(ValueError, match="non-negative integer"):
        FocusProgressDebited(**{**event_kwargs(), "payload": {"seconds": -1}})


def test_event_schema_version_defaults_and_unknown_types_are_rejected() -> None:
    event = SessionStarted(**event_kwargs())

    assert event.schema_version == 1
    with pytest.raises(ValueError, match="event_type"):
        DomainEvent.from_dict({**event.to_dict(), "event_type": "NotAnEvent"})
