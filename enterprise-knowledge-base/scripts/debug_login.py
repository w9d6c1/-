"""服务器登录问题排查脚本 — 在服务器上运行: docker exec kb-backend python /app/scripts/debug_login.py"""
import asyncio
import sys
sys.path.insert(0, "/app")

async def main():
    phone = "18808977122"
    code = "368839"

    # 1. Redis 连通性
    print("=" * 40)
    print("1. Redis 连通性")
    try:
        import redis
        r = redis.from_url("redis://redis:6379/0")
        r.ping()
        print("   Redis PING: OK")
    except Exception as e:
        print(f"   Redis PING: FAILED - {e}")

    # 2. 验证旧验证码
    print("=" * 40)
    print("2. 验证验证码 368839")
    try:
        from app.services.user_service import verify_sms_code
        ok = await verify_sms_code(phone, code)
        print(f"   验证结果: {ok}")
    except Exception as e:
        print(f"   验证异常: {e}")

    # 3. 生成新验证码并存取
    print("=" * 40)
    print("3. 生成新验证码并验证存取")
    try:
        from app.services.user_service import generate_sms_code, store_sms_code, verify_sms_code
        new_code = generate_sms_code()
        await store_sms_code(phone, new_code)
        print(f"   新验证码: {new_code} (已存入 Redis)")
        ok = await verify_sms_code(phone, new_code)
        print(f"   验新码结果: {ok}")
    except Exception as e:
        print(f"   存取异常: {e}")

    # 4. MySQL 连通性和用户注册
    print("=" * 40)
    print("4. MySQL 用户注册/查找")
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.user_service import UserService
        from app.schemas.user import UserCreate
        async with AsyncSessionLocal() as db:
            svc = UserService(db)
            token, user = await svc.authenticate_or_register_by_phone(phone)
            print(f"   用户ID: {user.id}, 角色: {user.role}, 手机: {user.phone}")
            print(f"   Token: {token[:30]}...")
    except Exception as e:
        print(f"   用户注册异常: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 40)
    print("排查完成")

asyncio.run(main())
