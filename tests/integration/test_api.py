import pytest
from httpx import ASGITransport, AsyncClient

from focus_game.main import create_app


@pytest.mark.asyncio
async def test_health_and_start_session() -> None:
    app = create_app("sqlite+aiosqlite:///:memory:")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/healthz")).json() == {"status": "ok"}
            response = await client.post(
                "/sessions",
                headers={"Idempotency-Key": "start-1"},
                json={"target_seconds": 60},
            )
            assert response.status_code == 201, response.text
            assert response.json()["state"]["stars"] == 3


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_rejected() -> None:
    app = create_app("sqlite+aiosqlite:///:memory:")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/sessions", json={"target_seconds": 60})
            assert response.status_code == 400
