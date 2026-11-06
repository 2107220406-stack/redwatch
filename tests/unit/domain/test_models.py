from datetime import UTC, date, datetime

import pytest

from focus_game.config import GameConfig
from focus_game.domain.commands import (
    ClaimDailyCheckin,
    CompleteSession,
    RecordPatrolObservation,
    StartSession,
)
from focus_game.domain.enums import (
    ObservationVerdict,
    SessionStatus,
    ViolationType,
    WorkStage,
)


def test_default_config_matches_rules() -> None:
    config = GameConfig()

    assert config.timezone_name == "Asia/Shanghai"
    assert config.initial_stars == 3
    assert config.daily_dungeon_threshold == 3
    assert config.dungeon_duration_hours == 8
    assert config.free_daily_pardon_count == 1
    assert config.paid_pardon_cost == 20
    assert config.expulsion_progress_penalty_seconds == 300
    assert config.absence_progress_penalty_seconds == 1800
    assert config.honor_threshold_hours == (0, 1, 10, 50, 100, 300, 600, 1000)


def test_business_date_uses_shanghai_midnight() -> None:
    instant = datetime(2026, 7, 31, 16, 30, tzinfo=UTC)

    assert GameConfig().business_date(instant) == date(2026, 8, 1)


def test_config_rejects_invalid_rules() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        GameConfig(honor_threshold_hours=(0, 1, 1))
    with pytest.raises(ValueError, match="non-negative"):
        GameConfig(paid_pardon_cost=-1)
    with pytest.raises(ValueError, match="positive"):
        GameConfig(dungeon_duration_hours=0)
    with pytest.raises(ValueError, match="at least 1"):
        GameConfig(initial_stars=0)


def test_domain_enums_use_stable_wire_values() -> None:
    assert SessionStatus.WORKING.value == "WORKING"
    assert WorkStage.RESTING.value == "RESTING"
    assert ObservationVerdict.UNKNOWN.value == "UNKNOWN"
    assert ViolationType.WORKSTATION_MISSING.value == "WORKSTATION_MISSING"


def test_commands_require_non_empty_identity_and_aware_time() -> None:
    requested_at = datetime(2026, 8, 1, 9, tzinfo=UTC)
    command = StartSession(
        player_id="player-1",
        idempotency_key="start-1",
        correlation_id="corr-1",
        requested_at=requested_at,
    )

    assert command.player_id == "player-1"
    assert command.requested_at == requested_at

    with pytest.raises(ValueError, match="player_id"):
        StartSession(
            player_id="",
            idempotency_key="start-1",
            correlation_id="corr-1",
            requested_at=requested_at,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        StartSession(
            player_id="player-1",
            idempotency_key="start-1",
            correlation_id="corr-1",
            requested_at=datetime(2026, 8, 1, 9),
        )


def test_observation_command_contains_replay_protection_metadata() -> None:
    captured_at = datetime(2026, 8, 1, 9, 5, tzinfo=UTC)
    command = RecordPatrolObservation(
        player_id="player-1",
        idempotency_key="obs-write-1",
        correlation_id="corr-1",
        requested_at=captured_at,
        session_id="session-1",
        observation_id="observation-1",
        captured_at=captured_at,
        stage=WorkStage.WORKING,
        observation={
            "verdict": ObservationVerdict.SUSPECTED_VIOLATION.value,
            "violation_type": ViolationType.PHONE.value,
            "confidence": 0.93,
        },
    )

    assert command.stage is WorkStage.WORKING
    assert command.observation["confidence"] == 0.93


def test_commands_validate_session_ids_and_non_negative_values() -> None:
    requested_at = datetime(2026, 8, 1, 9, tzinfo=UTC)
    complete = CompleteSession(
        player_id="player-1",
        idempotency_key="complete-1",
        correlation_id="corr-1",
        requested_at=requested_at,
        session_id="session-1",
    )
    claim = ClaimDailyCheckin(
        player_id="player-1",
        idempotency_key="checkin-1",
        correlation_id="corr-1",
        requested_at=requested_at,
    )

    assert complete.session_id == "session-1"
    assert claim.player_id == "player-1"

    with pytest.raises(ValueError, match="session_id"):
        CompleteSession(
            player_id="player-1",
            idempotency_key="complete-1",
            correlation_id="corr-1",
            requested_at=requested_at,
            session_id=" ",
        )
