"""Generic HTTP JSON multimodal provider."""

import base64
from datetime import datetime

import httpx

from .adapter import JsonVisionAdapter
from .port import VisionUnavailable
from .schemas import VisionObservation


class HttpJsonVisionProvider:
    def __init__(
        self,
        endpoint: str,
        *,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.adapter = JsonVisionAdapter(
            self._request_json,
            provider="http_json",
            model=model,
            version="1",
        )

    async def inspect(
        self, image: bytes, *, session_id: str, captured_at: datetime
    ) -> VisionObservation:
        return await self.adapter.inspect(image, session_id=session_id, captured_at=captured_at)

    async def _request_json(self, image: bytes, session_id: str) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json={
                        "session_id": session_id,
                        "image_base64": base64.b64encode(image).decode(),
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VisionUnavailable("vision provider request failed") from exc
        if not isinstance(payload, dict):
            raise VisionUnavailable("vision provider returned a non-object response")
        return payload
