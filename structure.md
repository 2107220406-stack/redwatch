根据你的项目结构（包含 FastAPI、事件溯源、AI Agent、视觉模块等），我为你制作了带有详细注释的树形图。

为了在 Markdown 中保持清晰，我使用 `#` 作为注释符号，并尽量对齐。你可以直接复制保存，或者用来完善你的 `README.md`。

```text
E:.
├── .env                           # 本地环境变量配置（包含密钥、数据库连接等，不提交到 Git）
├── .env.example                   # 环境变量模板文件，供其他开发者参考复制
├── .gitignore                     # Git 忽略文件配置（排除虚拟环境、缓存等）
├── .python-version                # 指定当前项目使用的 Python 版本（供 uv 等工具识别）
├── alembic.ini                    # Alembic 数据库迁移工具的配置文件
├── pyproject.toml                 # 项目核心配置及依赖声明（Python 包管理工具使用）
├── README.md                      # 项目介绍、运行指南与说明文档
├── uv.lock                        # uv 包管理器的依赖版本锁定文件
│
├── docs                           # 项目文档目录
│   ├── camera-smoke.html          # 摄像头连通性/冒烟测试的静态页面
│   ├── frontend-api.md            # 前端对接的 API 接口文档
│   └── implementation-plan.md     # 项目实施计划或技术架构设计文档
│
├── migrations                     # Alembic 数据库迁移脚本目录
│   ├── env.py                     # 迁移环境配置脚本（连接数据库等）
│   └── versions                   # 具体的迁移版本存放处
│       ├── 001_initial_event_store.py               # 初始化事件存储表的迁移脚本
│       └── 002_scope_idempotency_by_player.py       # 针对玩家作用域的幂等性调整迁移
│
├── src                            # 源代码根目录
│   └── focus_game                 # 核心业务包
│       ├── __init__.py            # 包初始化文件
│       ├── config.py              # 应用通用配置逻辑
│       ├── main.py                # FastAPI 应用入口及启动文件
│       ├── settings.py            # Pydantic Settings 配置类（读取 .env 环境变量）
│       │
│       ├── agents                 # AI Agent 智能体模块
│       │   ├── __init__.py
│       │   ├── narrative.py       # 负责生成叙事/剧情文本的 Agent 逻辑
│       │   ├── supervisor.py      # 负责调度、监督其他 Agent 的核心逻辑
│       │   └── tools.py           # Agent 可以调用的外部工具/函数封装
│       │
│       ├── api                    # HTTP API 接口层
│       │   ├── __init__.py
│       │   ├── auth.py            # 身份验证与鉴权逻辑（如 JWT）
│       │   ├── dependencies.py    # FastAPI 的依赖注入（如获取当前用户、数据库 Session）
│       │   ├── routes.py          # API 路由端点定义
│       │   └── schemas.py         # API 请求/响应的 Pydantic 数据模型（DTO）
│       │
│       ├── domain                 # 领域驱动设计 (DDD) 的核心业务层
│       │   ├── __init__.py
│       │   ├── commands.py        # CQRS 中的写操作命令对象（Command）
│       │   ├── enums.py           # 领域相关的枚举类型定义
│       │   ├── events.py          # 领域事件定义（用于事件溯源/消息传递）
│       │   ├── models.py          # 核心业务实体 (Entities) 与值对象
│       │   ├── rules.py           # 核心业务规则与校验逻辑
│       │   └── service.py         # 领域服务（协调实体、规则与事件）
│       │
│       ├── persistence            # 数据持久化层
│       │   ├── __init__.py
│       │   ├── database.py        # 数据库连接、引擎与会话管理 (SQLAlchemy)
│       │   ├── event_store.py     # 事件存储的具体实现（保存/读取领域事件）
│       │   ├── outbox.py          # Outbox 模式实现（保证事件与业务数据的一致性发布）
│       │   ├── serialization.py   # 数据模型/事件的序列化与反序列化逻辑
│       │   └── tables.py          # 数据库表结构定义 (SQLAlchemy ORM Models)
│       │
│       ├── story                  # 游戏剧情/故事配置模块
│       │   ├── __init__.py
│       │   └── default.yaml       # 默认的剧本、关卡或剧情走向的配置文件
│       │
│       └── vision                 # 视觉/图像识别模块
│           ├── __init__.py
│           ├── adapter.py         # 视觉模块的外部适配器
│           ├── fake.py            # 用于单元测试的假数据/模拟实现
│           ├── http.py            # 通过 HTTP 请求调用外部视觉服务
│           ├── openai_compatible.py # 兼容 OpenAI 多模态接口的视觉模型实现
│           ├── port.py            # 定义视觉模块的核心接口（端口）
│           └── schemas.py         # 视觉模块内部的 Pydantic 数据结构
│
└── tests                          # 测试代码目录
    ├── conftest.py                # Pytest 的共享 Fixture 与全局测试配置
    ├── test_scaffold.py           # 项目基础脚手架完整性测试
    │
    ├── integration                # 集成测试（测试多个模块协同）
    │   ├── test_api.py            # 针对 API 端点的集成测试
    │   ├── test_api_contract.py   # API 契约测试（确保接口结构不破坏）
    │   └── test_security_and_runtime.py # 安全机制与运行时环境测试
    │
    └── unit                       # 单元测试（测试独立模块）
        ├── test_rules.py          # 领域业务规则单元测试
        ├── test_time_rules.py     # 时间相关规则的单元测试
        ├── test_vision.py         # 视觉模块的单元测试
        │
        └── domain                 # 领域层相关的单元测试
            ├── test_events.py     # 领域事件生成与处理测试
            └── test_models.py     # 核心实体模型逻辑测试
```

> **架构解读小贴士**：
> 从目录结构可以看出，这是一个非常规范的**领域驱动设计 (DDD) + 事件溯源 (Event Sourcing) + CQRS** 架构的 Python 项目：
> 1. 核心业务在 `domain` 中，不依赖外部框架。
> 2. 持久化在 `persistence` 中，专门处理事件存储 (`event_store.py`) 和 Outbox。
> 3. 技术细节（FastAPI 接口、AI 大模型调用、视觉服务）都作为外层适配器。