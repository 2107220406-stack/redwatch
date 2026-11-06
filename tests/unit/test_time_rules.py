from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from focus_game.config import GameConfig
from focus_game.domain.commands import (
    ApplyAbsencePenalty,
    ClaimDailyCheckin,
    CompleteSession,
    ExitSession,
    RedeemPardon,
    StartSession,
)
from focus_game.domain.enums import SessionStatus
from focus_game.domain.service import DomainError, GameDomainService, PlayerState


def start(service: GameDomainService, state: PlayerState, key: str, now: datetime) -> PlayerState:
    return service.start_session(
        state,
        StartSession(state.player_id, key, key, now),
        now,
        target_seconds=60,
    ).state


def exit_session(
    service: GameDomainService, state: PlayerState, key: str, now: datetime
) -> PlayerState:
    assert state.active_session_id is not None
    return service.exit_session(
        state,
        ExitSession(state.player_id, key, key, now, state.active_session_id),
        now,
    ).state


def test_session_completion_credits_at_most_target_duration() -> None:
    service = GameDomainService()
    started_at = datetime(2026, 8, 1, 1, tzinfo=UTC)
    state = start(service, PlayerState("p1"), "start", started_at)

    decision = service.complete_session(
        state,
        CompleteSession(
            "p1",
            "complete",
            "complete",
            started_at + timedelta(seconds=600),
            state.active_session_id,
        ),
        started_at + timedelta(seconds=600),
    )

    assert decision.state.session_status is SessionStatus.COMPLETED
    assert decision.state.session_worked_seconds == 60
    assert decision.state.focus_progress_seconds == 60
    assert decision.events[0].occurred_at == started_at + timedelta(seconds=600)
    assert decision.events[0].business_date.isoformat() == "2026-08-01"


def test_beijing_business_date_resets_expulsion_count_at_midnight() -> None:
    service = GameDomainService()
    before_midnight = datetime(2026, 7, 31, 15, 59, 59, tzinfo=UTC)
    after_midnight = datetime(2026, 7, 31, 16, tzinfo=UTC)
    state = PlayerState("p1")

    state = start(service, state, "start-1", before_midnight)
    state = exit_session(service, state, "exit-1", before_midnight)
    state = start(service, state, "start-2", before_midnight)
    state = exit_session(service, state, "exit-2", before_midnight)
    state = start(service, state, "start-3", after_midnight)
    state = exit_session(service, state, "exit-3", after_midnight)

    counts = dict(state.daily_expulsions)
    assert counts == {
        datetime(2026, 7, 31).date(): 2,
        datetime(2026, 8, 1).date(): 1,
    }
    assert state.dungeon_until_at is None


def test_third_same_day_expulsion_enters_eight_hour_dungeon_until_exact_boundary() -> None:
    service = GameDomainService()
    expelled_at = datetime(2026, 8, 1, 2, tzinfo=UTC)
    state = PlayerState("p1")

    for index in range(3):
        state = start(service, state, f"start-{index}", expelled_at + timedelta(minutes=index))
        state = exit_session(
            service, state, f"exit-{index}", expelled_at + timedelta(minutes=index)
        )

    assert state.dungeon_until_at == expelled_at + timedelta(minutes=2, hours=8)
    with pytest.raises(DomainError, match="dungeon"):
        start(service, state, "blocked-start", state.dungeon_until_at - timedelta(seconds=1))

    available = start(service, state, "available-start", state.dungeon_until_at)
    assert available.session_status is SessionStatus.WORKING
    assert available.dungeon_until_at is None


def test_free_pardon_refreshes_by_beijing_day_and_clears_dungeon() -> None:
    service = GameDomainService()
    first_day = datetime(2026, 8, 1, 2, tzinfo=UTC)
    next_day = datetime(2026, 8, 1, 16, tzinfo=UTC)
    state = PlayerState(
        "p1",
        expelled_session_ids=("session-1", "session-2", "session-3"),
        dungeon_until_at=first_day + timedelta(hours=8),
    )

    first = service.redeem_pardon(
        state,
        RedeemPardon("p1", "pardon-1", "pardon-1", first_day),
        first_day,
    )
    assert first.state.free_pardon_remaining == 0
    assert first.state.free_pardon_business_date.isoformat() == "2026-08-01"
    assert first.state.dungeon_until_at is None

    second = service.redeem_pardon(
        replace(
            first.state,
            expelled_session_ids=first.state.expelled_session_ids + ("session-4",),
            dungeon_until_at=next_day + timedelta(hours=8),
        ),
        RedeemPardon("p1", "pardon-2", "pardon-2", next_day),
        next_day,
    )
    assert second.state.free_pardon_remaining == 0
    assert second.state.free_pardon_business_date.isoformat() == "2026-08-02"
    assert second.state.currency_balance == 0


