"""Development and production authentication helpers."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request, status

from focus_game.settings import AppSettings


def current_player_id(request: Request) -> str:
    settings: AppSettings = request.app.state.settings
    if settings.effective_auth_mode == "header":
        player_id = request.headers.get("X-Player-Id", "demo-player")
        if not player_id.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="player identity is required",
            )
        return player_id

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bearer token is required",
        )
    try:
        return verify_player_token(token, settings.auth_secret.get_secret_value())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_same_player(path_player_id: str, current_id: str) -> None:
    if path_player_id != current_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="player identity does not match request path",
        )


def require_internal_access(request: Request) -> None:
    expected = request.app.state.settings.internal_api_token.get_secret_value()
    supplied = request.headers.get("X-Internal-Token", "")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid internal token is required",
        )


def issue_player_token(player_id: str, secret: str, *, expires_in_seconds: int = 3600) -> str:
    if not player_id.strip():
        raise ValueError("player_id must not be empty")
    if len(secret) < 32:
        raise ValueError("secret must contain at least 32 characters")
    payload = _encode_json({"sub": player_id, "exp": int(time.time()) + expires_in_seconds})
    return f"{payload}.{_sign(payload, secret)}"


def verify_player_token(token: str, secret: str, *, now: int | None = None) -> str:
    try:
        payload_part, signature = token.split(".", 1)
        payload = _decode_json(payload_part)
        expected = _sign(payload_part, secret)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid bearer token signature")
        expires_at = int(payload["exp"])
        player_id = str(payload["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid bearer token") from exc
    if expires_at <= int(time.time() if now is None else now):
        raise ValueError("bearer token has expired")
    if not player_id.strip():
        raise ValueError("bearer token has no player subject")
    return player_id


def _encode_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_json(value: str) -> dict[str, Any]:
    padding = "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value + padding))


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
