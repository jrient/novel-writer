# Bitable CLI 数据源迁移 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 CLI 工具替换原有飞书 sheet 自动同步链路；rubric pipeline 直接读 bitable 规范化 JSON，不再依赖 xlsx。

**Architecture:** 用户在飞书克隆 bitable 副本（关闭高级权限）→ 把副本 URL 传给 `python data/sync_bitable.py <url>` → CLI 拉数据写 JSON → 默认串 rubric pipeline。无定时调度，无 API 触发。

**Tech Stack:** Python 3.11, FastAPI（仅维护移除路由）, requests, openpyxl（删除）, pydantic, pytest

**Spec 参考:** `docs/superpowers/specs/2026-04-27-bitable-cli-migration-design.md`

---

## 任务路径图

```
T0 (开放项验证)
  └→ T1 (feishu_common.py)
       └→ T2 (parse_bitable.py + 测试)
            └→ T3 (config.py + run.py 切换)
                 └→ T4 (sync_bitable.py CLI)
                      └→ T5 (打通 backend 路由清理)
                           └→ T6 (smoke test, 需用户提供副本 URL)
                                └→ T7 (清理删除)
                                     └→ T8 (最终验证 + commit)
```

每个任务都以 commit 结尾。T6 需要用户参与（提供真实副本 URL）。

---

## Task 0: 验证开放项 O1–O5

**Files:** 仅查询，无修改

- [ ] **Step 1：O1 验证 bitable:app:readonly 权限**

```bash
docker exec novel-writer-backend python /tmp/probe3.py 2>&1 | head -20
```

预期：能拉到 `name=外部待审核剧本 副本0427`、`tables.items` 非空，证明权限已通。如失败，需要在飞书开发者后台开通后重发布应用版本。

- [ ] **Step 2：O2 验证 rubric 其他测试不依赖 parse_xlsx**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest script_rubric/tests/ --collect-only -q 2>&1 | head -40"
```

确认看到 `test_extract_archive.py`, `test_iterate_handbook.py`, `test_synthesize.py` 等不在删除清单里的测试存在。仅记录清单，无 fix。

- [ ] **Step 3：O3 已确认（在计划编写阶段）**

`backend/app/routers/feishu_sync.py` 注册在 `backend/app/main.py:37,137`，前端无消费者。结论：**该路由整个删除**，相关函数从 `scheduled_task.py` 一并清理（task 5 处理）。

- [ ] **Step 4：O4 验证 backend 容器代码热加载行为**

```bash
docker inspect novel-writer-backend --format='{{.Config.Cmd}} {{.HostConfig.Binds}}' 2>&1
```

预期：若 `/app` 是 bind mount（项目目录映射进去），则代码改动自动生效，重启 uvicorn 即可（`docker restart novel-writer-backend`）。否则需 `docker compose build`。记录结论用于 task 5/8。

- [ ] **Step 5：O5 估算 raw_fields 体积**

```bash
docker exec novel-writer-backend python -c "
import json, requests
APP_ID='<FEISHU_APP_ID>'; APP_SECRET='<FEISHU_APP_SECRET>'
APP_TOKEN='<BITABLE_APP_TOKEN>'
NO_PROXY={'http':'','https':''}
r=requests.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
  json={'app_id':APP_ID,'app_secret':APP_SECRET},proxies=NO_PROXY)
tok=r.json()['tenant_access_token']
all_items=[]; pt=None
while True:
    params={'page_size':500}
    if pt: params['page_token']=pt
    r=requests.get(f'https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/tblkvyapBqrMSQWa/records',
      headers={'Authorization':f'Bearer {tok}'},params=params,proxies=NO_PROXY)
    d=r.json()['data']
    all_items.extend(d['items'])
    if not d.get('has_more'): break
    pt=d.get('page_token')
sz=len(json.dumps([i.get('fields',{}) for i in all_items],ensure_ascii=False).encode('utf-8'))
print(f'精品 records={len(all_items)} raw_fields_bytes={sz} ({sz/1024:.1f} KiB)')
"
```

预期：精品 180 条，raw_fields 总体积 < 5 MiB。如 > 10 MiB，需要在 task 4 实现时考虑剔除「点评」长文本字段。记录结论。

- [ ] **Step 6：Commit Task 0 记录（无代码改动则跳过）**

如有任何文档/笔记更新提交，否则跳过。本任务多为查询，无 commit。

---

## Task 1: 创建 `data/feishu_common.py`（共享工具）

**Files:**
- Create: `data/feishu_common.py`
- Create: `data/tests/__init__.py`
- Create: `data/tests/test_feishu_common.py`

抽取自旧 `data/get_feishu_doc.py` 的 token、URL 解析、wiki resolve 逻辑，作为新 CLI 的共享工具层。

- [ ] **Step 1：创建 `data/tests/__init__.py`（空）**

```bash
mkdir -p /data/project/novel-writer/data/tests
touch /data/project/novel-writer/data/tests/__init__.py
```

- [ ] **Step 2：写 `data/tests/test_feishu_common.py`（失败的测试）**

```python
"""data/feishu_common 单元测试。"""
import pytest
from data.feishu_common import extract_token, FeishuURLError


class TestExtractToken:
    def test_base_url(self):
        url = "https://<TENANT>.feishu.cn/base/<BITABLE_APP_TOKEN>"
        kind, token = extract_token(url)
        assert kind == "bitable"
        assert token == "<BITABLE_APP_TOKEN>"

    def test_base_url_with_query(self):
        url = "https://<TENANT>.feishu.cn/base/<BITABLE_APP_TOKEN>?from=copylink"
        kind, token = extract_token(url)
        assert kind == "bitable"
        assert token == "<BITABLE_APP_TOKEN>"

    def test_wiki_url(self):
        url = "https://<TENANT>.feishu.cn/wiki/IEorwlbIwiafLzk5WK2cDK0on4b"
        kind, token = extract_token(url)
        assert kind == "wiki"
        assert token == "IEorwlbIwiafLzk5WK2cDK0on4b"

    def test_invalid_url(self):
        with pytest.raises(FeishuURLError):
            extract_token("https://example.com/not-feishu")

    def test_bare_token_rejected(self):
        with pytest.raises(FeishuURLError):
            extract_token("<BITABLE_APP_TOKEN>")
```

- [ ] **Step 3：运行测试确认失败**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest data/tests/test_feishu_common.py -v 2>&1 | tail -20"
```

预期：`ModuleNotFoundError: No module named 'data.feishu_common'`

- [ ] **Step 4：写 `data/feishu_common.py` 最小实现**

