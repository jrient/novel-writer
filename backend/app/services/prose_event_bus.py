# backend/app/services/prose_event_bus.py
"""单进程内的 project 级事件总线，用于 prose SSE 推送。
与 adaptation_event_bus 相同模式，按 project_id 分组。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass(eq=False)
class _Subscriber:
    project_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    _uid: int = field(default_factory=lambda: id(object()), repr=False)

    def __hash__(self) -> int:
        return self._uid

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Subscriber) and self._uid == other._uid


class _EventBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[_Subscriber]] = {}

    def subscribe(self, project_id: int) -> _Subscriber:
        sub = _Subscriber(project_id=project_id)
        self._subs.setdefault(project_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        bucket = self._subs.get(sub.project_id)
        if bucket and sub in bucket:
            bucket.remove(sub)
            if not bucket:
                self._subs.pop(sub.project_id, None)

    async def publish(self, project_id: int, payload: Dict[str, Any]) -> None:
        for sub in list(self._subs.get(project_id, ())):
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                sub.queue.put_nowait(payload)


prose_event_bus = _EventBus()
