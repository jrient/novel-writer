"""单进程内的 reference 级事件总线，用于 canon 提取 SSE 推送。
与 prose_event_bus 相同模式，按 reference_id 分组。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass(eq=False)
class _Subscriber:
    reference_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    _uid: int = field(default_factory=lambda: id(object()), repr=False)

    def __hash__(self) -> int:
        return self._uid

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Subscriber) and self._uid == other._uid


class _EventBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[_Subscriber]] = {}

    def subscribe(self, reference_id: int) -> _Subscriber:
        sub = _Subscriber(reference_id=reference_id)
        self._subs.setdefault(reference_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        bucket = self._subs.get(sub.reference_id)
        if bucket and sub in bucket:
            bucket.remove(sub)
            if not bucket:
                self._subs.pop(sub.reference_id, None)

    async def publish(self, reference_id: int, payload: Dict[str, Any]) -> None:
        for sub in list(self._subs.get(reference_id, ())):
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                sub.queue.put_nowait(payload)


canon_event_bus = _EventBus()
