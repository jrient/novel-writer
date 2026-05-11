"""单进程内的 version 级事件总线，用于 SSE 推送。

- 仅支持单 worker 部署。
- 订阅者按 version_id 分组；publish 时往该 version 的所有订阅者 queue 各 put 一份。
- 订阅者负责调用 unsubscribe 释放资源。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass(eq=False)
class _Subscriber:
    version_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    _uid: int = field(default_factory=lambda: id(object()), repr=False)

    def __hash__(self) -> int:
        return self._uid

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Subscriber) and self._uid == other._uid


class _EventBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[_Subscriber]] = {}

    def subscribe(self, version_id: int) -> _Subscriber:
        sub = _Subscriber(version_id=version_id)
        self._subs.setdefault(version_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        bucket = self._subs.get(sub.version_id)
        if bucket and sub in bucket:
            bucket.remove(sub)
            if not bucket:
                self._subs.pop(sub.version_id, None)

    async def publish(self, version_id: int, payload: Dict[str, Any]) -> None:
        for sub in list(self._subs.get(version_id, ())):
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                sub.queue.put_nowait(payload)


event_bus = _EventBus()