def test_pardon_uses_twenty_currency_after_free_entitlement_is_exhausted() -> None:
    service = GameDomainService()
    now = datetime(2026, 8, 1, 2, tzinfo=UTC)
    state = PlayerState(
        "p1",
        expelled_session_ids=("session-1",),
        pardoned_session_ids=(),
        free_pardon_business_date=now.date(),
        free_pardon_remaining=0,
        currency_balance=20,
        dungeon_until_at=now + timedelta(hours=8),
    )

    decision = service.redeem_pardon(
        state,
        RedeemPardon("p1", "pardon-paid", "pardon-paid", now),
        now,
    )

    assert decision.state.currency_balance == 0
    assert decision.state.dungeon_until_at is None
    assert [event.event_type for event in decision.events] == ["CurrencyDebited", "PardonPurchased"]


def test_daily_checkin_rejects_duplicate_and_refreshes_after_beijing_midnight() -> None:
    service = GameDomainService()
    first_day = datetime(2026, 7, 31, 16, tzinfo=UTC)
    next_day = first_day + timedelta(days=1)
    state = PlayerState("p1")

    state = service.claim_daily_checkin(
        state,
        ClaimDailyCheckin("p1", "checkin-1", "checkin-1", first_day),
        first_day,
    ).state
    with pytest.raises(DomainError, match="already claimed"):
        service.claim_daily_checkin(
            state,
            ClaimDailyCheckin("p1", "checkin-duplicate", "checkin-duplicate", first_day),
            first_day,
        )

    refreshed = service.claim_daily_checkin(
        state,
        ClaimDailyCheckin("p1", "checkin-2", "checkin-2", next_day),
        next_day,
    ).state
    assert refreshed.currency_balance == 20
    assert refreshed.last_checkin_business_date.isoformat() == "2026-08-02"


def test_expulsion_penalty_is_five_minutes_but_never_below_honor_floor() -> None:
    service = GameDomainService()
    now = datetime(2026, 8, 1, 2, tzinfo=UTC)
    state = PlayerState("p1", focus_progress_seconds=7200, earned_honor_level=2)
    state = start(service, state, "start", now)
    state = exit_session(service, state, "exit", now)

    assert state.focus_progress_seconds == 6900

    protected = PlayerState("p2", focus_progress_seconds=3600, earned_honor_level=2)
    protected = start(service, protected, "start", now)
    protected = exit_session(service, protected, "exit", now)
    assert protected.focus_progress_seconds == 3600


def test_absence_penalty_configuration_is_thirty_minutes() -> None:
    assert GameConfig().absence_progress_penalty_seconds == 30 * 60


def test_completion_crossing_one_hour_reaches_honor_level_two() -> None:
    service = GameDomainService()
    started_at = datetime(2026, 8, 1, 1, tzinfo=UTC)
    state = PlayerState("p1", focus_progress_seconds=3600 - 60)
    state = start(service, state, "start", started_at)

    completed = service.complete_session(
        state,
        CompleteSession(
            "p1",
            "complete",
            "complete",
            started_at + timedelta(seconds=60),
            state.active_session_id,
        ),
        started_at + timedelta(seconds=60),
    ).state

    assert completed.focus_progress_seconds == 3600
    assert completed.earned_honor_level == 2


def test_absence_penalty_applies_once_per_beijing_day_and_respects_floor() -> None:
    service = GameDomainService()
    active_at = datetime(2026, 8, 1, 2, tzinfo=UTC)
    settled_at = datetime(2026, 8, 1, 16, tzinfo=UTC)
    state = PlayerState(
        "p1",
        focus_progress_seconds=7200,
        earned_honor_level=2,
        last_active_at=active_at,
    )

    decision = service.apply_absence_penalty(
        state,
        ApplyAbsencePenalty("p1", "absence-1", "absence-1", settled_at),
        settled_at,
    )

    assert decision.state.focus_progress_seconds == 5400
    assert decision.state.last_absence_penalty_business_date.isoformat() == "2026-08-02"
    assert [event.event_type for event in decision.events] == [
        "AbsencePenaltyApplied",
        "FocusProgressDebited",
    ]
    with pytest.raises(DomainError, match="already settled"):
        service.apply_absence_penalty(
            decision.state,
            ApplyAbsencePenalty("p1", "absence-2", "absence-2", settled_at),
            settled_at,
        )
