"""扩写模块路由测试"""
import pytest
from unittest.mock import patch, AsyncMock
from app.routers.expansion import router
from app.models.expansion_project import ExpansionProject
from app.models.expansion_segment import ExpansionSegment


class TestRouterRegistration:
    """测试路由注册"""

    def test_router_prefix(self):
        """测试路由前缀"""
        assert router.prefix == "/api/v1/expansion"

    def test_router_tags(self):
        """测试路由标签"""
        assert "expansion" in router.tags

    def test_routes_exist(self):
        """测试主要路由存在"""
        route_paths = [r.path for r in router.routes]
        assert "/api/v1/expansion/" in route_paths
        assert "/api/v1/expansion/{id}" in route_paths
        assert "/api/v1/expansion/{id}/analyze" in route_paths
        assert "/api/v1/expansion/{id}/segments" in route_paths
        assert "/api/v1/expansion/{id}/expand" in route_paths

    def test_project_crud_routes(self):
        """测试项目 CRUD 路由"""
        route_paths = [r.path for r in router.routes]
        assert "/api/v1/expansion/upload" in route_paths
        assert "/api/v1/expansion/import/novel" in route_paths
        assert "/api/v1/expansion/import/drama" in route_paths

    def test_segment_routes(self):
        """测试分段操作路由"""
        route_paths = [r.path for r in router.routes]
        assert "/api/v1/expansion/{id}/segments/split" in route_paths
        assert "/api/v1/expansion/{id}/segments/merge" in route_paths
        assert "/api/v1/expansion/{id}/segments/reorder" in route_paths

    def test_expansion_routes(self):
        """测试扩写操作路由"""
        route_paths = [r.path for r in router.routes]
        assert "/api/v1/expansion/{id}/expand" in route_paths
        assert "/api/v1/expansion/{id}/segments/{seg_id}/expand" in route_paths
        assert "/api/v1/expansion/{id}/pause" in route_paths
        assert "/api/v1/expansion/{id}/resume" in route_paths

    def test_export_convert_routes(self):
        """测试导出转换路由"""
        route_paths = [r.path for r in router.routes]
        assert "/api/v1/expansion/{id}/export" in route_paths
        assert "/api/v1/expansion/{id}/convert" in route_paths


class TestSchemas:
    """测试 Schema 验证"""

    def test_import_from_novel_request_schema(self):
        """测试从小说导入请求 schema"""
        from app.schemas.expansion import ImportFromNovelRequest

        data = ImportFromNovelRequest(
            title="导入测试",
            project_id=1,
            chapter_ids=[1, 2, 3],
            expansion_level="medium",
        )
        assert data.title == "导入测试"
        assert data.chapter_ids == [1, 2, 3]

    def test_import_from_drama_request_schema(self):
        """测试从剧本导入请求 schema"""
        from app.schemas.expansion import ImportFromDramaRequest

        data = ImportFromDramaRequest(
            title="导入测试",
            project_id=1,
            expansion_level="deep",
        )
        assert data.title == "导入测试"
        assert data.expansion_level == "deep"

    def test_convert_request_schema(self):
        """测试转换请求 schema"""
        from app.schemas.expansion import ConvertRequest

        data_novel = ConvertRequest(target="novel")
        assert data_novel.target == "novel"

        data_drama = ConvertRequest(target="drama")
        assert data_drama.target == "drama"

    def test_segment_split_request_schema(self):
        """测试分段拆分请求 schema"""
        from app.schemas.expansion import SegmentSplitRequest

        data = SegmentSplitRequest(segment_id=1, split_position=500)
        assert data.segment_id == 1
        assert data.split_position == 500

    def test_segment_merge_request_schema(self):
        """测试分段合并请求 schema"""
        from app.schemas.expansion import SegmentMergeRequest

        data = SegmentMergeRequest(segment_ids=[1, 2])
        assert len(data.segment_ids) == 2

    def test_segment_reorder_request_schema(self):
        """测试分段重排序请求 schema"""
        from app.schemas.expansion import SegmentReorderRequest

        data = SegmentReorderRequest(segment_ids=[3, 1, 2])
        assert data.segment_ids == [3, 1, 2]

    def test_expand_segment_request_schema(self):
        """测试扩写分段请求 schema"""
        from app.schemas.expansion import ExpandSegmentRequest

        data = ExpandSegmentRequest(
            segment_id=1,
            instructions="请详细扩写"
        )
        assert data.segment_id == 1
        assert data.instructions == "请详细扩写"


class TestHelperFunctions:
    """测试辅助函数"""

    @pytest.mark.asyncio
    async def test_sse_stream_format(self):
        """测试 SSE 流格式"""
        from app.routers.expansion import _sse_stream
        import json

        async def mock_generator():
            yield "chunk1"
            yield "chunk2"

        chunks = []
        async for chunk in _sse_stream(mock_generator()):
            chunks.append(chunk)

        # 应该有 3 个 chunk: 2 个文本 + 1 个 done
        assert len(chunks) == 3
        assert chunks[0].startswith("data: ")
        assert chunks[-1] == 'data: {"type": "done"}\n\n'

    def test_sse_response_headers(self):
        """测试 SSE 响应头"""
        from fastapi.responses import StreamingResponse
        from app.routers.expansion import _sse_response

        async def mock_gen():
            yield "test"

        response = _sse_response(mock_gen())
        assert isinstance(response, StreamingResponse)
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"


class TestExpansionAIServiceIntegration:
    """测试 ExpansionAIService 集成"""

    def test_service_initialization(self):
        """测试服务初始化"""
        from app.services.expansion_ai_service import ExpansionAIService

        service = ExpansionAIService()
        assert service.provider is not None

    def test_service_with_config(self):
        """测试带配置的服务初始化"""
        from app.services.expansion_ai_service import ExpansionAIService

        config = {
            "provider": "anthropic",
            "model": "claude-3-sonnet",
            "prompt_config": {
                "temperature": 0.8,
                "max_tokens": 4000,
            }
        }
        service = ExpansionAIService(config)
        assert service.provider == "anthropic"
        assert service.model == "claude-3-sonnet"
        assert service.temperature == 0.8

    def test_expansion_multipliers(self):
        """测试扩写倍数"""
        from app.services.expansion_ai_service import ExpansionAIService

        assert ExpansionAIService.get_expansion_multiplier("light") == 1.5
        assert ExpansionAIService.get_expansion_multiplier("medium") == 2.0
        assert ExpansionAIService.get_expansion_multiplier("deep") == 3.0

    def test_expansion_level_names(self):
        """测试扩写级别名称"""
        from app.services.expansion_ai_service import ExpansionAIService

        assert ExpansionAIService.get_expansion_level_name("light") == "轻度扩写"
        assert ExpansionAIService.get_expansion_level_name("medium") == "中度扩写"
        assert ExpansionAIService.get_expansion_level_name("deep") == "深度扩写"


class TestFileParser:
    """测试文件解析器"""

    def test_parse_txt(self):
        """测试 TXT 解析"""
        from app.services.file_parser import FileParser

        content = "这是测试内容。".encode("utf-8")
        result = FileParser.parse_txt(content)
        assert "这是测试内容" in result.text

    def test_parse_markdown(self):
        """测试 Markdown 解析"""
        from app.services.file_parser import FileParser

        content = "# 标题\n\n这是**粗体**内容。".encode("utf-8")
        result = FileParser.parse_markdown(content)
        assert "标题" in result.text
        assert "粗体" in result.text

    def test_file_parser_max_chars(self):
        """测试文件解析器字符限制"""
        from app.services.file_parser import FileParser

        assert FileParser.MAX_CHARS == 30000
