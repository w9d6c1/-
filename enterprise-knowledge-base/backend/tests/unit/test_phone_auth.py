"""手机号验证码认证测试 (TDD)"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/admin/auth/login",
        data={"username": username, "password": password},
    )
    return resp.json()["access_token"]


# 模拟验证码存储 (测试环境无Redis)
_test_codes: dict[str, str] = {}
_test_rate: set[str] = set()


async def _mock_store_sms_code(phone, code):
    _test_codes[phone] = code


async def _mock_verify_sms_code(phone, code):
    stored = _test_codes.get(phone)
    if stored and stored == code:
        del _test_codes[phone]
        return True
    return False


async def _mock_check_rate_limit(phone):
    return False  # 测试环境不限制频率


@pytest.fixture(autouse=True)
def _mock_redis():
    _test_codes.clear()
    _test_rate.clear()
    with patch("app.api.admin.auth.store_sms_code", _mock_store_sms_code):
        with patch("app.api.admin.auth.verify_sms_code", _mock_verify_sms_code):
            with patch("app.api.admin.auth.check_rate_limit", _mock_check_rate_limit):
                yield


@pytest.mark.asyncio
async def test_send_code_returns_code_in_debug(client: AsyncClient):
    """开发环境发送验证码返回code"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "code" in data
    assert len(data["code"]) == 6


@pytest.mark.asyncio
async def test_send_code_rate_limit(client: AsyncClient):
    """60秒内重复发送限流"""
    with patch("app.api.admin.auth.check_rate_limit", side_effect=[False, True]):
        await client.post("/api/admin/auth/send-code", json={"phone": "13800138002"})
        resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138002"})
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_phone_login_new_user_auto_register(client: AsyncClient):
    """新手机号验证码登录自动注册"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138003"})
    code = resp.json()["code"]

    resp = await client.post("/api/admin/auth/phone-login", json={"phone": "13800138003", "code": code})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["phone"] == "13800138003"
    assert data["user"]["role"] == "readonly"


@pytest.mark.asyncio
async def test_phone_login_existing_user(client: AsyncClient):
    """已注册手机号验证码登录"""
    # 第一次注册
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138004"})
    code1 = resp.json()["code"]
    await client.post("/api/admin/auth/phone-login", json={"phone": "13800138004", "code": code1})

    # 第二次登录
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138004"})
    code2 = resp.json()["code"]
    resp = await client.post("/api/admin/auth/phone-login", json={"phone": "13800138004", "code": code2})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_phone_login_wrong_code(client: AsyncClient):
    """错误验证码拒绝登录"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138005"})
    _code = resp.json()["code"]
    resp = await client.post("/api/admin/auth/phone-login", json={"phone": "13800138005", "code": "000000"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_phone_login_code_single_use(client: AsyncClient):
    """验证码一次性有效"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138006"})
    code = resp.json()["code"]

    # 第一次成功
    resp = await client.post("/api/admin/auth/phone-login", json={"phone": "13800138006", "code": code})
    assert resp.status_code == 200

    # 第二次用同样的码失败
    resp = await client.post("/api/admin/auth/phone-login", json={"phone": "13800138006", "code": code})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_phone_password_login(client: AsyncClient):
    """手机号+密码登录"""
    # 注册一个用户
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138007"})
    code = resp.json()["code"]
    await client.post("/api/admin/auth/phone-login", json={"phone": "13800138007", "code": code})

    # 设置密码后测试密码登录
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138007"})
    code2 = resp.json()["code"]
    await client.post("/api/admin/auth/reset-password", json={
        "phone": "13800138007", "code": code2,
        "new_password": "NewP@ssw0rd", "password_confirm": "NewP@ssw0rd",
    })

    resp = await client.post("/api/admin/auth/phone-password-login", json={
        "phone": "13800138007", "password": "NewP@ssw0rd",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_phone_password_login_wrong(client: AsyncClient):
    """错误密码拒绝"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138008"})
    code = resp.json()["code"]
    await client.post("/api/admin/auth/phone-login", json={"phone": "13800138008", "code": code})

    resp = await client.post("/api/admin/auth/phone-password-login", json={
        "phone": "13800138008", "password": "WrongP@ss1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_password(client: AsyncClient):
    """验证码找回密码"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138009"})
    code1 = resp.json()["code"]
    await client.post("/api/admin/auth/phone-login", json={"phone": "13800138009", "code": code1})

    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138009"})
    code2 = resp.json()["code"]
    resp = await client.post("/api/admin/auth/reset-password", json={
        "phone": "13800138009", "code": code2,
        "new_password": "ResetP@ss1", "password_confirm": "ResetP@ss1",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_reset_password_unregistered(client: AsyncClient):
    """未注册号码无法重置"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138010"})
    code = resp.json()["code"]
    resp = await client.post("/api/admin/auth/reset-password", json={
        "phone": "13800138010", "code": code,
        "new_password": "ResetP@ss2", "password_confirm": "ResetP@ss2",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reset_password_mismatch(client: AsyncClient):
    """两次密码不一致拒绝"""
    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138011"})
    code1 = resp.json()["code"]
    await client.post("/api/admin/auth/phone-login", json={"phone": "13800138011", "code": code1})

    resp = await client.post("/api/admin/auth/send-code", json={"phone": "13800138011"})
    code2 = resp.json()["code"]
    resp = await client.post("/api/admin/auth/reset-password", json={
        "phone": "13800138011", "code": code2,
        "new_password": "ResetP@ss3", "password_confirm": "DifferentP@ss",
    })
    assert resp.status_code == 422
