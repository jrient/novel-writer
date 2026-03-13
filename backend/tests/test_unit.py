"""
单元测试 - 直接测试模型和工具函数
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.tree import TreeNode, build_tree, flatten_tree, sort_tree_by_order


class TestTreeUtils:
    """测试树构建工具函数"""

    def test_build_tree_empty(self):
        """测试空列表"""
        result = build_tree([])
        assert result == []

    def test_build_tree_single_root(self):
        """测试单个根节点"""
        class Item:
            def __init__(self, id, parent_id=None):
                self.id = id
                self.parent_id = parent_id

        items = [Item(1)]
        result = build_tree(items, id_field="id", parent_field="parent_id")
        assert len(result) == 1
        assert result[0].data.id == 1

    def test_build_tree_with_children(self):
        """测试带子节点的树"""
        class Item:
            def __init__(self, id, parent_id=None, sort_order=0):
                self.id = id
                self.parent_id = parent_id
                self.sort_order = sort_order

        items = [
            Item(1, None),
            Item(2, 1),
            Item(3, 1),
            Item(4, None),
        ]
        result = build_tree(items, id_field="id", parent_field="parent_id")
        assert len(result) == 2  # 两个根节点
        # 第一个根节点有两个子节点
        assert len(result[0].children) == 2

    def test_flatten_tree(self):
        """测试树扁平化"""
        class Item:
            def __init__(self, id, parent_id=None):
                self.id = id
                self.parent_id = parent_id

        items = [Item(1), Item(2), Item(3)]
        tree = build_tree(items)
        flat = flatten_tree(tree)
        assert len(flat) == 3

    def test_sort_tree_by_order(self):
        """测试树排序"""
        class Item:
            def __init__(self, id, sort_order=0, parent_id=None):
                self.id = id
                self.sort_order = sort_order
                self.parent_id = parent_id

        items = [
            Item(1, 3),
            Item(2, 1),
            Item(3, 2),
        ]
        tree = build_tree(items)
        sorted_tree = sort_tree_by_order(tree, order_field="sort_order")
        assert sorted_tree[0].data.id == 2  # sort_order=1
        assert sorted_tree[1].data.id == 3  # sort_order=2
        assert sorted_tree[2].data.id == 1  # sort_order=3


class TestConfig:
    """测试配置"""

    def test_default_settings(self):
        """测试默认配置"""
        from app.core.config import settings

        assert settings.DEFAULT_AI_PROVIDER == "openai"
        assert settings.AI_CONTEXT_CHARACTER_LIMIT == 10
        assert settings.AI_CONTEXT_WORLDBUILDING_LIMIT == 10
        assert settings.AI_MAX_TOKENS_DEFAULT == 4000
        assert settings.AI_MAX_TOKENS_STREAM == 8000


class TestDependencies:
    """测试依赖函数"""

    def test_get_project_or_404_import(self):
        """测试依赖函数可导入"""
        from app.core.dependencies import get_project_or_404
        assert callable(get_project_or_404)


class TestProviderBase:
    """测试 AI Provider 基类"""

    def test_import_provider(self):
        """测试 Provider 可导入"""
        from app.services.providers.base import BaseLLMProvider, GenerationResult, StreamChunk

        assert BaseLLMProvider is not None
        assert GenerationResult is not None
        assert StreamChunk is not None

    def test_generation_result_dataclass(self):
        """测试 GenerationResult"""
        from app.services.providers.base import GenerationResult

        result = GenerationResult(
            content="测试内容",
            tokens_used=100,
            model="gpt-4o",
            provider="openai"
        )
        assert result.content == "测试内容"
        assert result.tokens_used == 100

    def test_stream_chunk_dataclass(self):
        """测试 StreamChunk"""
        from app.services.providers.base import StreamChunk

        chunk = StreamChunk(text="测试", done=False, error=None)
        assert chunk.text == "测试"
        assert chunk.done is False