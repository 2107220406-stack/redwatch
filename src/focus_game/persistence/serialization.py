"""JSON conversion for the domain snapshot."""

from datetime import date, datetime
from typing import Any

from focus_game.domain.enums import SessionStatus, WorkStage
from focus_game.domain.service import PlayerState


def state_to_dict(state: PlayerState) -> dict[str, Any]:
    data = dict(state.__dict__)
    for key in ("session_status", "work_stage"):
        value = data[key]
        data[key] = value.value if value is not None else None
    for key in ("session_started_at", "dungeon_until_at", "last_active_at"):
        value = data[key]
        data[key] = value.isoformat() if value is not None else None
    for key in (
        "free_pardon_business_date",
        "last_checkin_business_date",
        "last_absence_penalty_business_date",
    ):
        value = data[key]
        data[key] = value.isoformat() if value is not None else None
    data["daily_expulsions"] = [[day.isoformat(), count] for day, count in state.daily_expulsions]
    return data


def state_from_dict(data: dict[str, Any]) -> PlayerState:
    values = dict(data)
    values.setdefault("last_absence_penalty_business_date", None)
    for key in ("session_started_at", "dungeon_until_at", "last_active_at"):
        if values[key] is not None:
            values[key] = datetime.fromisoformat(values[key])
    for key in (
        "free_pardon_business_date",
        "last_checkin_business_date",
        "last_absence_penalty_business_date",
    ):
        if values[key] is not None:
            values[key] = date.fromisoformat(values[key])
    values["session_status"] = (
        SessionStatus(values["session_status"]) if values["session_status"] else None
    )
    values["work_stage"] = WorkStage(values["work_stage"]) if values["work_stage"] else None
    values["daily_expulsions"] = tuple(
        (date.fromisoformat(day), count) for day, count in values["daily_expulsions"]
    )
    for key in (
        "processed_command_keys",
        "expelled_session_ids",
        "pardoned_session_ids",
    ):
        values[key] = tuple(values.get(key, ()))
    return PlayerState(**values)
