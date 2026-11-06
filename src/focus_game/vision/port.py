"""Stable port between the application and a multimodal provider."""

from datetime import datetime
from typing import Protocol

from .schemas import VisionObservation


class VisionUnavailable(RuntimeError):
    pass


class VisionProvider(Protocol):
    async def inspect(
        self, image: bytes, *, session_id: str, captured_at: datetime
    ) -> VisionObservation: ...
