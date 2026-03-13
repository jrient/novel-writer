"""
章节路由测试
"""
import pytest
from fastapi.testclient import TestClient

from app.models.project import Project
from app.models.chapter import Chapter


def test_list_chapters(client, sample_chapter):
    """测试获取章节列表"""
    response = client.get(f"/api/v1/projects/{sample_chapter.project_id}/chapters/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


def test_create_chapter(client, sample_project):
    """测试创建章节"""
    response = client.post(
        f"/api/v1/projects/{sample_project.id}/chapters/",
        json={
            "title": "新章节",
            "content": "新章节的内容",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "新章节"


def test_get_chapter(client, sample_chapter):
    """测试获取单个章节"""
    response = client.get(
        f"/api/v1/projects/{sample_chapter.project_id}/chapters/{sample_chapter.id}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == sample_chapter.title


def test_update_chapter_content(client, sample_chapter, sample_project):
    """测试更新章节内容"""
    new_content = "这是更新后的章节内容，包含更多文字。"
    response = client.put(
        f"/api/v1/projects/{sample_project.id}/chapters/{sample_chapter.id}",
        json={"content": new_content},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == new_content


def test_delete_chapter(client, sample_chapter):
    """测试删除章节"""
    chapter_id = sample_chapter.id
    project_id = sample_chapter.project_id

    response = client.delete(
        f"/api/v1/projects/{project_id}/chapters/{chapter_id}"
    )

    assert response.status_code == 204


def test_batch_delete_chapters(client, sample_project):
    """测试批量删除章节"""
    # 创建多个章节
    chapter_ids = []
    for i in range(3):
        response = client.post(
            f"/api/v1/projects/{sample_project.id}/chapters/",
            json={"title": f"批量测试章节{i+1}", "content": f"内容{i+1}"},
        )
        assert response.status_code == 201
        chapter_ids.append(response.json()["id"])

    # 批量删除
    response = client.post(
        f"/api/v1/projects/{sample_project.id}/chapters/batch-delete",
        json={"ids": chapter_ids},
    )

    assert response.status_code == 204