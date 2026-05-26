# Spec-2：剧本 → 知乎严选风格短篇小说 设计文档

- 日期：2026-05-26
- 状态：待 user 评审
- 依赖：Spec-1「知乎严选风格样本库」（已交付）

---

## 一、目标与范围

### 目标

将平台内已有的剧本（ScriptProject）一键改写为知乎严选风格的短篇散文小说。风格来源于 Spec-1 样本库，通过语义检索自动匹配，无需用户手动选择。

### 范围内

- 从现有 ScriptProject 导入，按场次展平剧本节点树
- 用用户输入的"一句话故事梗概"自动检索 Top-3 风格样本
- 按场次并发 LLM 改写，SSE 实时推送进度
- 详情页展示逐场散文 + 整体进度
- 导出 TXT / DOCX

### 范围外

- 上传新文件 / 粘贴文本（仅支持已有 ScriptProject）
- 用户手动选择风格样本
- 在线手改散文内容
- 多版本存档与对比
- 单场重跑（发现质量差则新建项目重跑）

---

## 二、模块分解

| 单元 | 类型 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `models/prose_project.py` | ORM | — | `ProseProject`, `ProseScene` 两张表 | `Base` |
| `services/prose_pipeline.py` | 服务 | project_id | 全流程：FETCH → SEARCH → REWRITE | `style_sample_indexer`, `ai_service` |
| `routers/prose.py` | API | HTTP | CRUD + SSE 5 个端点 | 上面服务 |
| `frontend/views/ProseListView.vue` | 页面 | — | 列表 + 删除 | 新 API |
| `frontend/views/ProseCreateView.vue` | 页面 | — | 创建表单 | 新 API |
| `frontend/views/ProseDetailView.vue` | 页面 | — | 详情 + 进度 + 导出 | 新 API |

---

## 三、数据模型

```python
class ProseProject(Base):
    __tablename__ = "prose_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # 来源剧本（弱引用：剧本删除后散文项目历史保留）
    script_project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    script_project_title: Mapped[Optional[str]] = mapped_column(String(200))

    # 检索参数
    premise: Mapped[str] = mapped_column(Text, nullable=False)   # 一句话故事梗概
    genre: Mapped[Optional[str]] = mapped_column(String(50))     # 从 ScriptProject 继承

    # 生成时使用的风格样本快照（JSON，供回溯）
    style_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    # 结构：[{"sample_id": 1, "title": "...", "prompt_fragment": "...", "prose_excerpt": "..."}]

    # 状态机：pending / generating / done / partial / failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_scenes: Mapped[int] = mapped_column(Integer, default=0)
    done_scenes: Mapped[int] = mapped_column(Integer, default=0)
    failed_scenes: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())


class ProseScene(Base):
    __tablename__ = "prose_scenes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("prose_projects.id", ondelete="CASCADE"), index=True
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_title: Mapped[str] = mapped_column(String(200), default="")
    original_scene_text: Mapped[str] = mapped_column(Text, nullable=False)
    prose_text: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending / running / done / failed
    error: Mapped[Optional[str]] = mapped_column(Text)
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())
```

### 关键决定

- `script_project_id` 弱引用（不设 `ondelete="CASCADE"`）：剧本删除后散文项目的历史仍可查阅
- `style_snapshot` 冗余落库：方便日后审阅"这篇用了哪些风格样本生成"
- 无 version 表：只读输出，不支持多版本；重跑即新建项目

---

## 四、API 设计

挂在 `/api/v1/prose`，5 个端点，全部要求 `get_current_user`：

```
POST   /api/v1/prose
       body: { script_project_id, premise, title?, genre? }
       行为: 同步创建 ProseProject(status=pending) + 后台任务跑全流程
       返回: { id, status, ... }

GET    /api/v1/prose
       列表（分页），仅返回当前用户的项目
       返回: 元信息 + status + 进度计数（不含 scenes）

GET    /api/v1/prose/{id}
       详情：project 全部字段 + 所有 scenes（含 prose_text）
       用于生成完成后展示全文

GET    /api/v1/prose/{id}/stream          ← SSE
       订阅生成进度（短票据鉴权，避免 EventSource 401）
       每场完成推一条事件：
         { "type": "scene_done", "scene_index": 2, "scene_title": "...",
           "status": "done", "prose_text": "..." }
       全部完成推 project_done 事件

DELETE /api/v1/prose/{id}
       删除项目（CASCADE 删 scenes）
```

### 导出

在详情页前端拼接所有 `prose_text` 后下载 TXT；DOCX 复用现有 `export` service 或纯前端生成。不新增导出后端路由（MVP 阶段前端直接拼接足够）。

---

## 五、Pipeline 设计

