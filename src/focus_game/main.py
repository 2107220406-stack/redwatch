"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from focus_game.api.routes import router
from focus_game.config import GameConfig
from focus_game.domain.service import GameDomainService
from focus_game.persistence.database import create_engine, create_schema, session_factory
from focus_game.settings import AppSettings
from focus_game.vision.fake import FakeVisionProvider
from focus_game.vision.http import HttpJsonVisionProvider
from focus_game.vision.openai_compatible import OpenAICompatibleVisionProvider
from focus_game.vision.port import VisionProvider


def create_app(
    database_url: str | None = None,
    *,
    settings: AppSettings | None = None,
    vision_provider: VisionProvider | None = None,
) -> FastAPI:
    app_settings = settings or AppSettings()
    if database_url is not None:
        app_settings = app_settings.model_copy(update={"database_url": database_url})
    app_settings.validate_runtime()
    engine = create_engine(app_settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app_settings.schema_auto_create_enabled:
            await create_schema(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="Focus Companion Game API", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.settings = app_settings
    app.state.session_factory = session_factory(engine)
    app.state.domain_service = GameDomainService(
        GameConfig(timezone_name=app_settings.app_timezone)
    )
    app.state.vision_provider = vision_provider or _build_vision_provider(app_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/camera-smoke", include_in_schema=False)
    async def camera_smoke_page() -> FileResponse:
        return FileResponse(Path(__file__).resolve().parents[2] / "docs" / "camera-smoke.html")

    return app


def _build_vision_provider(settings: AppSettings) -> VisionProvider:
    if settings.vision_provider == "fake":
        return FakeVisionProvider()
    if settings.vision_provider == "http_json":
        api_key = (
            settings.vision_api_key.get_secret_value() if settings.vision_api_key else None
        )
        return HttpJsonVisionProvider(
            settings.vision_endpoint or "",
            model=settings.vision_model,
            api_key=api_key,
            timeout_seconds=settings.vision_timeout_seconds,
        )
    if settings.vision_provider == "openai_compatible":
        return OpenAICompatibleVisionProvider(
            settings.vision_endpoint or "",
            model=settings.vision_model,
            api_key=settings.vision_api_key.get_secret_value() if settings.vision_api_key else "",
            timeout_seconds=settings.vision_timeout_seconds,
        )
    raise RuntimeError(
        f"vision provider {settings.vision_provider!r} requires an injected "
        "VisionProvider implementation"
    )


app = create_app()
