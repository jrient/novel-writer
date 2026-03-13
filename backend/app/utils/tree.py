"""
树形结构工具函数
用于构建层级结构（大纲节点、世界观条目等）
"""
from typing import TypeVar, Generic, List, Optional

T = TypeVar("T")


class TreeNode(Generic[T]):
    """通用树节点"""
    def __init__(self, data: T):
        self.data = data
        self.children: List["TreeNode[T]"] = []


def build_tree(
    items: List[T],
    id_field: str = "id",
    parent_field: str = "parent_id",
) -> List[TreeNode[T]]:
    """
    将扁平列表构建为树形结构

    Args:
        items: 扁平列表项
        id_field: ID 字段名
        parent_field: 父 ID 字段名

    Returns:
        根节点列表
    """
    if not items:
        return []

    # 创建节点映射
    id_to_node: dict = {}
    root_nodes: List[TreeNode[T]] = []

    # 第一遍：创建所有节点
    for item in items:
        node = TreeNode(item)
        item_id = getattr(item, id_field, None)
        if item_id is not None:
            id_to_node[item_id] = node

    # 第二遍：建立父子关系
    for item in items:
        item_id = getattr(item, id_field, None)
        parent_id = getattr(item, parent_field, None)

        if item_id is None:
            continue

        node = id_to_node.get(item_id)
        if node is None:
            continue

        if parent_id is None:
            # 根节点
            root_nodes.append(node)
        else:
            # 子节点
            parent_node = id_to_node.get(parent_id)
            if parent_node:
                parent_node.children.append(node)
            else:
                # 父节点不存在，作为根节点
                root_nodes.append(node)

    return root_nodes


def flatten_tree(nodes: List[TreeNode[T]]) -> List[T]:
    """
    将树形结构扁平化为列表（深度优先遍历）

    Args:
        nodes: 根节点列表

    Returns:
        扁平化的数据列表
    """
    result: List[T] = []

    def dfs(node: TreeNode[T]):
        result.append(node.data)
        for child in node.children:
            dfs(child)

    for node in nodes:
        dfs(node)

    return result


def sort_tree_by_order(
    nodes: List[TreeNode[T]],
    order_field: str = "sort_order",
) -> List[TreeNode[T]]:
    """
    按排序字段对树节点进行排序（递归）

    Args:
        nodes: 节点列表
        order_field: 排序字段名

    Returns:
        排序后的节点列表
    """
    # 排序当前层级
    sorted_nodes = sorted(
        nodes,
        key=lambda n: getattr(n.data, order_field, 0) or 0
    )

    # 递归排序子节点
    for node in sorted_nodes:
        node.children = sort_tree_by_order(node.children, order_field)

    return sorted_nodes