```python
"""
飞书 API 共享工具
==================

抽取自旧 data/get_feishu_doc.py，提供：
  - URL 解析（区分 base 多维表格 / wiki 节点）
  - tenant_access_token 获取
  - wiki 节点解析为实际 obj_token
  - 通用 GET 调用封装
"""
from __future__ import annotations

import os
import re
from typing import Any

import requests

FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]

BASE_URL = "https://open.feishu.cn"
NO_PROXY = {"http": "", "https": ""}


class FeishuURLError(ValueError):
    """飞书 URL 无法解析。"""


class FeishuAPIError(RuntimeError):
    """飞书 API 调用失败（非 0 code 或网络异常）。"""


def extract_token(url: str) -> tuple[str, str]:
    """从飞书 URL 中提取 token 和类型。

    返回 (kind, token):
      - kind = "bitable" 表示 /base/<app_token>
      - kind = "wiki"    表示 /wiki/<wiki_token>，需后续 resolve_wiki_node
    """
    m = re.search(r"feishu\.cn/(base|wiki)/([A-Za-z0-9]+)", url)
    if not m:
        raise FeishuURLError(
            f"URL 不是飞书 base/wiki 链接: {url}\n"
            f"期望形如: https://xxx.feishu.cn/base/<token> 或 .../wiki/<token>"
        )
    kind_raw, token = m.group(1), m.group(2)
    kind = "bitable" if kind_raw == "base" else "wiki"
    return kind, token


def get_tenant_access_token() -> str:
    """获取 tenant_access_token。"""
    url = f"{BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url,
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        proxies=NO_PROXY,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuAPIError(f"tenant_access_token 失败: code={data.get('code')} msg={data.get('msg')}")
    return data["tenant_access_token"]


def resolve_wiki_node(token: str, wiki_token: str) -> tuple[str, str]:
    """把 wiki_token 解析为底层 obj_token + obj_type。"""
    url = f"{BASE_URL}/open-apis/wiki/v2/spaces/get_node"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"token": wiki_token},
        proxies=NO_PROXY,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuAPIError(f"wiki 解析失败: code={data.get('code')} msg={data.get('msg')}")
    node = data["data"]["node"]
    return node["obj_token"], node["obj_type"]


def call_get(token: str, path: str, params: dict | None = None) -> dict[str, Any]:
    """通用 GET 调用：返回解析后的 JSON dict，非 0 code 抛 FeishuAPIError。"""
    url = f"{BASE_URL}{path}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        proxies=NO_PROXY,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuAPIError(f"GET {path} 失败: code={data.get('code')} msg={data.get('msg')}")
    return data
```

- [ ] **Step 5：运行测试确认通过**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest data/tests/test_feishu_common.py -v 2>&1 | tail -20"
```

预期：5 个测试全部 PASS。

- [ ] **Step 6：Commit**

```bash
cd /data/project/novel-writer
git add data/feishu_common.py data/tests/__init__.py data/tests/test_feishu_common.py
git commit -m "$(cat <<'EOF'
feat(data): add feishu_common shared utility module

Extracts token/URL parsing and tenant_access_token logic from the
legacy get_feishu_doc.py into a focused module reusable by the new
sync_bitable CLI.

Constraint: Each bitable copy gets a fresh token, so URL parsing is the only stable abstraction
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 创建 `script_rubric/pipeline/parse_bitable.py`

**Files:**
- Create: `script_rubric/pipeline/parse_bitable.py`
- Create: `script_rubric/tests/test_parse_bitable.py`
- Create: `script_rubric/tests/fixtures/bitable_jingpin_minimal.json`

替代 `parse_xlsx.py`。读取 CLI 落地的精品 JSON，自动发现评审员，输出 `ScriptRecord` 列表。

- [ ] **Step 1：创建测试 fixture（最小可解析的精品 JSON）**

```bash
mkdir -p /data/project/novel-writer/script_rubric/tests/fixtures
```

写入 `script_rubric/tests/fixtures/bitable_jingpin_minimal.json`:

```json
{
  "synced_at": "2026-04-27T14:30:12+08:00",
  "source_app_token": "test_token",
  "source_table_id": "tbl_test",
  "source_table_name": "精品",
  "total": 3,
  "reviewers": ["小冉", "贾酒"],
  "records": [
    {
      "record_id": "rec_1",
      "title": "已确认状态的剧本",
      "source_type": "改编",
      "genre": "女频",
      "submitter": "47",
      "status": "改",
      "overall_score": 75,
      "scores": {"小冉": 80, "贾酒": 70},
      "comments": {"小冉": "好看", "贾酒": "一般"}
    },
    {
      "record_id": "rec_2",
      "title": "仅有评分待推断的剧本",
      "source_type": "原创",
      "genre": "男频",
      "submitter": "千北",
      "status": "",
      "overall_score": null,
      "scores": {"小冉": 85, "贾酒": 82},
      "comments": {"小冉": "优秀", "贾酒": "可签"}
    },
    {
      "record_id": "rec_3",
      "title": "评分不足的剧本",
      "source_type": "改编",
      "genre": "女频",
      "submitter": "贾酒",
      "status": "",
      "overall_score": null,
      "scores": {"小冉": 60, "贾酒": null},
      "comments": {"小冉": "节奏慢", "贾酒": null}
    }
  ]
}
```

- [ ] **Step 2：写 `script_rubric/tests/test_parse_bitable.py`（失败测试）**

```python
"""script_rubric.pipeline.parse_bitable 测试。"""
from pathlib import Path
import json
import pytest

from script_rubric.pipeline.parse_bitable import parse_bitable_json, BitableSchemaError

FIXTURE = Path(__file__).parent / "fixtures" / "bitable_jingpin_minimal.json"


class TestParseBitable:
    def test_returns_list(self):
        records = parse_bitable_json(FIXTURE)
        assert isinstance(records, list)

    def test_confirmed_status_record(self):
        records = parse_bitable_json(FIXTURE)
        confirmed = [r for r in records if r.status_source == "confirmed"]
        assert len(confirmed) == 1
        r = confirmed[0]
        assert r.title == "已确认状态的剧本"
        assert r.status == "改"
        assert r.source_type == "改编"
        assert r.genre == "女频"
        assert r.submitter == "47"
        assert len(r.reviews) == 2

    def test_score_inferred_with_include_scored(self):
        records = parse_bitable_json(FIXTURE, include_scored=True)
        inferred = [r for r in records if r.status_source == "score_inferred"]
        assert len(inferred) == 1
        r = inferred[0]
        assert r.title == "仅有评分待推断的剧本"
        assert r.status == "签"  # mean=83.5, >=80 -> 签

    def test_score_inferred_without_flag_excluded(self):
        records = parse_bitable_json(FIXTURE, include_scored=False)
        for r in records:
            assert r.status_source == "confirmed"

    def test_below_min_scores_excluded(self):
        records = parse_bitable_json(FIXTURE, include_scored=True)
        titles = [r.title for r in records]
        assert "评分不足的剧本" not in titles

    def test_reviewers_appear_in_reviews(self):
        records = parse_bitable_json(FIXTURE, include_scored=True)
        for r in records:
            for rev in r.reviews:
                assert rev.reviewer in {"小冉", "贾酒"}
                if rev.score is not None:
                    assert 0 <= rev.score <= 100

    def test_missing_required_field_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"records": [{"title": "X"}]}), encoding="utf-8")
        with pytest.raises(BitableSchemaError):
            parse_bitable_json(bad)

    def test_zero_reviewers_raises(self, tmp_path):
        bad = tmp_path / "no_reviewers.json"
        bad.write_text(json.dumps({
            "synced_at": "2026-04-27T00:00:00+08:00",
            "source_app_token": "x", "source_table_id": "y", "source_table_name": "精品",
            "total": 0, "reviewers": [], "records": []
        }), encoding="utf-8")
        with pytest.raises(BitableSchemaError, match="评审员"):
            parse_bitable_json(bad)
```

