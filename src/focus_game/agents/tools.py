"""Explicit tool boundary exposed to deepagents."""

from typing import Any

from focus_game.domain.commands import RecordPatrolObservation
from focus_game.domain.service import Decision, GameDomainService, PlayerState


class GameAgentTools:
    def __init__(self, service: GameDomainService) -> None:
        self.service = service

    def get_session_snapshot(self, state: PlayerState) -> dict[str, Any]:
        return {
            "player_id": state.player_id,
            "session_id": state.active_session_id,
            "status": state.session_status.value if state.session_status else None,
            "stage": state.work_stage.value if state.work_stage else None,
            "stars": state.stars,
            "focus_progress_seconds": state.focus_progress_seconds,
        }

    def submit_observation(
        self, state: PlayerState, command: RecordPatrolObservation, now
    ) -> Decision:
        return self.service.record_observation(state, command, now)

    @staticmethod
    def send_narrative_notice(player_id: str, message: str) -> dict[str, str]:
        return {"player_id": player_id, "message": message}
