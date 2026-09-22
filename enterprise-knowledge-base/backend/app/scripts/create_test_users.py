"""批量创建试运行用户

用法:
  docker compose exec backend python -m app.scripts.create_test_users \
    --prefix testuser --count 30 --role readonly --dept "市场部"
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.models.user import User


async def create_users(
    prefix: str = "user",
    count: int = 30,
    role: str = "readonly",
    department: str = "测试部",
    password: str = "Test@123456",
) -> list[str]:
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    created: list[str] = []

    async with AsyncSessionLocal() as db:
        for i in range(1, count + 1):
            username = f"{prefix}{i:03d}"
            existing = await db.get(User, None)
            from sqlalchemy import select
            r = await db.execute(select(User.id).where(User.username == username).limit(1))
            if r.scalar_one_or_none() is not None:
                print(f"[SKIP] {username} already exists")
                continue

            user = User(
                username=username,
                password_hash=pwd_ctx.hash(password),
                display_name=f"{department}{i:02d}号",
                role=role,
                department=department,
                is_active=1,
            )
            db.add(user)
            await db.commit()
            created.append(username)

    return created


async def _main():
    import argparse

    parser = argparse.ArgumentParser(description="批量创建试运行用户")
    parser.add_argument("--prefix", default="user", help="用户名前缀")
    parser.add_argument("--count", type=int, default=30, help="创建数量")
    parser.add_argument("--role", default="readonly", help="角色")
    parser.add_argument("--dept", default="测试部", help="部门")
    parser.add_argument("--password", default="Test@123456", help="默认密码")
    args = parser.parse_args()

    created = await create_users(
        prefix=args.prefix,
        count=args.count,
        role=args.role,
        department=args.dept,
        password=args.password,
    )
    print(f"Created {len(created)} users: {created[:5]}... ({args.role} @ {args.dept})")


if __name__ == "__main__":
    asyncio.run(_main())