- [ ] **Step 3：运行测试确认失败**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest script_rubric/tests/test_parse_bitable.py -v 2>&1 | tail -25"
```

预期：`ModuleNotFoundError: No module named 'script_rubric.pipeline.parse_bitable'`

- [ ] **Step 4：写 `script_rubric/pipeline/parse_bitable.py` 实现**

```python
"""
读取 CLI 落地的 bitable 规范化 JSON，输出 ScriptRecord 列表。

输入 schema (data/bitable_dumps/精品.json):
{
  "synced_at": str,
  "source_app_token": str, "source_table_id": str, "source_table_name": str,
  "total": int,
  "reviewers": [str, ...],   # CLI 自动发现
  "records": [
    {
      "record_id": str, "title": str, "source_type": str, "genre": str,
      "submitter": str, "status": "签|改|拒|''",
      "overall_score": int | None,
      "scores": {reviewer: int | None},
      "comments": {reviewer: str | None}
    }
  ]
}
"""
from __future__ import annotations

import json
from pathlib import Path

from script_rubric.config import MIN_SCORES_FOR_INCLUSION, SCORE_TIER_THRESHOLDS
from script_rubric.models import Review, ScriptRecord


class BitableSchemaError(ValueError):
    """JSON 形态不符合期望（缺字段、0 评审员等）。"""


def parse_bitable_json(path: Path, include_scored: bool = False) -> list[ScriptRecord]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    if "records" not in raw:
        raise BitableSchemaError(f"{path}: 缺 'records' 字段")
    reviewers = raw.get("reviewers", [])
    if not reviewers:
        raise BitableSchemaError(
            f"{path}: 0 评审员被发现。可能字段命名变化（期望 '<人名>打分' + '<人名>点评' 配对）"
        )

    out: list[ScriptRecord] = []
    for rec in raw["records"]:
        title = (rec.get("title") or "").strip()
        if not title:
            continue

        status = (rec.get("status") or "").strip()
        scores_map = rec.get("scores") or {}
        comments_map = rec.get("comments") or {}

        reviews: list[Review] = []
        for name in reviewers:
            score = scores_map.get(name)
            comment = comments_map.get(name)
            if isinstance(comment, str):
                comment = comment.strip() or None
            if score is None and not comment:
                continue
            reviews.append(Review(
                reviewer=name,
                score=int(score) if isinstance(score, (int, float)) else None,
                comment=comment,
            ))

        active_reviews = [r for r in reviews if r.score is not None or r.comment]

        if status in ("签", "改", "拒"):
            if not any(r.score is not None for r in reviews):
                continue
            out.append(ScriptRecord(
                title=title,
                source_type=(rec.get("source_type") or "").strip(),
                genre=(rec.get("genre") or "").strip(),
                submitter=(rec.get("submitter") or "").strip(),
                status=status,
                status_source="confirmed",
                reviews=active_reviews,
            ))
        elif include_scored:
            inferred = _infer_status_from_scores(reviews)
            if inferred is None:
                continue
            out.append(ScriptRecord(
                title=title,
                source_type=(rec.get("source_type") or "").strip(),
                genre=(rec.get("genre") or "").strip(),
                submitter=(rec.get("submitter") or "").strip(),
                status=inferred,
                status_source="score_inferred",
                reviews=active_reviews,
            ))

    return out


def save_parsed(records: list[ScriptRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump() for r in records]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_parsed(path: Path) -> list[ScriptRecord]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ScriptRecord.model_validate(d) for d in data]


def _infer_status_from_scores(reviews: list[Review]) -> str | None:
    scores = [r.score for r in reviews if r.score is not None]
    if len(scores) < MIN_SCORES_FOR_INCLUSION:
        return None
    mean = sum(scores) / len(scores)
    if mean >= SCORE_TIER_THRESHOLDS["签"]:
        return "签"
    if mean >= SCORE_TIER_THRESHOLDS["改"]:
        return "改"
    return "拒"
```

- [ ] **Step 5：运行测试确认通过**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest script_rubric/tests/test_parse_bitable.py -v 2>&1 | tail -25"
```

预期：8 个测试全部 PASS。

- [ ] **Step 6：Commit**

```bash
cd /data/project/novel-writer
git add script_rubric/pipeline/parse_bitable.py \
        script_rubric/tests/test_parse_bitable.py \
        script_rubric/tests/fixtures/bitable_jingpin_minimal.json
git commit -m "$(cat <<'EOF'
feat(rubric): add parse_bitable.py reader to replace parse_xlsx

Reads CLI-produced normalized JSON instead of xlsx. Auto-discovers
reviewers from JSON's 'reviewers' field; fail-loud when zero reviewers
detected (catches silent column-rename failures per Gemini review #2).
Output schema (ScriptRecord) is identical to parse_xlsx for zero
downstream impact.

Constraint: rubric pipeline pass1/pass2 untouched
Rejected: keep parse_xlsx as fallback | dead code accumulation
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 切换 `config.py` 与 `run.py` 到 bitable

**Files:**
- Modify: `script_rubric/config.py:18,39-60`
- Modify: `script_rubric/pipeline/run.py:13,18,35,100,156,171`

把 rubric pipeline 的数据源从 xlsx 切换到 bitable JSON。**这一步切换后，rubric pipeline 暂时无法运行**（因为 JSON 文件还不存在），直到 Task 4+6 跑完 CLI 才有数据。

- [ ] **Step 1：修改 `script_rubric/config.py`**

替换：
```python
XLSX_PATH = PROJECT_ROOT / "uploads" / "外部待审核剧本.xlsx"
DRAMA_DIR = PROJECT_ROOT / "uploads" / "drama"
```
为：
```python
DRAMA_DIR = PROJECT_ROOT / "uploads" / "drama"
BITABLE_DUMPS_DIR = PROJECT_ROOT / "data" / "bitable_dumps"
BITABLE_RUBRIC_JSON = BITABLE_DUMPS_DIR / "精品.json"
BITABLE_REFERENCE_JSON = BITABLE_DUMPS_DIR / "冲量.json"
RUBRIC_TARGET_TABLE = "精品"
RUBRIC_REFERENCE_TABLE = "冲量"
```

并删除整个 `XLSX_COLUMNS = {...}` 字典（行 39-46）和 `REVIEWERS = [...]` 列表（行 48-60）。

最终 config.py 中相关段应该长这样：
```python
DRAMA_DIR = PROJECT_ROOT / "uploads" / "drama"
BITABLE_DUMPS_DIR = PROJECT_ROOT / "data" / "bitable_dumps"
BITABLE_RUBRIC_JSON = BITABLE_DUMPS_DIR / "精品.json"
BITABLE_REFERENCE_JSON = BITABLE_DUMPS_DIR / "冲量.json"
RUBRIC_TARGET_TABLE = "精品"
RUBRIC_REFERENCE_TABLE = "冲量"

