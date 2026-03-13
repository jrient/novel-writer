"""
项目路由测试
"""
import pytest
from fastapi.testclient import TestClient

from app.models.project import Project


def test_list_projects(client, sample_project):
    """测试获取项目列表"""
    response = client.get("/api/v1/projects/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(p["title"] == "测试小说" for p in data)


def test_create_project(client):
    """测试创建项目"""
    response = client.post(
        "/api/v1/projects/",
        json={
            "title": "新测试项目",
            "genre": "科幻",
            "description": "测试创建功能",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "新测试项目"
    assert data["genre"] == "科幻"


def test_get_project(client, sample_project):
    """测试获取单个项目"""
    response = client.get(f"/api/v1/projects/{sample_project.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "测试小说"
    assert data["genre"] == "玄幻"


def test_get_project_not_found(client):
    """测试获取不存在的项目"""
    response = client.get("/api/v1/projects/99999")

    assert response.status_code == 404


def test_update_project(client, sample_project):
    """测试更新项目"""
    response = client.put(
        f"/api/v1/projects/{sample_project.id}",
        json={
            "title": "更新后的标题",
            "status": "in_progress",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "更新后的标题"
    assert data["status"] == "in_progress"


def test_delete_project(client, sample_project):
    """测试删除项目"""
    project_id = sample_project.id
    response = client.delete(f"/api/v1/projects/{project_id}")

    assert response.status_code == 204

    # 验证项目已被删除
    response = client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 404