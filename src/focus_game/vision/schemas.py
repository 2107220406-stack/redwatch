"""Provider-neutral structured vision observations."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageRetention(StrEnum):
    DISCARD_AFTER_INFERENCE = "DISCARD_AFTER_INFERENCE"
    RETAIN_FOR_APPEAL = "RETAIN_FOR_APPEAL"


class VisionVerdict(StrEnum):
    COMPLIANT = "COMPLIANT"
    SUSPECTED_VIOLATION = "SUSPECTED_VIOLATION"
    UNKNOWN = "UNKNOWN"


class DistractionObservation(BaseModel):
    type: str
    present: bool
    confidence: float = Field(ge=0, le=1)


class PoseObservation(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)


class GazeObservation(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)


class ModelMetadata(BaseModel):
    provider: str
    name: str
    version: str


class VisionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    session_id: str
    captured_at: datetime
    person_detected: bool | None = None
    workstation_detected: bool | None = None
    distractions: list[DistractionObservation] = Field(default_factory=list)
    posture: PoseObservation | None = None
    gaze: GazeObservation | None = None
    people_count: int | None = Field(default=None, ge=0)
    overall_confidence: float = Field(ge=0, le=1)
    verdict: VisionVerdict = VisionVerdict.UNKNOWN
    violation_type: str | None = None
    model: ModelMetadata
    image_retention: ImageRetention = ImageRetention.DISCARD_AFTER_INFERENCE

    @field_validator("observation_id", "session_id")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be empty")
        return value