API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://yibuapi.com/v1")
...
MIN_SCORES_FOR_INCLUSION = 3
SCORE_TIER_THRESHOLDS = {"签": 80, "改": 70}

DIMENSION_KEYS = [...]  # 保留
DIMENSION_NAMES_ZH = {...}  # 保留
```

- [ ] **Step 2：修改 `script_rubric/pipeline/run.py` 的 import**

替换：
```python
from script_rubric.config import (
    XLSX_PATH, DRAMA_DIR, PARSED_DIR, ARCHIVES_DIR, HANDBOOK_DIR,
    HOLDOUT_RATIO, HOLDOUT_SEED,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
)
from script_rubric.pipeline.parse_xlsx import parse_xlsx, save_parsed
```
为：
```python
from script_rubric.config import (
    BITABLE_RUBRIC_JSON, DRAMA_DIR, PARSED_DIR, ARCHIVES_DIR, HANDBOOK_DIR,
    HOLDOUT_RATIO, HOLDOUT_SEED,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
)
from script_rubric.pipeline.parse_bitable import parse_bitable_json, save_parsed
```

- [ ] **Step 3：替换 4 处 `parse_xlsx(XLSX_PATH, ...)` 调用**

`run.py:35`:  `all_records = parse_xlsx(XLSX_PATH, include_scored=True)` → `all_records = parse_bitable_json(BITABLE_RUBRIC_JSON, include_scored=True)`

`run.py:100`: `records = parse_xlsx(XLSX_PATH, include_scored=True)` → `records = parse_bitable_json(BITABLE_RUBRIC_JSON, include_scored=True)`

`run.py:156`: `records = parse_xlsx(XLSX_PATH)` → `records = parse_bitable_json(BITABLE_RUBRIC_JSON)`

`run.py:171`: `all_records = parse_xlsx(XLSX_PATH, include_scored=True)` → `all_records = parse_bitable_json(BITABLE_RUBRIC_JSON, include_scored=True)`

- [ ] **Step 4：用 fixture 烟测 run.py import 不报错**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -c 'from script_rubric.pipeline import run; print(\"import ok\")' 2>&1"
```

预期：输出 `import ok`，无 ImportError。

- [ ] **Step 5：跑测试确认 parse_bitable 那套仍 PASS、与 rubric 其他模块无冲突**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest script_rubric/tests/test_parse_bitable.py script_rubric/tests/test_extract_archive.py -v 2>&1 | tail -30"
```

预期：所有指定测试 PASS。**注意**：`test_parse_xlsx.py` 现在会因 import 错误失败，**这是预期的**——它会在 Task 7 删除。

- [ ] **Step 6：Commit**

```bash
cd /data/project/novel-writer
git add script_rubric/config.py script_rubric/pipeline/run.py
git commit -m "$(cat <<'EOF'
refactor(rubric): switch data source from xlsx to bitable JSON

Replaces XLSX_PATH/XLSX_COLUMNS/REVIEWERS in config with bitable JSON
paths. run.py now imports parse_bitable_json instead of parse_xlsx.
Pipeline runs are temporarily blocked until sync_bitable CLI lands the
JSON file (Task 4 + Task 6).

Constraint: ScriptRecord schema unchanged so pass1/pass2/backtest are untouched
Directive: Do not run rubric pipeline until data/bitable_dumps/精品.json exists
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 创建 `data/sync_bitable.py` (CLI 入口)

**Files:**
- Create: `data/sync_bitable.py`
- Create: `data/tests/test_sync_bitable.py`

CLI 主体。流程：解析 URL → 拉数据 → 规范化 → 原子写文件 → 追加历史 → 可选串 rubric pipeline。

- [ ] **Step 1：写 `data/tests/test_sync_bitable.py`（针对纯函数的单元测试）**

```python
"""data/sync_bitable 单元测试（纯函数）。"""
import pytest
from data.sync_bitable import (
    discover_reviewers,
    normalize_jingpin_record,
    normalize_chongliang_record,
    BitableSchemaError,
)


class TestDiscoverReviewers:
    def test_paired_score_and_comment(self):
        fields = [
            {"field_name": "标题"},
            {"field_name": "小冉打分"}, {"field_name": "小冉点评"},
            {"field_name": "贾酒打分"}, {"field_name": "贾酒点评"},
            {"field_name": "47点评"},  # 落单，不计入
        ]
        assert discover_reviewers(fields) == ["小冉", "贾酒"]

    def test_no_reviewers_returns_empty(self):
        fields = [{"field_name": "标题"}, {"field_name": "类型"}]
        assert discover_reviewers(fields) == []

    def test_score_only_field_dropped(self):
        fields = [
            {"field_name": "帕克打分"},  # 只有打分
            {"field_name": "Vicki打分"}, {"field_name": "Vicki点评"},
        ]
        assert discover_reviewers(fields) == ["Vicki"]


class TestNormalizeJingpinRecord:
    def test_basic_record(self):
        rec = {
            "record_id": "rec_x",
            "fields": {
                "文本": "测试剧本",
                "类型": "改编",
                "分类": "女频",
                "提交人": "47",
                "状态": "改",
                "评分(80+S,75+A,70+B)": 75,
                "小冉打分": 80, "小冉点评": "好看",
                "贾酒打分": 70, "贾酒点评": "一般",
            }
        }
        normalized = normalize_jingpin_record(rec, reviewers=["小冉", "贾酒"])
        assert normalized["record_id"] == "rec_x"
        assert normalized["title"] == "测试剧本"
        assert normalized["source_type"] == "改编"
        assert normalized["genre"] == "女频"
        assert normalized["submitter"] == "47"
        assert normalized["status"] == "改"
        assert normalized["overall_score"] == 75
        assert normalized["scores"] == {"小冉": 80, "贾酒": 70}
        assert normalized["comments"] == {"小冉": "好看", "贾酒": "一般"}

    def test_missing_title_raises(self):
        rec = {"record_id": "rec_x", "fields": {"类型": "改编"}}
        with pytest.raises(BitableSchemaError, match="title"):
            normalize_jingpin_record(rec, reviewers=["小冉"])

    def test_missing_reviewer_score_becomes_none(self):
        rec = {
            "record_id": "rec_x",
            "fields": {"文本": "X", "贾酒打分": 80},  # 无小冉打分
        }
        normalized = normalize_jingpin_record(rec, reviewers=["小冉", "贾酒"])
        assert normalized["scores"]["小冉"] is None
        assert normalized["scores"]["贾酒"] == 80
```

