"""Core HTTP routes."""

import hashlib
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from focus_game.domain.commands import (
    ApplyAbsencePenalty,
    ClaimDailyCheckin,
    CompleteSession,
    ExitSession,
    PurchasePardon,
    RecordPatrolObservation,
    RedeemPardon,
    StartSession,
)
from focus_game.domain.enums import WorkStage
from focus_game.domain.service import DomainError, GameDomainService
from focus_game.persistence.event_store import ConcurrencyConflict, EventStore, IdempotencyConflict
from focus_game.persistence.serialization import state_to_dict
from focus_game.vision.port import VisionUnavailable

from .auth import require_internal_access, require_same_player
from .dependencies import current_player_id, db_session, domain_service
from .schemas import (
    CurrencyLedgerEntry,
    CurrencyLedgerResponse,
    DecisionResponse,
    HonorResponse,
    ObservationRequest,
    PlayerStateResponse,
    SessionResponse,
    StartSessionRequest,
)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(UTC)


def _command_key(value: str | None) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return value


def _require_aware_captured_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="captured_at must include a timezone offset",
        )
    return value


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, DomainError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (ConcurrencyConflict, IdempotencyConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, VisionUnavailable):
        return HTTPException(status_code=503, detail="vision provider unavailable")
    return HTTPException(status_code=500, detail="internal error")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(db_session)) -> dict[str, str]:
    try:
        await session.connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}


