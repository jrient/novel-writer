"""统一 UTC 时间工具。

替代已弃用的 datetime.utcnow()。整个项目的 DateTime 列均未带 timezone=True
（即 PG 的 TIMESTAMP WITHOUT TIME ZONE），asyncpg 拒绝写 tz-aware datetime，
所以这里只暴露 naive UTC。如未来切到 timezone=True，可在此集中演进。
"""
from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """当前 UTC 时间的 naive datetime，语义等价于 datetime.utcnow()。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
