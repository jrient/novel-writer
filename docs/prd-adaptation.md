# 剧本改编功能 PRD

## 1. 功能概述

剧本改编模块是一个 AI 驱动的剧本文本改写系统，核心目标是将已有剧本按用户指定的**改编强度、新设定、实体映射**进行智能化改写，输出可导出的新版剧本。适用于网文短剧的"去识别化"改编、时代重塑、剧本润色等场景。

## 2. 用户角色

| 角色 | 权限 |
|------|------|
| 普通用户 | 创建/管理自己的改编项目，执行所有改写操作 |
| 超级管理员 | 可访问所有用户的项目 |

## 3. 核心流程

```
导入原文 → 抽实体 → 建映射 → 切场 → 全场改写 → 单场精修 → 导出
```

### 3.1 流程详解

#### Step 1：导入剧本
- 支持两种输入方式：
  - **粘贴文本**：直接提交 raw_text
  - **上传文件**：支持 `.txt`、`.docx`、`.md` 格式，后端自动解析
- 原文字数上限：200,000 字（`ADAPTATION_MAX_CHARS`）
- 创建时需填写：标题、改编强度（默认2）、改编意图（可选）、新设定（可选）

#### Step 2：AI 抽实体
- LLM 自动从原文中抽取四类实体 + 人物性格标签：
  - **person**（人物）
  - **place**（地点）
  - **prop**（关键道具）
  - **era_term**（时代关键词）
  - **other**（其他）
- 返回结构：
  - `entities`：实体列表（type / text / 出现次数 / 示例上下文）
  - `character_traits`：主要人物性格标签 + 口头禅（出场≥3次的人物）
- 已存在且 `locked=true` 的行不会被覆盖

#### Step 3：实体映射表
- 用户可对抽取出的实体进行以下操作：
  - **手动编辑**：修改 original_text / replacement_text / entity_type / notes
  - **AI 建议替换**：LLM 按"去识别化"规则自动生成替换名，内置五条强制规避规则：
    1. 字面零重叠：新名禁止包含原名任何汉字
    2. 音近规避：禁止同音字/谐音变体
    3. 结构错位：原名两字→新名优先三字，叠字禁止叠字结构
    4. 姓氏全换：人物姓氏必须更换
    5. 意译过近规避：地名/道具不得近义替换
  - **锁定**：锁定后 AI 建议不会覆盖，改写时严格按映射替换
  - **添加/删除**行
- 映射表整表 PUT（全量替换），前端需先保存映射再触发后续操作

#### Step 4：切场
- 将剧本按场景切分，三种策略依次降级：
  1. **正则切场**（优先）：识别"场1"、"第X场"、"1-1"、INT./EXT. 等场标记，命中≥2处即采用
  2. **LLM 切场**：正则未命中时，LLM 按内在场景切分，返回字符偏移
  3. **单场兜底**：LLM 也失败时，整篇视为一场
- 切场结果存储在 `project.metadata_.scene_boundaries` 中，前端以折叠面板预览

#### Step 5：全场改写
- 触发后创建一个新版本（version_no 自增），后台异步执行
- 改写策略根据强度（intensity）分三档：

| 强度 | 名称 | 策略 |
|------|------|------|
| 1 | 替换 | 纯实体替换，保持原文结构不变，仅处理同名消歧和代词一致性 |
| 2 | 润色 | **两步改写**：Pass1 抽骨架+金句 → Pass2 从骨架重写。保留网感金句原句，压缩过场对白，按策略替换实体 |
| 3 | 重铸 | **两步改写 + 时代重塑**：在润色基础上增加时代重塑（物件/职业/语言风格全部时代化），道具可艺术性替换 |

- **两步改写流程**（intensity≥2）：
  - **Pass 1（结构分析）**：提取剧情骨架（3~8节奏点）、必须保留的网感金句、节奏点细节
  - **Pass 2（从零创作）**：基于骨架重写，不看原文。金句原样嵌入，其余台词全新创作
  - Pass 1 JSON 解析失败时，自动回退到 intensity=1 的纯实体替换，避免激进删改导致丢戏

- 并发控制：每场独立调用 LLM，信号量限制并发数（默认5，`ADAPTATION_REWRITE_CONCURRENCY`）
- 单场超时：90秒（`ADAPTATION_PER_SCENE_TIMEOUT_SEC`）
- 每场改写完成后通过 SSE 实时推送进度到前端