- [ ] **Step 2：运行测试确认失败**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest data/tests/test_sync_bitable.py -v 2>&1 | tail -15"
```

预期：`ModuleNotFoundError: No module named 'data.sync_bitable'`

- [ ] **Step 3：写 `data/sync_bitable.py`**

```python
#!/usr/bin/env python3
"""
飞书 bitable CLI 同步工具
==========================

用法:
    python data/sync_bitable.py <BITABLE_URL> [--no-pipeline] [--mode incremental|full]

每次飞书 bitable 副本 token 不同 → 必须把 URL 显式传入。
拉取 "冲量" + "精品" 两表，规范化展平后写到 data/bitable_dumps/，
默认串 script_rubric pipeline；--no-pipeline 关闭。

退出码:
  0  全流程成功
  1  bitable 拉取失败 (URL/权限/网络)
  2  数据形态异常 (表名缺失、字段命名变化)
  3  rubric pipeline 失败 (CLI 自身已成功)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# 容器与本地脚本兼容
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.feishu_common import (
    extract_token,
    get_tenant_access_token,
    resolve_wiki_node,
    call_get,
    FeishuAPIError,
    FeishuURLError,
)


PROJECT_ROOT = Path(__file__).parent.parent
DUMPS_DIR = PROJECT_ROOT / "data" / "bitable_dumps"
LOG_DIR = PROJECT_ROOT / "data" / "cli_sync_logs"
LOG_FILE = LOG_DIR / "sync_history.json"
MAX_HISTORY = 50

EXPECTED_TABLES = ("冲量", "精品")
RUBRIC_RUN_PY = PROJECT_ROOT / "script_rubric" / "pipeline" / "run.py"


class BitableSchemaError(ValueError):
    """数据结构异常 (表/字段命名变化等)。"""


# ── 字段发现 ──────────────────────────────────────────────────────────────────

def discover_reviewers(fields: list[dict]) -> list[str]:
    """从字段定义里找 '<人名>打分' + '<人名>点评' 配对。"""
    names = {f["field_name"] for f in fields}
    out = []
    for n in names:
        m = re.match(r"^(.+)打分$", n)
        if m and f"{m.group(1)}点评" in names:
            out.append(m.group(1))
    return sorted(out)


# ── 单元格提取 ────────────────────────────────────────────────────────────────

def _extract_text(val: Any) -> str | None:
    """飞书单元格 → 字符串。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return val.strip() or None
    if isinstance(val, list):
        parts = []
        for it in val:
            if isinstance(it, dict):
                parts.append(str(it.get("text", "")).strip())
        joined = "".join(parts).strip()
        return joined or None
    if isinstance(val, dict):
        return str(val.get("text", "")).strip() or None
    return str(val).strip() or None


