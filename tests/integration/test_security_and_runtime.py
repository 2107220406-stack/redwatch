from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from focus_game.api.auth import issue_player_token
from focus_game.main import create_app
from focus_game.persistence.outbox import deliver_pending, retry_failed
from focus_game.persistence.tables import OutboxRecord
from focus_game.settings import AppSettings


def settings(**overrides) -> AppSettings:
    return AppSettings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        auto_create_schema=True,
        **overrides,
    )


@pytest.mark.asyncio
async def test_player_paths_are_bound_to_authenticated_identity() -> None:
    app = create_app(settings=settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/players/player-b/checkins",
                headers={"X-Player-Id": "player-a", "Idempotency-Key": "checkin"},
            )
            assert response.status_code == 403
            state = await client.get(
                "/players/player-b/state",
                headers={"X-Player-Id": "player-b"},
            )
    assert state.json()["state"]["currency_balance"] == 0


@pytest.mark.asyncio
async def test_idempotency_keys_are_scoped_by_player_and_conflicts_remain_409() -> None:
    app = create_app(settings=settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                "/sessions",
                headers={"X-Player-Id": "player-a", "Idempotency-Key": "shared"},
                json={"target_seconds": 60},
            )
            second = await client.post(
                "/sessions",
                headers={"X-Player-Id": "player-b", "Idempotency-Key": "shared"},
                json={"target_seconds": 60},
            )
            conflict = await client.post(
                "/players/player-a/checkins",
                headers={"X-Player-Id": "player-a", "Idempotency-Key": "shared"},
            )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["state"]["player_id"] == "player-b"
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_hmac_auth_rejects_header_spoofing_and_client_observations() -> None:
    secret = "x" * 32
    app = create_app(settings=settings(auth_mode="hmac", auth_secret=secret))
    token = issue_player_token("secure-player", secret)
    headers = {"Authorization": f"Bearer {token}"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unauthorized = await client.get(
                "/players/secure-player/state",
                headers={"X-Player-Id": "secure-player"},
            )
            started = await client.post(
                "/sessions",
                headers={**headers, "Idempotency-Key": "secure-start"},
                json={"target_seconds": 60},
            )
            session_id = started.json()["state"]["active_session_id"]
            forged = await client.post(
                f"/sessions/{session_id}/observations",
                headers={**headers, "Idempotency-Key": "forged"},
                json={
                    "captured_at": datetime.now(UTC).isoformat(),
                    "observation": {"verdict": "COMPLIANT", "confidence": 0.99},
                },
            )

    assert unauthorized.status_code == 401
    assert started.status_code == 201
    assert forged.status_code == 403


@pytest.mark.asyncio
async def test_multipart_frame_and_state_queries_use_server_provider() -> None:
    app = create_app(settings=settings())
    headers = {"X-Player-Id": "camera-player"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            started = await client.post(
                "/sessions",
                headers={**headers, "Idempotency-Key": "camera-start"},
                json={"target_seconds": 60},
            )
            session_id = started.json()["state"]["active_session_id"]
            frame = await client.post(
                f"/sessions/{session_id}/frames",
                headers={**headers, "Idempotency-Key": "camera-frame"},
                data={"captured_at": "2026-08-01T09:30:00+08:00"},
                files={"image": ("frame.jpg", b"jpeg-data", "image/jpeg")},
            )
            state = await client.get("/players/camera-player/state", headers=headers)
            session_response = await client.get(f"/sessions/{session_id}", headers=headers)

    assert frame.status_code == 200, frame.text
    assert state.status_code == 200
    assert session_response.status_code == 200
    assert session_response.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_camera_capture_time_requires_timezone_offset() -> None:
    app = create_app(settings=settings())
    headers = {"X-Player-Id": "timezone-player"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            started = await client.post(
                "/sessions",
                headers={**headers, "Idempotency-Key": "timezone-start"},
                json={"target_seconds": 60},
            )
            session_id = started.json()["state"]["active_session_id"]
            observation = await client.post(
                f"/sessions/{session_id}/observations",
                headers={**headers, "Idempotency-Key": "timezone-observation"},
                json={
                    "captured_at": "2026-08-01T09:30:00",
                    "observation": {"verdict": "COMPLIANT", "confidence": 0.99},
                },
            )
            frame = await client.post(
                f"/sessions/{session_id}/frames",
                headers={**headers, "Idempotency-Key": "timezone-frame"},
                data={"captured_at": "2026-08-01T09:30:00"},
                files={"image": ("frame.jpg", b"jpeg-data", "image/jpeg")},
            )

    assert observation.status_code == 422
    assert frame.status_code == 422


@pytest.mark.asyncio
async def test_internal_absence_settlement_requires_internal_token() -> None:
    app_settings = settings(internal_api_token="internal-secret")
    app = create_app(settings=app_settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            rejected = await client.post(
                "/internal/players/player-a/absence/settle",
                headers={"Idempotency-Key": "absence"},
            )
            accepted = await client.post(
                "/internal/players/player-a/absence/settle",
                headers={
                    "X-Internal-Token": "internal-secret",
                    "Idempotency-Key": "absence",
                },
            )

    assert rejected.status_code == 401
    assert accepted.status_code == 409
    assert accepted.json()["detail"] == "player has no activity history"


@pytest.mark.asyncio
async def test_outbox_delivery_and_retry_transitions() -> None:
    app = create_app(settings=settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/sessions",
                headers={"Idempotency-Key": "outbox-start"},
                json={"target_seconds": 60},
            )

        delivered_ids: list[str] = []

        async def publish(record: OutboxRecord) -> None:
            delivered_ids.append(record.event_id)

        async with app.state.session_factory() as db:
            delivered = await deliver_pending(db, publish)
            records = list((await db.execute(select(OutboxRecord))).scalars().all())

        assert delivered == 1
        assert len(delivered_ids) == 1
        assert records[0].status == "DELIVERED"

        async def fail(_: OutboxRecord) -> None:
            raise RuntimeError("publisher unavailable")

        records[0].status = "PENDING"
        async with app.state.session_factory() as db:
            stored = await db.get(OutboxRecord, records[0].event_id)
            stored.status = "PENDING"
            await db.commit()
            assert await deliver_pending(db, fail) == 0
            assert await retry_failed(db) == 1


@pytest.mark.asyncio
async def test_historical_session_and_currency_ledger_are_queryable() -> None:
    app = create_app(settings=settings())
    headers = {"X-Player-Id": "history-player"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            started = await client.post(
                "/sessions",
                headers={**headers, "Idempotency-Key": "history-start"},
                json={"target_seconds": 60},
            )
            session_id = started.json()["state"]["active_session_id"]
            completed = await client.post(
                f"/sessions/{session_id}/complete",
                headers={**headers, "Idempotency-Key": "history-complete"},
            )
            session_response = await client.get(f"/sessions/{session_id}", headers=headers)
            await client.post(
                "/players/history-player/checkins",
                headers={**headers, "Idempotency-Key": "history-checkin"},
            )
            ledger = await client.get("/players/history-player/currency/ledger", headers=headers)

    assert completed.status_code == 200
    assert session_response.status_code == 200
    assert session_response.json()["status"] == "COMPLETED"
    assert ledger.status_code == 200
    assert ledger.json()["balance"] == 10
    assert ledger.json()["entries"][0]["amount"] == 10
