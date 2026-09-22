"""基础冒烟测试 - 验证应用骨架可启动"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "企业知识库系统"


@pytest.mark.asyncio
async def test_admin_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/admin/status")
    assert response.status_code == 200
    assert response.json()["module"] == "admin"


@pytest.mark.asyncio
async def test_agent_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/agent/status")
    assert response.status_code == 200
    assert response.json()["module"] == "agent"


@pytest.mark.asyncio
async def test_request_id_header():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert "X-Request-ID" in response.headers
