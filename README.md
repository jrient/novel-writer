# AI辅助小说创作平台

一个为小说创作者设计的智能写作辅助工具，提供文风分析、AI续写、章节管理等功能。

## 技术栈

- **后端**: Python FastAPI + SQLAlchemy 2.0 + SQLite
- **前端**: Vue 3 + TypeScript + Vite + Element Plus
- **编辑器**: Tiptap (无头架构)
- **AI 支持**: OpenAI / Claude / Ollama
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
OPENAI_API_KEY=sk-xxx
# 或
ANTHROPIC_API_KEY=sk-ant-xxx
# 或使用本地 Ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
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

### Phase 1 (当前版本 - MVP)

- ✅ 项目 CRUD 管理
- ✅ 章节创建、编辑、删除、重排序
- ✅ Tiptap 富文本编辑器
- ✅ 自动保存与字数统计
- ✅ 三栏工作台布局
- ✅ Docker Compose 一键部署

### Phase 2 (Story Bible 系统)

- ⏳ 角色管理 CRUD
- ⏳ 世界观设定管理
- ⏳ 大纲树系统

### Phase 3 (AI 核心能力)

- ⏳ AI 服务层 (多模型适配)
- ⏳ 上下文组装引擎
- ⏳ 智能续写 (SSE 流式响应)

### Phase 4 (文风分析)

- ⏳ 参考小说上传
- ⏳ 文风分析引擎

### Phase 5 (体验优化)

- ⏳ 导出功能
- ⏳ 章节版本快照
- ⏳ Prompt 模板管理

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
│   └── app/
│       ├── main.py
│       ├── core/           # 配置、数据库
│       ├── models/         # SQLAlchemy ORM
│       ├── schemas/        # Pydantic 模型
│       ├── routers/        # API 路由
│       └── services/       # 业务逻辑
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
│       ├── views/          # 页面视图
│       ├── components/     # 组件
│       ├── stores/         # Pinia 状态
│       └── api/            # API 封装
├── data/                   # SQLite 数据库 (自动创建)
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

### 数据库

SQLite 数据库文件位于 `data/novel_writer.db`，首次启动时自动创建表结构。

## API 文档

启动后端服务后访问 http://localhost:8000/docs 查看 Swagger 文档。

主要 API 端点：

- `GET /api/v1/projects` - 获取项目列表
- `POST /api/v1/projects` - 创建项目
- `GET /api/v1/projects/{id}` - 获取项目详情
- `GET /api/v1/projects/{id}/chapters` - 获取章节列表
- `POST /api/v1/projects/{id}/chapters` - 创建章节
- `PUT /api/v1/projects/{id}/chapters/{chapter_id}` - 更新章节

## License

MIT