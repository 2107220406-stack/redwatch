"""Application-independent domain service."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import uuid4

from focus_game.config import GameConfig

from .commands import (
    ApplyAbsencePenalty,
    ClaimDailyCheckin,
    CompleteSession,
    ExitSession,
    PurchasePardon,
    RecordPatrolObservation,
    RedeemPardon,
    StartSession,
)
from .enums import SessionStatus, WorkStage
from .events import (
    AbsencePenaltyApplied,
    CurrencyCredited,
    CurrencyDebited,
    DailyCheckinClaimed,
    DungeonEntered,
    FocusProgressCredited,
    FocusProgressDebited,
    HonorLevelReached,
    PardonGranted,
    PardonPurchased,
    PatrolObservationRecorded,
    SessionCompleted,
    SessionExited,
    SessionExpelled,
    SessionStarted,
    StarDeducted,
    ViolationEvidenceAccumulated,
)
from .models import PatrolObservation, require_non_empty_id, require_non_negative_integer
from .rules import (
    apply_progress_penalty,
    dungeon_until,
    honor_level_for_seconds,
    observation_is_usable,
    protected_progress_seconds,
    should_confirm_violation,
)


class DomainError(ValueError):
    """Expected command rejection."""


@dataclass(frozen=True)
class PlayerState:
    player_id: str
    active_session_id: str | None = None
    session_status: SessionStatus | None = None
    work_stage: WorkStage | None = None
    session_started_at: datetime | None = None
    session_target_seconds: int = 0
    session_worked_seconds: int = 0
    stars: int = 0
    focus_progress_seconds: int = 0
    earned_honor_level: int = 1
    currency_balance: int = 0
    daily_expulsions: tuple[tuple[date, int], ...] = ()
    dungeon_until_at: datetime | None = None
    free_pardon_business_date: date | None = None
    free_pardon_remaining: int = 0
    last_checkin_business_date: date | None = None
    last_absence_penalty_business_date: date | None = None
    last_active_at: datetime | None = None
    previous_observation: dict[str, object] | None = None
    processed_command_keys: tuple[str, ...] = ()
    expelled_session_ids: tuple[str, ...] = ()
    pardoned_session_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty_id(self.player_id, "player_id")
        for field_name in (
            "session_target_seconds",
            "session_worked_seconds",
            "stars",
            "focus_progress_seconds",
            "earned_honor_level",
            "currency_balance",
            "free_pardon_remaining",
        ):
            require_non_negative_integer(getattr(self, field_name), field_name)


@dataclass(frozen=True)
class Decision:
    decision_id: str
    state: PlayerState
    events: tuple[object, ...]
    message: str = ""


class GameDomainService:
    def __init__(
        self, config: GameConfig | None = None, *, violation_confidence: float = 0.85
    ) -> None:
        self.config = config or GameConfig()
        self.violation_confidence = violation_confidence

    def start_session(
        self, state: PlayerState, command: StartSession, now: datetime, target_seconds: int = 1500
    ) -> Decision:
        self._idempotent(state, command.idempotency_key)
        self._available(state, now)
        if target_seconds <= 0:
            raise DomainError("target_seconds must be positive")
        session_id = f"session_{uuid4().hex}"
        expired_dungeon = state.dungeon_until_at is not None and now >= state.dungeon_until_at
        next_state = replace(
            state,
            active_session_id=session_id,
            session_status=SessionStatus.WORKING,
            work_stage=WorkStage.WORKING,
            session_started_at=now,
            session_target_seconds=target_seconds,
            session_worked_seconds=0,
            stars=self.config.initial_stars,
            previous_observation=None,
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
            last_active_at=now,
            dungeon_until_at=None if expired_dungeon else state.dungeon_until_at,
        )
        event = self._event(
            SessionStarted,
            state,
            command,
            now,
            {"session_id": session_id, "target_seconds": target_seconds},
        )
        return Decision(str(uuid4()), next_state, (event,), "session started")

    def record_observation(
        self, state: PlayerState, command: RecordPatrolObservation, now: datetime
    ) -> Decision:
        self._idempotent(state, command.idempotency_key)
        if state.active_session_id != command.session_id:
            raise DomainError("session is not active for player")
        if state.session_status != SessionStatus.WORKING or command.stage != WorkStage.WORKING:
            raise DomainError("observations are accepted only while working")
        observation = dict(command.observation)
        observation["stage"] = command.stage.value
        PatrolObservation(command.observation_id, command.captured_at, command.stage, observation)
        next_state = replace(
            state,
            previous_observation=observation,
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
            last_active_at=now,
        )
        events: list[object] = [
            self._event(
                PatrolObservationRecorded,
                state,
                command,
                now,
                {
                    "session_id": command.session_id,
                    "observation_id": command.observation_id,
                    "observation": observation,
                },
            )
        ]
        if observation_is_usable(observation) and should_confirm_violation(
            state.previous_observation, observation, self.violation_confidence
        ):
            events.append(
                self._event(
                    ViolationEvidenceAccumulated,
                    state,
                    command,
                    now,
                    {"violation_type": observation.get("violation_type")},
                )
            )
            if state.stars > 0:
                remaining = state.stars - 1
                next_state = replace(next_state, stars=remaining)
                events.append(
                    self._event(
                        StarDeducted,
                        state,
                        command,
                        now,
                        {"amount": 1, "remaining_stars": remaining},
                    )
                )
                if remaining == 0:
                    next_state, expulsion_events = self._expel(next_state, command, now)
                    events.extend(expulsion_events)
        return Decision(str(uuid4()), next_state, tuple(events), "observation recorded")

    def complete_session(
        self, state: PlayerState, command: CompleteSession, now: datetime
    ) -> Decision:
        self._idempotent(state, command.idempotency_key)
        if state.active_session_id != command.session_id:
            raise DomainError("session is not active for player")
        if state.session_status == SessionStatus.COMPLETED:
            return Decision(str(uuid4()), state, (), "session already completed")
        if state.session_status != SessionStatus.WORKING:
            raise DomainError("only a working session can be completed")
        worked = self._worked_seconds(state, now)
        credited = max(0, worked - state.session_worked_seconds)
        new_progress = state.focus_progress_seconds + credited
        level = honor_level_for_seconds(new_progress, self.config.honor_threshold_hours)
        next_state = replace(
            state,
            active_session_id=None,
            session_status=SessionStatus.COMPLETED,
            work_stage=None,
            session_worked_seconds=worked,
            focus_progress_seconds=new_progress,
            earned_honor_level=max(state.earned_honor_level, level),
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
            last_active_at=now,
        )
        events: list[object] = [
            self._event(
                SessionCompleted,
                state,
                command,
                now,
                {"session_id": command.session_id, "worked_seconds": worked},
            )
        ]
        if credited:
            events.append(
                self._event(FocusProgressCredited, state, command, now, {"seconds": credited})
            )
        if level > state.earned_honor_level:
            events.append(self._event(HonorLevelReached, state, command, now, {"level": level}))
        return Decision(str(uuid4()), next_state, tuple(events), "session completed")

    def exit_session(self, state: PlayerState, command: ExitSession, now: datetime) -> Decision:
        self._idempotent(state, command.idempotency_key)
        if state.active_session_id != command.session_id:
            raise DomainError("session is not active for player")
        if state.session_status in (SessionStatus.COMPLETED, SessionStatus.EXPELLED):
            return Decision(str(uuid4()), state, (), "session already ended")
        next_state, events = self._expel(state, command, now, voluntary=True)
        next_state = replace(
            next_state,
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
            last_active_at=now,
        )
        return Decision(str(uuid4()), next_state, tuple(events), "session exited")

    def redeem_pardon(self, state: PlayerState, command: RedeemPardon, now: datetime) -> Decision:
        self._idempotent(state, command.idempotency_key)
        if not state.expelled_session_ids:
            raise DomainError("no expelled session to pardon")
        session_id = state.expelled_session_ids[-1]
        if session_id in state.pardoned_session_ids:
            return Decision(str(uuid4()), state, (), "session already pardoned")
        business_date = self.config.business_date(now)
        remaining = state.free_pardon_remaining
        free_date = state.free_pardon_business_date
        if free_date != business_date:
            remaining = self.config.free_daily_pardon_count
            free_date = business_date
        if remaining > 0:
            remaining -= 1
            next_state = replace(
                state,
                free_pardon_business_date=free_date,
                free_pardon_remaining=remaining,
                dungeon_until_at=None,
                pardoned_session_ids=state.pardoned_session_ids + (session_id,),
                processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
            )
            event = self._event(
                PardonGranted, state, command, now, {"session_id": session_id, "source": "FREE"}
            )
            return Decision(str(uuid4()), next_state, (event,), "free pardon granted")
        if state.currency_balance < self.config.paid_pardon_cost:
            raise DomainError("insufficient currency for pardon")
        next_state = replace(
            state,
            currency_balance=state.currency_balance - self.config.paid_pardon_cost,
            dungeon_until_at=None,
            pardoned_session_ids=state.pardoned_session_ids + (session_id,),
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
        )
        events = (
            self._event(
                CurrencyDebited,
                state,
                command,
                now,
                {"amount": self.config.paid_pardon_cost, "reason": "PARDON"},
            ),
            self._event(
                PardonPurchased,
                state,
                command,
                now,
                {"session_id": session_id, "amount": self.config.paid_pardon_cost},
            ),
        )
        return Decision(str(uuid4()), next_state, events, "pardon purchased")

    def purchase_pardon(
        self, state: PlayerState, command: PurchasePardon, now: datetime
    ) -> Decision:
        self._idempotent(state, command.idempotency_key)
        if not state.expelled_session_ids:
            raise DomainError("no expelled session to pardon")
        session_id = state.expelled_session_ids[-1]
        if session_id in state.pardoned_session_ids:
            return Decision(str(uuid4()), state, (), "session already pardoned")
        if state.currency_balance < self.config.paid_pardon_cost:
            raise DomainError("insufficient currency for pardon")
        next_state = replace(
            state,
            currency_balance=state.currency_balance - self.config.paid_pardon_cost,
            dungeon_until_at=None,
            pardoned_session_ids=state.pardoned_session_ids + (session_id,),
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
        )
        events = (
            self._event(
                CurrencyDebited,
                state,
                command,
                now,
                {"amount": self.config.paid_pardon_cost, "reason": "PARDON"},
            ),
            self._event(
                PardonPurchased,
                state,
                command,
                now,
                {"session_id": session_id, "amount": self.config.paid_pardon_cost},
            ),
        )
        return Decision(str(uuid4()), next_state, events, "pardon purchased")

    def claim_daily_checkin(
        self, state: PlayerState, command: ClaimDailyCheckin, now: datetime, reward: int = 10
    ) -> Decision:
        self._idempotent(state, command.idempotency_key)
        business_date = self.config.business_date(now)
        if state.last_checkin_business_date == business_date:
            raise DomainError("daily check-in already claimed")
        next_state = replace(
            state,
            currency_balance=state.currency_balance + reward,
            last_active_at=now,
            last_checkin_business_date=business_date,
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
        )
        events = (
            self._event(
                DailyCheckinClaimed,
                state,
                command,
                now,
                {"business_date": business_date.isoformat()},
            ),
            self._event(
                CurrencyCredited, state, command, now, {"amount": reward, "reason": "DAILY_CHECKIN"}
            ),
        )
        return Decision(str(uuid4()), next_state, events, "daily check-in claimed")

    def apply_absence_penalty(
        self, state: PlayerState, command: ApplyAbsencePenalty, now: datetime
    ) -> Decision:
        self._idempotent(state, command.idempotency_key)
        business_date = self.config.business_date(now)
        if state.last_absence_penalty_business_date == business_date:
            raise DomainError("absence penalty already settled")
        if state.last_active_at is None:
            raise DomainError("player has no activity history")
        active_today = state.last_active_at and (
            self.config.business_date(state.last_active_at) == business_date
        )
        if active_today:
            raise DomainError("player is not absent")
        protected = protected_progress_seconds(
            state.earned_honor_level, self.config.honor_threshold_hours
        )
        new_progress = apply_progress_penalty(
            state.focus_progress_seconds,
            self.config.absence_progress_penalty_seconds,
            protected,
        )
        debited = state.focus_progress_seconds - new_progress
        next_state = replace(
            state,
            focus_progress_seconds=new_progress,
            last_absence_penalty_business_date=business_date,
            processed_command_keys=state.processed_command_keys + (command.idempotency_key,),
        )
        events: list[object] = [
            self._event(
                AbsencePenaltyApplied,
                state,
                command,
                now,
                {"business_date": business_date.isoformat(), "seconds": debited},
            ),
        ]
        if debited:
            events.append(
                self._event(
                    FocusProgressDebited,
                    state,
                    command,
                    now,
                    {"seconds": debited, "reason": "ABSENCE"},
                )
            )
        return Decision(str(uuid4()), next_state, tuple(events), "absence penalty applied")

    def _expel(
        self, state: PlayerState, command: object, now: datetime, voluntary: bool = False
    ) -> tuple[PlayerState, list[object]]:
        session_id = state.active_session_id
        if session_id is None:
            raise DomainError("no active session")
        business_date = self.config.business_date(now)
        count = dict(state.daily_expulsions)
        count[business_date] = count.get(business_date, 0) + 1
        protected = protected_progress_seconds(
            state.earned_honor_level, self.config.honor_threshold_hours
        )
        new_progress = apply_progress_penalty(
            state.focus_progress_seconds, self.config.expulsion_progress_penalty_seconds, protected
        )
        next_state = replace(
            state,
            active_session_id=None,
            session_status=SessionStatus.EXPELLED,
            work_stage=None,
            focus_progress_seconds=new_progress,
            daily_expulsions=tuple(sorted(count.items())),
            expelled_session_ids=state.expelled_session_ids + (session_id,),
            previous_observation=None,
        )
        events: list[object] = [
            self._event(
                SessionExited if voluntary else SessionExpelled,
                state,
                command,
                now,
                {"session_id": session_id, "business_date": business_date.isoformat()},
            ),
            self._event(
                FocusProgressDebited,
                state,
                command,
                now,
                {
                    "seconds": state.focus_progress_seconds - new_progress,
                    "reason": "VOLUNTARY_EXIT" if voluntary else "EXPULSION",
                },
            ),
        ]
        if count[business_date] >= self.config.daily_dungeon_threshold:
            until = dungeon_until(now, self.config.dungeon_duration_hours)
            next_state = replace(next_state, dungeon_until_at=until)
            events.append(
                self._event(
                    DungeonEntered,
                    state,
                    command,
                    now,
                    {"until": until.isoformat(), "business_date": business_date.isoformat()},
                )
            )
        return next_state, events

    def _available(self, state: PlayerState, now: datetime) -> None:
        if state.dungeon_until_at and now < state.dungeon_until_at:
            raise DomainError("player is in dungeon")
        if state.active_session_id is not None:
            raise DomainError("another session is already active")

    def _idempotent(self, state: PlayerState, key: str) -> None:
        if key in state.processed_command_keys:
            raise DomainError("command was already processed")

    def _worked_seconds(self, state: PlayerState, now: datetime) -> int:
        if state.session_started_at is None:
            return state.session_worked_seconds
        elapsed = max(0, int((now - state.session_started_at).total_seconds()))
        return min(state.session_target_seconds, elapsed)

    def _event(
        self,
        event_cls: type,
        state: PlayerState,
        command: object,
        now: datetime,
        payload: dict[str, object],
    ):
        command_key = command.idempotency_key
        correlation_id = command.correlation_id
        return event_cls(
            event_id=f"event_{uuid4().hex}",
            aggregate_id=state.player_id,
            aggregate_version=len(state.processed_command_keys) + 1,
            occurred_at=now,
            business_date=self.config.business_date(now),
            causation_id=None,
            correlation_id=correlation_id,
            idempotency_key=command_key,
            payload=payload,
        )
