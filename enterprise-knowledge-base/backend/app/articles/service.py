"""文章批量生成 — 业务服务层

模式: 遵循 app/services/document_service.py 的 per-request Service 类。
"""

import asyncio
import io
import json
import zipfile
from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.articles.generator import evaluate_articles, generate_batch
from app.articles.models import Article, ArticleBatch, PlatformAccount, PublishingRecord
from app.articles.photo_service import PhotoService
from app.articles.publisher import (
    PLATFORMS,
    export_docx,
    export_html,
    export_markdown,
)
from app.articles.vision import analyze_photos
from app.core.config import settings
from app.core.logging import logger
from app.core.minio_client import get_minio_client, upload_file

# MinIO 存储桶 + 前缀
_PHOTO_BUCKET = "knowledge-docs"
_PHOTO_PREFIX = "article-photos/"


class ArticleService:
    """文章批量生成服务"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ============================================================
    # Batch CRUD
    # ============================================================

    async def create_batch(
        self,
        topic: str,
        article_count: int,
        user_id: int,
        angle_keys: list[str] | None = None,
        account_type: str | None = None,
    ) -> ArticleBatch:
        batch = ArticleBatch(
            topic=topic,
            article_count=article_count,
            user_id=user_id,
            status="draft",
            account_type=account_type,
            selected_angle_keys=angle_keys,
        )
        self.db.add(batch)
        await self.db.commit()
        await self.db.refresh(batch)
        logger.info(
            "article_batch_created",
            batch_id=batch.id,
            topic=topic,
            account_type=account_type,
        )
        return batch

    async def get_batch(self, batch_id: int) -> ArticleBatch | None:
        return await self.db.get(ArticleBatch, batch_id)

    async def list_batches(
        self, user_id: int | None, page: int = 1, page_size: int = 20
    ) -> tuple[list[ArticleBatch], int]:
        base = select(ArticleBatch)
        count_q = select(func.count(ArticleBatch.id))
        if user_id is not None:
            base = base.where(ArticleBatch.user_id == user_id)
            count_q = count_q.where(ArticleBatch.user_id == user_id)
        base = base.order_by(ArticleBatch.id.desc()).offset((page - 1) * page_size).limit(page_size)

        total = (await self.db.execute(count_q)).scalar() or 0
        rows = (await self.db.execute(base)).scalars().all()
        return list(rows), total

    async def delete_batch(self, batch_id: int) -> bool:
        batch = await self.get_batch(batch_id)
        if not batch:
            return False
        await self.db.delete(batch)
        await self.db.commit()
        logger.info("article_batch_deleted", batch_id=batch_id)
        return True

    async def update_batch_status(self, batch_id: int, status: str, error: str | None = None) -> None:
        batch = await self.get_batch(batch_id)
        if batch:
            batch.status = status
            if error:
                batch.error_message = error
            await self.db.commit()

    # ============================================================
    # Photo Upload
    # ============================================================

    async def upload_photos(self, batch_id: int, files: list[tuple[str, bytes, str]]) -> list[str]:
        """上传照片到 MinIO，返回 object_name 列表。

        files: [(filename, data_bytes, content_type), ...]
        """
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"批次 {batch_id} 不存在")

        object_names: list[str] = []
        for filename, data, content_type in files:
            object_name = f"{_PHOTO_PREFIX}{batch_id}/{filename}"
            upload_file(_PHOTO_BUCKET, object_name, data, content_type)
            object_names.append(object_name)

        batch.photo_object_names = object_names
        batch.photo_count = len(object_names)
        await self.db.commit()
        logger.info("article_photos_uploaded", batch_id=batch_id, count=len(object_names))
        return object_names

    # ============================================================
    # Generation Orchestration
    # ============================================================

    async def run_generation(self, batch_id: int, template_ids: list[int] | None = None, photo_ids: list[int] | None = None, min_words: int | None = None, max_words: int | None = None) -> None:
        """后台任务：分析照片 → 检索 → 生成文章 → 写入数据库 → 质量评估。

        由 API 层通过 asyncio.create_task() 调用。
        支持断点续传：若 batch.generated_count > 0，跳过已生成篇数继续。
        支持照片库模式：若 photo_ids 提供，直接读取 Photo 表的 description，跳过 Vision API。
        """
        batch = await self.get_batch(batch_id)
        if not batch:
            return

        photo_svc = PhotoService(self.db)

        try:
            # 1. 标记为生成中
            batch.status = "generating"
            await self.db.commit()

            # 2. 获取模板指令（指定模板优先；未指定且批次带账号类型时，自动解析该类型预设模板）
            template_instructions = ""
            if template_ids:
                from app.articles.template_service import get_template_instructions
                template_instructions = await get_template_instructions(template_ids, self.db)
            elif batch.account_type:
                from app.articles.template_service import TemplateService
                ts = TemplateService(self.db)
                account_template_ids = await ts.resolve_account_template_ids(batch.account_type)
                if account_template_ids:
                    from app.articles.template_service import get_template_instructions as _gti
                    template_instructions = await _gti(account_template_ids, self.db)
                    logger.info(
                        "article_account_templates_resolved",
                        batch_id=batch_id,
                        account_type=batch.account_type,
                        template_ids=account_template_ids,
                    )

            # 3. 获取照片描述（照片库模式 vs 手动上传模式）
            photo_descriptions = ""
            photo_object_names: list = []

            if photo_ids:
                library_photos = await photo_svc.get_batch_photos(batch_id)
                if library_photos:
                    desc_parts = []
                    for i, p in enumerate(library_photos):
                        photo_object_names.append(p.object_name)
                        tag_str = ", ".join(p.tags) if p.tags else ""
                        desc_text = p.description or ""
                        if not desc_text and tag_str:
                            desc_text = f"标签：{tag_str}"
                        elif not desc_text:
                            desc_text = f"文件名：{p.filename}"
                        desc_parts.append(f"【照片 {i + 1}：{p.filename} | 标签：{tag_str}】\n{desc_text}")
                    photo_descriptions = "\n\n---\n\n".join(desc_parts)
                    batch.photo_object_names = photo_object_names
                    batch.photo_descriptions = photo_descriptions
                    batch.photo_count = len(photo_object_names)
                    await self.db.commit()
                    logger.info("article_using_photo_library", batch_id=batch_id, count=len(library_photos))
            elif batch.photo_object_names:
                photo_object_names = batch.photo_object_names
                photo_descriptions = await analyze_photos(
                    batch.photo_object_names, batch.topic
                )
                batch.photo_descriptions = photo_descriptions
                await self.db.commit()

            # 4. 生成文章（断点续传：跳过已生成的篇数）
            skip = batch.generated_count
            if skip > 0:
                logger.info("article_resume_generation", batch_id=batch_id, skip=skip, total=batch.article_count)

            articles = await generate_batch(
                topic=batch.topic,
                photo_descriptions=photo_descriptions,
                article_count=batch.article_count,
                skip_count=skip,
                angle_keys=batch.selected_angle_keys,
                photo_object_names=photo_object_names,
                template_instructions=template_instructions,
                min_words=min_words,
                max_words=max_words,
                account_type=batch.account_type,
            )

            # 5. 逐篇写入数据库（内存安全，追加模式）
            for i, art in enumerate(articles):
                article = Article(
                    batch_id=batch_id,
                    title=art["title"],
                    content=art["content"],
                    word_count=art["word_count"],
                    angle=art["angle"],
                    account_type=art.get("account_type") or batch.account_type,
                    image_placement=art.get("image_placement"),
                    status="draft",
                    user_id=batch.user_id,
                )
                self.db.add(article)
                batch.generated_count = skip + i + 1
                await self.db.commit()

            # 6. 质量评估
            evaluation = await evaluate_articles(
                [{
                    "title": art["title"],
                    "content": art["content"],
                    "word_count": art["word_count"],
                    "angle": art["angle"],
                } for art in articles],
                min_words=min_words,
                max_words=max_words,
            )

            if evaluation["passed"]:
                batch.status = "completed"
                batch.error_message = None
                logger.info("article_generation_done", batch_id=batch_id, count=len(articles), eval="passed")
            else:
                issues_text = "; ".join(evaluation["issues"])
                batch.status = "completed"
                batch.error_message = f"[评估警告] {issues_text}"
                logger.warning("article_evaluate_warnings", batch_id=batch_id, issues=evaluation["issues"])

            await self.db.commit()

            # 7. 若为照片库模式，标记照片已使用
            if photo_ids:
                await photo_svc.mark_batch_photos_used(batch_id)

        except Exception as exc:
            logger.error("article_generation_failed", batch_id=batch_id, error=str(exc))
            await self.update_batch_status(batch_id, "failed", str(exc))
            await self.db.refresh(batch)

    # ============================================================
    # Article CRUD
    # ============================================================

    async def list_articles(
        self, batch_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[Article], int]:
        base = select(Article).where(Article.batch_id == batch_id)
        count_q = select(func.count(Article.id)).where(Article.batch_id == batch_id)
        base = base.order_by(Article.id.asc()).offset((page - 1) * page_size).limit(page_size)

        total = (await self.db.execute(count_q)).scalar() or 0
        rows = (await self.db.execute(base)).scalars().all()
        return list(rows), total

    async def get_article(self, article_id: int) -> Article | None:
        return await self.db.get(Article, article_id)

    async def update_article(self, article_id: int, title: str | None, content: str | None) -> Article | None:
        article = await self.get_article(article_id)
        if not article:
            return None
        if title is not None:
            article.title = title
        if content is not None:
            article.content = content
            article.word_count = len(content)
        await self.db.commit()
        await self.db.refresh(article)
        return article

    async def delete_article(self, article_id: int) -> bool:
        article = await self.get_article(article_id)
        if not article:
            return False
        await self.db.delete(article)
        await self.db.commit()
        return True

    async def regenerate_article(self, article_id: int) -> Article | None:
        """重生成单篇文章"""
        article = await self.get_article(article_id)
        if not article:
            return None
        batch = await self.get_batch(article.batch_id)
        if not batch:
            return None

        from app.articles.generator import DEFAULT_ANGLES, generate_single_article
        from app.retrieval.fusion import hybrid_retrieve

        # 找到对应角度
        angle = next((a for a in DEFAULT_ANGLES if a["key"] == article.angle), DEFAULT_ANGLES[0])
        retrieved = await hybrid_retrieve(angle.get("retrieval_query", angle["label"]), top_k=8)

        # 账号类型的固定模板指令（与批量生成保持一致）
        template_instructions = ""
        if batch.account_type:
            from app.articles.template_service import TemplateService, get_template_instructions
            ts = TemplateService(self.db)
            account_template_ids = await ts.resolve_account_template_ids(batch.account_type)
            if account_template_ids:
                template_instructions = await get_template_instructions(account_template_ids, self.db)

        result = await generate_single_article(
            topic=batch.topic,
            angle=angle,
            retrieved_context=retrieved,
            photo_descriptions=batch.photo_descriptions or "",
            photo_object_names=batch.photo_object_names or [],
            template_instructions=template_instructions,
            account_type=batch.account_type,
        )

        article.title = result["title"]
        article.content = result["content"]
        article.word_count = result["word_count"]
        article.account_type = result.get("account_type") or batch.account_type
        article.image_placement = result.get("image_placement")
        await self.db.commit()
        await self.db.refresh(article)
        return article

    # ============================================================
    # Platform Account — 账号管理
    # ============================================================

    async def create_account(self, platform_id: str, account_name: str, account_group: str = "", ws_token: str = "", credentials: str | None = None, credentials_type: str = "token", user_id: int = 0) -> PlatformAccount:
        from app.articles.crypto import encrypt_credentials
        account = PlatformAccount(
            platform_id=platform_id,
            account_name=account_name,
            account_group=account_group or None,
            ws_token=encrypt_credentials(ws_token) if ws_token else None,
            credentials=encrypt_credentials(credentials) if credentials else None,
            credentials_type=credentials_type,
            user_id=user_id,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        logger.info("platform_account_created", account_id=account.id, platform=platform_id, name=account_name, group=account_group)
        return account

    async def list_accounts(self, user_id: int | None, platform_id: str | None = None) -> list[PlatformAccount]:
        base = select(PlatformAccount)
        if user_id is not None:
            base = base.where(PlatformAccount.user_id == user_id)
        if platform_id:
            base = base.where(PlatformAccount.platform_id == platform_id)
        base = base.order_by(PlatformAccount.id.desc())
        result = await self.db.execute(base)
        return list(result.scalars().all())

    async def get_account(self, account_id: int) -> PlatformAccount | None:
        return await self.db.get(PlatformAccount, account_id)

    async def update_account(self, account_id: int, account_name: str | None = None, account_group: str | None = None, ws_token: str | None = None, credentials: str | None = None, credentials_type: str | None = None) -> PlatformAccount | None:
        account = await self.get_account(account_id)
        if not account:
            return None
        if account_name is not None:
            account.account_name = account_name
        if account_group is not None:
            account.account_group = account_group
        if ws_token is not None and ws_token != "":
            from app.articles.crypto import encrypt_credentials
            account.ws_token = encrypt_credentials(ws_token)
        if credentials is not None and credentials != "":
            from app.articles.crypto import encrypt_credentials
            account.credentials = encrypt_credentials(credentials)
        if credentials_type is not None:
            account.credentials_type = credentials_type
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def delete_account(self, account_id: int) -> bool:
        account = await self.get_account(account_id)
        if not account:
            return False
        await self.db.delete(account)
        await self.db.commit()
        logger.info("platform_account_deleted", account_id=account_id)
        return True

    async def verify_account(self, account_id: int) -> dict:
        """验证账号连接 — 测试凭证是否有效"""
        account = await self.get_account(account_id)
        if not account:
            return {"success": False, "message": "账号不存在"}

        from app.articles.crypto import decrypt_credentials

        try:
            if account.credentials_type == "token":
                pass
            elif account.credentials:
                creds = json.loads(decrypt_credentials(account.credentials))
            else:
                creds = {}

            if account.credentials_type == "token":
                async with httpx.AsyncClient(timeout=10.0) as client:
                    try:
                        resp = await client.get(f"{settings.publisher_bridge_url}/health")
                        if resp.status_code == 200 and resp.json().get("ok"):
                            account.last_verified_at = datetime.now()
                            account.error_message = None
                            account.status = "active"
                            await self.db.commit()
                            logger.info("account_verify_success", account_id=account_id, method="bridge")
                            return {"success": True, "message": "桥接器连接正常"}
                        else:
                            return {"success": False, "message": "桥接器未就绪"}
                    except httpx.ConnectError:
                        return {"success": False, "message": "桥接器未启动(3010不可达)"}

            elif account.platform_id == "wechat_mp" and account.credentials_type == "appid_secret":
                appid = creds.get("appid", "")
                secret = creds.get("appsecret", "")
                if not appid or not secret:
                    return {"success": False, "message": "凭证不完整：缺少 appid 或 appsecret"}

                url = "https://api.weixin.qq.com/cgi-bin/token"
                params = {"grant_type": "client_credential", "appid": appid, "secret": secret}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url, params=params)
                    data = resp.json()
                    if "access_token" in data:
                        account.last_verified_at = datetime.now()
                        account.error_message = None
                        account.status = "active"
                        await self.db.commit()
                        logger.info("account_verify_success", account_id=account_id)
                        return {"success": True, "message": "验证成功"}
                    else:
                        err = data.get("errmsg", str(data))
                        account.error_message = err
                        account.status = "error"
                        await self.db.commit()
                        return {"success": False, "message": f"微信返回错误: {err}"}

            elif account.credentials_type in ("cookie_token", "custom"):
                if settings.wechatsync_cli_path:
                    account.last_verified_at = datetime.now()
                    account.error_message = None
                    account.status = "active"
                    await self.db.commit()
                    return {"success": True, "message": "凭证已保存（wechatsync CLI 模式：请在实际发布时验证）"}
                else:
                    return {"success": False, "message": "wechatsync CLI 未配置"}

            else:
                return {"success": False, "message": f"不支持的凭证类型: {account.credentials_type}"}

        except Exception as exc:
            account.error_message = str(exc)
            account.status = "error"
            await self.db.commit()
            return {"success": False, "message": str(exc)}

    # ============================================================
    # Publishing
    # ============================================================

    async def publish_articles(
        self,
        batch_id: int,
        platform_ids: list[str],
        article_ids: list[int] | None = None,
        account_id: int | None = None,
        scheduled_at: datetime | None = None,
    ) -> list[PublishingRecord]:
        """发布文章到指定平台（异步队列模式）

        仅创建 pending 记录并立即返回，由 30 秒调度器
        （app/articles/schedule.py）接管实际发布，避免长耗时发布阻塞请求。
        同一 (article_id, platform, account_id) 已有 pending 记录时跳过，防止重复发布。
        """
        if article_ids is None:
            articles, _ = await self.list_articles(batch_id, page=1, page_size=100)
            article_ids = [a.id for a in articles]

        if account_id:
            account = await self.get_account(account_id)
            if not account:
                raise ValueError(f"账号 {account_id} 不存在")

        existing = await self.db.execute(
            select(PublishingRecord.article_id, PublishingRecord.platform).where(
                PublishingRecord.status == "pending",
                PublishingRecord.article_id.in_(article_ids),
                PublishingRecord.platform.in_(platform_ids),
            )
        )
        pending_pairs = {(row.article_id, row.platform) for row in existing.all()}

        records: list[PublishingRecord] = []
        for aid in article_ids:
            article = await self.get_article(aid)
            if not article:
                continue

            for pid in platform_ids:
                pinfo = PLATFORMS.get(pid)
                if not pinfo:
                    continue
                if (aid, pid) in pending_pairs:
                    logger.info("publish_skip_duplicate_pending", article_id=aid, platform=pid)
                    continue

                record = PublishingRecord(
                    article_id=aid,
                    platform=pid,
                    platform_name=pinfo["name"],
                    account_id=account_id,
                    status="pending",
                    scheduled_at=scheduled_at,
                )
                self.db.add(record)
                await self.db.commit()
                await self.db.refresh(record)
                pending_pairs.add((aid, pid))
                records.append(record)

        return records

    async def get_publishing_records(self, article_id: int) -> list[PublishingRecord]:
        result = await self.db.execute(
            select(PublishingRecord)
            .where(PublishingRecord.article_id == article_id)
            .order_by(PublishingRecord.id.desc())
        )
        return list(result.scalars().all())

    async def get_batch_publishing_records(self, batch_id: int) -> list[PublishingRecord]:
        """查询批次内全部文章的发布记录（每篇文章保留最新一条/平台）"""
        articles, _ = await self.list_articles(batch_id, page=1, page_size=100)
        article_ids = [a.id for a in articles]
        if not article_ids:
            return []
        result = await self.db.execute(
            select(PublishingRecord)
            .where(PublishingRecord.article_id.in_(article_ids))
            .order_by(PublishingRecord.id.desc())
        )
        return list(result.scalars().all())

    async def get_publishing_stats(self) -> dict:
        """获取发布仪表板统计数据"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total_published = (await self.db.execute(
            select(func.count(PublishingRecord.id)).where(PublishingRecord.status == "published")
        )).scalar() or 0

        total_failed = (await self.db.execute(
            select(func.count(PublishingRecord.id)).where(PublishingRecord.status == "failed")
        )).scalar() or 0

        total_pending = (await self.db.execute(
            select(func.count(PublishingRecord.id)).where(PublishingRecord.status == "pending")
        )).scalar() or 0

        today_published = (await self.db.execute(
            select(func.count(PublishingRecord.id)).where(
                PublishingRecord.status == "published",
                PublishingRecord.published_at >= today_start,
            )
        )).scalar() or 0

        today_failed = (await self.db.execute(
            select(func.count(PublishingRecord.id)).where(
                PublishingRecord.status == "failed",
                PublishingRecord.created_at >= today_start,
            )
        )).scalar() or 0

        by_platform_rows = (await self.db.execute(
            select(PublishingRecord.platform, func.count(PublishingRecord.id))
            .where(PublishingRecord.status == "published")
            .group_by(PublishingRecord.platform)
        )).all()

        by_platform = [
            {"platform": row[0], "count": row[1]}
            for row in by_platform_rows
        ]

        recent_result = await self.db.execute(
            select(PublishingRecord)
            .order_by(PublishingRecord.id.desc())
            .limit(20)
        )
        recent = list(recent_result.scalars().all())

        return {
            "total_published": total_published,
            "total_failed": total_failed,
            "total_pending": total_pending,
            "today_published": today_published,
            "today_failed": today_failed,
            "by_platform": by_platform,
            "recent_records": recent,
        }

    # ============================================================
    # Export
    # ============================================================

    async def export_article(self, article_id: int, fmt: str = "md") -> tuple[bytes, str, str]:
        """导出单篇文章，返回 (content_bytes, filename, content_type)"""
        article = await self.get_article(article_id)
        if not article:
            raise ValueError(f"文章 {article_id} 不存在")

        placements = article.image_placement if isinstance(article.image_placement, list) else []
        title, content = article.title, article.content

        # 渲染为 CPU 密集同步操作，放入线程池避免阻塞事件循环
        data = await asyncio.to_thread(_render_article, title, content, placements, fmt)

        if fmt == "docx":
            filename = f"{title}.docx"
            ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif fmt == "html":
            filename = f"{title}.html"
            ct = "text/html; charset=utf-8"
        else:
            filename = f"{title}.md"
            ct = "text/markdown; charset=utf-8"
        return data, filename, ct

    async def export_batch_zip(self, batch_id: int) -> bytes:
        """批量导出整个批次的文章为 ZIP（含照片文件夹）"""
        articles, _ = await self.list_articles(batch_id, page=1, page_size=100)
        batch = await self.get_batch(batch_id)

        items = [
            (
                a.title,
                a.content,
                a.image_placement if isinstance(a.image_placement, list) else [],
            )
            for a in articles
        ]
        raw_names = batch.photo_object_names if batch and batch.photo_object_names else []
        photo_names = list(dict.fromkeys(raw_names))

        # zip 打包 + MinIO 下载为同步阻塞操作，放入线程池避免阻塞事件循环
        return await asyncio.to_thread(_build_batch_zip, items, photo_names)