def _extract_number(val: Any) -> int | float | None:
    """飞书数字 → int 优先，否则 float。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = _extract_text(val)
    if s is None:
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


# ── 规范化 ────────────────────────────────────────────────────────────────────

def normalize_jingpin_record(rec: dict, reviewers: list[str]) -> dict:
    """把「精品」表的一条 bitable 记录展平为 rubric 友好的形状。"""
    fields = rec.get("fields", {})
    title = _extract_text(fields.get("文本"))
    if not title:
        raise BitableSchemaError(
            f"record_id={rec.get('record_id')} 缺 title (字段「文本」)"
        )

    scores = {n: _to_int(_extract_number(fields.get(f"{n}打分"))) for n in reviewers}
    comments = {n: _extract_text(fields.get(f"{n}点评")) for n in reviewers}

    return {
        "record_id": rec.get("record_id", ""),
        "title": title,
        "source_type": _extract_text(fields.get("类型")) or "",
        "genre": _extract_text(fields.get("分类")) or "",
        "submitter": _extract_text(fields.get("提交人")) or "",
        "status": _extract_text(fields.get("状态")) or "",
        "overall_score": _to_int(_extract_number(fields.get("评分(80+S,75+A,70+B)"))),
        "scores": scores,
        "comments": comments,
        "raw_fields": fields,
    }


def normalize_chongliang_record(rec: dict, reviewers: list[str]) -> dict:
    """「冲量」表展平。仅供参考 dump，不进 rubric。
    注意标题字段叫「书名」（与精品的「文本」不同）。
    """
    fields = rec.get("fields", {})
    title = _extract_text(fields.get("书名")) or ""

    scores = {n: _to_int(_extract_number(fields.get(f"{n}打分"))) for n in reviewers}
    comments = {n: _extract_text(fields.get(f"{n}点评")) for n in reviewers}

    return {
        "record_id": rec.get("record_id", ""),
        "title": title,
        "source_type": _extract_text(fields.get("类型")) or "",
        "genre": _extract_text(fields.get("分类")) or "",
        "submitter": _extract_text(fields.get("提交人")) or "",
        "status": _extract_text(fields.get("状态")) or "",
        "price": _extract_number(fields.get("价格")),
        "director": _extract_text(fields.get("导演")),
        "rating": _extract_text(fields.get("评级")),
        "scores": scores,
        "comments": comments,
        "raw_fields": fields,
    }


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return None


# ── bitable 抓取 ──────────────────────────────────────────────────────────────

def fetch_table(token: str, app_token: str, table_id: str) -> tuple[list[dict], list[dict]]:
    """返回 (字段定义, 全部记录)。自动翻页。"""
    fields_resp = call_get(
        token,
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
        params={"page_size": 100},
    )
    fields = fields_resp["data"]["items"]

    records = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        recs_resp = call_get(
            token,
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params=params,
        )
        data = recs_resp["data"]
        records.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")

    return fields, records


# ── 原子写入 ──────────────────────────────────────────────────────────────────

def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ── 同步历史 ──────────────────────────────────────────────────────────────────

def append_history(entry: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    history = []
    if LOG_FILE.exists():
        try:
            history = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    atomic_write_json(LOG_FILE, history) if isinstance(history, dict) else \
        LOG_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sync(url: str, run_pipeline: bool, mode: str) -> int:
    t_start = time.time()
    print(f"[sync_bitable] 开始: url={url}")

    # 1. 解析 URL
    try:
        kind, raw_token = extract_token(url)
    except FeishuURLError as e:
        print(f"❌ URL 解析失败: {e}", file=sys.stderr)
        return 1

    # 2. 获取 token
    try:
        access_token = get_tenant_access_token()
        print("[sync_bitable] tenant_access_token OK")
    except Exception as e:
        print(f"❌ 获取访问令牌失败: {e}", file=sys.stderr)
        return 1

    # 3. 解析 wiki → app_token
    if kind == "wiki":
        try:
            obj_token, obj_type = resolve_wiki_node(access_token, raw_token)
        except FeishuAPIError as e:
            print(f"❌ wiki 节点解析失败: {e}", file=sys.stderr)
            return 1
        if obj_type != "bitable":
            print(f"❌ wiki 节点不是多维表格，obj_type={obj_type}", file=sys.stderr)
            return 1
        app_token = obj_token
    else:
        app_token = raw_token
    print(f"[sync_bitable] app_token={app_token}")

    # 4. 拉 app 元信息
    try:
        meta = call_get(access_token, f"/open-apis/bitable/v1/apps/{app_token}")
        app_name = meta["data"]["app"].get("name", "?")
        is_advanced = meta["data"]["app"].get("is_advanced", False)
        print(f"[sync_bitable] app_name={app_name}  is_advanced={is_advanced}")
    except FeishuAPIError as e:
        print(f"❌ 获取 app 元信息失败: {e}", file=sys.stderr)
        return 1

    # 5. 列出表
    try:
        tables_resp = call_get(
            access_token,
            f"/open-apis/bitable/v1/apps/{app_token}/tables",
            params={"page_size": 100},
        )
    except FeishuAPIError as e:
        print(f"❌ 列出表失败: {e}", file=sys.stderr)
        return 1

    tables = tables_resp["data"].get("items", [])
    if not tables:
        print(
            "❌ 表列表为空。可能原因：飞书副本仍开启「高级权限」。\n"
            "   解决：飞书 → 副本 → 右上角 ... → 权限设置 → 关闭「高级权限」",
            file=sys.stderr,
        )
        return 2

    name_to_id = {t["name"]: t["table_id"] for t in tables}
    missing = [n for n in EXPECTED_TABLES if n not in name_to_id]
    if missing:
        print(
            f"❌ 副本里找不到表 {missing}。实际表: {list(name_to_id.keys())}\n"
            f"   解决：确认副本结构未被改名，或更新 EXPECTED_TABLES",
            file=sys.stderr,
        )
        return 2

    # 6. 拉 + 规范化两张表
    summary = {"冲量": {}, "精品": {}}
    for tname in EXPECTED_TABLES:
        tid = name_to_id[tname]
        print(f"[sync_bitable] 拉取「{tname}」 table_id={tid}")
        fields, records = fetch_table(access_token, app_token, tid)
        reviewers = discover_reviewers(fields)
        print(f"  字段={len(fields)}  记录={len(records)}  评审员={reviewers}")

        if tname == "精品":
            normalizer = normalize_jingpin_record
        else:
            normalizer = normalize_chongliang_record

        try:
            normalized = [normalizer(r, reviewers) for r in records]
        except BitableSchemaError as e:
            print(f"❌ 规范化失败: {e}", file=sys.stderr)
            return 2

        out = {
            "synced_at": now_iso(),
            "source_app_token": app_token,
            "source_app_name": app_name,
            "source_table_id": tid,
            "source_table_name": tname,
            "total": len(normalized),
            "reviewers": reviewers,
            "records": normalized,
        }
        atomic_write_json(DUMPS_DIR / f"{tname}.json", out)
        print(f"  ✅ 写入 {DUMPS_DIR / f'{tname}.json'}")

        summary[tname] = {
            "table_id": tid,
            "records": len(normalized),
            "fields": len(fields),
            "reviewers_detected": len(reviewers),
        }

    elapsed_sync = round(time.time() - t_start, 1)
    print(f"[sync_bitable] 数据同步完成，耗时 {elapsed_sync}s")

    pipeline_result: dict | None = None
    pipeline_exit = 0

    if run_pipeline:
        print(f"[sync_bitable] 触发 rubric pipeline (mode={mode})...")
        cmd = [sys.executable, str(RUBRIC_RUN_PY), mode]
        t_p = time.time()
        try:
            res = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False, timeout=3600)
            pipeline_exit = res.returncode
        except subprocess.TimeoutExpired:
            pipeline_exit = -1
        elapsed_p = round(time.time() - t_p, 1)
        pipeline_result = {
            "success": pipeline_exit == 0,
            "exit_code": pipeline_exit,
            "elapsed_s": elapsed_p,
            "mode": mode,
        }
        print(f"[sync_bitable] pipeline exit={pipeline_exit} elapsed={elapsed_p}s")

    # 7. 追加历史
    entry = {
        "synced_at": now_iso(),
        "source_url": url,
        "source_app_token": app_token,
        "source_app_name": app_name,
        "tables": summary,
        "elapsed_sync_s": elapsed_sync,
        "pipeline_triggered": run_pipeline,
        "pipeline_result": pipeline_result,
        "success": pipeline_exit == 0 if run_pipeline else True,
        "error": None,
    }
    append_history(entry)

    if run_pipeline and pipeline_exit != 0:
        return 3
    return 0


def main():
    parser = argparse.ArgumentParser(description="飞书 bitable CLI 同步")
    parser.add_argument("url", help="bitable 副本 URL (https://xxx.feishu.cn/base/<token>)")
    parser.add_argument("--no-pipeline", action="store_true", help="不串 rubric pipeline")
    parser.add_argument("--mode", default="incremental",
                        choices=["incremental", "full"],
                        help="rubric pipeline 模式（默认 incremental）")
    args = parser.parse_args()

    code = sync(args.url, run_pipeline=not args.no_pipeline, mode=args.mode)
    sys.exit(code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4：运行单元测试**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest data/tests/test_sync_bitable.py -v 2>&1 | tail -20"
```

预期：5 个 normalize/discover 单元测试 PASS。

- [ ] **Step 5：CLI argparse 烟测**

```bash
docker exec novel-writer-backend bash -c "cd /app && python data/sync_bitable.py --help 2>&1"
```

预期：显示 usage 与 url/--no-pipeline/--mode 参数。

- [ ] **Step 6：Commit**

```bash
cd /data/project/novel-writer
git add data/sync_bitable.py data/tests/test_sync_bitable.py
git commit -m "$(cat <<'EOF'
feat(data): add sync_bitable.py CLI for bitable data ingestion

Replaces the old scheduled sheet sync. Each invocation:
1. parses a bitable URL (base or wiki)
2. fetches 冲量 + 精品 tables with auto-pagination
3. auto-discovers reviewers from <name>打分/<name>点评 field pairs
4. normalizes records into rubric-ready JSON
5. atomic-writes to data/bitable_dumps/{冲量,精品}.json
6. appends to data/cli_sync_logs/sync_history.json
7. by default chains script_rubric.pipeline.run incremental

Constraint: bitable copy tokens change every time, so URL must be CLI arg
Constraint: bitable copies retain table names — script hardcodes EXPECTED_TABLES
Rejected: api endpoint trigger | user chose CLI-only (Q3=D)
Rejected: cron with stored URL | overcomplicates trivial workflow (Q3=C rejected)
Directive: When EXPECTED_TABLES check fails, show actual table names so the user can diagnose schema drift quickly
Confidence: high
Scope-risk: moderate
Not-tested: real-network pagination beyond 500 records (current 180 fits in 1 page)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 清理 backend 旧 sheet 同步壳

**Files:**
- Modify: `backend/app/services/scheduled_task.py` (大量删除，留 scheduler 空壳)
- Modify: `backend/app/main.py:37,137` (删除 feishu_sync_router 注册)
- Delete: `backend/app/routers/feishu_sync.py`

按设计 4.1=B + 8.4=乙 + O3 结论：保留 APScheduler 空壳，删除所有飞书同步业务逻辑与路由。

- [ ] **Step 1：重写 `backend/app/services/scheduled_task.py`**

替换整个文件为：

```python
"""
定时任务服务 - APScheduler 集成
=================================

