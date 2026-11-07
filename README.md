# Focus Companion Game Backend

面向专注工作游戏的后端 MVP。故事内容与规则解耦：领域服务是星数、进度、特赦、地牢、荣誉和军功币的唯一裁决者；摄像头多模态模型只产生结构化观察；`deepagents` 只能编排受限工具和生成叙事，不能写入游戏数值。

前端对接细节见 [docs/frontend-api.md](docs/frontend-api.md)，设计边界和实现顺序见 [docs/implementation-plan.md](docs/implementation-plan.md)。

## ✨ 已实现特性

- **FastAPI 接口**：开始场次、提交观察或摄像头帧、完成、主动退出、特赦、签到、状态、场次、荣誉、币种流水，以及内部缺勤结算。
- **确定性规则**：3 颗星；连续两次同类且置信度至少 0.85 的疑似违规才扣 1 星；星数归零或主动退出会遣返；北京时间同日第 3 次遣返进入 8 小时地牢。
- **权益系统**：每天一次免费特赦，之后自动扣 20 军功币；每天签到增加 10 军功币；遣返扣 300 秒、缺勤扣 1800 秒，均不低于已获得荣誉等级的保护下限。
- **持久化**：SQLAlchemy 异步事件存储、玩家快照、玩家维度的幂等记录、乐观并发检查和事务 outbox。支持 SQLite 与 MySQL。
- **视觉输入**：Fake provider（本地联调无需真实摄像头和 API）、通用 `http_json` provider、JSON 观察和 multipart 摄像头帧上传。默认不保存原始图像。
- **认证**：开发环境使用 `X-Player-Id`，生产环境使用 HMAC Bearer token；内部缺勤接口另需 `X-Internal-Token`。

---

## 🚀 本地开发环境搭建 (Windows + MySQL)

**环境要求**：Python 3.11+，`uv`，MySQL 8+。项目已在 `pyproject.toml` 固定清华 PyPI 源。

### 1. 安装依赖与驱动
在项目根目录打开 PowerShell 或 PyCharm 终端，同步基础依赖，并额外安装 MySQL 异步驱动：

```powershell
uv sync
uv add aiomysql
```

### 2. 初始化 MySQL 数据库
打开 MySQL 命令行工具（确保 `root` 用户可用）：
```sql
CREATE DATABASE focus_game CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
*(注：如果你使用的是 MySQL 8 默认的 `caching_sha2_password` 认证插件导致 Python 连接失败，请在 MySQL 中执行：`ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '你的密码'; FLUSH PRIVILEGES;`)*

### 3. 配置本地环境变量 (`.env`)
复制模板文件，并修改数据库连接：
```powershell
Copy-Item .env.example .env
```
打开 `.env` 文件，**务必注意以下几点**：
1. **配置 MySQL 连接**：
   ```env
   DATABASE_URL=mysql+aiomysql://root:你的密码@127.0.0.1:3306/focus_game?charset=utf8mb4
   ```
2. **布尔类型不可留空**（会导致 Pydantic 报错）：
   ```env
   AUTO_CREATE_SCHEMA=false
   ALLOW_CLIENT_OBSERVATION=true
   ```
3. **环境**
   本地默认配置是 MySQL 和 Fake vision provider，可直接联调。生产环境应至少设置：

   ```text
   APP_ENV=production
   DATABASE_URL=mysql+aiomysql://root:你的密码@127.0.0.1:3306/focus_game?charset=utf8mb4
   AUTH_MODE=hmac
   AUTH_SECRET=<至少 32 字符>
   INTERNAL_API_TOKEN=<至少 32 字符>
   VISION_PROVIDER=http_json
   VISION_ENDPOINT=https://<你的多模态网关>
   VISION_API_KEY=<可选，取决于网关>
   ```

   生产环境拒绝 `fake` 视觉 provider，且默认不自动建表，必须先执行 Alembic 迁移。   

   ---
   
4. **本地调试视觉模型**：
   ```env
   VISION_PROVIDER=fake
   ```
   *(在 fake 模式下，`VISION_ENDPOINT` 等留空即可，不会发送真实请求)*

### 4. 摄像头接入

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

---

### 5. 执行数据库迁移
**注意**：如果你使用的是全新的 MySQL 8 数据库，原项目的 `002_scope_idempotency_by_player.py` 迁移脚本可能会因为 `key` 是 MySQL 保留字而报错。如果你还未修复，请确保在脚本中为 `key` 字段加上反引号（\`key\`），然后再执行：
```powershell
uv run alembic upgrade head
```

### 6. 启动服务
```powershell
uv run uvicorn focus_game.main:app --reload
```
服务地址为 `http://127.0.0.1:8000`，调试接口为 `/docs`，存活检查为 `/healthz`，数据库就绪检查为 `/readyz`。

