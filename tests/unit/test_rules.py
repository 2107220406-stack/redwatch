from datetime import UTC, datetime, timedelta

from focus_game.domain.commands import ExitSession, RecordPatrolObservation, StartSession
from focus_game.domain.enums import ViolationType, WorkStage
from focus_game.domain.service import GameDomainService, PlayerState


def command(key: str, now: datetime, session_id: str) -> RecordPatrolObservation:
    return RecordPatrolObservation(
        "p1",
        key,
        "corr-" + key,
        now,
        session_id,
        "obs-" + key,
        now,
        WorkStage.WORKING,
        {
            "verdict": "SUSPECTED_VIOLATION",
            "violation_type": ViolationType.PHONE.value,
            "confidence": 0.95,
        },
    )


def test_three_stars_and_continuous_violation_expel() -> None:
    service = GameDomainService()
    now = datetime(2026, 8, 1, 9, tzinfo=UTC)
    started = service.start_session(PlayerState("p1"), StartSession("p1", "start", "c", now), now)
    state = started.state
    session_id = state.active_session_id
    state = service.record_observation(state, command("one", now, session_id), now).state
    state = service.record_observation(
        state, command("two", now + timedelta(seconds=10), session_id), now
    ).state
    assert state.stars == 2

    for index in range(2, 4):
        state = service.record_observation(
            state,
            command(f"obs-{index}", now + timedelta(seconds=index * 10), session_id),
            now,
        ).state
    assert state.session_status.value == "EXPELLED"
    assert state.active_session_id is None


def test_progress_penalty_respects_honor_floor_and_dungeon_threshold() -> None:
    service = GameDomainService()
    now = datetime(2026, 8, 1, 9, tzinfo=UTC)
    state = PlayerState(
        "p1", focus_progress_seconds=3600, earned_honor_level=2, currency_balance=20
    )
    state = service.start_session(state, StartSession("p1", "start", "c", now), now).state
    state = service.exit_session(
        state,
        ExitSession("p1", "exit", "c2", now, state.active_session_id),
        now,
    ).state
    assert state.focus_progress_seconds == 3600