历史背景: 此前每天 02:00 自动同步飞书 sheet。该流程已迁移到 CLI
(data/sync_bitable.py)，原因是新数据源是飞书 bitable 副本，每次副本
token 不同，无法定时调度。

当前: 调度器框架保留作为将来注册其他定时任务的入口；目前不注册任何 job。
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("api_logger")

scheduler: Optional[AsyncIOScheduler] = None


def init_scheduler():
    global scheduler
    if scheduler is not None:
        return
    scheduler = AsyncIOScheduler()
    logger.info("Scheduler initialized (no jobs registered)")


async def start_scheduler():
    init_scheduler()
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started (idle)")


async def stop_scheduler():
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
```

- [ ] **Step 2：删除 `backend/app/routers/feishu_sync.py`**

```bash
rm /data/project/novel-writer/backend/app/routers/feishu_sync.py
```

- [ ] **Step 3：从 `backend/app/main.py` 移除 router 注册**

读取 main.py 查看上下文，删除两行：
- `from app.routers.feishu_sync import router as feishu_sync_router`（line 37）
- `app.include_router(feishu_sync_router)`（line 137）

可用 Edit 单独删除每行。

- [ ] **Step 4：重启 backend 容器，验证启动无错误**

```bash
docker restart novel-writer-backend
docker logs novel-writer-backend --tail 30 2>&1
```

预期：日志显示 `Scheduler started (idle)` 类似消息，无 ImportError，无 `feishu_sync` 引用。

- [ ] **Step 5：API smoke test：曾经的飞书路由应返回 404**

```bash
sleep 3 && curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/feishu-sync/status
```

预期：`404`（路由已移除）。如果端口不是 8000，找正确端口（`docker port novel-writer-backend`）。

- [ ] **Step 6：Commit**

```bash
cd /data/project/novel-writer
git add backend/app/services/scheduled_task.py backend/app/main.py
git rm backend/app/routers/feishu_sync.py
git commit -m "$(cat <<'EOF'
refactor(backend): strip legacy feishu sync scheduler & router

- scheduled_task.py: keep AsyncIOScheduler shell, remove run_feishu_sync,
  trigger_manual_sync, history persistence, rubric pipeline trigger.
  Reason: bitable copy tokens are non-stable so no automated job is feasible.
- routers/feishu_sync.py: delete entirely. Frontend has no consumer.
- main.py: drop the router registration.

Constraint: User chose CLI-only (Q3=D), no API/UI trigger
Rejected: keep router pointing at CLI history | frontend never used it
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 端到端 smoke test（需要用户参与）

**Files:** 仅运行，无修改

⚠️ **此任务必须有最新副本 URL**——执行前先让用户在飞书新建副本并提供 URL。

- [ ] **Step 1：用户在飞书克隆原 bitable，关闭高级权限，提供副本 URL**

提示用户：
> 请在飞书克隆原 bitable，关闭副本高级权限，把副本 URL 贴给我。形如 https://<TENANT>.feishu.cn/base/&lt;token&gt;

记录 URL，下面用 `<URL>` 占位。

- [ ] **Step 2：跑 CLI（不串 pipeline，只验证拉数据）**

```bash
docker exec novel-writer-backend bash -c "cd /app && python data/sync_bitable.py '<URL>' --no-pipeline 2>&1 | tail -30"
```

预期输出包含：
- `tenant_access_token OK`
- `app_name=外部待审核剧本... is_advanced=False`
- `拉取「冲量」 ... 记录=177  评审员=['47', '帕克', 'Vicki', '千北', '步步']`（评审员可能略有不同）
- `拉取「精品」 ... 记录=180  评审员=['47', 'Vicki', '千北', '小冉', '帕克', '步步', '贾酒']`
- `数据同步完成，耗时 X.Xs`
- 退出码 0

- [ ] **Step 3：检查文件落地**

```bash
docker exec novel-writer-backend bash -c "ls -la /app/data/bitable_dumps/ /app/data/cli_sync_logs/ 2>&1"
docker exec novel-writer-backend bash -c "head -50 /app/data/bitable_dumps/精品.json 2>&1"
docker exec novel-writer-backend bash -c "cat /app/data/cli_sync_logs/sync_history.json 2>&1 | head -30"
```

预期：
- `bitable_dumps/精品.json` + `冲量.json` 存在
- 精品.json 顶部有 `synced_at`/`reviewers`/`records[0].title`
- `sync_history.json` 是数组，第一条 `success: true, pipeline_triggered: false`

- [ ] **Step 4：跑 CLI 串 rubric pipeline（耗时较长，~10 分钟）**

```bash
docker exec novel-writer-backend bash -c "cd /app && timeout 1800 python data/sync_bitable.py '<URL>' 2>&1 | tail -50"
```

预期：
- 数据同步部分跟 step 2 一致
- `[sync_bitable] 触发 rubric pipeline (mode=incremental)`
- rubric pipeline 输出 `Step X: ...` 日志
- 末尾 `pipeline exit=0 elapsed=XXXs`
- 退出码 0

- [ ] **Step 5：验证 rubric pipeline 产出了 handbook 新版本**

```bash
docker exec novel-writer-backend bash -c "ls -lt /app/script_rubric/outputs/handbook/ 2>&1 | head -5"
```

预期：最新 `handbook_v<N>.md` 时间戳是刚才生成的；`<N>` 应该是当前最高 + 1（之前 v10，现在应是 v11）。

- [ ] **Step 6：Commit smoke test 通过的标记（可选 — 如果同步过程产生新 outputs/archives 需要 commit）**

