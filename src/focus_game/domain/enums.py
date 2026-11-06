"""Stable wire values used by domain contracts."""

from enum import StrEnum


class SessionStatus(StrEnum):
    READY = "READY"
    WORKING = "WORKING"
    RESTING = "RESTING"
    COMPLETED = "COMPLETED"
    EXPELLED = "EXPELLED"


class WorkStage(StrEnum):
    WORKING = "WORKING"
    RESTING = "RESTING"


class ObservationVerdict(StrEnum):
    COMPLIANT = "COMPLIANT"
    SUSPECTED_VIOLATION = "SUSPECTED_VIOLATION"
    UNKNOWN = "UNKNOWN"


class ViolationType(StrEnum):
    PHONE = "PHONE"
    NO_PERSON = "NO_PERSON"
    MULTIPLE_PEOPLE = "MULTIPLE_PEOPLE"
    WORKSTATION_MISSING = "WORKSTATION_MISSING"
