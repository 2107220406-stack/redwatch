# Focus Companion Game Backend

面向专注工作游戏的后端 MVP。故事内容与规则解耦：领域服务是星数、进度、特赦、地牢、荣誉和军功币的唯一裁决者；摄像头多模态模型只产生结构化观察；`deepagents` 只能编排受限工具和生成叙事，不能写入游戏数值。

前端对接细节见 [docs/frontend-api.md](docs/frontend-api.md)，设计边界和实现顺序见 [docs/implementation-plan.md](docs/implementation-plan.md)。

## 已实现

- FastAPI：开始场次、提交观察或摄像头帧、完成、主动退出、特赦、签到、状态、场次、荣誉、币种流水，以及内部缺勤结算。
- 确定性规则：3 颗星；连续两次同类且置信度至少 0.85 的疑似违规才扣 1 星；星数归零或主动退出会遣返；北京时间同日第 3 次遣返进入 8 小时地牢。
- 权益：每天一次免费特赦，之后自动扣 20 军功币；每天签到增加 10 军功币；遣返扣 300 秒、缺勤扣 1800 秒，均不低于已获得荣誉等级的保护下限。
- 持久化：SQLAlchemy 异步事件存储、玩家快照、玩家维度的幂等记录、乐观并发检查和事务 outbox。
- 视觉输入：Fake provider、通用 `http_json` provider、JSON 观察和 multipart 摄像头帧上传。默认不保存原始图像。
- 认证：开发环境使用 `X-Player-Id`，生产环境使用 HMAC Bearer token；内部缺勤接口另需 `X-Internal-Token`。

## 环境

要求 Python 3.11+ 与 `uv`。项目已在 `pyproject.toml` 固定清华 PyPI 源。

```powershell
uv sync
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn focus_game.main:app --reload
```

服务地址为 `http://127.0.0.1:8000`，调试接口为 `/docs`，存活检查为 `/healthz`，数据库就绪检查为 `/readyz`。

本地默认配置是 SQLite 和 Fake vision provider，可直接联调。生产环境应至少设置：

```text
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://...
AUTH_MODE=hmac
AUTH_SECRET=<至少 32 字符>
INTERNAL_API_TOKEN=<至少 32 字符>
VISION_PROVIDER=http_json
VISION_ENDPOINT=https://<你的多模态网关>
VISION_API_KEY=<可选，取决于网关>
```

生产环境拒绝 `fake` 视觉 provider，且默认不自动建表，必须先执行 Alembic 迁移。

## 摄像头接入

客户端使用 `POST /sessions/{session_id}/frames` 上传 `image/jpeg`、`image/png` 或 `image/webp`，默认最大 5 MiB。服务端把图片以 Base64 JSON 转发给 `VISION_ENDPOINT`，期望网关返回符合 `VisionObservation` 的对象，例如：

```json
{
  "verdict": "SUSPECTED_VIOLATION",
  "overall_confidence": 0.95,
  "violation_type": "PHONE",
  "person_detected": true,
  "workstation_detected": true
}
```

视觉服务超时、HTTP 失败或结果不合规时返回 `503`，不会扣星。生产环境禁止客户端直接提交 `verdict`；只有开发环境且使用 Fake provider 时，`/observations` 可用于前端联调。

## 关键时间约定

- API 时间用带时区的 ISO 8601；数据库事件存 UTC。
- 业务自然日、免费特赦和签到按 `Asia/Shanghai` 计算。
- `target_seconds`、场次结算时长、专注进度均为整数秒。
- 完成场次实际结算 `min(服务端当前时间 - 开始时间, target_seconds)`。
- `now == dungeon_until_at` 时允许重新开始；前端倒计时仅用于显示，最终以服务端判断为准。

## 验证

```powershell
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q src migrations
```

时间用例覆盖目标时长上限、北京时间跨日、同日第三次遣返、八小时地牢边界、免费和付费特赦、签到跨日、遣返/缺勤扣减与荣誉保护下限。安全用例覆盖玩家路径绑定、HMAC token、生产环境禁止客户端观察和内部接口令牌。

## 当前边界

- 已提供 HMAC token 校验，但尚未实现完整 JWT/OIDC 登录、签发和密钥轮换。
- 已提供数据库 outbox 的投递和重试原语，尚未提供消息队列适配器或常驻 worker。
- 已引入并限制 `deepagents` 的 supervisor 和工具边界，尚未将模型调用接入 HTTP 请求生命周期；当前 API 返回确定性的领域结果。
- 提供通用 HTTP JSON 视觉协议，不绑定任何具体厂商 SDK。
