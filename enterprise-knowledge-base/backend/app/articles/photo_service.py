"""照片库业务层 — 上传 / AI 标签 / 智能匹配 / CRUD

职责：
- 照片入库（MinIO 存储 + Vision API 自动生成标签和描述）
- 根据主题 LLM 智能匹配照片（标签匹配 + 防重复窗口）
- 照片库 CRUD
"""

import asyncio
import base64
import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import call_llm_with_retry, create_llm
from app.articles.models import BatchPhoto, Photo
from app.core.config import settings
from app.core.logging import logger
from app.core.minio_client import get_minio_client, upload_file

_PHOTO_BUCKET = "knowledge-docs"
_PHOTO_PREFIX = "photo-library/"

_TAG_PROMPT = """你是一位建筑防潮防水领域的内容分类专家。请如实分析这张照片，返回 JSON 格式结果（只返回 JSON，不要其他文字）：

{
  "tags": ["标签1", "标签2", "标签3"],
  "description": "照片内容的如实描述（100-200字）"
}

标签规则（硬性）：
- 2-6 个标签，每个必须是 2-8 字的简短关键词（名词或短词），如"地下室""电渗透""电极""注浆"
- 严禁输出长句、标语、广告语、品牌口号、宣传语或把照片中整段文字抄作标签（例如"XX要打造好房子"这类必须忽略，仅从中提取主题词如"室内""环境场景"）
- 标签只能从以下分类中挑选，每个分类最多 1 个标签：
  场景类型：地下室/外墙/地面/屋顶/室内/材料堆放/设备间/其他
  工艺：电渗透/注浆/卷材防水/涂料防水/堵漏/剔凿/养护/其他
  视角：施工细节/设备全貌/前后对比/环境场景/人物操作
  材料设备：电极/主机/注浆机/防水卷材/涂料桶/工具/其他
- 若某分类画面中不可见，则不要给出该分类标签
- 单个标签超过 8 字即视为违规，不得输出

描述要求：
- 只描述画面中确实可见的内容：场景、材料、设备、工艺动作
- 看不清或无法确定的内容一律不写，必要时写"无法确认"
- 严禁推测、脑补、编造设备型号、工艺名称或具体操作
- 不要评价照片质量"""


