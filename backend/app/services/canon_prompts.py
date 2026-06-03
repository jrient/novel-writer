"""原作设定提取 prompts：原子提取 + 跨块归并消歧。
设计要点（对应 spec 准确度三难点）：
- 原子提取强制每条设定附原文 quote + 章节定位（溯源/防幻觉）
- 归并按 entity_type 分组，要求消歧同一实体的不同称呼
"""
import json

ENTITY_TYPES_CN = {
    "character": "角色（人物）",
    "location": "地点（地名/场所）",
    "ability": "能力（功法/法术/法宝/技能）",
    "faction": "势力（门派/国家/组织）",
    "worldrule": "世界观规则（修炼体系/天道法则/社会设定）",
    "event": "关键事件（推动剧情的重大事件）",
}

ATOMIC_SYSTEM = """你是一位严谨的原作设定分析专家。请从给定的小说片段中，只提取【本片段明确出现】的设定信息，分为六类：
角色(character)/地点(location)/能力(ability)/势力(faction)/世界观规则(worldrule)/关键事件(event)。

【铁律——防止幻觉】
1. 只提取片段中【确有文字依据】的设定，严禁脑补、严禁补充原作其他章节的知识。
2. 每一条设定都必须附带 source（原文引用片段 quote，≤40字，从片段中原样摘录）。
3. 无法确定的字段留空，不要编造。

严格输出 JSON 数组，每个元素格式：
{
  "entity_type": "character|location|ability|faction|worldrule|event",
  "canonical_name": "设定名",
  "aliases": ["别名/称呼"],
  "summary": "一句话设定（仅依据本片段）",
  "attributes": {"任意键": "值"},
  "source": {"quote": "原文摘录≤40字"},
  "importance": "critical|major|minor"
}
只输出 JSON 数组，不要任何解释文字。"""

MERGE_SYSTEM = """你是一位严谨的原作设定归并专家。下面是从同一部原作不同片段提取的【同一类型】设定条目，其中可能有重复或指代同一对象的不同称呼。

【任务】
1. 把指代同一对象的条目【归并为一条】：选最正式的名字作 canonical_name，其余称呼并入 aliases。
2. 合并各条目的 attributes（冲突时保留更具体的，并在 summary 注明）。
3. 保留所有来源 source 到 source_refs 数组，不得丢弃。
4. 严禁新增原文没有的设定。

严格输出 JSON 数组，每个元素格式：
{
  "entity_type": "<与输入相同>",
  "canonical_name": "权威名",
  "aliases": ["所有别名"],
  "summary": "综合一句话设定",
  "attributes": {...},
  "source_refs": [{"quote": "..."}, ...],
  "importance": "critical|major|minor"
}
只输出 JSON 数组，不要任何解释文字。"""


def build_atomic_prompt(chunk_text: str, chunk_label: str) -> str:
    return (
        f"{ATOMIC_SYSTEM}\n\n"
        f"【片段位置】{chunk_label}\n"
        f"【片段正文】\n{chunk_text}\n\n"
        f"请输出本片段的设定 JSON 数组（每条含 source.quote 原文引用）："
    )


def build_merge_prompt(entity_type: str, raw_entities: list) -> str:
    type_cn = ENTITY_TYPES_CN.get(entity_type, entity_type)
    payload = json.dumps(raw_entities, ensure_ascii=False, indent=2)
    return (
        f"{MERGE_SYSTEM}\n\n"
        f"【设定类型】{type_cn}（{entity_type}）\n"
        f"【待归并条目】\n{payload}\n\n"
        f"请输出归并消歧后的 JSON 数组："
    )
