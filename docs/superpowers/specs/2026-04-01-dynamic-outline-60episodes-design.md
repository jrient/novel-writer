# 动态漫大纲支持自定义集数（60集+）设计文档

**日期**: 2026-04-01
**状态**: 已批准

## 背景

当前 AI 剧本创作功能中，动态漫大纲生成在 prompt 中硬编码了 5-8 集的范围。用户需要生成 60 集甚至更多集数的大纲，现有设计无法满足。

## 需求

1. 用户可自定义目标集数（不再固定 5-8 集）
2. 采用两阶段生成策略：先生成简要大纲（标题+概要），再逐集展开详细场景
3. 集数输入入口在摘要编辑阶段（Step 1）
4. 第一阶段尝试一次性生成全部简要大纲，如后续发现不稳定再补充降级逻辑

## 方案选择

选择**方案 A（最小改动方案）**：直接在现有流程上扩展，复用现有架构，风险低。

排除方案 B（分层生成）：多一个步骤，用户体验变复杂。
排除方案 C（混合方案）：降级逻辑增加代码复杂度，可后续按需演进。

## 设计详情

### 1. 数据模型与 Schema 变更

**SessionSummaryResponse** 新增 `目标集数` 字段：

```python
class SessionSummaryResponse(BaseModel):
    故事概要: str
    主要角色: List[str]
    核心冲突: str
    场景设定: str
    风格基调: str
    目标集数: int = 20  # 新增，默认20集
```

**outline_draft JSON 结构**保持兼容，`children` 初始为空数组：

```json
{
  "title": "剧本标题",
  "summary": "剧本总体概述",
  "sections": [
    {
      "node_type": "episode",
      "title": "第一集：标题",
      "content": "本集一句话概要",
      "sort_order": 0,
      "children": []
    }
  ]
}
```

前端通过 `children.length === 0` 判断该集是否已展开。

### 2. AI Prompt 变更

#### 第一阶段 — 简要大纲生成（修改现有 `outline` prompt）

- system prompt 改为"长篇剧本大纲"定位
- user prompt 接受 `{episode_count}` 参数
- 要求只生成标题+一句话概要，不展开场景
- `children` 为空数组

#### 第二阶段 — 新增 `expand_episode` prompt

- 输入上下文：
  - 剧本标题、总体概述（`outline_draft.summary`）
  - 主要角色列表（从 `session.summary.主要角色` 获取）
  - 核心冲突、风格基调（从 `session.summary` 获取）
  - 当前集在整体中的位置（如"第 15 集 / 共 60 集，处于故事发展阶段"）
  - 前一集/当前集/后一集的 title+content
- 输出：2-4 个详细场景（含场景描述、对白、动作）
- 全局上下文 + 相邻集信息共同保证连贯性

#### Token 配置与预估

第一阶段每集 JSON 约 80-120 tokens（中文），各档位预估：

| 集数 | 预估 tokens | max_tokens 建议 |
|------|-------------|-----------------|
| 20   | 2000-3000   | 8000            |
| 40   | 4000-5500   | 12000           |
| 60   | 6000-8000   | 16000           |
| 100  | 10000-13000 | 20000           |
| 200  | 20000-26000 | 32000           |

策略：根据 `episode_count` 动态计算 `max_tokens = max(8000, episode_count * 150)`，上限 32000。

第二阶段（展开单集）使用默认 8000 即可。

#### JSON 截断错误处理

当 AI 输出因 max_tokens 被截断导致 JSON 不完整时：

1. 后端尝试修复截断 JSON（补全尾部 `]}` 括号）
2. 修复失败则向前端发送 `partial_error` 事件，携带已解析的集数
3. 前端提示用户："大纲生成不完整（已生成 X / Y 集），请减少集数后重试"
4. 后续可演进为自动分批重试

### 3. 后端 API 变更

#### 修改 `generate_outline` 端点

`POST /api/v1/drama/{id}/session/generate-outline`

- 从 `session.summary` 中读取 `目标集数`，传递给 AI service
- `generate_outline()` 方法新增 `episode_count` 参数
- 格式化到 prompt 中的 `{episode_count}` 占位符

#### 新增 `expand_episode` 端点

`POST /api/v1/drama/{id}/session/expand-episode`

请求体：
```json
{ "episode_index": 0 }
```

响应：SSE 流式

逻辑：
1. 从 `session.outline_draft` 中按 index 找到目标集
2. 取前一集和后一集的 title+content 作为上下文
3. 调用 `ai_service.expand_episode()` 流式生成场景
4. 生成完成后，将 children 写回 `outline_draft.sections[index].children`
5. 保存到数据库

#### 前端 API 层新增（drama.ts）

```typescript
export function streamExpandEpisode(
  projectId: number,
  episodeIndex: number,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController
```

### 4. 前端 UI 变更

#### Step 1（信息确认）— 新增目标集数输入

在"风格基调"下方新增：

```html
<div class="summary-section">
  <h4>目标集数</h4>
  <el-input-number
    v-model="editableSummary.目标集数"
    :min="1"
    :max="200"
    :step="10"
    controls-position="right"
  />
</div>
```

默认值 20。仅在 `script_type === 'dynamic'` 时显示该控件。

#### 前端类型定义变更

```typescript
// drama.ts - SessionSummary 接口新增
interface SessionSummary {
  故事概要: string
  主要角色: string[]
  核心冲突: string
  场景设定: string
  风格基调: string
  目标集数: number  // 新增
}
```

`editableSummary` reactive 对象新增 `目标集数` 默认值 20。
`syncEditableSummary` 函数同步处理 `目标集数` 字段（缺省时填充默认值 20）。

#### Step 2（大纲预览）— 区分已展开/未展开集

- 未展开（`children.length === 0`）：显示标题 + 概要 + **"展开此集"按钮**
- 已展开（`children.length > 0`）：显示标题 + 场景树（现有行为）
- 展开中：按钮变为 loading 状态

交互流程：
1. 用户看到 N 集的标题列表
2. 点击某集的"展开"按钮
3. SSE 流式生成该集场景，完成后刷新该集 children
4. 不强制全部展开才能确认大纲

#### Step 2 操作区

- "确认大纲，开始创作"按钮不变
- 未展开的集在确认后仍可在工作台中按需展开

## 兼容性

- outline_draft 结构向后兼容（children 从有值变为可能为空）
- 现有已生成的大纲（5-8集，children 已有场景）不受影响
- 前端通过 `children.length` 判断状态，无需新增字段
- 无需数据库迁移，`目标集数` 存储于 `session.summary` JSON 字段中
- 旧版前端发送的 payload 不含 `目标集数`，Pydantic 使用默认值 20，行为正确
- `目标集数` 仅对动态漫（dynamic）生效，解说漫（explanatory）场景下忽略该字段

## 已知限制

- `expand_episode` 使用数组 index 定位集，并发重新生成大纲时可能指向错误的集。当前阶段不处理，后续可改为 UUID 定位
- 问答阶段槽位 5（集数与节奏）中用户提到的集数可能与 Step 1 手动输入不一致，以 Step 1 最终确认值为准

## 后续演进

- 如一次性生成大集数简要大纲不稳定，可补充按故事阶段分批生成的降级逻辑（方案 C）
- 可考虑"批量展开"功能（一键展开选中的多集）
