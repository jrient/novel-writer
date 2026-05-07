"""
飞书 API 公共模块
==================

提供多维表格（Bitable）/ 文档（Docx）API 的公共 helper 函数。

凭证仅从环境变量读取（FEISHU_APP_ID / FEISHU_APP_SECRET）。本仓库不接受
任何形式的硬编码 fallback——历史 fallback 凭证已在 git history 暴露过，
对应 app secret 必须在飞书侧轮换后重新写入本地 .env。
"""

from __future__ import annotations

import os
import re
import requests

BASE_URL = "https://open.feishu.cn"
NO_PROXY = {"http": "", "https": ""}


def get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token，凭证只从环境变量读取。"""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError(
            "缺少飞书凭证：请在 .env 或 shell 中设置 FEISHU_APP_ID 与 FEISHU_APP_SECRET"
        )

    url = f"{BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url,
        json={"app_id": app_id, "app_secret": app_secret},
        proxies=NO_PROXY,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败 (code={data.get('code')}): {data.get('msg')}")
    return data["tenant_access_token"]


def extract_bitable_token(url_or_token: str) -> str:
    """从 URL 或直接输入解析 bitable app_token。

    支持格式:
      - https://xxx.feishu.cn/base/Abc123
      - Abc123 (直接 token)
    """
    match = re.search(r"/base/([A-Za-z0-9]+)", url_or_token)
    if match:
        return match.group(1)
    if "/" not in url_or_token:
        return url_or_token
    raise ValueError(f"无法从输入解析 bitable token: {url_or_token}")


def call_get(endpoint: str, token: str, params: dict | None = None) -> dict:
    """通用 GET 请求封装，自动处理错误码。"""
    url = f"{BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params or {}, proxies=NO_PROXY)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"API 错误 (code={result.get('code')}): {result.get('msg')}")
    return result.get("data", {})


def list_bitable_tables(token: str, app_token: str) -> list:
    data = call_get(
        f"/open-apis/bitable/v1/apps/{app_token}/tables",
        token,
        {"page_size": 100},
    )
    return data.get("items", [])


def list_bitable_fields(token: str, app_token: str, table_id: str) -> list:
    data = call_get(
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
        token,
        {"page_size": 200},
    )
    return data.get("items", [])


def fetch_all_bitable_records(token: str, app_token: str, table_id: str) -> list:
    """分页拉取指定表的所有记录。

    使用 text_field_as_array=true 让富文本字段（含 Docx mention 链接、URL 等）以
    数组形式返回，避免 link/token 信息被自动 flatten 丢失。下游需要用
    extract_segments_text/extract_segments_docx_token 处理这种结构。
    """
    records = []
    page_token = None
    while True:
        params = {"page_size": 500, "text_field_as_array": "true"}
        if page_token:
            params["page_token"] = page_token
        data = call_get(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            token,
            params,
        )
        items = data.get("items", [])
        records.extend(items)
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break
    return records


def extract_segments_text(value) -> str | None:
    """从字段值提取纯文本。

    兼容三种格式：
    - str：直接返回（trim）
    - list[dict|str]：富文本数组，拼接所有 text 段
    - dict：单选字段 {"text": ..., "name": ...}
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, list):
        parts = []
        for seg in value:
            if isinstance(seg, dict):
                t = seg.get("text") or ""
                if t:
                    parts.append(t)
            elif isinstance(seg, str):
                parts.append(seg)
        s = "".join(parts).strip()
        return s or None
    if isinstance(value, dict):
        t = value.get("text") or value.get("name")
        return t.strip() if isinstance(t, str) and t.strip() else None
    return str(value).strip() or None


