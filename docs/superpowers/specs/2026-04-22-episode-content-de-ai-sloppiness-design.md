# Episode Content 去 AI 味设计

> 日期: 2026-04-22
> 状态: 待实施
> 讨论参与者: Claude + Gemini

## 背景

当前 `generate_episode_content` 生成的剧本单集内容有浓重"AI 味"：辞藻堆砌、套路化比喻、书面语对白、平铺直叙。现有的 handbook 注入提供了评审维度和地雷清单（规则层），但缺少真实文笔样本（风格层）和反向约束（禁用清单）。

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 优化范围 | 仅 `episode_content` | 用户最终看到的成品，杠杆最大 |
| 范本策略 | 双层：1 段完整范本 + 金句清单 + 反 AI 味清单 | 范本教段落结构，金句教对白口吻，反例做反向约束 |
| 匹配策略 | script_type 分两套（dynamic/explanatory），预留 genre 加成接口 | 第一轮最小闭环，后续迭代按 genre 细化 |
| 范本提取 | 从 rubric scripts.json 筛选 writing_dialogue≥7 且 status=签 的剧本 | 编辑认可的高分文笔 |
| Prompt 注入位置 | 规则+反例 → System prompt；范本+金句 → User prompt 末尾 `<examples>` | LLM 对 User prompt 最近注入的示例模仿最强 |
| Token 控制 | 范本 ≤1500 tokens，反例 ≤500 tokens，新增总量 ≤2000 | 占当前 max_tokens ~10% |
| 防过度模仿 | 范本轮换（每次随机 1-2 段）+ "模仿节奏结构，禁用范本辞藻" 指令 | 避免风格固化 |

## 反 AI 味清单（9 条）

| # | 条目 | 示例 |
|---|------|------|
| 1 | 禁用过度抽象形容词 | ❌ "眼神中透露出坚毅的目光" |
| 2 | 禁用套路化比喻/暗喻 | ❌ "仿佛一把利刃刺穿了心"、"月光如水" |
| 3 | 禁用书面语对白 | ❌ "既然如此，我别无选择" → ✅ "行，没别的招了" |
| 4 | 禁用环境描写先行开场 | 第一镜禁止大空镜/缓慢建立场景 |
| 5 | 禁用情绪解释代替情绪表现 | ❌ "她感到很伤心" → ✅ "她眼眶红了，没说话" |
| 6 | 禁用总结性陈词与升华 | ❌ "这一刻他明白了勇气的真谛" → 留白 |
| 7 | 禁用万能动词（感到/觉得/变得/充满） | ❌ "他变得愤怒" → ✅ "他指关节捏得咯吱响" |
| 8 | 禁用排比/三段论 | 禁止连续三个结构相似的句子 |
| 9 | 禁用全知视角心理描写 | ❌ "他心中泛起一丝苦涩" → 用镜头可见的微表情/动作 |

## 架构总览

```
script_rubric/data/parsed/scripts.json
        │
        ▼
extract_fewshots.py（新增）
筛选：writing_dialogue≥7 + status=签
提取：分场正文（正则跳过人设/大纲，只取 △动作/对白/VO/OS）
输出：style_samples_dynamic.json / style_samples_explanatory.json
        │
        ▼
style_guard.py（新增）
├── get_style_samples(script_type) → 随机返回 1-2 段范本
├── get_golden_quotes(script_type) → 返回 15-20 条金句/句式
└── get_anti_slop_rules() → 返回 9 条反 AI 味清单
        │
        ▼
generate_episode_content prompt 三层结构
├── System prompt: 规则层 + 反 AI 味清单
└── User prompt: 生成指令 + <examples> 范本 + 金句
```

## 详细设计

### 1. 范本提取脚本

**新增文件：** `script_rubric/pipeline/extract_fewshots.py`

**逻辑：**
1. 加载 `scripts.json`
2. 筛选：`writing_dialogue >= 7` 且 `status == "签"`
3. 解析 `text_content`，用正则跳过"人设"/"大纲"/"小传"等标题段，只提取分场正文
4. 对动态漫：按 `mean_score` 降序，取 top 3，每部提取 1 个开场场景（第一场或冲突最强的前两场），300-500 字
5. 对解说漫：以 `drama/解说漫：买榴莲.txt` 为唯一范本，从中手工提炼 10-15 条金句/句式
6. 输出为 `script_rubric/outputs/style_samples_dynamic.json` 和 `style_samples_explanatory.json`

**输出格式：**
```json
{
  "script_type": "dynamic",
  "samples": [
    {
      "title": "剧本标题",
      "writing_dialogue_score": 8,
      "mean_score": 79.5,
      "excerpt": "01-1 日 内 办公室\n△张总猛拍桌，文件飞散...\n..."
    }
  ],
  "golden_quotes": [
    "△她眼眶红了，没说话。",
    "张总（暴怒）：三十万！公司账上的三十万！你敢说不知道？！",
    "..."
  ]
}
```

### 2. StyleGuard 服务

**新增文件：** `backend/app/services/style_guard.py`

