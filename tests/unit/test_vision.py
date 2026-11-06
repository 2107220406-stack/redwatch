from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from focus_game.vision.adapter import JsonVisionAdapter
from focus_game.vision.fake import FakeVisionProvider
from focus_game.vision.openai_compatible import OpenAICompatibleVisionProvider
from focus_game.vision.port import VisionUnavailable
from focus_game.vision.schemas import VisionObservation, VisionVerdict


@pytest.mark.asyncio
async def test_fake_provider_returns_structured_observation() -> None:
    captured_at = datetime(2026, 8, 1, 9, tzinfo=UTC)
    result = await FakeVisionProvider().inspect(b"frame", session_id="s1", captured_at=captured_at)
    assert result.session_id == "s1"
    assert result.verdict is VisionVerdict.COMPLIANT
    assert result.image_retention.value == "DISCARD_AFTER_INFERENCE"


def test_vision_schema_rejects_rule_decision_fields() -> None:
    with pytest.raises(ValidationError):
        VisionObservation.model_validate(
            {
                "observation_id": "o1",
                "session_id": "s1",
                "captured_at": datetime(2026, 8, 1, 9, tzinfo=UTC),
                "overall_confidence": 0.9,
                "model": {"provider": "test", "name": "model", "version": "1"},
                "deduct_star": True,
            }
        )


@pytest.mark.asyncio
async def test_adapter_rejects_model_rule_decisions() -> None:
    async def request_json(image: bytes, session_id: str) -> dict:
        return {"observation_id": "o1", "overall_confidence": 0.9, "deduct_star": True}

    adapter = JsonVisionAdapter(request_json, provider="test", model="model", version="1")
    with pytest.raises(VisionUnavailable):
        await adapter.inspect(
            b"frame", session_id="s1", captured_at=datetime(2026, 8, 1, 9, tzinfo=UTC)
        )


@pytest.mark.asyncio
async def test_openai_compatible_provider_extracts_structured_json(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"verdict":"COMPLIANT","overall_confidence":0.91,'
                                '"violation_type":null,"person_detected":true,'
                                '"workstation_detected":true}'
                            )
                        }
                    }
                ],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, **kwargs):
            assert url == "https://gateway.test/v1/chat/completions"
            assert kwargs["json"]["model"] == "gpt-4o-mini"
            assert kwargs["json"]["messages"][1]["content"][1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
            return FakeResponse()

    monkeypatch.setattr("focus_game.vision.openai_compatible.httpx.AsyncClient", FakeClient)
    result = await OpenAICompatibleVisionProvider(
        "https://gateway.test", model="gpt-4o-mini", api_key="secret"
    ).inspect(b"jpeg", session_id="s1", captured_at=datetime(2026, 8, 1, 9, tzinfo=UTC))
    assert result.verdict is VisionVerdict.COMPLIANT
    assert result.model.name == "gpt-4o-mini"