```bash
cd /data/project/novel-writer
git status
# 如有新的 outputs/handbook/ outputs/archives/ 文件:
git add script_rubric/outputs/  data/bitable_dumps/  data/cli_sync_logs/
git commit -m "$(cat <<'EOF'
chore(rubric): first end-to-end smoke run via sync_bitable CLI

Verifies the full pipeline: URL → bitable fetch → normalized JSON →
rubric incremental → handbook v<N>. Uses copy created on $(date +%F).

Confidence: high
Scope-risk: narrow
Not-tested: error-path (e.g., invalid URL — covered by unit tests but not by this smoke)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

如果 git status 没有需要 commit 的实质改动，跳过 commit。

---

## Task 7: 删除旧代码（仅在 Task 6 通过后）

**Files:**
- Delete: `data/get_feishu_doc.py`
- Delete: `uploads/外部待审核剧本.xlsx`
- Delete: `script_rubric/pipeline/parse_xlsx.py`
- Delete: `script_rubric/tests/test_parse_xlsx.py`
- Delete: `script_rubric/tests/test_match_texts.py`

⚠️ **执行前确认 Task 6 retval=0 且 handbook 新版本生成成功**。

- [ ] **Step 1：备份 xlsx 到本地（保险）**

```bash
cp /data/project/novel-writer/uploads/外部待审核剧本.xlsx /tmp/外部待审核剧本_backup_$(date +%Y%m%d).xlsx
echo "备份: /tmp/外部待审核剧本_backup_$(date +%Y%m%d).xlsx"
```

记录备份路径，事故时可恢复。

- [ ] **Step 2：删除文件**

```bash
cd /data/project/novel-writer
git rm data/get_feishu_doc.py
git rm uploads/外部待审核剧本.xlsx
git rm script_rubric/pipeline/parse_xlsx.py
git rm script_rubric/tests/test_parse_xlsx.py
git rm script_rubric/tests/test_match_texts.py
```

- [ ] **Step 3：检查无残留引用**

```bash
docker exec novel-writer-backend bash -c "cd /app && grep -rn 'parse_xlsx\|get_feishu_doc\|XLSX_PATH\|XLSX_COLUMNS' --include='*.py' 2>&1 | grep -v '/__pycache__/\|/.git/\|/docs/'"
```

预期：无输出（或仅输出 docs/specs/plans 相关的 markdown 引用，不算）。如有 Python 文件残留引用立即修复。

- [ ] **Step 4：重启 backend，全量跑测试**

```bash
docker restart novel-writer-backend
sleep 5
docker exec novel-writer-backend bash -c "cd /app && python -m pytest script_rubric/tests/ data/tests/ -v 2>&1 | tail -40"
```

预期：所有 (`test_parse_bitable.py`, `test_feishu_common.py`, `test_sync_bitable.py`, `test_extract_archive.py` 等) PASS。

- [ ] **Step 5：Commit**

```bash
cd /data/project/novel-writer
git commit -m "$(cat <<'EOF'
chore: remove legacy xlsx-based feishu sync code

Smoke test (Task 6) confirmed the bitable CLI path produces an equivalent
or newer handbook version. Removing dead code:

- data/get_feishu_doc.py (replaced by data/feishu_common.py + data/sync_bitable.py)
- uploads/外部待审核剧本.xlsx (rubric no longer reads it; backup kept at /tmp)
- script_rubric/pipeline/parse_xlsx.py (replaced by parse_bitable.py)
- script_rubric/tests/test_parse_xlsx.py & test_match_texts.py (test deleted modules)

Backup: /tmp/外部待审核剧本_backup_<date>.xlsx (local only, not committed)

Confidence: high
Scope-risk: narrow
Directive: If a future bug requires reverting, restore xlsx from /tmp backup and revert this commit + Task 3's commit together — the data source switch and the cleanup are coupled

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 最终验证 + 文档更新

**Files:**
- Optional modify: `script_rubric/README.md` (如需更新数据源描述)

- [ ] **Step 1：再次跑全套测试**

```bash
docker exec novel-writer-backend bash -c "cd /app && python -m pytest -v 2>&1 | tail -50"
```

预期：所有测试 PASS。

- [ ] **Step 2：检查 backend 容器日志（最近 5 分钟）**

```bash
docker logs novel-writer-backend --since 5m 2>&1 | tail -40
```

预期：无新报错；`Scheduler started (idle)` 在启动时出现一次。

- [ ] **Step 3：更新 `script_rubric/README.md` 的数据源描述（如有）**

```bash
grep -n "外部待审核剧本.xlsx\|XLSX\|parse_xlsx\|get_feishu_doc" /data/project/novel-writer/script_rubric/README.md 2>&1
```

如有引用，编辑 README 把 "uploads/外部待审核剧本.xlsx" 改为 "data/bitable_dumps/精品.json (由 data/sync_bitable.py 生成)"。如 README 没有相关引用，跳过本步。

- [ ] **Step 4：（如有 README 改动）Commit**

```bash
cd /data/project/novel-writer
git diff --stat script_rubric/README.md
# 如有改动：
git add script_rubric/README.md
git commit -m "$(cat <<'EOF'
docs(rubric): update data source description to bitable JSON

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5：最终 git log 概览**

```bash
cd /data/project/novel-writer
git log --oneline -15
```

预期：本计划共产出约 6-7 个 commit（T1/T2/T3/T4/T5/T7/T8 各 1 个；T0 和 T6 通常无 commit）。

---

## 自审

**1. Spec 覆盖：**
- 第 2 节架构 → T1+T4（CLI 与共享工具）+ T3（rubric reader 切换）
- 第 3 节组件清单 4 新增 → T1/T2/T4 全部覆盖
- 第 3 节 3 个修改 → T3（config + run.py）、T5（scheduled_task 简化）
- 第 3 节 5 个删除 → T7
- 第 4 节 CLI 接口 → T4（实现）+ T6（验证）
- 第 4 节 JSON 格式 → T4 中 `normalize_jingpin_record` / `normalize_chongliang_record` 直接对应 spec 字段
- 第 4 节 同步历史 → T4 `append_history`
- 第 5 节风险吸收 R1-R5：
  - R1 (record_id 跨副本不稳) → 设计中 record_id 仅作 raw_fields 留存，rubric 用 title — 已落实 in `parse_bitable_json` 中 title-based dedup
  - R2 (字段命名变化) → `parse_bitable_json` zero-reviewer fail-loud (T2 测试) + `normalize_jingpin_record` missing-title fail-loud (T4 测试)
  - R3 (原子写入) → T4 `atomic_write_json`
  - R4 (表名硬编码) → spec 已抽 `RUBRIC_TARGET_TABLE` 常量，T3 加入 config；CLI 用 `EXPECTED_TABLES` 模块常量便于改
  - R5 (高级权限错误提示) → T4 `sync()` 函数检测 `tables empty` 后显式提示
- 第 6 节测试 → T2 单元测试 + T4 单元测试 + T6 集成 smoke
- 第 7 节迁移注意 → T7 step 1 备份 xlsx
- 第 8 节 Open Items O1-O5 → T0 全部覆盖
- 附录 A 飞书 API → T1 + T4 全部用到

**2. Placeholder 扫描：** 所有 `<URL>` 占位仅出现在 T6 step 2/4，明确说明需用户提供。无 TBD/TODO。

**3. 类型一致性：**
- `parse_bitable_json(path, include_scored=...)` 在 T2 与 T3 一致
- `discover_reviewers(fields) -> list[str]` 在 T4 一致
- `normalize_jingpin_record(rec, reviewers)` / `normalize_chongliang_record(rec, reviewers)` 签名在 T4 一致
- `BitableSchemaError` 同名分别定义在 `parse_bitable.py`（T2）和 `sync_bitable.py`（T4）—— **这是有意的**，两处都有 fail-loud 入口，但**不互相 import**。如未来要复用，提取到 `feishu_common.py`；当前阶段不做。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-27-bitable-cli-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
