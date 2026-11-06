"""Commands accepted by the focus game application layer."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .enums import WorkStage
from .models import PatrolObservation, require_aware_datetime, require_non_empty_id


@dataclass(frozen=True)
class Command:
    player_id: str
    idempotency_key: str
    correlation_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_id(self.player_id, "player_id")
        require_non_empty_id(self.idempotency_key, "idempotency_key")
        require_non_empty_id(self.correlation_id, "correlation_id")
        require_aware_datetime(self.requested_at, "requested_at")


@dataclass(frozen=True)
class StartSession(Command):
    pass


@dataclass(frozen=True)
class RecordPatrolObservation(Command):
    session_id: str
    observation_id: str
    captured_at: datetime
    stage: WorkStage
    observation: Mapping[str, Any]

    def __post_init__(self) -> None:
        super().__post_init__()
        PatrolObservation(
            observation_id=self.observation_id,
            captured_at=self.captured_at,
            stage=self.stage,
            observation=self.observation,
        )
        require_non_empty_id(self.session_id, "session_id")


@dataclass(frozen=True)
class CompleteSession(Command):
    session_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        require_non_empty_id(self.session_id, "session_id")


@dataclass(frozen=True)
class ExitSession(Command):
    session_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        require_non_empty_id(self.session_id, "session_id")


@dataclass(frozen=True)
class RedeemPardon(Command):
    pass


@dataclass(frozen=True)
class PurchasePardon(Command):
    pass


@dataclass(frozen=True)
class ClaimDailyCheckin(Command):
    pass


@dataclass(frozen=True)
class ApplyAbsencePenalty(Command):
    pass
