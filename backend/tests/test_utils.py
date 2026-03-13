"""
测试工具函数
"""
import pytest


class TestUtils:
    """测试工具函数集合"""

    @staticmethod
    def assert_valid_response(response, expected_keys: list):
        """验证响应包含必需的字段"""
        data = response.json()
        for key in expected_keys:
            assert key in data, f"响应缺少必需字段: {key}"
        return data

    @staticmethod
    def assert_error_response(response, expected_status: int, expected_detail: str = None):
        """验证错误响应"""
        assert response.status_code == expected_status
        if expected_detail:
            data = response.json()
            assert expected_detail in data.get("detail", "")