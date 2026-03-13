# AI辅助小说创作平台

一个为小说创作者设计的智能写作辅助工具，提供文风分析、AI续写、章节管理等功能。

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://github.com/your-repo/novel-writer)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 技术栈

- **后端**: Python FastAPI + SQLAlchemy 2.0 (异步) + PostgreSQL/SQLite + pgvector
- **前端**: Vue 3 + TypeScript + Vite + Element Plus
- **编辑器**: Tiptap (无头架构)
- **AI 支持**: OpenAI / Claude / Ollama / Gemini
- **部署**: Docker Compose

## 快速开始

### 环境要求

- Docker & Docker Compose
- (可选) Node.js 20+ 和 Python 3.11+ 用于本地开发

### 配置

1. 复制环境变量模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，配置 AI API 密钥：
```env
# OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Ollama (本地)
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3

# CORS (生产环境必须配置)
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8083

# AI 上下文限制
AI_CONTEXT_CHARACTER_LIMIT=10
AI_CONTEXT_WORLDBUILDING_LIMIT=10
```

### 启动服务

```bash
# 构建并启动所有服务
docker compose up --build

# 后台运行
docker compose up -d --build
```

### 访问地址

- 前端界面: http://localhost:3000
- API 文档: http://localhost:8000/docs

## 功能特性

### 核心功能

- ✅ 项目 CRUD 管理
- ✅ 章节创建、编辑、删除、重排序
- ✅ Tiptap 富文本编辑器
- ✅ 自动保存与字数统计
- ✅ 章节版本历史
- ✅ 三栏工作台布局
- ✅ Docker Compose 一键部署

### Story Bible 系统

- ✅ 角色管理 CRUD
- ✅ 世界观设定管理
- ✅ 大纲树系统
- ✅ 小说创作向导
- ✅ 事件管理
- ✅ 笔记管理

### AI 核心能力

- ✅ AI 服务层 (多模型适配)
- ✅ 上下文组装引擎
- ✅ 智能续写 (SSE 流式响应)
- ✅ 批量章节生成
- ✅ AI 除痕功能 (清理 AI 生成痕迹)
- ✅ Provider 路由机制

### 文风分析

- ✅ 参考小说上传
- ✅ 文风分析引擎
- ✅ 知识库检索

### 导出功能

- ✅ 章节导出 (TXT/Markdown)
- ✅ 整书导出

## 项目结构

```
novel-writer/
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── core/           # 配置、数据库、依赖
│   │   ├── middleware/     # 中间件 (请求追踪)
│   │   ├── models/         # SQLAlchemy ORM
│   │   ├── schemas/        # Pydantic 模型
│   │   ├── routers/        # API 路由
│   │   ├── services/       # 业务逻辑
│   │   │   ├── ai_service.py
│   │   │   └── providers/  # AI Provider 抽象
│   │   └── utils/          # 工具函数
│   └── tests/              # 单元测试
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
│       ├── views/          # 页面视图
│       ├── components/     # 组件
│       ├── stores/         # Pinia 状态
│       └── api/            # API 封装
├── data/                   # 数据库文件
└── uploads/                # 上传文件
```

## 开发指南

### 本地开发

后端：
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

前端：
```bash
cd frontend
npm install
npm run dev
```

### 运行测试

```bash
cd backend
pytest
```

### 数据库

- 开发环境: SQLite (`data/novel_writer.db`)
- 生产环境: PostgreSQL with pgvector

## API 文档

启动后端服务后访问 http://localhost:8000/docs 查看 Swagger 文档。

主要 API 端点：

### 项目管理
- `GET /api/v1/projects` - 获取项目列表
- `POST /api/v1/projects` - 创建项目
- `GET /api/v1/projects/{id}` - 获取项目详情
- `PUT /api/v1/projects/{id}` - 更新项目
- `DELETE /api/v1/projects/{id}` - 删除项目

### 章节管理
- `GET /api/v1/projects/{id}/chapters` - 获取章节列表
- `POST /api/v1/projects/{id}/chapters` - 创建章节
- `PUT /api/v1/projects/{id}/chapters/{chapter_id}` - 更新章节
- `DELETE /api/v1/projects/{id}/chapters/{chapter_id}` - 删除章节
- `POST /api/v1/projects/{id}/chapters/batch-delete` - 批量删除

### AI 功能
- `POST /api/v1/projects/{id}/ai/generate` - AI 流式生成
- `POST /api/v1/projects/{id}/ai/batch-generate` - 批量生成章节
- `GET /api/v1/ai/config` - 获取 AI 配置

### 角色管理
- `GET /api/v1/projects/{id}/characters` - 获取角色列表
- `POST /api/v1/projects/{id}/characters` - 创建角色

### 世界观管理
- `GET /api/v1/projects/{id}/worldbuilding` - 获取世界观列表
- `GET /api/v1/projects/{id}/worldbuilding/tree` - 获取世界观树

## 架构特点

### 安全性
- CORS 白名单配置
- 全局异常处理
- 事务保护 (原子操作)
- 环境变量敏感信息隔离

### 可观测性
- 结构化日志
- 请求 ID 追踪 (X-Request-ID)
- AI 调用耗时统计

### 可维护性
- 共享依赖函数
- 树构建工具模块
- AI Provider 抽象层
- 完整类型注解

### 性能优化
- 数据库连接池
- N+1 查询优化
- 批量操作支持

## License

MIT

## 更新日志

查看 [CHANGELOG.md](./CHANGELOG.md) 了解版本更新历史。