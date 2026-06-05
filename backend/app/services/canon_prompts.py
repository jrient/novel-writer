"""原作设定提取 prompts：原子提取 + 跨块归并消歧。
设计要点（对应 spec 准确度三难点）：
- 原子提取强制每条设定附原文 quote + 章节定位（溯源/防幻觉）
- 归并按 entity_type 分组，要求消歧同一实体的不同称呼
"""
import json

ENTITY_TYPES_CN = {
    "character": "角色（人物）",
    "location": "地点（地名/场所）",
    "ability": "能力（功法/法术/技能）",
    "faction": "势力（门派/国家/组织）",
    "worldrule": "世界观规则（修炼体系/天道法则/社会设定）",
    "event": "关键事件（推动剧情的重大事件）",
    "item": "物品（法宝/神器/丹药/功法秘籍等实体道具）",
    "race": "种族/血脉（人族/妖族/魔族/血脉传承）",
    "realm": "境界/体系（修为境界/等级体系，如练气→筑基）",
    "concept": "专有术语（设定专名，非上述具体物）",
}

ATOMIC_SYSTEM = """你是一位严谨的原作设定分析专家。请从给定的小说片段中，只提取【本片段明确出现】的设定信息，分为十类：
角色(character)/地点(location)/能力(ability)/势力(faction)/世界观规则(worldrule)/关键事件(event)/物品(item)/种族血脉(race)/境界体系(realm)/专有术语(concept)。

【铁律——防止幻觉】
1. 只提取片段中【确有文字依据】的设定，严禁脑补、严禁补充原作其他章节的知识。
2. 每一条设定都必须附带 source（原文引用片段 quote，≤40字，从片段中原样摘录）。
3. 无法确定的字段留空，不要编造。

严格输出 JSON 数组，每个元素格式：
{
  "entity_type": "character|location|ability|faction|worldrule|event|item|race|realm|concept",
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

# 受控关系词表：key 为存储值，value 为说明
RELATION_TYPES_CN = {
    "亲属": "角色↔角色：血缘/姻亲",
    "师徒": "角色↔角色：师承",
    "情感": "角色↔角色：恋慕/夫妻/挚友",
    "盟友": "角色↔角色 或 势力↔势力：结盟",
    "敌对": "角色/势力之间：敌对仇杀",
    "上下级": "角色↔角色：统属/主从",
    "属于": "角色→势力/种族：归属",
    "领导": "角色→势力：领导/掌门",
    "创立": "角色→势力：开创",
    "出身": "角色→地点：出生地/来历",
    "居于": "角色→地点：居所",
    "统治": "角色→地点/势力：治理",
    "掌握": "角色→能力：习得功法/技能",
    "持有": "角色→物品：拥有",
    "炼制": "角色→物品：炼制/创造",
    "处于境界": "角色→境界：当前修为",
    "参与": "角色→事件：参与",
    "主导": "角色→事件：主导/发动",
    "受害": "角色→事件：受害方",
    "承载": "物品→能力：法宝赋予能力",
    "记载": "物品→能力：秘籍记载功法",
    "天赋": "种族→能力：天生能力",
    "进阶": "境界→境界：层级递进",
    "因果": "事件→事件：因果",
    "时序": "事件→事件：先后",
    "伏笔": "事件→事件：伏笔呼应",
    "发生于": "事件→地点：发生地",
    "隶属": "势力→势力 或 地点→地点：层级隶属",
    "custom": "以上都不匹配时，用自由文本 label 描述关系",
}

RELATION_SYSTEM = """你是一位严谨的原作关系分析专家。下面给你【本部原作已确认的设定实体清单】和【一个原文片段】。
请只在【清单内实体之间】抽取本片段中【有文字依据】的关系，形成三元组。

【铁律】
1. source 与 target 必须是清单里的 canonical_name，严禁出现清单外的名字。
2. 只抽本片段确有依据的关系，严禁脑补；每条须附 quote（原文摘录≤40字）。
3. relation_type 优先取受控词表的 key；都不匹配时填 "custom" 并在 label 写明关系。

严格输出 JSON 数组，元素格式：
{
  "source": "清单中的 canonical_name",
  "target": "清单中的 canonical_name",
  "relation_type": "受控词表 key 或 custom",
  "label": "关系简述（custom 必填，其它可选）",
  "quote": "原文摘录≤40字"
}
只输出 JSON 数组，不要任何解释文字。"""


def build_relation_prompt(entities: list, chunk_text: str, chunk_label: str) -> str:
    vocab = "\n".join(f"- {k}：{v}" for k, v in RELATION_TYPES_CN.items())
    ent_lines = "\n".join(
        f"- {e.get('canonical_name')}（{e.get('entity_type')}）" for e in entities
    )
    return (
        f"{RELATION_SYSTEM}\n\n"
        f"【受控关系词表】\n{vocab}\n\n"
        f"【实体清单】\n{ent_lines}\n\n"
        f"【片段位置】{chunk_label}\n【片段正文】\n{chunk_text}\n\n"
        f"请输出本片段实体间的关系 JSON 数组（每条含 quote）："
    )