```
[Step 1] FETCH_SCRIPT
    读 ScriptProject + ScriptNode（按 order 展平叶子节点作为"场"）
    每个叶子节点 → ProseScene(status=pending, original_scene_text=node.content)
    project.total_scenes = N，project.status = generating

[Step 2] SEARCH_STYLE
    调 style_sample_indexer 内部检索（不走 HTTP，直接调 service）
    query = premise，filter.genre = project.genre（若有）
    top_k = 3
    结果写入 project.style_snapshot
    若样本库为空 / 命中 0 → 降级：不注入风格指南，继续生成（不阻塞）

[Step 3] REWRITE（并发）
    asyncio.Semaphore(PROSE_REWRITE_CONCURRENCY, 默认 3)
    构造每场 prompt：
      system = PROSE_SYSTEM_HEADER
             + "\n\n".join(snapshot[i].prompt_fragment for i in 0..2)
             + "\n\n# 参考段落\n" + snapshot[0].prose_excerpt
      user   = "将以下剧本场景改写为知乎严选风格短篇散文：\n{scene.original_scene_text}"
    每场完成 → update ProseScene + SSE event
    全部完成 → project.status = done / partial / failed
```

### PROSE_SYSTEM_HEADER（固定前缀）

```
你是一位专业的中文短篇小说作者，擅长知乎严选风格。
你的任务是将输入的剧本场景改写为连贯流畅的散文小说段落。
要求：保留原场景的核心情节与情感走向；风格完全遵照下方风格指南；
不要保留剧本格式（场景头、对白标记等）；直接输出散文正文，不加任何说明。
```

### 失败处理

| 场景 | 行为 |
|---|---|
| ScriptProject 不存在或无权访问 | POST 同步 400 |
| ScriptProject 无节点内容 | POST 同步 400 |
| 样本库空 / 检索 0 结果 | 降级继续，`style_snapshot = []` |
| 单场 LLM 失败 | `scene.status=failed`，其余继续；`project.failed_scenes++` |
| 全部场完成（含失败）| `project.status = done`（全成）/ `partial`（部分失败）/ `failed`（全失败）|

---

## 六、前端页面

**遵守 [[feedback_no_split_layout]]**：全程上下堆叠 + 抽屉/弹窗，禁止左右分屏。

### `/prose` — 列表页

```
┌─ 顶部工具栏 ──────────────────────────────────────┐
│  [+ 新建散文项目]  [刷新]                           │
└───────────────────────────────────────────────────┘
┌─ 表格 ────────────────────────────────────────────┐
│  标题 / 来源剧本 / 进度 / 状态徽章 / 创建时间 / 操作  │
│  操作：[查看] [删除]                                │
│  状态徽章：                                         │
│    pending(灰) / generating(蓝+进度%) /             │
│    done(绿) / partial(橙) / failed(红)              │
└───────────────────────────────────────────────────┘
```

### `/prose/new` — 创建页

- ScriptProject 下拉选择（搜索框过滤）
- 输入"一句话故事梗概"（必填，placeholder 示例）
- 题材（可选，自动从剧本继承）
- 提交后跳转详情页，SSE 接管进度展示

### `/prose/{id}` — 详情页

```
┌─ 项目信息 ────────────────────────────────────────┐
│  来源：《XXX》 | 梗概：… | 状态：generating 7/12   │
│  进度条（已完成场次 / 总场次）                      │
│  [展开风格样本快照]                                │
└───────────────────────────────────────────────────┘
┌─ 场次列表（上下堆叠）──────────────────────────────┐
│  ▸ 场1  [done]    散文正文（折叠/展开）              │
│  ▸ 场2  [running] 生成中…                          │
│  ▸ 场3  [pending]                                  │
│  ▸ 场4  [failed]  错误提示                          │
└───────────────────────────────────────────────────┘
[导出 TXT]  [导出 DOCX]   ← status=done/partial 时可用
```

---

## 七、测试策略

**Unit 测试**（`backend/tests/`）：
- `test_prose_pipeline.py`：mock LLM + mock style search，验证三步流程、并发状态机、降级逻辑
- `test_prose_router.py`：TestClient 覆盖 5 个端点 happy path + 主要 error path

**手工验收**（实现完成后）：
- 选 1 个已有剧本项目，输入梗概，生成到 done
- 检查逐场散文的风格是否明显区别于"原始改编"
- 导出 TXT 验证全文完整

---

## 八、与现有基础设施的复用

| 现有组件 | 用法 | 改动 |
|---|---|---|
| `services/style_sample_indexer.py` | 直接调内部检索，不走 HTTP | 无 |
| `services/ai_service.py` | 改写 prompt 走默认 LLM provider | 无 |
| `models/script_project.py` + `script_node.py` | 读取剧本内容，弱引用 | 无 |
| `routers/auth.py` `get_current_user` | 鉴权 | 仅 import |
| adaptation 模块的 SSE 短票据方案 | 复用 EventBus 模式 | 仅参考 |
| Alembic / `Base.metadata.create_all` | 新表 migration | 仅生成 migration |

---

## 九、Spec-2 完成 Exit 标志

- 5 个 API 端点可用且有单元测试
- 前端列表 / 创建 / 详情三个页面可用
- 至少 1 个剧本完整生成到 `status=done`，散文可读
- 导出 TXT 功能可用
- DB migration 已生成
