"""OpenAI-compatible Chat Completions vision provider."""

import base64
import json
from datetime import datetime

import httpx

from .port import VisionUnavailable
from .schemas import VisionObservation


class OpenAICompatibleVisionProvider:
    def __init__(
        self,
        endpoint: str,
        *,
        model: str,
        api_key: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        base_url = endpoint.rstrip("/")
        self.endpoint = (
            base_url + "/chat/completions"
            if base_url.endswith("/v1")
            else base_url + "/v1/chat/completions"
        )
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def inspect(
        self, image: bytes, *, session_id: str, captured_at: datetime
    ) -> VisionObservation:
        prompt = (
            "Analyze this camera frame conservatively. Return only JSON with exactly these "
            "fields: verdict (COMPLIANT, SUSPECTED_VIOLATION, or UNKNOWN), "
            "overall_confidence (number from 0 to 1), violation_type (PHONE, NO_PERSON, "
            "MULTIPLE_PEOPLE, WORKSTATION_MISSING, or null), person_detected (boolean), "
            "workstation_detected (boolean). Never include game rules or penalties."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 160,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Classify this camera frame."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64," + base64.b64encode(image).decode()
                            },
                        },
                    ],
                },
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
            result = json.loads(content) if isinstance(content, str) else content
            return VisionObservation.model_validate(
                {
                    **result,
                    "observation_id": f"vision_{captured_at.timestamp()}".replace(".", "_"),
                    "session_id": session_id,
                    "captured_at": captured_at,
                    "model": {
                        "provider": "openai_compatible",
                        "name": self.model,
                        "version": "chat-completions",
                    },
                }
            )
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise VisionUnavailable("OpenAI-compatible vision request failed") from exc
