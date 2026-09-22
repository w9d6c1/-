"""用户业务逻辑层"""

import base64
import hashlib
import hmac
import json
import random
import time as _time
import urllib.parse
from datetime import UTC, datetime, timedelta

import httpx
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import func, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.user import User
from app.schemas.user import UserCreate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        _redis_client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _redis_client


class DuplicateUserError(Exception):
    pass


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self.db.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def create(self, payload: UserCreate) -> User:
        user = User(
            username=payload.username,
            password_hash=pwd_context.hash(payload.password),
            display_name=payload.display_name,
            email=payload.email,
            phone=payload.phone,
            role=payload.role,
            department=payload.department,
        )
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise DuplicateUserError
        await self.db.refresh(user)
        return user

    async def create_by_phone(self, phone: str) -> User:
        """手机号注册—自动生成用户名和随机初始密码"""
        username = f"user_{phone}"
        # 检查username唯一性
        existing = await self.get_by_username(username)
        if existing:
            username = f"{username}_{datetime.now(UTC).strftime('%H%M%S')}"
        user = User(
            username=username,
            phone=phone,
            password_hash=pwd_context.hash(phone),  # 初始密码=手机号(首次可通过验证码登录后修改)
            display_name=phone,
            role=settings.wecom_default_role,
        )
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise DuplicateUserError
        await self.db.refresh(user)
        return user

    async def list_users(self, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
        count_result = await self.db.execute(select(func.count()).select_from(User))
        total = count_result.scalar() or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(User).order_by(User.id.desc()).offset(offset).limit(page_size)
        )
        return list(result.scalars()), total

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def update(self, user_id: int, role: str | None = None, department: str | None = None, display_name: str | None = None, is_active: bool | None = None) -> User | None:
        user = await self.db.get(User, user_id)
        if user is None:
            return None
        if role is not None:
            user.role = role
        if department is not None:
            user.department = department
        if display_name is not None:
            user.display_name = display_name
        if is_active is not None:
            user.is_active = is_active
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate(self, username: str, password: str) -> str | None:
        user = await self.get_by_username(username)
        if user is None or not pwd_context.verify(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return self._make_token(user)

    async def authenticate_by_phone_password(self, phone: str, password: str) -> str | None:
        user = await self.get_by_phone(phone)
        if user is None or not pwd_context.verify(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return self._make_token(user)

    async def authenticate_or_register_by_phone(self, phone: str) -> tuple[str, User]:
        """手机号验证码登录—用户不存在则自动注册"""
        user = await self.get_by_phone(phone)
        is_new = False
        if user is None:
            user = await self.create_by_phone(phone)
            is_new = True
        if not user.is_active:
            raise ValueError("Account is disabled")
        return self._make_token(user), user

    async def reset_password(self, phone: str, new_password: str) -> bool:
        user = await self.get_by_phone(phone)
        if user is None:
            return False
        user.password_hash = pwd_context.hash(new_password)
        await self.db.commit()
        return True

    def _make_token(self, user: User) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
        return jwt.encode(
            {"sub": str(user.id), "role": user.role, "department": user.department, "exp": expire},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )


def generate_sms_code() -> str:
    return f"{random.randint(0, 999999):06d}"


async def store_sms_code(phone: str, code: str) -> None:
    """存储验证码到 Redis，TTL=300秒"""
    try:
        r = _get_redis()
        await r.set(f"sms:{phone}", code, ex=300)
        await r.set(f"sms:rate:{phone}", "1", ex=60)
    except Exception:
        logger.warning("sms_code_store_failed", phone=phone[-4:])


async def verify_sms_code(phone: str, code: str) -> bool:
    """验证验证码，匹配后删除"""
    try:
        r = _get_redis()
        stored = await r.get(f"sms:{phone}")
        if stored and stored == code:
            await r.delete(f"sms:{phone}")
            return True
    except Exception:
        logger.warning("sms_code_verify_failed", phone=phone[-4:])
    return False


async def check_rate_limit(phone: str) -> bool:
    """检查60秒内是否已发送过验证码"""
    try:
        r = _get_redis()
        return await r.exists(f"sms:rate:{phone}") > 0
    except Exception:
        return False


def _sms_configured() -> bool:
    return all([
        settings.sms_access_key_id,
        settings.sms_access_key_secret,
        settings.sms_sign_name,
        settings.sms_template_code,
    ])


def _aliyun_sign(params: dict[str, str], secret: str) -> str:
    sorted_keys = sorted(params.keys())
    canonical = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(params[k], safe='')}"
        for k in sorted_keys
    )
    string_to_sign = f"GET&{urllib.parse.quote('/', safe='')}&{urllib.parse.quote(canonical, safe='')}"
    key = (secret + "&").encode("utf-8")
    signature = base64.b64encode(
        hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return signature


async def send_sms_via_aliyun(phone: str, code: str) -> bool:
    if not _sms_configured():
        return False

    import uuid

    params: dict[str, str] = {
        "AccessKeyId": settings.sms_access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "SignName": settings.sms_sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": settings.sms_template_code,
        "TemplateParam": json.dumps({"code": code}, separators=(",", ":")),
        "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }

    params["Signature"] = _aliyun_sign(params, settings.sms_access_key_secret)

    url = "https://dysmsapi.aliyuncs.com/?" + urllib.parse.urlencode(params)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()
            if body.get("Code") != "OK":
                logger.error(
                    "sms_send_failed",
                    code=body.get("Code"),
                    message=body.get("Message"),
                )
                return False
            logger.info("sms_sent", phone=phone[-4:])
            return True
    except Exception as exc:
        logger.error("sms_send_exception", error=str(exc))
        return False
