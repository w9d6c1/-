"""AI 写作 — 自然语言意图分析 + 参数推荐"""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.llm import call_llm_with_retry, create_llm
from app.articles.template_service import TemplateService
from app.core.config import settings
from app.core.dependencies import DbDep, require_auth
from app.core.logging import logger
from app.models.user import User
from app.articles.models import WritingTemplate

router = APIRouter(tags=["admin-ai-write"])


class AnalyzeRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000, description="用户自然语言写作意图描述")


class SuggestedTemplate(BaseModel):
    id: int
    name: str
    type: str


class AnalyzeResponse(BaseModel):
    topic: str = Field(..., description="提取的写作主题")
    suggested_template_ids: list[int] = Field(default_factory=list)
    word_count_min: int = Field(default=1200)
    word_count_max: int = Field(default=2000)
    recommended_photo_count: int = Field(default=3)
    photo_search_keywords: list[str] = Field(default_factory=list)


async def _load_templates(db) -> list[WritingTemplate]:
    from sqlalchemy import select
    q = select(WritingTemplate)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_intent(body: AnalyzeRequest, db: DbDep, _user=Depends(require_auth)):
    templates = await _load_templates(db)
    templates_text = "\n".join(
        f"- id={t.id}, name={t.name}, type={t.type}, instruction={t.prompt_instruction[:200]}"
        for t in templates
    )

    prompt = f"""你是写作规划助手。根据用户的写作意图，推荐合适的模板和参数。

可用模板列表：
{templates_text}

用户写作意图：{body.description}

请返回 JSON（不要代码块标记）：
{{
    "topic": "清晰的文章主题",
    "suggested_template_ids": [1, 5],
    "word_count_min": 1200,
    "word_count_max": 2000,
    "recommended_photo_count": 3,
    "photo_search_keywords": ["关键词1", "关键词2"]
}}

规则：
- topic: 从用户意图中提炼出简洁的写作主题
- suggested_template_ids: 选择 1-2 个最合适的模板 ID（1 个 structure + 1 个 style）
- word_count_min/max: 建议字数范围，技术类 1200-2000，教程类 1500-2500，故事类 800-1500
- recommended_photo_count: 建议配图数，1-20
- photo_search_keywords: 3-5 个中英文标签关键词，用于在照片库中搜索相关照片"""

    llm = create_llm(temperature=0.2, max_tokens=512, top_p=0.85)
    raw = await call_llm_with_retry(llm, [{"role": "user", "content": prompt}], max_retries=2)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("ai_write_parse_failed", raw=raw[:200])
        return AnalyzeResponse(
            topic=body.description[:100],
            word_count_min=1200,
            word_count_max=2000,
            recommended_photo_count=3,
            photo_search_keywords=[],
        )

    return AnalyzeResponse(
        topic=data.get("topic", body.description[:100]),
        suggested_template_ids=data.get("suggested_template_ids", []),
        word_count_min=data.get("word_count_min", 1200),
        word_count_max=data.get("word_count_max", 2000),
        recommended_photo_count=max(1, min(20, data.get("recommended_photo_count", 3))),
        photo_search_keywords=data.get("photo_search_keywords", []),
    )
