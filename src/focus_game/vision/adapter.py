"""Generic JSON-based multimodal adapter.

The transport is injected so the domain does not depend on a vendor SDK.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from .port import VisionUnavailable
from .schemas import ModelMetadata, VisionObservation


class JsonVisionAdapter:
    def __init__(
        self,
        request_json: Callable[[bytes, str], Awaitable[dict[str, Any]]],
        *,
        provider: str,
        model: str,
        version: str,
    ) -> None:
        self.request_json = request_json
        self.metadata = ModelMetadata(provider=provider, name=model, version=version)

    async def inspect(
        self, image: bytes, *, session_id: str, captured_at: datetime
    ) -> VisionObservation:
        try:
            raw = await self.request_json(image, session_id)
            if any(key in raw for key in ("deduct_star", "enter_dungeon", "currency_amount")):
                raise ValidationError.from_exception_data("VisionObservation", [])
            return VisionObservation.model_validate(
                {
                    **raw,
                    "session_id": session_id,
                    "captured_at": captured_at,
                    "model": self.metadata.model_dump(),
                }
            )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise VisionUnavailable("vision response failed schema validation") from exc
        except TimeoutError as exc:
            raise VisionUnavailable("vision provider timed out") from exc
