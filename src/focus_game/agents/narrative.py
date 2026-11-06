"""Story-only message generation with a deterministic fallback."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NarrativeMessage:
    player_id: str
    text: str
    decision_id: str


class NarrativeAgent:
    """Renders configured story copy without changing game state."""

    def __init__(self, story_messages: dict[str, str]) -> None:
        self.story_messages = story_messages

    def render(self, player_id: str, decision_id: str, event_type: str) -> NarrativeMessage:
        text = self.story_messages.get(
            event_type, self.story_messages.get("default", "状态已更新。")
        )
        return NarrativeMessage(player_id=player_id, text=text, decision_id=decision_id)
