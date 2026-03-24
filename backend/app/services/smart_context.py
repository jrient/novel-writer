"""
智能上下文服务
基于语义匹配自动注入最相关的角色、世界观、事件、伏笔等上下文信息
"""
import logging
from typing import List, Dict, Optional, Any, Set
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.models.event import StoryEvent
from app.models.note import Note
from app.models.outline import OutlineNode

logger = logging.getLogger(__name__)


class ContextEntity:
    """上下文实体"""
    def __init__(
        self,
        id: int,
        type: str,
        name: str,
        summary: str = "",
        relevance: float = 0,
        match_reason: str = "",
        is_pinned: bool = False,
        raw_data: Dict = None
    ):
        self.id = id
        self.type = type
        self.name = name
        self.summary = summary
        self.relevance = relevance
        self.match_reason = match_reason
        self.is_pinned = is_pinned
        self.raw_data = raw_data or {}

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "summary": self.summary,
            "relevance": self.relevance,
            "match_reason": self.match_reason,
            "is_pinned": self.is_pinned,
        }


class SmartContextService:
    """智能上下文服务：基于语义匹配构建 AI 上下文"""

    def __init__(self, db: AsyncSession, project_id: int):
        self.db = db
        self.project_id = project_id

    async def build_smart_context(
        self,
        content: str = "",
        action: str = "continue",
        chapter_id: Optional[int] = None,
        include_events: bool = True,
        include_notes: bool = True,
        include_outline: bool = True,
        max_characters: int = 8,
        max_worldbuilding: int = 5,
        max_events: int = 5,
        max_notes: int = 3,
        pinned_context: Optional[Dict[str, List[int]]] = None,
    ) -> Dict[str, Any]:
        """
        构建智能上下文

        Args:
            content: 当前章节内容/用户输入
            action: AI 动作类型
            chapter_id: 当前章节 ID
            include_events: 是否包含事件
            include_notes: 是否包含笔记/伏笔
            include_outline: 是否包含大纲
            max_characters: 最大角色数
            max_worldbuilding: 最大世界观条目数
            max_events: 最大事件数
            max_notes: 最大笔记数
            pinned_context: 用户固定的上下文实体 {"characters": [id1, id2], "worldbuilding": [id3], ...}

        Returns:
            包含各类上下文的字典，新增 entities 字段用于前端展示
        """
        result = {
            "characters": [],
            "worldbuilding": [],
            "events": [],
            "notes": [],
            "outline": [],
            "context_text": "",
            "entities": [],  # 新增：结构化实体列表，用于前端反馈
        }

        # 解析固定上下文
        pinned_chars: Set[int] = set(pinned_context.get("characters", [])) if pinned_context else set()
        pinned_world: Set[int] = set(pinned_context.get("worldbuilding", [])) if pinned_context else set()
        pinned_events: Set[int] = set(pinned_context.get("events", [])) if pinned_context else set()
        pinned_notes: Set[int] = set(pinned_context.get("notes", [])) if pinned_context else set()

        try:
            # 1. 获取所有角色和世界观基础数据
            all_characters = await self._get_all_characters()
            all_worldbuilding = await self._get_all_worldbuilding()

            # 2. 基于语义匹配选择最相关的角色和世界观
            if content and len(content) > 20:
                # 有内容时进行语义匹配
                result["characters"] = await self._match_characters(
                    content, all_characters, max_characters, pinned_chars
                )
                result["worldbuilding"] = await self._match_worldbuilding(
                    content, all_worldbuilding, max_worldbuilding, pinned_world
                )
            else:
                # 无内容时返回优先级最高的
                result["characters"] = self._prioritize_characters(all_characters, max_characters, pinned_chars)
                result["worldbuilding"] = self._add_pinned_flag(all_worldbuilding[:max_worldbuilding], pinned_world)

            # 3. 获取相关事件
            if include_events:
                result["events"] = await self._get_relevant_events(chapter_id, max_events, pinned_events)

            # 4. 获取活跃伏笔和笔记
            if include_notes:
                result["notes"] = await self._get_active_notes(max_notes, pinned_notes)

            # 5. 获取大纲概览
            if include_outline:
                result["outline"] = await self._get_outline_summary()

            # 6. 构建格式化的上下文文本
            result["context_text"] = self._format_context_text(result)

            # 7. 构建结构化实体列表（用于前端反馈）
            result["entities"] = self._build_entities_list(result)

        except Exception as e:
            logger.error(f"构建智能上下文失败: {e}", exc_info=True)

        return result

    def _add_pinned_flag(self, items: List[Dict], pinned_ids: Set[int]) -> List[Dict]:
        """为已固定的实体添加标记"""
        for item in items:
            if item.get("id") in pinned_ids:
                item["is_pinned"] = True
                item["match_reason"] = "用户固定"
        return items

    async def _get_all_characters(self) -> List[Dict]:
        """获取项目所有角色"""
        result = await self.db.execute(
            select(Character)
            .where(Character.project_id == self.project_id)
            .order_by(Character.id)
        )
        characters = result.scalars().all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "role_type": c.role_type or "supporting",
                "gender": c.gender or "",
                "age": c.age or "",
                "occupation": c.occupation or "",
                "personality": c.personality_traits or "",
                "appearance": c.appearance or "",
                "background": c.background or "",
                "growth_arc": c.growth_arc or "",
            }
            for c in characters
        ]

    async def _get_all_worldbuilding(self) -> List[Dict]:
        """获取项目所有世界观设定"""
        result = await self.db.execute(
            select(WorldbuildingEntry)
            .where(WorldbuildingEntry.project_id == self.project_id)
            .order_by(WorldbuildingEntry.id)
        )
        entries = result.scalars().all()
        return [
            {
                "id": w.id,
                "title": w.title,
                "category": w.category or "其他",
                "content": w.content or "",
            }
            for w in entries
        ]

    async def _match_characters(
        self,
        content: str,
        all_characters: List[Dict],
        max_count: int,
        pinned_ids: Set[int] = None
    ) -> List[Dict]:
        """基于语义匹配选择最相关的角色"""
        if not all_characters:
            return []

        pinned_ids = pinned_ids or set()
        mentioned_chars = []
        other_chars = []

        # 首先处理固定的角色（最高优先级）
        for char in all_characters:
            if char["id"] in pinned_ids:
                mentioned_chars.append({**char, "relevance": 1.0, "is_pinned": True, "match_reason": "用户固定"})
            elif char["name"] in content:
                mentioned_chars.append({**char, "relevance": 0.9, "match_reason": "名称出现在文中"})
            else:
                other_chars.append(char)

        # 方法2：关键词匹配
        if len(mentioned_chars) < max_count and other_chars and len(content) > 50:
            try:
                keyword_scores = []
                for i, c in enumerate(other_chars):
                    score = 0
                    # 检查职业/身份关键词
                    if c.get("occupation"):
                        for kw in c["occupation"].split():
                            if kw in content:
                                score += 0.3
                    # 检查性格关键词
                    if c.get("personality"):
                        for kw in c["personality"].split()[:5]:
                            if kw in content:
                                score += 0.2
                    keyword_scores.append((c, score))

                # 按分数排序
                keyword_scores.sort(key=lambda x: x[1], reverse=True)
                for c, score in keyword_scores[:max_count - len(mentioned_chars)]:
                    match_reason = "关键词匹配" if score > 0.3 else "语义相关"
                    mentioned_chars.append({**c, "relevance": score, "match_reason": match_reason})

            except Exception as e:
                logger.warning(f"角色语义匹配失败，使用默认排序: {e}")
                mentioned_chars.extend(other_chars[:max_count - len(mentioned_chars)])

        # 补充主角（如果有空间）
        if len(mentioned_chars) < max_count:
            for c in all_characters:
                if c["id"] not in [x["id"] for x in mentioned_chars]:
                    if c["role_type"] == "protagonist":
                        mentioned_chars.append({**c, "relevance": 0.5, "match_reason": "主角"})
                        if len(mentioned_chars) >= max_count:
                            break

        return mentioned_chars[:max_count]

    async def _match_worldbuilding(
        self,
        content: str,
        all_worldbuilding: List[Dict],
        max_count: int,
        pinned_ids: Set[int] = None
    ) -> List[Dict]:
        """基于语义匹配选择最相关的世界观"""
        if not all_worldbuilding:
            return []

        pinned_ids = pinned_ids or set()
        matched = []

        # 首先处理固定的世界观（最高优先级）
        for w in all_worldbuilding:
            if w["id"] in pinned_ids:
                matched.append({**w, "relevance": 1.0, "is_pinned": True, "match_reason": "用户固定"})
                continue

            score = 0
            # 标题匹配
            if w["title"] in content:
                score += 0.9
            # 内容关键词匹配
            if w.get("content"):
                keywords = w["content"][:100].split()
                for kw in keywords:
                    if len(kw) > 1 and kw in content:
                        score += 0.1
            if score > 0:
                matched.append({**w, "relevance": score, "match_reason": "关键词匹配"})

        # 按相关性排序
        matched.sort(key=lambda x: x.get("relevance", 0), reverse=True)

        # 补充不足的部分
        if len(matched) < max_count:
            for w in all_worldbuilding:
                if w["id"] not in [x["id"] for x in matched]:
                    matched.append({**w, "relevance": 0, "match_reason": "默认选择"})
                    if len(matched) >= max_count:
                        break

        return matched[:max_count]

    def _prioritize_characters(self, characters: List[Dict], max_count: int, pinned_ids: Set[int] = None) -> List[Dict]:
        """按优先级排序角色（主角优先），固定角色最优先"""
        pinned_ids = pinned_ids or set()
        result = []

        # 首先添加固定角色
        for c in characters:
            if c["id"] in pinned_ids:
                result.append({**c, "relevance": 1.0, "is_pinned": True, "match_reason": "用户固定"})

        # 然后按优先级添加其他角色
        priority_order = {"protagonist": 0, "antagonist": 1, "supporting": 2, "minor": 3}
        remaining = [c for c in characters if c["id"] not in pinned_ids]
        sorted_chars = sorted(
            remaining,
            key=lambda x: priority_order.get(x.get("role_type", "minor"), 3)
        )

        for c in sorted_chars:
            if len(result) >= max_count:
                break
            match_reason = "主角" if c.get("role_type") == "protagonist" else "默认选择"
            result.append({**c, "relevance": 0.5, "match_reason": match_reason})

        return result[:max_count]

    async def _get_relevant_events(
        self,
        chapter_id: Optional[int],
        max_count: int,
        pinned_ids: Set[int] = None
    ) -> List[Dict]:
        """获取相关事件"""
        pinned_ids = pinned_ids or set()
        result = await self.db.execute(
            select(StoryEvent)
            .where(
                StoryEvent.project_id == self.project_id,
                StoryEvent.status != "dropped"
            )
            .order_by(StoryEvent.timeline_order, StoryEvent.id)
            .limit(max_count * 2)
        )
        events = result.scalars().all()

        # 按重要性排序
        importance_order = {"critical": 0, "major": 1, "minor": 2}
        sorted_events = sorted(
            events,
            key=lambda x: importance_order.get(x.importance, 2)
        )

        # 构建结果，固定的事件优先
        final_events = []
        for e in sorted_events:
            if e.id in pinned_ids:
                final_events.append({
                    "id": e.id,
                    "title": e.title,
                    "description": e.description or "",
                    "event_type": e.event_type,
                    "status": e.status,
                    "importance": e.importance,
                    "is_pinned": True,
                    "match_reason": "用户固定",
                })
        for e in sorted_events:
            if e.id not in pinned_ids and len(final_events) < max_count:
                final_events.append({
                    "id": e.id,
                    "title": e.title,
                    "description": e.description or "",
                    "event_type": e.event_type,
                    "status": e.status,
                    "importance": e.importance,
                    "match_reason": "关键事件" if e.importance == "critical" else "相关事件",
                })

        return final_events[:max_count]

    async def _get_active_notes(self, max_count: int, pinned_ids: Set[int] = None) -> List[Dict]:
        """获取活跃的伏笔和笔记"""
        pinned_ids = pinned_ids or set()
        result = await self.db.execute(
            select(Note)
            .where(
                Note.project_id == self.project_id,
                Note.status == "active"
            )
            .order_by(Note.note_type, Note.created_at.desc())
            .limit(max_count * 2)
        )
        notes = result.scalars().all()

        # 伏笔优先
        foreshadowing = [n for n in notes if n.note_type == "foreshadowing"]
        others = [n for n in notes if n.note_type != "foreshadowing"]

        selected = []

        # 首先添加固定的笔记
        for n in foreshadowing + others:
            if n.id in pinned_ids:
                selected.append({
                    "id": n.id,
                    "title": n.title,
                    "content": n.content or "",
                    "note_type": n.note_type,
                    "is_pinned": True,
                    "match_reason": "用户固定",
                })

        # 然后添加其他笔记
        for n in foreshadowing + others:
            if n.id not in pinned_ids and len(selected) < max_count:
                type_map = {"foreshadowing": "伏笔", "inspiration": "灵感", "note": "笔记", "miaoji": "妙记"}
                selected.append({
                    "id": n.id,
                    "title": n.title,
                    "content": n.content or "",
                    "note_type": n.note_type,
                    "match_reason": f"活跃{type_map.get(n.note_type, '笔记')}",
                })

        return selected[:max_count]

    async def _get_outline_summary(self) -> List[Dict]:
        """获取大纲概览"""
        result = await self.db.execute(
            select(OutlineNode)
            .where(OutlineNode.project_id == self.project_id)
            .order_by(OutlineNode.level, OutlineNode.sort_order)
            .limit(20)
        )
        nodes = result.scalars().all()

        return [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content or "",
                "node_type": n.node_type,
                "level": n.level,
            }
            for n in nodes
        ]

    def _build_entities_list(self, context: Dict) -> List[Dict]:
        """构建结构化实体列表，用于前端反馈"""
        entities = []

        # 角色
        for c in context.get("characters", []):
            summary = f"{c.get('role_type', '配角')}"
            if c.get("occupation"):
                summary += f"，{c.get('occupation')}"
            if c.get("personality"):
                summary += f"，{c.get('personality', '')[:50]}"
            entities.append({
                "id": c.get("id"),
                "type": "character",
                "name": c.get("name", "未命名"),
                "summary": summary,
                "relevance": c.get("relevance", 0),
                "match_reason": c.get("match_reason", ""),
                "is_pinned": c.get("is_pinned", False),
            })

        # 世界观
        for w in context.get("worldbuilding", []):
            summary = f"[{w.get('category', '其他')}] "
            if w.get("content"):
                summary += w.get("content", "")[:80]
            entities.append({
                "id": w.get("id"),
                "type": "worldbuilding",
                "name": w.get("title", "未命名"),
                "summary": summary,
                "relevance": w.get("relevance", 0),
                "match_reason": w.get("match_reason", ""),
                "is_pinned": w.get("is_pinned", False),
            })

        # 事件
        for e in context.get("events", []):
            importance_map = {"critical": "关键", "major": "重要", "minor": "次要"}
            summary = f"[{importance_map.get(e.get('importance'), '普通')}] {e.get('event_type', '')}"
            if e.get("description"):
                summary += f"：{e.get('description', '')[:60]}"
            entities.append({
                "id": e.get("id"),
                "type": "event",
                "name": e.get("title", "未命名"),
                "summary": summary,
                "relevance": 1.0 if e.get("importance") == "critical" else 0.5,
                "match_reason": e.get("match_reason", ""),
                "is_pinned": e.get("is_pinned", False),
            })

        # 笔记/伏笔
        for n in context.get("notes", []):
            type_map = {"foreshadowing": "伏笔", "inspiration": "灵感", "note": "笔记", "miaoji": "妙记"}
            summary = f"[{type_map.get(n.get('note_type'), '笔记')}]"
            if n.get("content"):
                summary += f" {n.get('content', '')[:60]}"
            entities.append({
                "id": n.get("id"),
                "type": "note",
                "name": n.get("title", "未命名"),
                "summary": summary,
                "relevance": 0.7 if n.get("note_type") == "foreshadowing" else 0.4,
                "match_reason": n.get("match_reason", ""),
                "is_pinned": n.get("is_pinned", False),
            })

        # 大纲
        for o in context.get("outline", []):
            summary = f"{'  ' * o.get('level', 0)}[{o.get('node_type', '章节')}]"
            if o.get("content"):
                summary += f" {o.get('content', '')[:50]}"
            entities.append({
                "id": o.get("id"),
                "type": "outline",
                "name": o.get("title", "未命名"),
                "summary": summary,
                "relevance": 0.3,
                "match_reason": "故事大纲",
                "is_pinned": False,
            })

        # 按相关性和类型排序：固定的最前，然后按相关性排序
        entities.sort(key=lambda x: (
            not x.get("is_pinned", False),  # 固定的在前
            -x.get("relevance", 0),  # 相关性高的在前
        ))

        return entities

    def _format_context_text(self, context: Dict) -> str:
        """格式化上下文为文本"""
        parts = []

        # 角色设定
        if context.get("characters"):
            char_lines = []
            for c in context["characters"]:
                line = f"- {c.get('name', '未命名')}"

                # 角色类型
                role_map = {"protagonist": "主角", "antagonist": "反派", "supporting": "配角", "minor": "次要"}
                line += f"（{role_map.get(c.get('role_type'), '配角')}）"

                # 基本信息
                if c.get("occupation"):
                    line += f"，身份：{c['occupation']}"
                if c.get("personality"):
                    line += f"，性格：{c['personality'][:100]}"
                if c.get("background"):
                    line += f"，背景：{c['background'][:150]}"
                if c.get("appearance"):
                    line += f"，外貌：{c['appearance'][:80]}"

                char_lines.append(line)
            parts.append("【角色设定】\n" + "\n".join(char_lines))

        # 世界观设定
        if context.get("worldbuilding"):
            world_lines = []
            for w in context["worldbuilding"]:
                line = f"- {w.get('title', '未命名')}（{w.get('category', '其他')}）"
                if w.get("content"):
                    line += f"：{w['content'][:150]}"
                world_lines.append(line)
            parts.append("【世界观设定】\n" + "\n".join(world_lines))

        # 重要事件
        if context.get("events"):
            event_lines = []
            for e in context["events"]:
                importance_map = {"critical": "关键", "major": "重要", "minor": "次要"}
                line = f"- [{importance_map.get(e.get('importance'), '普通')}] {e.get('title', '')}"
                if e.get("description"):
                    line += f"：{e['description'][:100]}"
                event_lines.append(line)
            parts.append("【重要事件】\n" + "\n".join(event_lines))

        # 活跃伏笔
        if context.get("notes"):
            note_lines = []
            for n in context["notes"]:
                type_map = {"foreshadowing": "伏笔", "inspiration": "灵感", "note": "笔记", "miaoji": "妙记"}
                line = f"- [{type_map.get(n.get('note_type'), '笔记')}] {n.get('title', '')}"
                if n.get("content"):
                    line += f"：{n['content'][:80]}"
                note_lines.append(line)
            parts.append("【伏笔/笔记】\n" + "\n".join(note_lines))

        # 大纲概览
        if context.get("outline"):
            outline_lines = []
            for o in context["outline"]:
                indent = "  " * o.get("level", 0)
                line = f"{indent}- {o.get('title', '')}"
                if o.get("content"):
                    line += f"：{o['content'][:50]}"
                outline_lines.append(line)
            parts.append("【故事大纲】\n" + "\n".join(outline_lines))

        return "\n\n".join(parts)