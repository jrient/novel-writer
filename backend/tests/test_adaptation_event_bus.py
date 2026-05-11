"""事件总线测试。"""
import asyncio
import pytest
from app.services.adaptation_event_bus import event_bus


@pytest.mark.asyncio
async def test_subscribe_receives_published_events():
    sub = event_bus.subscribe(version_id=42)
    try:
        async def publish_later():
            await asyncio.sleep(0.01)
            await event_bus.publish(42, {"event": "scene_done", "scene_index": 0})
            await event_bus.publish(43, {"event": "ignored"})
            await event_bus.publish(42, {"event": "done"})

        task = asyncio.create_task(publish_later())
        msgs: list = []
        async with asyncio.timeout(1.0):
            while len(msgs) < 2:
                msgs.append(await sub.queue.get())
        await task
        assert msgs[0]["event"] == "scene_done"
        assert msgs[1]["event"] == "done"
    finally:
        event_bus.unsubscribe(sub)


@pytest.mark.asyncio
async def test_publish_no_subscribers_drops_silently():
    await event_bus.publish(999, {"event": "x"})
