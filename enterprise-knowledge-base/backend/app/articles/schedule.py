"""发布调度器（定时 + 即时队列）

每 30 秒扫描 publishing_record 表中 status='pending' 的记录：
- scheduled_at 为空 → 立即发布队列（一键提交后由本调度器接管）
- scheduled_at <= now() → 到期的定时发布任务
使用对应账号凭证执行发布。
"""

import json
from datetime import datetime

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.articles.models import PlatformAccount, PublishingRecord


async def _execute_scheduled_publishes() -> None:
    """扫描并执行发布任务（即时队列 + 到期的定时任务）"""
    now = datetime.now()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PublishingRecord).where(
                    PublishingRecord.status == "pending",
                    or_(
                        PublishingRecord.scheduled_at.is_(None),
                        PublishingRecord.scheduled_at <= now,
                    ),
                ).order_by(PublishingRecord.id.asc()).limit(20)
            )
            records = result.scalars().all()

            if not records:
                return

            from app.articles.publisher import PLATFORMS, publish_to_wechat_mp, publish_via_bridge, publish_via_wechatsync

            for record in records:
                try:
                    pinfo = PLATFORMS.get(record.platform)
                    if not pinfo:
                        record.status = "failed"
                        record.error_message = f"未知平台: {record.platform}"
                        await db.commit()
                        continue

                    # 获取文章内容
                    from app.articles.models import Article
                    article_result = await db.execute(
                        select(Article).where(Article.id == record.article_id)
                    )
                    article = article_result.scalar()
                    if not article:
                        record.status = "failed"
                        record.error_message = "文章不存在"
                        await db.commit()
                        continue

                    # 获取账号凭证
                    account_creds: dict = {}
                    account_group: str = ""
                    ws_token: str = ""
                    if record.account_id:
                        account_result = await db.execute(
                            select(PlatformAccount).where(PlatformAccount.id == record.account_id)
                        )
                        account = account_result.scalar()
                        if account:
                            from app.articles.crypto import decrypt_credentials
                            account_group = account.account_group or ""
                            if account.ws_token:
                                try:
                                    ws_token = decrypt_credentials(account.ws_token)
                                except Exception:
                                    pass
                            if account.credentials:
                                try:
                                    account_creds = json.loads(decrypt_credentials(account.credentials))
                                except Exception:
                                    pass

                    # 执行发布
                    result: dict = {"success": False, "url": None, "error": "未知发布方式"}
                    method = pinfo["method"]

                    record.status = "publishing"
                    await db.commit()

                    if method == "direct_api" and record.platform == "wechat_mp":
                        result = await publish_to_wechat_mp(
                            article.title, article.content,
                            appid=account_creds.get("appid", settings.wechat_mp_appid),
                            appsecret=account_creds.get("appsecret", settings.wechat_mp_appsecret),
                            image_placement=article.image_placement,
                        )
                    elif method == "wechatsync":
                        if account_group and ws_token:
                            result = await publish_via_bridge(
                                article.title, article.content,
                                record.platform,
                                account_group=account_group, token=ws_token,
                                image_placement=article.image_placement,
                            )
                        else:
                            result = await publish_via_wechatsync(
                                article.title, article.content,
                                record.platform,
                                credentials=account_creds or None,
                                image_placement=article.image_placement,
                            )

                    record.status = "published" if result["success"] else "failed"
                    record.published_url = result.get("url")
                    record.remote_article_id = result.get("remote_article_id")
                    record.error_message = result.get("error") or (None if result["success"] else "未知错误")
                    record.published_at = datetime.now() if result["success"] else None
                    await db.commit()

                    logger.info(
                        "scheduled_publish_done",
                        record_id=record.id,
                        platform=record.platform,
                        status=record.status,
                    )

                except Exception as exc:
                    await db.rollback()
                    logger.warning("scheduled_publish_failed", record_id=record.id, error=repr(exc))
                    # rollback 会令 record 过期；重新拉取后再更新，避免 async 会话过期实例写入报错
                    try:
                        failed = await db.get(PublishingRecord, record.id)
                        if failed is not None:
                            failed.status = "failed"
                            failed.error_message = str(exc) or repr(exc)
                            await db.commit()
                    except Exception as state_exc:
                        await db.rollback()
                        logger.warning(
                            "scheduled_publish_failed_state_update",
                            record_id=record.id,
                            error=repr(state_exc),
                        )

    except Exception:
        logger.warning("scheduled_publish_check_failed", exc_info=True)