#### Step 6：单场精修
- **单场重跑**：对某场重新调用 LLM 改写，可附加 extra_prompt 指导改写方向
- **手动编辑**：用户直接修改改写后的文本，保存后状态变为 `manual_edited`，所有修改记录在 `manual_edits` 中
- **Diff 对比**：前端提供原文/改写后/Diff 三个 Tab，Diff 使用 LCS 算法做行级对齐（大场回退朴素 diff）

#### Step 7：导出
- 支持两种格式：
  - **.txt**：纯文本，场与场之间空行分隔
  - **.docx**：Word 文档，场标题自动识别为 Heading2，人物列表行加粗
- 导出时自动补全场号标题行和人物列表行（若改写结果中缺失）

## 4. 数据模型

### 4.1 AdaptationProject（改编项目）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| user_id | int | 所属用户 |
| title | str(200) | 项目标题 |
| source_filename | str(255) | 上传文件名 |
| source_text | text | 原文（写入后只读） |
| intent | text | 改编意图 |
| intensity | int | 改编强度 1/2/3 |
| era_target | text | 新时代/世界设定 |
| status | str(20) | 项目状态 |
| metadata_ | JSON | 扩展字段（scene_boundaries / character_traits / split_method / scene_summaries） |
| created_at / updated_at | datetime | 时间戳 |

**项目状态流转**：
```
parsing → ready → generating → done
                    ↘ extract_failed
```

### 4.2 AdaptationVersion（改写版本）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| project_id | int | 所属项目 |
| version_no | int | 版本号（自增） |
| triggered_by | str(20) | 触发方式（full_run） |
| prompt_overrides | JSON | 额外提示词 |
| status | str(20) | 版本状态 |
| stats | JSON | 统计（total_scenes / succeeded / failed / total_tokens） |
| mapping_snapshot | JSON | 运行时的映射表快照 |
| error | text | 错误信息 |
| created_at / completed_at | datetime | 时间戳 |

**版本状态流转**：
```
running → done / partial / failed
```

### 4.3 AdaptationSceneResult（单场结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| version_id | int | 所属版本 |
| scene_index | int | 场序号 |
| scene_title | str(200) | 场标题 |
| original_scene_text | text | 原文片段 |
| rewritten_scene_text | text | 改写结果 |
| status | str(20) | 场状态 |
| error | text | 错误信息 |
| token_used | int | 消耗 token 数 |
| line_count_delta_pct | float | 行数偏差百分比 |
| manual_edits | JSON | 手动编辑/重跑记录 |
| updated_at | datetime | 更新时间 |

**场状态流转**：
```
pending → running → done / failed
                    ↘ manual_edited（手动编辑后）
```

### 4.4 AdaptationMappingEntry（实体映射）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| project_id | int | 所属项目 |
| entity_type | str(20) | person/place/prop/era_term/other |
| original_text | str(200) | 原名 |
| replacement_text | str(200) | 替换名 |
| locked | bool | 是否锁定 |
| notes | text | 备注 |
| order_index | int | 排序序号 |

## 5. API 接口

### 5.1 项目 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/adaptation/projects` | 创建项目（粘贴文本） |
| POST | `/api/v1/adaptation/projects/upload` | 创建项目（上传文件） |
| GET | `/api/v1/adaptation/projects` | 列出当前用户所有项目 |
| GET | `/api/v1/adaptation/projects/{id}` | 获取项目详情（含 versions + mappings） |
| PATCH | `/api/v1/adaptation/projects/{id}` | 更新项目（标题/意图/强度/设定） |
| DELETE | `/api/v1/adaptation/projects/{id}` | 删除项目（级联删除版本和映射） |

### 5.2 实体与映射

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/adaptation/projects/{id}/extract` | AI 抽实体 |
| PUT | `/api/v1/adaptation/projects/{id}/mappings` | 全量更新映射表 |
| POST | `/api/v1/adaptation/projects/{id}/mappings/suggest` | AI 建议替换名 |

### 5.3 切场与改写

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/adaptation/projects/{id}/split` | 切场 |
| POST | `/api/v1/adaptation/projects/{id}/runs` | 发起全场改写 |
| GET | `/api/v1/adaptation/projects/{id}/runs` | 列出所有版本 |

