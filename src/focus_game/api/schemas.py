"""Pydantic HTTP request and response contracts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from focus_game.domain.enums import ObservationVerdict, ViolationType


class StartSessionRequest(BaseModel):
    target_seconds: int = Field(default=1500, ge=60, le=86400)


class ObservationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: ObservationVerdict
    confidence: float = Field(ge=0, le=1)
    violation_type: ViolationType | None = None
    person_detected: bool | None = None
    workstation_detected: bool | None = None

    @model_validator(mode="after")
    def validate_violation_type(self) -> "ObservationPayload":
        if (
            self.verdict is ObservationVerdict.SUSPECTED_VIOLATION
            and self.violation_type is None
        ):
            raise ValueError("violation_type is required for suspected violations")
        if self.verdict is not ObservationVerdict.SUSPECTED_VIOLATION:
            self.violation_type = None
        return self


class ObservationRequest(BaseModel):
    image: bytes | None = None
    observation: ObservationPayload | None = None
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def captured_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a timezone offset")
        return value


class DecisionResponse(BaseModel):
    decision_id: str
    aggregate_version: int
    message: str
    events: list[dict[str, Any]]
    state: dict[str, Any]


class PardonResponse(DecisionResponse):
    pass


class HonorResponse(BaseModel):
    player_id: str
    focus_progress_seconds: int
    earned_honor_level: int
    currency_balance: int


class PlayerStateResponse(BaseModel):
    state: dict[str, Any]
    aggregate_version: int


class SessionResponse(BaseModel):
    player_id: str
    session_id: str | None
    status: str | None
    stage: str | None
    stars: int
    focus_progress_seconds: int
    currency_balance: int
    dungeon_until: datetime | None
    session_started_at: datetime | None
    session_target_seconds: int
    session_worked_seconds: int


class CurrencyLedgerEntry(BaseModel):
    event_id: str
    aggregate_version: int
    occurred_at: datetime
    amount: int
    reason: str
    event_type: str


class CurrencyLedgerResponse(BaseModel):
    player_id: str
    balance: int
    entries: list[CurrencyLedgerEntry]
