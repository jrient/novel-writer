"""canon_event_bus：subscribe/publish/unsubscribe，按 reference_id 分组"""
import pytest
from app.services.canon_event_bus import canon_event_bus


async def test_publish_reaches_subscriber():
    sub = canon_event_bus.subscribe(reference_id=42)
    await canon_event_bus.publish(42, {"event": "progress", "chunk_done": 1})
    msg = sub.queue.get_nowait()
    assert msg["event"] == "progress"
    canon_event_bus.unsubscribe(sub)


async def test_unsubscribe_removes_bucket():
    sub = canon_event_bus.subscribe(reference_id=7)
    canon_event_bus.unsubscribe(sub)
    # 再 publish 不应抛错（无订阅者）
    await canon_event_bus.publish(7, {"event": "done"})
