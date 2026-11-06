"""Deterministic provider used by tests and local development."""

from datetime import datetime

from .schemas import ModelMetadata, VisionObservation, VisionVerdict


class FakeVisionProvider:
    def __init__(
        self, *, verdict: VisionVerdict = VisionVerdict.COMPLIANT, confidence: float = 0.95
    ) -> None:
        self.verdict = verdict
        self.confidence = confidence

    async def inspect(
        self, image: bytes, *, session_id: str, captured_at: datetime
    ) -> VisionObservation:
        del image
        return VisionObservation(
            observation_id=f"vision_{captured_at.timestamp()}".replace(".", "_"),
            session_id=session_id,
            captured_at=captured_at,
            person_detected=True,
            workstation_detected=True,
            overall_confidence=self.confidence,
            verdict=self.verdict,
            model=ModelMetadata(provider="fake", name="fake-model", version="1"),
        )
