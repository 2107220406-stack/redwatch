# Focus Companion Game Backend Implementation Plan

## Goal

Build a story-configurable focus-work game backend. The deterministic domain service owns
stars, expulsions, dungeon time, pardons, honor, progress, and currency. The multimodal
vision model only returns structured observations. `deepagents` only orchestrates patrol
flows and generates narrative text.

## Stack

- Python 3.11+
- `uv` environment and lock file
- Tsinghua PyPI mirror: `https://pypi.tuna.tsinghua.edu.cn/simple`
- FastAPI and Pydantic
- SQLAlchemy, Alembic, and PostgreSQL
- `deepagents`
- pytest and Ruff

## Implementation order

1. Domain contracts: configuration, state, commands, events, and serialization.
2. Deterministic rules: sessions, patrol evidence windows, stars, expulsions, dungeon,
   pardons, honor, progress, and currency.
3. Event persistence: PostgreSQL tables, idempotency, optimistic concurrency, projections,
   and outbox.
4. HTTP API: sessions, patrol observations, completion, exit, pardons, check-ins, honor,
   and currency queries.
5. Vision: single-frame input, provider-neutral observation schema, fake provider, and
   multimodal provider adapter.
6. Agent orchestration: restricted tools, supervisor, story configuration, and narrative
   fallback.
7. Operations: privacy deletion, audit data, cross-day tests, retries, and end-to-end tests.

## Invariants

- A vision model cannot decide or modify stars, currency, dungeon time, progress, or honor.
- An Agent cannot directly write to the database.
- Low confidence, model timeout, and image parsing failure cannot deduct a star.
- Every entitlement change is an immutable event with an idempotency key.
- Database timestamps are UTC; business dates use `Asia/Shanghai`.
- Camera frames are discarded after inference by default.

## Acceptance

- Three stars, continuous violation evidence, and zero-star expulsion are replayable.
- The third same-day expulsion enters an eight-hour dungeon.
- One free pardon is available per Beijing business day; paid pardon costs 20 currency.
- Honor thresholds are 0, 1, 10, 50, 100, 300, 600, and 1000 focus hours.
- Expulsion and voluntary exit deduct five minutes; absence deducts 30 minutes per day,
  subject to the earned-honor floor.
- Retries do not duplicate stars, currency, pardons, or settlement.
- The system continues safely when vision is unavailable.
- `uv run pytest -q`, `uv run ruff check src tests migrations`, and Python compilation pass.
