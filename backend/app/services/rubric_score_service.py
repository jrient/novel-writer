"""
单本剧本即时评分服务
=====================

接受一个飞书 docx 链接，拉取正文，用最新版 handbook 跑 backtest_predict，
返回打分 + 维度分 + 红/绿旗 + 修改建议。

与 rubric_pipeline_service 的关系：
- rubric_pipeline_service 跑全流程（同步→Pass1→Pass2→回测），输出 handbook
- 本服务消费 handbook，做单本即时评分，无需重跑 pipeline
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("api_logger")

DOC_LINK_RE = re.compile(r"/(docx|wiki|docs)/([A-Za-z0-9]+)")
HANDBOOK_VERSION_RE = re.compile(r"handbook_v(\d+)\.md$")

# 解析 handbook 路径：backend/app/services/.. -> 项目根 -> script_rubric/outputs/handbook
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
_PROJECT_ROOT = _BACKEND_ROOT.parent
_HANDBOOK_DIR = _PROJECT_ROOT / "script_rubric" / "outputs" / "handbook"
if not _HANDBOOK_DIR.exists():
    # Fallback：Docker 内 /app 模式
    _HANDBOOK_DIR = Path("/app/script_rubric/outputs/handbook")


def extract_doc_link(url_or_token: str) -> Optional[tuple[str, str]]:
    """从飞书文档链接解析 (kind, token)。

    支持：
    - /docx/<token>  → ("docx", token)
    - /wiki/<token>  → ("wiki", token)   wiki 节点，需 resolve 拿 docx token
    - /docs/<token>  → ("docs", token)   旧版 doc，暂不支持，返回会在调用处报错
    - 裸 token       → ("docx", token)   默认按 docx 处理
    """
    if not url_or_token:
        return None
    m = DOC_LINK_RE.search(url_or_token)
    if m:
        return m.group(1), m.group(2)
    s = url_or_token.strip()
    if "/" not in s and re.fullmatch(r"[A-Za-z0-9]+", s):
        return "docx", s
    return None


def find_latest_handbook() -> Optional[Path]:
    """选最新版 handbook（按 _vN 数值最大）。"""
    if not _HANDBOOK_DIR.exists():
        return None
    candidates = list(_HANDBOOK_DIR.glob("handbook_v*.md"))
    if not candidates:
        return None

    def vnum(p: Path) -> int:
        m = HANDBOOK_VERSION_RE.search(p.name)
        return int(m.group(1)) if m else 0

    return max(candidates, key=vnum)


def _handbook_version_label(path: Path) -> str:
    m = HANDBOOK_VERSION_RE.search(path.name)
    return f"v{m.group(1)}" if m else path.stem


async def _score_text_core(
    *,
    content: str,
    title: str,
    docx_token: str = "",
    text_file_hint: str = "",
) -> dict:
    """评分核心：拿到纯文本与标题后，构造 ScriptRecord → predict_one → 标准化返回。
    供 score_docx（飞书拉取）与 score_text（直接文本输入）共用。
    """
    from script_rubric.pipeline.backtest import predict_one
    from script_rubric.models import ScriptRecord
    from script_rubric.config import MODEL

    handbook_path = find_latest_handbook()
    if handbook_path is None:
        raise ValueError(f"未找到 handbook 文件（{_HANDBOOK_DIR}）")
    handbook_text = handbook_path.read_text(encoding="utf-8")
    handbook_version = _handbook_version_label(handbook_path)

    record = ScriptRecord(
        title=title,
        source_type="",
        genre="",
        submitter="",
        status="待评估",
        status_source="ad_hoc",
        table_source="",
        text_content=content,
        text_file=text_file_hint or (f"docx:{docx_token}" if docx_token else "ad_hoc"),
        docx_token=docx_token,
    )

    pred = await predict_one(record, handbook_text)
    if pred is None:
        raise ValueError("预测失败：LLM 返回不可解析的结果")

    return {
        "title": pred.title,
        "predicted_score": pred.predicted_score,
        "predicted_status": pred.predicted_status,
        "dimension_scores": pred.dimension_scores,
        "comments": pred.comments,
        "red_flags_hit": pred.red_flags_hit,
        "green_flags_hit": pred.green_flags_hit,
        "handbook_version": handbook_version,
        "model": MODEL,
        "docx_token": docx_token,
        "text_length": len(content),
        "detected_title": title,
    }


async def score_text(text: str, title: str) -> dict:
    """对一段纯文本剧本做即时评分（跳过飞书拉取）。

    用于 adaptation 改编工作台一键评分等场景：把数据库里多场拼接出来的
    完整剧本直接送评分，免去导出 docx 上传飞书的中间步骤。

    Args:
        text: 剧本全文（已拼接好所有场，含场号标题行）
        title: 项目标题，作为 ScriptRecord.title 使用

    Returns:
        与 score_docx 同 schema（docx_token 为空串）
    """
    if not text or not text.strip():
        raise ValueError("剧本内容为空，无法评分")
    if not title:
        title = "未命名"
    logger.info(f"score_text: title={title} len={len(text)}")
    return await _score_text_core(
        content=text,
        title=title,
        docx_token="",
        text_file_hint="adaptation",
    )


async def score_docx(url: str, force_refresh: bool = True) -> dict:
    """对一个飞书 docx 链接做即时评分。

    Args:
        url: 飞书文档链接 (https://...feishu.cn/docx/<token>) 或裸 token
        force_refresh: True 时跳过本地 cache，强制重新拉飞书（默认 True，
            因为剧本可能反复修改，本地 cache 可能过期）

    Returns:
        {title, predicted_score, predicted_status, dimension_scores,
         comments, red_flags_hit, green_flags_hit, handbook_version,
         model, docx_token, text_length}
    """
    # Lazy imports：script_rubric 依赖 OPENAI/FEISHU 环境变量，懒加载避免启动期失败
    from script_rubric.feishu.feishu_common import (
        get_tenant_access_token,
        fetch_docx_raw_content,
        resolve_wiki_node,
    )
    from script_rubric.pipeline.fetch_docx import save_cache, load_cached

    parsed = extract_doc_link(url)
    if not parsed:
        raise ValueError(f"无法从输入解析飞书文档链接：{url}")
    kind, raw_token = parsed

    # wiki 链接：先 resolve 出真正的 docx token
    if kind == "wiki":
        access_token = get_tenant_access_token()
        node = resolve_wiki_node(access_token, raw_token)
        obj_type = node.get("obj_type")
        if obj_type != "docx":
            raise ValueError(
                f"wiki 节点指向 {obj_type or '未知'}，仅支持 docx 类型；"
                f"请直接打开该文档复制 docx 链接（URL 中是 /docx/...）"
            )
        docx_token = node.get("obj_token")
        if not docx_token:
            raise ValueError(f"wiki 节点解析失败，未拿到 obj_token")
    elif kind == "docs":
        raise ValueError("不支持旧版飞书文档（/docs/...），请使用新版 docx 或 wiki 链接")
    else:
        docx_token = raw_token

    # 拉正文
    content: Optional[str] = None
    if not force_refresh:
        content = load_cached(docx_token)
    if content is None:
        access_token = get_tenant_access_token()
        content = fetch_docx_raw_content(access_token, docx_token)
        if content:
            save_cache(docx_token, content)
    if not content:
        raise ValueError("docx 正文为空")

    title = next((ln.strip() for ln in content.splitlines() if ln.strip()), "未命名")
    logger.info(f"score_docx: token={docx_token} title={title} len={len(content)}")

    return await _score_text_core(content=content, title=title, docx_token=docx_token)