### 5.4 版本与场景

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/adaptation/runs/{vid}` | 获取版本详情（含 scene_results） |
| POST | `/api/v1/adaptation/runs/{vid}/stream/ticket` | 获取 SSE 订阅票据 |
| GET | `/api/v1/adaptation/runs/{vid}/stream?ticket=...` | SSE 实时推送改写进度 |
| POST | `/api/v1/adaptation/runs/{vid}/scenes/{idx}/rerun` | 单场重跑 |
| PATCH | `/api/v1/adaptation/runs/{vid}/scenes/{idx}` | 手动编辑场景 |
| GET | `/api/v1/adaptation/runs/{vid}/export?format=txt\|docx` | 导出 |

## 6. SSE 事件协议

改写过程中通过 Server-Sent Events 推送以下事件：

| 事件 | 触发时机 | 载荷 |
|------|----------|------|
| subscribed | 前端连上 SSE | `{event, version_id}` |
| scene_running | 某场开始改写 | `{event, scene_index}` |
| scene_done | 某场改写完成 | `{event, scene_index, status, rewritten, error, line_count_delta_pct}` |
| version_done | 全部场次完成 | `{event, version_id, status}` |
| version_failed | 全场改写异常 | `{event, error}` |

**鉴权机制**：浏览器 EventSource 无法携带 Authorization 头，因此先 POST `/stream/ticket` 获取一次性短时票据，再以 `?ticket=...` 参数拉取 SSE 流。

## 7. 前端页面

### 7.1 改编列表页（`/adaptation`）
- 卡片式展示所有改编项目
- 显示：标题、强度、状态、最新版本号、字数、创建时间
- 点击卡片进入工作台

### 7.2 新建改编页（`/adaptation/create`）
- 四步向导式布局：
  - ① 导入剧本：粘贴文本 / 上传文件
  - ② 实体映射：AI 抽实体 / AI 建议替换 / 手动编辑 / 添加删除行 / 保存
  - ③ 改编强度与设定：滑块选强度（1替换/2润色/3重铸）+ 意图 + 新设定
  - ④ 场切分预览：正则/LLM 切场结果展示
- 全部完成后跳转工作台

### 7.3 改编工作台（`/adaptation/workbench/:id`）
- 顶部栏：项目标题、版本选择器、全场重跑、导出按钮
- 进度条：已完成/总数 + 失败数
- 场次表格：序号、状态标签、场标题、行数偏差、快速重跑按钮
- 场次详情抽屉（底部弹出）：
  - 原文 / 改写后 / Diff 三个 Tab
  - 底部操作栏：额外提示词输入 + 单场重跑 + 保存手改
- SSE 实时更新进度，页面可关闭后重连

## 8. 系统配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| ADAPTATION_MAX_CHARS | 200,000 | 原文字数上限 |
| ADAPTATION_REWRITE_CONCURRENCY | 5 | 全场改写并发数 |
| ADAPTATION_PER_SCENE_TIMEOUT_SEC | 90 | 单场改写超时秒数 |
| ADAPTATION_EXTRACT_MODEL | None | 抽实体/切场模型（None=用默认模型） |
| ADAPTATION_REWRITE_MODEL | None | 改写模型（None=用默认模型） |
| ADAPTATION_MAX_TOKENS | 64,000 | LLM 最大输出 token |
| ADAPTATION_STALE_RUN_CLEANUP_AGE_SEC | 3600 | 悬挂任务清理阈值（秒） |

## 9. 异常与容错

| 场景 | 处理策略 |
|------|----------|
| 服务重启时存在 running 状态的版本 | 自动标记为 failed，关联场景也标记 failed |
| 单场改写超时 | 该场标记 failed，其余场继续 |
| 部分场失败 | 版本状态为 partial，已成功的场仍可用 |
| LLM 返回空内容（reasoning 模型截断） | 抛出明确错误提示增大 max_tokens 或换非 reasoning 模型 |
| Pass 1 JSON 解析失败 | 回退到 intensity=1 纯实体替换，避免激进删改丢戏 |
| AI 建议替换出现字面重叠 | 保留建议但记录日志，由用户在 UI 上自行调整或锁定 |
| SSE 连接断开 | 前端自动重试 loadVersion 轮询 |

## 10. LLM 调用架构

- **Provider**：OpenAI-compatible 非流式调用，优先 DeepSeek，其次 OpenAI
- **双模型路由**：
  - `extract_model`：抽实体、切场、Pass1 骨架分析（偏理解，温度0.3）
  - `rewrite_model`：单场改写、Pass2 重写（偏创作，温度0.75）
- **温度策略**：
  - 抽实体/切场/Pass1：0.3（确定性优先）
  - intensity=1 纯替换：0.3
  - intensity≥2 Pass2 重写：0.75（创作空间，但高于0.85会改写金句）