class PhotoService:
    """照片库服务"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ============================================================
    # Upload — 上传 + AI 打标签
    # ============================================================

    async def upload_photo(
        self, filename: str, data: bytes, content_type: str, user_id: int
    ) -> dict:
        """上传照片到 MinIO → Vision API 分析 → 返回 AI 标签 + 描述。

        照片先写入数据库（获得 ID），再存 MinIO（路径含 ID）。
        """
        photo = Photo(
            object_name="",
            filename=filename,
            tags=[],
            description=None,
            file_size=len(data),
            content_type=content_type,
            user_id=user_id,
        )
        self.db.add(photo)
        await self.db.commit()
        await self.db.refresh(photo)

        object_name = f"{_PHOTO_PREFIX}{photo.id}/{filename}"
        upload_file(_PHOTO_BUCKET, object_name, data, content_type)
        photo.object_name = object_name

        tags, description = await self._analyze_photo(data, filename)
        photo.tags = tags
        photo.description = description
        await self.db.commit()
        await self.db.refresh(photo)

        logger.info("photo_library_uploaded", photo_id=photo.id, tags=tags)
        return {
            "photo_id": photo.id,
            "object_name": object_name,
            "tags": tags,
            "description": description,
            "tagged": bool(tags),
            "warning": None if tags else "AI 打标失败（视觉接口异常），可稍后重试或手动添加标签",
        }

    # ============================================================
    # AI 标签生成
    # ============================================================

    async def suggest_tags(self, photo_id: int) -> list[str]:
        """重新为已有照片生成 AI 标签建议。

        分析失败（tags 为空且 description 为失败占位）时保留原标签与描述，
        避免视觉接口故障期间把已标好的标签清空。
        """
        photo = await self.db.get(Photo, photo_id)
        if not photo:
            raise ValueError(f"照片 {photo_id} 不存在")

        client = get_minio_client()
        response = client.get_object(_PHOTO_BUCKET, photo.object_name)
        data = response.read()
        response.close()
        response.release_conn()

        tags, description = await self._analyze_photo(data, photo.filename)
        if not tags and (not description or description == photo.filename):
            logger.warning("photo_suggest_skipped", photo_id=photo_id, reason="analysis_failed")
            return photo.tags or []

        photo.tags = tags
        photo.description = description
        await self.db.commit()

        return tags

    async def _analyze_photo(self, data: bytes, filename: str) -> tuple[list[str], str]:
        """调用 Vision API 分析照片，返回 (tags, description)。

        未配置 Vision API key 时返回空标签和文件名作为描述。
        对限流/临时错误做指数退避重试（最多 3 次），仍失败返回空标签并记 warning。
        """
        from app.articles.vision import get_vision_provider

        provider = get_vision_provider()
        if provider is None:
            logger.warning("photo_analyze_skipped", reason="no_vision_api_key")
            return [], filename

        img_b64 = base64.b64encode(data).decode()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                raw = await provider.analyze(img_b64, _TAG_PROMPT)

                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                result = json.loads(raw)
                tags = self._sanitize_tags(result.get("tags", []))
                description = result.get("description", "")
                return tags, description
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "photo_analyze_attempt_failed",
                    filename=filename,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
        del img_b64

        logger.warning("photo_analyze_failed", filename=filename, error=str(last_error))
        return [], filename

    @staticmethod
    def _sanitize_tags(raw_tags: list) -> list[str]:
        """清洗 AI 生成的标签：只保留 2-8 字的简短关键词，去空白、去重、上限 6 个。

        丢弃过长（>=9 字，如标语/长句/整段文字）及非法值，防止脏标签入库。
        """
        seen: set[str] = set()
        cleaned: list[str] = []
        for t in raw_tags:
            if not isinstance(t, str):
                continue
            tag = t.strip()
            if not (2 <= len(tag) <= 8):
                continue
            if tag in seen:
                continue
            seen.add(tag)
            cleaned.append(tag)
            if len(cleaned) >= 6:
                break
        return cleaned

    # ============================================================
    # 智能匹配 — LLM 根据主题匹配标签
    # ============================================================

    async def match_photos(
        self, topic: str, count: int = 5, exclude_days: int = 30
    ) -> list[dict]:
        """根据文章主题从照片库匹配最相关的照片。

        策略：LLM 提取主题关键词 → SQL 标签 LIKE 匹配 → 排除窗口期内已用
        """
        window_start = datetime.now() - timedelta(days=exclude_days)
        used_subq = select(BatchPhoto.photo_id).where(
            BatchPhoto.used_at >= window_start
        )

        all_photos = (
            (await self.db.execute(
                select(Photo).where(
                    Photo.id.not_in(used_subq),
                    Photo.tags.isnot(None),
                    func.json_length(Photo.tags) > 0,
                ).order_by(Photo.id.desc())
            ))
            .scalars()
            .all()
        )

        if not all_photos:
            logger.info("photo_match_no_photos", topic=topic)
            return []

        photo_map = self._build_photo_index(all_photos)

        matches = await self._llm_match(topic, photo_map, count)

        result = []
        for match in matches[:count]:
            pid = match["photo_id"]
            if pid in photo_map:
                p = photo_map[pid]
                result.append({
                    "photo_id": pid,
                    "object_name": p.object_name,
                    "filename": p.filename,
                    "tags": p.tags,
                    "description": p.description,
                    "confidence": match.get("confidence", 0.5),
                    "reason": match.get("reason", ""),
                })

        logger.info("photo_match_done", topic=topic, matched=len(result))
        return result

    @staticmethod
    def _build_photo_index(photos: list[Photo]) -> dict[int, Photo]:
        """构建照片索引，返回 {photo_id: Photo}"""
        return {p.id: p for p in photos}

    # ============================================================
    # 权重匹配 — LLM 语义分 + 规则权重（标签命中/新鲜度/防复用）
    # ============================================================

    async def match_photos_weighted(
        self,
        topic: str,
        template_instruction: str = "",
        count: int = 5,
        exclude_days: int | None = None,
    ) -> list[dict]:
        """结合主题与写作模板指令，按权重评分匹配照片。

        权重组成（系数来自 settings.photo_match_weights）：
        - tag_keyword: 主题/模板关键词在照片标签中的命中覆盖度
        - semantic:    LLM 对(主题+模板)相关度的语义评分
        - freshness:   照片越新分越高
        - anti_reuse:  近期未使用/从未使用分越高
        LLM 不可用时降级为纯规则评分。
        """
        exclude_days = exclude_days or settings.photo_reuse_window_days
        weights = settings.photo_match_weights
        now = datetime.now()

        window_start = now - timedelta(days=exclude_days)
        used_subq = select(BatchPhoto.photo_id).where(
            BatchPhoto.used_at >= window_start
        )
        # 注意：不用 func.json_length 过滤，保证 SQLite(测试) 与 MySQL 均可执行；
        # 空标签照片在 Python 侧过滤。
        all_photos = (
            (await self.db.execute(
                select(Photo).where(
                    Photo.id.not_in(used_subq),
                    Photo.tags.isnot(None),
                ).order_by(Photo.id.desc())
            ))
            .scalars()
            .all()
        )
        all_photos = [p for p in all_photos if p.tags]

        if not all_photos:
            logger.info("photo_weighted_match_no_photos", topic=topic)
            return []

        photo_map = self._build_photo_index(all_photos)

        # 1. LLM 提取关键词（用于标签命中度）
        keywords = await self._llm_extract_keywords(topic, template_instruction)
        # 2. LLM 语义评分（主题+模板）
        semantic_scores = await self._llm_semantic_scores(
            topic, template_instruction, photo_map
        )

        # 3. 规则评分 + 加权合并
        last_use_map = await self._last_use_map(photo_map)
        scored: list[dict] = []
        for pid, p in photo_map.items():
            tag_score = self._tag_keyword_score(keywords, p.tags)
            sem_score = semantic_scores.get(pid, tag_score)
            fresh_score = self._freshness_score(p.created_at, now)
            reuse_score = self._anti_reuse_score(last_use_map.get(pid), exclude_days)

            total = (
                weights.get("tag_keyword", 0.4) * tag_score
                + weights.get("semantic", 0.3) * sem_score
                + weights.get("freshness", 0.2) * fresh_score
                + weights.get("anti_reuse", 0.1) * reuse_score
            )
            reason = (
                semantic_scores.get("__reason__", {}).get(pid, "")
                or f"标签命中 {round(tag_score * 100)}%"
            )
            scored.append({
                "photo_id": pid,
                "object_name": p.object_name,
                "filename": p.filename,
                "tags": p.tags,
                "description": p.description,
                "confidence": round(min(total, 1.0), 4),
                "reason": reason,
                "weights": {
                    "tag_keyword": round(tag_score, 4),
                    "semantic": round(sem_score, 4),
                    "freshness": round(fresh_score, 4),
                    "anti_reuse": round(reuse_score, 4),
                },
            })

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        logger.info(
            "photo_weighted_match_done",
            topic=topic,
            matched=min(len(scored), count),
            keywords=len(keywords),
        )
        return scored[:count]

    @staticmethod
    async def _llm_extract_keywords(topic: str, template_instruction: str) -> list[str]:
        """从主题+模板指令提取照片匹配关键词（失败返回空列表）。"""
        if not topic:
            return []
        prompt = (
            f'文章主题: "{topic}"\n'
            f"写作模板要求:\n{template_instruction or '（无）'}\n\n"
            "从中提取 6-10 个用于匹配施工现场/产品照片的中文关键词（场景、工艺、材料、设备等）。\n"
            '只返回 JSON 字符串数组，不要其他文字，例如 ["地下室","电渗透","电极","注浆"]。'
        )
        try:
            llm = create_llm(temperature=0.1, max_tokens=512, top_p=0.85)
            raw = await call_llm_with_retry(
                llm, [{"role": "user", "content": prompt}], max_retries=1
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)
            return [str(k).strip() for k in parsed if str(k).strip()][:12]
        except Exception as exc:
            logger.warning("photo_keywords_failed", topic=topic, error=str(exc))
            return []

    @staticmethod
    async def _llm_semantic_scores(
        topic: str, template_instruction: str, photo_map: dict[int, Photo]
    ) -> dict:
        """LLM 按(主题+模板)对每张候选照片做语义相关度评分，返回 {photo_id: 0-1}。

        失败时返回空字典，调用方回退到标签命中分。额外返回 "__reason__" 键存一句话理由。
        """
        if not photo_map:
            return {}
        photo_lines = []
        for pid, p in photo_map.items():
            tags_str = ", ".join(p.tags) if p.tags else "无标签"
            desc_short = (p.description or "")[:120]
            photo_lines.append(f"ID={pid} | 标签: {tags_str} | 描述: {desc_short}")
        prompt = (
            f'文章主题: "{topic}"\n'
            f"写作模板要求:\n{template_instruction or '（无）'}\n\n"
            f"候选照片：\n" + "\n".join(photo_lines) + "\n\n"
            "请评估每张照片与本篇文章（主题+模板要求）的契合程度，输出 JSON 数组：\n"
            '[{"photo_id": 数字, "semantic_score": 0.0-1.0, "reason": "一句话（12字内）"}, ...]\n'
            "评分规则：与主题明显无关的照片给 0.2 以下，不要勉强凑数；"
            "仅当照片确实贴合主题+模板要求时才给 0.5 以上。\n"
            "只返回 JSON，不要其他文字。"
        )
        try:
            llm = create_llm(temperature=0.1, max_tokens=2048, top_p=0.85)
            raw = await call_llm_with_retry(
                llm, [{"role": "user", "content": prompt}], max_retries=1
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)
            scores: dict = {}
            reasons: dict = {}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                pid = int(item.get("photo_id") or 0)
                if pid in photo_map:
                    s = float(item.get("semantic_score") or 0.0)
                    scores[pid] = max(0.0, min(1.0, s))
                    reasons[pid] = str(item.get("reason", ""))
            if reasons:
                scores["__reason__"] = reasons
            return scores
        except Exception as exc:
            logger.warning("photo_semantic_scores_failed", topic=topic, error=str(exc))
            return {}

    @staticmethod
    def _tag_keyword_score(keywords: list[str], tags: list[str]) -> float:
        """关键词在照片标签中的覆盖度：命中关键词数 / 关键词数。"""
        if not keywords:
            return 0.5
        hit = sum(1 for kw in keywords if any(kw in t or t in kw for t in (tags or [])))
        return round(hit / len(keywords), 4)

    @staticmethod
    def _freshness_score(created_at: datetime | None, now: datetime) -> float:
        """照片新鲜度：越新越高，180 天内线性衰减。"""
        if not created_at:
            return 0.5
        days = max(0, (now - created_at).days)
        return round(max(0.0, 1.0 - days / 180.0), 4)

    @staticmethod
    def _anti_reuse_score(last_used_at: datetime | None, exclude_days: int) -> float:
        """防复用分：从未使用=1.0；近期使用则线性恢复。"""
        if last_used_at is None:
            return 1.0
        days = max(0, (datetime.now() - last_used_at).days)
        return round(min(1.0, days / max(exclude_days, 1)), 4)

    async def _last_use_map(self, photo_map: dict[int, Photo]) -> dict[int, datetime | None]:
        """查询每张照片最近一次使用时间（BatchPhoto.used_at 最大）。"""
        ids = list(photo_map.keys())
        if not ids:
            return {}
        result = await self.db.execute(
            select(BatchPhoto.photo_id, func.max(BatchPhoto.used_at))
            .where(BatchPhoto.photo_id.in_(ids))
            .group_by(BatchPhoto.photo_id)
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def _llm_match(
        topic: str, photo_map: dict[int, Photo], count: int
    ) -> list[dict]:
        """调用 LLM 匹配照片（轻量模型即可）"""
        if not photo_map:
            return []

        photo_lines = []
        for pid, p in photo_map.items():
            tags_str = ", ".join(p.tags) if p.tags else "无标签"
            desc_short = (p.description or "")[:120]
            photo_lines.append(f"ID={pid} | 标签: {tags_str} | 描述: {desc_short}")
        photo_text = "\n".join(photo_lines)

        prompt = (
            f'文章主题: "{topic}"\n\n'
            f"从以下照片库中选择最相关的 {count} 张照片。按标签和描述与主题的相关度排序。\n\n"
            f"{photo_text}\n\n"
            f"返回 JSON 数组（只返回 JSON，不要其他文字）：\n"
            f'[{{"photo_id": 数字, "confidence": 0.0-1.0, "reason": "一句话（10字以内）"}}, ...]\n'
        )

        try:
            llm = create_llm(temperature=0.1, max_tokens=2048, top_p=0.85)
            raw = await call_llm_with_retry(
                llm, [{"role": "user", "content": prompt}], max_retries=1
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return json.loads(raw)
        except Exception as exc:
            logger.warning("photo_llm_match_failed", topic=topic, error=str(exc))
            first = list(photo_map.values())[:count]
            return [
                {
                    "photo_id": p.id,
                    "confidence": 0.3,
                    "reason": "标签匹配降级",
                }
                for p in first
            ]

    # ============================================================
    # Photo CRUD
    # ============================================================

    async def list_photos(
        self, user_id: int | None, page: int = 1, page_size: int = 20, tag: str | None = None
    ) -> tuple[list[Photo], int]:
        """照片列表（分页 + 标签筛选 + 按用户过滤）"""
        base = select(Photo)
        count_q = select(func.count(Photo.id))

        if user_id is not None:
            base = base.where(Photo.user_id == user_id)
            count_q = count_q.where(Photo.user_id == user_id)

        if tag:
            base = base.where(Photo.tags.isnot(None)).where(
                func.json_search(
                    func.cast(Photo.tags, func.json),
                    "one",
                    tag,
                ).isnot(None)
            )
            count_q = count_q.where(Photo.tags.isnot(None)).where(
                func.json_search(
                    func.cast(Photo.tags, func.json),
                    "one",
                    tag,
                ).isnot(None)
            )

        base = base.order_by(Photo.id.desc()).offset((page - 1) * page_size).limit(page_size)

        total = (await self.db.execute(count_q)).scalar() or 0
        rows = (await self.db.execute(base)).scalars().all()
        return list(rows), total

    async def get_photo(self, photo_id: int) -> Photo | None:
        return await self.db.get(Photo, photo_id)

    async def update_photo(self, photo_id: int, tags: list[str] | None) -> Photo | None:
        photo = await self.get_photo(photo_id)
        if not photo:
            return None
        if tags is not None:
            photo.tags = tags
        await self.db.commit()
        await self.db.refresh(photo)
        return photo

    async def delete_photo(self, photo_id: int) -> bool:
        photo = await self.get_photo(photo_id)
        if not photo:
            return False

        try:
            client = get_minio_client()
            client.remove_object(_PHOTO_BUCKET, photo.object_name)
        except Exception as exc:
            logger.warning("photo_minio_delete_failed", photo_id=photo_id, error=str(exc))

        await self.db.delete(photo)
        await self.db.commit()
        logger.info("photo_library_deleted", photo_id=photo_id)
        return True

    # ============================================================
    # Batch-Photo 关联
    # ============================================================

    async def select_photos_for_batch(self, batch_id: int, photo_ids: list[int]) -> list[BatchPhoto]:
        """将照片关联到批次，used_at 置为空（生成完成后再更新）"""
        records = []
        for pid in photo_ids:
            bp = BatchPhoto(batch_id=batch_id, photo_id=pid)
            self.db.add(bp)
            records.append(bp)
        await self.db.commit()
        logger.info("batch_photo_selected", batch_id=batch_id, count=len(photo_ids))
        return records

    async def get_batch_photos(self, batch_id: int) -> list[Photo]:
        """获取批次关联的照片"""
        result = await self.db.execute(
            select(Photo)
            .join(BatchPhoto, BatchPhoto.photo_id == Photo.id)
            .where(BatchPhoto.batch_id == batch_id)
        )
        return list(result.scalars().all())

    async def mark_batch_photos_used(self, batch_id: int) -> None:
        """生成完成后标记批次照片为已使用"""
        result = await self.db.execute(
            select(BatchPhoto).where(BatchPhoto.batch_id == batch_id)
        )
        for bp in result.scalars().all():
            if bp.used_at is None:
                bp.used_at = datetime.now()
        await self.db.commit()
        logger.info("batch_photo_marked_used", batch_id=batch_id)
