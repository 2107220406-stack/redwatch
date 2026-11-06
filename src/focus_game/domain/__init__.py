"""Pure domain contracts for the focus companion game."""

from .enums import ObservationVerdict, SessionStatus, ViolationType, WorkStage
from .events import DomainEvent

__all__ = [
    "DomainEvent",
    "ObservationVerdict",
    "SessionStatus",
    "ViolationType",
    "WorkStage",
]