def extract_segments_docx_token(value) -> str | None:
    """从富文本数组提取首个 Docx mention 的 token。

    数组里 mention 段形如：
        {"type": "mention", "mentionType": "Docx", "token": "...", "link": "..."}
    """
    if not isinstance(value, list):
        return None
    for seg in value:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "mention" and seg.get("mentionType") in ("Docx", "Doc"):
            tok = seg.get("token")
            if tok:
                return tok
        link = seg.get("link") or ""
        if "/docx/" in link:
            try:
                return link.split("/docx/")[1].split("?")[0].split("/")[0]
            except Exception:
                pass
    return None


def fetch_docx_raw_content(token: str, docx_token: str) -> str:
    """拉取飞书 Docx 文档的纯文本正文。"""
    data = call_get(
        f"/open-apis/docx/v1/documents/{docx_token}/raw_content",
        token,
        {"lang": 0},
    )
    return data.get("content", "")


def resolve_wiki_node(token: str, wiki_token: str) -> dict:
    """解析飞书 wiki 节点，拿到真正的 obj_token + obj_type。

    wiki 链接（/wiki/<wiki_token>）背后是一个节点（node），节点指向 docx/sheet/...。
    Returns:
        {"obj_type": "docx" | "sheet" | ..., "obj_token": "..."}
    """
    data = call_get(
        "/open-apis/wiki/v2/spaces/get_node",
        token,
        {"token": wiki_token, "obj_type": "wiki"},
    )
    node = data.get("node") or {}
    return {
        "obj_type": node.get("obj_type", ""),
        "obj_token": node.get("obj_token", ""),
        "title": node.get("title", ""),
    }


# === 多数据源合并 ===

TITLE_FIELD_CANDIDATES = ("书名", "文本", "剧本名称", "剧本", "标题")


def _extract_record_title(record: dict) -> str | None:
    """从一条记录中提取标题值（兼容富文本数组）。"""
    fields = record.get("fields", {})
    for name in TITLE_FIELD_CANDIDATES:
        val = fields.get(name)
        text = extract_segments_text(val)
        if text:
            return text
    return None


def merge_bitable_tables(
    existing_tables: list,
    new_tables: list,
) -> tuple[list, dict]:
    """合并两组 bitable 表数据。

    以 title 为去重键：
    - 匹配到 → 更新（新数据覆盖旧数据）
    - 未匹配到 → 追加
    - 旧数据中未在新数据出现的记录 → 保留（不删除）
    """
    stats = {"updated": 0, "appended": 0, "retained": 0}

    existing_by_name = {tbl["table_name"]: tbl for tbl in existing_tables}
    new_by_name = {tbl["table_name"]: tbl for tbl in new_tables}

    all_table_names = list(existing_by_name.keys())
    for name in new_by_name:
        if name not in existing_by_name:
            all_table_names.append(name)

    merged = []
    for table_name in all_table_names:
        old_tbl = existing_by_name.get(table_name)
        new_tbl = new_by_name.get(table_name)

        if old_tbl and new_tbl:
            old_records = [r for r in old_tbl.get("records", []) if r.get("fields")]
            new_records = new_tbl.get("records", [])

            old_by_title = {}
            for idx, rec in enumerate(old_records):
                t = _extract_record_title(rec)
                if t:
                    old_by_title[t] = idx

            new_titles = set()
            for rec in new_records:
                t = _extract_record_title(rec)
                if t:
                    new_titles.add(t)
                    if t in old_by_title:
                        stats["updated"] += 1
                        old_records[old_by_title[t]] = rec
                    else:
                        stats["appended"] += 1
                        old_records.append(rec)

            retained_with_title = sum(1 for t in old_by_title if t not in new_titles)
            stats["retained"] += retained_with_title

            merged.append({
                "table_id": new_tbl.get("table_id", old_tbl.get("table_id", "")),
                "table_name": table_name,
                "fields": new_tbl.get("fields", old_tbl.get("fields", [])),
                "records": old_records,
            })
        elif new_tbl:
            merged.append(new_tbl)
            stats["appended"] += len(new_tbl.get("records", []))
        elif old_tbl:
            merged.append(old_tbl)
            stats["retained"] += len(old_tbl.get("records", []))

    return merged, stats