```python
class StyleGuard:
    def __init__(self, samples_dir: Optional[str] = None):
        """加载 style_samples_{dynamic|explanatory}.json"""

    def get_style_samples(self, script_type: str, count: int = 1) -> list[str]:
        """随机返回 1-2 段范本（轮换防固化）"""

    def get_golden_quotes(self, script_type: str) -> list[str]:
        """返回 15-20 条金句/句式"""

    def get_anti_slop_rules(self) -> str:
        """返回 9 条反 AI 味清单，格式化为 prompt 文本"""

    def build_style_context(self, script_type: str) -> str:
        """组合：范本 + 金句，格式化为 <examples> 标签块"""
```

### 3. Prompt 三层结构

**修改：** `script_ai_service.py` 的 `generate_episode_content` 方法

**System prompt 变更（追加反 AI 味清单）：**

```diff
 你是一位顶级分场剧本撰写师...
 ...（保留现有 4 条核心能力描述）
 ...（保留现有格式规范/对白规范/△动作规范/VO规范）

+【写作禁忌——绝对不要出现以下内容】
+1. 过度抽象形容词（"眼神中透露出坚毅的目光"）
+2. 套路化比喻/暗喻（"仿佛一把利刃刺穿了心"）
+3. 书面语对白（角色说话要像真人，不像论文）
+4. 环境描写先行开场（第一镜禁止大空镜/缓慢建立场景）
+5. 情绪解释代替情绪表现（用微表情/动作替代"她感到伤心"）
+6. 总结性陈词与升华（"他明白了勇气的真谛" → 留白）
+7. 万能动词（感到/觉得/变得/充满 → 用具体阻力动词替代）
+8. 排比/三段论（禁止连续三个结构相似的句子）
+9. 全知视角心理描写（"心中泛起苦涩" → 用镜头可见的微表情/动作替代）
```

**User prompt 变更（追加 `<examples>` 标签）：**

```diff
 直接从 {episode_number}-1 开始输出，无任何前缀解释：

+【风格参考范本】
+以下是编辑认可的高分剧本片段，请模仿其节奏、句式结构和对白口吻。
+严禁直接使用范本中的具体辞藻、人名、地名。
+
+<examples>
+{style_samples}  ← 随机 1-2 段，300-500 字/段
+
+--- 金句/句式参考 ---
+{golden_quotes}  ← 15-20 条，每条 10-50 字
+</examples>
```

### 4. 解说漫特殊处理

解说漫只有 1 份样本（《买榴莲》），从以下维度提炼通用特征注入 prompt：

**从《买榴莲》提取的金句/句式维度：**

| 维度 | 示例 |
|------|------|
| 短句开场 | "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。" |
| 动作特写 | "我扶着门框的手指骨节泛白，指甲死死抠进木头里。" |
| 情绪留白 | "哀莫大于心死。原来就是这种感觉。" |
| 口语化对白 | "你在家煮屎吗？！" |
| 信息密度 | 每段不超过 3 句，每句 10-20 字 |
| 视觉节奏 | 独立成段制造停顿感 |

### 5. Token 控制

| 组件 | Token 估算 |
|------|-----------|
| 规则层（现有 system prompt） | ~600 |
| 反 AI 味清单（9 条） | ~400 |
| 范本（1 段 × 400 字） | ~600 |
| 金句（15 条 × 30 字） | ~450 |
| 生成指令（user prompt 已有） | ~500 |
| **新增合计** | **~1450** |
| 当前 max_tokens（动态漫 ~4000-8000） | 占比 ~18% |

### 6. 涉及文件变更

#### 新增
- `script_rubric/pipeline/extract_fewshots.py` — 范本提取脚本
- `backend/app/services/style_guard.py` — 反 AI 味清单 + 金句管理服务
- `script_rubric/outputs/style_samples_dynamic.json` — 动态漫范本数据
- `script_rubric/outputs/style_samples_explanatory.json` — 解说漫范本数据

#### 修改
- `backend/app/services/script_ai_service.py` — `generate_episode_content` prompt 注入三层结构

#### 不变
- 路由层（`drama.py`）— `script_type` 已在现有方法签名中
- 前端 — 无任何 UI 变更
- HandbookProvider — 不受影响
- 其他生成方法（outline/expand/rewrite）— 暂不改动

## 实施顺序

1. 运行 `extract_fewshots.py` 提取范本 → 人工审核 → 输出 JSON
2. 编写 `style_guard.py` 服务
3. 修改 `script_ai_service.py` 的 `generate_episode_content`
4. 测试：生成 1-2 集，对比有/无范本的输出质量
5. 根据测试结果微调范本选择和反例清单

## 风险与缓解

| 风险 | 缓解策略 |
|------|---------|
| Few-shot 过度模仿单一范本 | 每次请求随机轮换 1-2 段范本；Prompt 中明确"模仿节奏结构，禁用范本辞藻" |
| 反例清单导致 AI 僵硬 | 反例用"禁止"而非"必须"的表述，给 AI 正向创作空间；temperature 保持 0.7-0.85 |
| 解说漫样本不足 | 从动态漫范本中提取通用文笔特征（短句/留白/口语化/信息密度）补充 |
| Token 开销过大 | 范本总量 ≤1500 tokens；提供 `use_style_samples` 开关可关闭 |
| 正则提取脏数据 | 提取后人工审核，不纯净的片段手工剔除 |