# ============================================================
# 导出 — 同步阻塞辅助函数（由 asyncio.to_thread 调用）
# ============================================================

def _render_article(title: str, content: str, placements: list, fmt: str) -> bytes:
    """渲染单篇文章为 MD / HTML / DOCX 字节流（CPU 密集）"""
    if fmt == "docx":
        return export_docx(title, content, placements)
    if fmt == "html":
        return export_html(title, content, placements)
    return export_markdown(title, content, placements)


def _build_batch_zip(items: list[tuple[str, str, list]], photo_names: list[str]) -> bytes:
    """打包批次文章为 ZIP（含照片文件夹）。items: [(title, content, placements), ...]"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for title, content, placements in items:
            safe_title = title.replace("/", "_").replace("\\", "_")[:100]
            zf.writestr(f"{safe_title}.md", export_markdown(title, content, placements))
            zf.writestr(f"{safe_title}.docx", export_docx(title, content, placements))

        for obj_name in photo_names:
            try:
                client = get_minio_client()
                response = client.get_object(_PHOTO_BUCKET, obj_name)
                img_data = response.read()
                response.close()
                response.release_conn()
                local_name = obj_name.split("/")[-1]
                zf.writestr(f"photos/{local_name}", img_data)
            except Exception as exc:
                logger.warning("zip_photo_bundle_failed", object_name=obj_name, error=str(exc))

    buf.seek(0)
    return buf.getvalue()


# ============================================================
# SSE 事件构造（供路由层使用）
# ============================================================

def sse_event(event_type: str, batch_id: int, message: str, data: dict | None = None) -> str:
    """构造一条 SSE 事件字符串"""
    payload = json.dumps({
        "type": event_type,
        "batch_id": batch_id,
        "message": message,
        "data": data,
    }, ensure_ascii=False)
    return f"data: {payload}\n\n"
