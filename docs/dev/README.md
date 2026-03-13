# 开发者文档

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ 工作台  │ │ 向导    │ │ 设置    │ │ 编辑器  │           │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │
│       │           │           │           │                 │
│       └───────────┴─────┬─────┴───────────┘                 │
│                         │ Axios/SSE                         │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                    后端 (FastAPI)                            │
│                         │                                   │
│  ┌──────────────────────┼──────────────────────┐            │
│  │                     API 层                   │            │
│  │  routers/ (project, chapter, ai, character)  │            │
│  └──────────────────────┼──────────────────────┘            │
│                         │                                   │
│  ┌──────────────────────┼──────────────────────┐            │
│  │                   服务层                      │            │
│  │  services/ (ai_service, providers/)          │            │
│  └──────────────────────┼──────────────────────┘            │
│                         │                                   │
│  ┌──────────────────────┼──────────────────────┐            │
│  │                   数据层                      │            │
│  │  models/ (SQLAlchemy ORM)                    │            │
│  └──────────────────────┼──────────────────────┘            │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                    数据存储                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PostgreSQL   │  │   Redis      │  │   文件系统   │      │
│  │ + pgvector   │  │   (缓存)     │  │   (上传)     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────────┐
│                   AI Provider                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ OpenAI  │  │ Claude  │  │ Ollama  │  │ Gemini  │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
novel-writer/
├── docker-compose.yml      # Docker 编排配置
├── .env.example            # 环境变量模板
├── README.md               # 项目说明
├── CHANGELOG.md            # 更新日志
├── docs/                   # 文档
│   └── dev/                # 开发者文档
├── backend/                # 后端代码
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini          # Pytest 配置
│   ├── app/
│   │   ├── main.py         # FastAPI 入口
│   │   ├── core/           # 核心配置
│   │   │   ├── config.py   # 配置管理
│   │   │   ├── database.py # 数据库连接
│   │   │   └── dependencies.py
│   │   ├── middleware/     # 中间件
│   │   ├── models/         # ORM 模型
│   │   ├── schemas/        # Pydantic 模型
│   │   ├── routers/        # API 路由
│   │   ├── services/       # 业务逻辑
│   │   │   ├── ai_service.py
│   │   │   └── providers/  # AI Provider 抽象
│   │   └── utils/          # 工具函数
│   ├── scripts/            # 脚本
│   └── tests/              # 测试
├── frontend/               # 前端代码
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
│       ├── views/          # 页面
│       ├── components/     # 组件
│       ├── stores/         # Pinia 状态
│       ├── api/            # API 封装
│       └── assets/         # 静态资源
├── data/                   # 数据库文件 (开发)
└── uploads/                # 上传文件
```

## 环境配置

### 必需环境变量

```env
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

# AI 配置 (至少配置一个)
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_MODEL=claude-sonnet-4-20250514

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# 安全
ALLOWED_ORIGINS=http://localhost:3000
```

### 可选环境变量

```env
# AI 上下文限制
AI_CONTEXT_CHARACTER_LIMIT=10
AI_CONTEXT_WORLDBUILDING_LIMIT=10

# Embedding
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-3-small
```

## API 端点

完整 API 文档请访问 `/docs` (Swagger UI) 或 `/redoc` (ReDoc)。

### 主要端点

| 模块 | 端点前缀 | 说明 |
|------|----------|------|
| 项目 | `/api/v1/projects` | 项目 CRUD |
| 章节 | `/api/v1/projects/{id}/chapters` | 章节管理 |
| 角色 | `/api/v1/projects/{id}/characters` | 角色管理 |
| 世界观 | `/api/v1/projects/{id}/worldbuilding` | 世界观管理 |
| 大纲 | `/api/v1/projects/{id}/outline` | 大纲管理 |
| 事件 | `/api/v1/projects/{id}/events` | 事件管理 |
| 笔记 | `/api/v1/projects/{id}/notes` | 笔记管理 |
| AI | `/api/v1/projects/{id}/ai` | AI 功能 |
| 向导 | `/api/v1/wizard` | 创作向导 |

## AI Provider 架构

```
services/
├── ai_service.py           # AI 服务主入口
└── providers/              # Provider 实现
    ├── base.py             # 基类定义
    ├── openai_provider.py  # OpenAI
    ├── anthropic_provider.py # Claude
    ├── ollama_provider.py  # Ollama
    └── gemini_provider.py  # Gemini
```

### 添加新的 AI Provider

1. 在 `providers/` 创建新的 provider 文件
2. 继承 `BaseProvider` 类
3. 实现 `generate()` 和 `generate_stream()` 方法
4. 在 `ai_service.py` 中注册

## 开发指南

### 本地开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

### 运行测试

```bash
cd backend
pytest

# 带覆盖率
pytest --cov=app
```

### 代码规范

- **后端**: Ruff (替代 black/isort/flake8)
- **前端**: ESLint + Prettier
- **提交**: Conventional Commits

### 提交规范

```
feat: 新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式
refactor: 重构
test: 测试
chore: 构建/工具
```

## 数据库迁移

使用 Alembic 管理数据库版本：

```bash
# 生成迁移
alembic revision --autogenerate -m "description"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

## 部署

### Docker Compose

```bash
docker compose up -d --build
```

### 生产环境注意

1. 配置 `ALLOWED_ORIGINS` 白名单
2. 使用 PostgreSQL 而非 SQLite
3. 配置 HTTPS
4. 启用 Redis 缓存（可选）