@router.post("/sessions", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    request: StartSessionRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    player_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    key = _command_key(idempotency_key)
    store = EventStore(session)
    state, version = await store.load_state(player_id)
    now = _now()
    request_data = request.model_dump()
    command = StartSession(player_id, key, key, now)
    try:
        replay = await store.get_idempotent_response(player_id, key, request_data)
        if replay is not None:
            return DecisionResponse.model_validate(replay)
        decision = service.start_session(state, command, now, request.target_seconds)
        result = await store.append(
            player_id=player_id,
            expected_version=version,
            command_key=key,
            request=request_data,
            decision=decision,
        )
        await session.commit()
        return DecisionResponse.model_validate(result.response)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/observations", response_model=DecisionResponse)
async def observation(
    session_id: str,
    body: ObservationRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    player_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    key = _command_key(idempotency_key)
    store = EventStore(session)
    state, version = await store.load_state(player_id)
    now = _now()
    request_data = body.model_dump(mode="json")
    try:
        replay = await store.get_idempotent_response(player_id, key, request_data)
        if replay is not None:
            return DecisionResponse.model_validate(replay)
        if body.observation is not None:
            if not request.app.state.settings.client_observation_enabled:
                raise HTTPException(
                    status_code=403,
                    detail="client-provided observations are disabled",
                )
            observation_data = body.observation.model_dump(mode="json")
        else:
            if not body.image:
                raise HTTPException(status_code=422, detail="camera image is required")
            if len(body.image) > request.app.state.settings.max_image_bytes:
                raise HTTPException(status_code=413, detail="camera image is too large")
            result = await request.app.state.vision_provider.inspect(
                body.image or b"",
                session_id=session_id,
                captured_at=body.captured_at,
            )
            observation_data = {
                "verdict": result.verdict.value,
                "confidence": result.overall_confidence,
                "violation_type": result.violation_type,
                "person_detected": result.person_detected,
                "workstation_detected": result.workstation_detected,
            }
        command = RecordPatrolObservation(
            player_id,
            key,
            key,
            now,
            session_id,
            f"observation_{key}",
            body.captured_at,
            WorkStage.WORKING,
            observation_data,
        )
        decision = service.record_observation(state, command, now)
        result = await store.append(
            player_id=player_id,
            expected_version=version,
            command_key=key,
            request=request_data,
            decision=decision,
        )
        await session.commit()
        return DecisionResponse.model_validate(result.response)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/frames", response_model=DecisionResponse)
async def inspect_frame(
    session_id: str,
    request: Request,
    captured_at: datetime = Form(...),
    image: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    player_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    key = _command_key(idempotency_key)
    _require_aware_captured_at(captured_at)
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="unsupported camera image type")
    max_bytes = request.app.state.settings.max_image_bytes
    frame = await image.read(max_bytes + 1)
    if not frame:
        raise HTTPException(status_code=422, detail="camera image is empty")
    if len(frame) > max_bytes:
        raise HTTPException(status_code=413, detail="camera image is too large")

    request_data = {
        "captured_at": captured_at.isoformat(),
        "content_type": image.content_type,
        "image_sha256": hashlib.sha256(frame).hexdigest(),
    }
    store = EventStore(session)
    state, version = await store.load_state(player_id)
    now = _now()
    try:
        replay = await store.get_idempotent_response(player_id, key, request_data)
        if replay is not None:
            return DecisionResponse.model_validate(replay)
        result = await request.app.state.vision_provider.inspect(
            frame,
            session_id=session_id,
            captured_at=captured_at,
        )
        observation_data = {
            "verdict": result.verdict.value,
            "confidence": result.overall_confidence,
            "violation_type": result.violation_type,
            "person_detected": result.person_detected,
            "workstation_detected": result.workstation_detected,
        }
        command = RecordPatrolObservation(
            player_id,
            key,
            key,
            now,
            session_id,
            f"observation_{key}",
            captured_at,
            WorkStage.WORKING,
            observation_data,
        )
        decision = service.record_observation(state, command, now)
        appended = await store.append(
            player_id=player_id,
            expected_version=version,
            command_key=key,
            request=request_data,
            decision=decision,
        )
        await session.commit()
        return DecisionResponse.model_validate(appended.response)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/complete", response_model=DecisionResponse)
async def complete_session(
    session_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    player_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    key = _command_key(idempotency_key)
    store = EventStore(session)
    state, version = await store.load_state(player_id)
    now = _now()
    command = CompleteSession(player_id, key, key, now, session_id)
    try:
        request_data = {"session_id": session_id, "action": "complete"}
        replay = await store.get_idempotent_response(player_id, key, request_data)
        if replay is not None:
            return DecisionResponse.model_validate(replay)
        decision = service.complete_session(state, command, now)
        result = await store.append(
            player_id=player_id,
            expected_version=version,
            command_key=key,
            request=request_data,
            decision=decision,
        )
        await session.commit()
        return DecisionResponse.model_validate(result.response)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/exit", response_model=DecisionResponse)
async def exit_session(
    session_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    player_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    key = _command_key(idempotency_key)
    store = EventStore(session)
    state, version = await store.load_state(player_id)
    now = _now()
    command = ExitSession(player_id, key, key, now, session_id)
    try:
        request_data = {"session_id": session_id, "action": "exit"}
        replay = await store.get_idempotent_response(player_id, key, request_data)
        if replay is not None:
            return DecisionResponse.model_validate(replay)
        decision = service.exit_session(state, command, now)
        result = await store.append(
            player_id=player_id,
            expected_version=version,
            command_key=key,
            request=request_data,
            decision=decision,
        )
        await session.commit()
        return DecisionResponse.model_validate(result.response)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.get("/players/{player_id}/state", response_model=PlayerStateResponse)
async def player_state(
    player_id: str,
    current_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
) -> PlayerStateResponse:
    require_same_player(player_id, current_id)
    state, version = await EventStore(session).load_state(player_id)
    return PlayerStateResponse(state=state_to_dict(state), aggregate_version=version)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def session_snapshot(
    session_id: str,
    player_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> SessionResponse:
    store = EventStore(session)
    state, _ = await store.load_state(player_id)
    events = list(await store.list_events(player_id))
    start_index = next(
        (
            index
            for index, event in enumerate(events)
            if event.event_type == "SessionStarted"
            and event.payload.get("session_id") == session_id
        ),
        None,
    )
    if start_index is None:
        raise HTTPException(status_code=404, detail="session not found")
    end_index = next(
        (
            index
            for index in range(start_index + 1, len(events))
            if events[index].event_type == "SessionStarted"
        ),
        len(events),
    )
    session_events = events[start_index:end_index]
    started_event = session_events[0]
    started_at = started_event.occurred_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    target_seconds = int(started_event.payload.get("target_seconds", 0))
    response_status = "WORKING"
    response_stage: str | None = "WORKING"
    worked_seconds = 0
    stars = service.config.initial_stars
    dungeon_until = None
    for event in session_events:
        if event.event_type == "StarDeducted":
            stars = int(event.payload.get("remaining_stars", stars))
        elif event.event_type == "SessionCompleted":
            response_status = "COMPLETED"
            response_stage = None
            worked_seconds = int(event.payload.get("worked_seconds", 0))
        elif event.event_type in {"SessionExited", "SessionExpelled"}:
            response_status = "EXPELLED"
            response_stage = None
        elif event.event_type == "DungeonEntered":
            until = event.payload.get("until")
            dungeon_until = datetime.fromisoformat(str(until)) if until else None
    if state.active_session_id == session_id:
        response_status = state.session_status.value if state.session_status else response_status
        response_stage = state.work_stage.value if state.work_stage else None
        started_for_clock = state.session_started_at or _now()
        worked_seconds = min(
            state.session_target_seconds,
            max(0, int((_now() - started_for_clock).total_seconds())),
        )
        stars = state.stars
        dungeon_until = state.dungeon_until_at
    return SessionResponse(
        player_id=player_id,
        session_id=session_id,
        status=response_status,
        stage=response_stage,
        stars=stars,
        focus_progress_seconds=state.focus_progress_seconds,
        currency_balance=state.currency_balance,
        dungeon_until=dungeon_until,
        session_started_at=started_at,
        session_target_seconds=target_seconds,
        session_worked_seconds=worked_seconds,
    )


@router.get("/players/{player_id}/honor", response_model=HonorResponse)
async def honor(
    player_id: str,
    current_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
) -> HonorResponse:
    require_same_player(player_id, current_id)
    state, _ = await EventStore(session).load_state(player_id)
    return HonorResponse(
        player_id=player_id,
        focus_progress_seconds=state.focus_progress_seconds,
        earned_honor_level=state.earned_honor_level,
        currency_balance=state.currency_balance,
    )


@router.get("/players/{player_id}/currency/ledger", response_model=CurrencyLedgerResponse)
async def currency_ledger(
    player_id: str,
    current_id: str = Depends(current_player_id),
    session: AsyncSession = Depends(db_session),
) -> CurrencyLedgerResponse:
    require_same_player(player_id, current_id)
    store = EventStore(session)
    state, _ = await store.load_state(player_id)
    events = await store.list_events(player_id)
    entries = []
    for event in events:
        if event.event_type not in {"CurrencyCredited", "CurrencyDebited"}:
            continue
        amount = int(event.payload.get("amount", 0))
        if event.event_type == "CurrencyDebited":
            amount = -amount
        occurred_at = event.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        entries.append(
            CurrencyLedgerEntry(
                event_id=event.event_id,
                aggregate_version=event.aggregate_version,
                occurred_at=occurred_at,
                amount=amount,
                reason=str(event.payload.get("reason", "UNKNOWN")),
                event_type=event.event_type,
            )
        )
    return CurrencyLedgerResponse(
        player_id=player_id,
        balance=state.currency_balance,
        entries=entries,
    )


async def _apply_player_command(
    player_id: str,
    key: str,
    request_data: dict,
    command: object,
    session: AsyncSession,
    service: GameDomainService,
    action,
) -> DecisionResponse:
    store = EventStore(session)
    try:
        replay = await store.get_idempotent_response(player_id, key, request_data)
        if replay is not None:
            return DecisionResponse.model_validate(replay)
        state, version = await store.load_state(player_id)
        now = _now()
        decision = action(service, state, command, now)
        result = await store.append(
            player_id=player_id,
            expected_version=version,
            command_key=key,
            request=request_data,
            decision=decision,
        )
        await session.commit()
        return DecisionResponse.model_validate(result.response)
    except Exception as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/players/{player_id}/pardons/redeem", response_model=DecisionResponse)
async def redeem_pardon(
    player_id: str,
    current_id: str = Depends(current_player_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    require_same_player(player_id, current_id)
    key = _command_key(idempotency_key)
    command = RedeemPardon(player_id, key, key, _now())
    return await _apply_player_command(
        player_id,
        key,
        {"action": "redeem_pardon"},
        command,
        session,
        service,
        lambda svc, state, cmd, now: svc.redeem_pardon(state, cmd, now),
    )


@router.post("/players/{player_id}/pardons/purchase", response_model=DecisionResponse)
async def purchase_pardon(
    player_id: str,
    current_id: str = Depends(current_player_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    require_same_player(player_id, current_id)
    key = _command_key(idempotency_key)
    command = PurchasePardon(player_id, key, key, _now())
    return await _apply_player_command(
        player_id,
        key,
        {"action": "purchase_pardon"},
        command,
        session,
        service,
        lambda svc, state, cmd, now: svc.purchase_pardon(state, cmd, now),
    )


@router.post("/players/{player_id}/checkins", response_model=DecisionResponse)
async def checkin(
    player_id: str,
    current_id: str = Depends(current_player_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    require_same_player(player_id, current_id)
    key = _command_key(idempotency_key)
    command = ClaimDailyCheckin(player_id, key, key, _now())
    return await _apply_player_command(
        player_id,
        key,
        {"action": "daily_checkin"},
        command,
        session,
        service,
        lambda svc, state, cmd, now: svc.claim_daily_checkin(state, cmd, now),
    )


@router.post("/internal/players/{player_id}/absence/settle", response_model=DecisionResponse)
async def settle_absence(
    player_id: str,
    _: None = Depends(require_internal_access),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(db_session),
    service: GameDomainService = Depends(domain_service),
) -> DecisionResponse:
    key = _command_key(idempotency_key)
    command = ApplyAbsencePenalty(player_id, key, key, _now())
    return await _apply_player_command(
        player_id,
        key,
        {"action": "absence_settle"},
        command,
        session,
        service,
        lambda svc, state, cmd, now: svc.apply_absence_penalty(state, cmd, now),
    )
