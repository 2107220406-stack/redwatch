import re

import pytest
from httpx import ASGITransport, AsyncClient

from focus_game.main import create_app


@pytest.mark.asyncio
async def test_start_session_replays_same_response_for_same_idempotency_key() -> None:
    app = create_app("sqlite+aiosqlite:///:memory:")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-Player-Id": "api-player", "Idempotency-Key": "start-replay"}
            first = await client.post("/sessions", headers=headers, json={"target_seconds": 60})
            replay = await client.post("/sessions", headers=headers, json={"target_seconds": 60})
            conflict = await client.post(
                "/sessions",
                headers=headers,
                json={"target_seconds": 120},
            )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_start_response_contains_aware_server_time_and_stable_state_fields() -> None:
    app = create_app("sqlite+aiosqlite:///:memory:")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/sessions",
                headers={"Idempotency-Key": "time-contract"},
                json={"target_seconds": 60},
            )

    payload = response.json()
    assert response.status_code == 201
    started_at = payload["state"]["session_started_at"]
    assert re.fullmatch(r".*(?:Z|[+-]\d{2}:\d{2})", started_at)
    assert payload["state"]["session_status"] == "WORKING"
    assert payload["state"]["work_stage"] == "WORKING"
    assert payload["state"]["session_target_seconds"] == 60