---

## 🧪 快速验证业务链路 (Swagger UI)

打开浏览器访问 `http://127.0.0.1:8000/docs`，按照以下顺序体验完整业务逻辑：

1. **开始场次**：`POST /sessions`
   - Header 填入 `Idempotency-Key: test-key-001`
   - Body 填入 `{"target_seconds": 1500}`
   - *获取返回的 `session_id` 备用*。
2. **上传监控画面**：`POST /sessions/{session_id}/frames`
   - Header 填入 `Idempotency-Key: frame-key-001`
   - Body 选择 `multipart/form-data`，`captured_at` 填入任意 ISO 时间（如 `2026-11-06T12:16:08.977Z`），`image` 随便上传一张本地图片（Fake 模型会默认返回合规结果）。
3. **完成结算**：`POST /sessions/{session_id}/complete`
   - Header 填入 `Idempotency-Key: complete-key-001`
4. **查验状态**：`GET /players/demo-player/state`
   - 查看当前的星数、地牢状态、荣誉等。
5. **签到测试**：`POST /players/demo-player/checkins`
   - 然后调用 `GET /players/demo-player/currency/ledger` 查看军功币流水。

---

## 📝 关键时间约定

- API 时间用带时区的 ISO 8601；数据库事件存 UTC。
- 业务自然日、免费特赦和签到按 `Asia/Shanghai` 计算。
- `target_seconds`、场次结算时长、专注进度均为整数秒。
- 完成场次实际结算 `min(服务端当前时间 - 开始时间, target_seconds)`。
- `now == dungeon_until_at` 时允许重新开始；前端倒计时仅用于显示，最终以服务端判断为准。

## 🛡️ Git 提交规范提醒

为了保持仓库清洁和防止敏感信息泄露，本地开发需注意：
- **不要提交 `.env`**：其中包含你的本地数据库密码。
- **不要提交 `.idea/` 或 `.vscode/`**：其中包含 PyCharm 或 VS Code 的本地路径、数据库连接配置 (`dataSources.xml`)、代码检查配置 (`profiles_settings.xml`)。
- 请在 `.gitignore` 中确认已包含：
  ```gitignore
  .env
  .idea/
  *.iml
  ```

## 验证与测试
```powershell
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q src migrations
```

时间用例覆盖目标时长上限、北京时间跨日、同日第三次遣返、八小时地牢边界、免费和付费特赦、签到跨日、遣返/缺勤扣减与荣誉保护下限。安全用例覆盖玩家路径绑定、HMAC token、生产环境禁止客户端观察和内部接口令牌。

---

## ⚠️ 当前边界
- 已提供 HMAC token 校验，但尚未实现完整 JWT/OIDC 登录、签发和密钥轮换。
- 已提供数据库 outbox 的投递和重试原语，尚未提供消息队列适配器或常驻 worker。
- 已引入并限制 `deepagents` 的 supervisor 和工具边界，尚未将模型调用接入 HTTP 请求生命周期；当前 API 返回确定性的领域结果。
- 提供通用 HTTP JSON 视觉协议，不绑定任何具体厂商 SDK。