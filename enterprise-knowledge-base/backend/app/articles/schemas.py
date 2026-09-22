"""文章批量生成 — Pydantic 请求/响应模型

参照: app/schemas/document.py
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse  # noqa: F401 — 供路由层复用


# ============================================================
# Batch — 批次
# ============================================================

class BatchCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500, description="文章主题/题目")
    article_count: int = Field(default=5, ge=1, le=10, description="目标文章数")
    account_type: str | None = Field(
        default=None,
        description="目标账号类型: user/designer/dealer，None=通用（使用默认角度+手动模板）",
    )
    angle_keys: list[str] | None = Field(
        default=None,
        description="选中的角度 keys，None=全选。可选值: technical_detail, case_study, benefit_analysis, comparison, maintenance_guide",
    )


class BatchResponse(BaseModel):
    id: int
    topic: str
    account_type: str | None = None
    photo_count: int
    article_count: int
    generated_count: int
    status: str
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchDetailResponse(BatchResponse):
    photo_object_names: list[str] | None = None
    photo_descriptions: str | None = None
    error_message: str | None = None


class BulkDeleteBatchesRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200, description="待删除批次 ID 列表")


# ============================================================
# Article — 文章
# ============================================================

class ArticleResponse(BaseModel):
    id: int
    batch_id: int
    title: str
    word_count: int
    angle: str
    account_type: str | None = None
    status: str
    review_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArticleDetailResponse(ArticleResponse):
    content: str
    image_placement: list | None = None
    user_id: int | None = None


class ArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = None


# ============================================================
# Publishing — 发布
# ============================================================

class PublishRequest(BaseModel):
    platform_ids: list[str] = Field(min_length=1, description="目标平台标识列表")
    article_ids: list[int] | None = Field(default=None, description="指定文章 ID，None=发布整个批次")
    account_id: int | None = Field(default=None, description="指定发布账号 ID（必选）")
    scheduled_at: datetime | None = Field(default=None, description="定时发布时间（None=立即发布）")


class PublishingRecordResponse(BaseModel):
    id: int
    article_id: int
    platform: str
    platform_name: str | None = None
    account_id: int | None = None
    status: str
    published_url: str | None = None
    remote_article_id: str | None = None
    error_message: str | None = None
    retry_count: int
    published_at: datetime | None = None
    scheduled_at: datetime | None = None
    stats: dict | None = None
    stats_updated_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Platform — 平台信息
# ============================================================

class PlatformInfo(BaseModel):
    platform: str
    name: str
    method: Literal["direct_api", "wechatsync", "export"]
    available: bool = True


# ============================================================
# Platform Account — 平台账号管理
# ============================================================

CREDENTIALS_TYPE = Literal["appid_secret", "cookie_token", "custom", "token"]


class PlatformAccountCreate(BaseModel):
    platform_id: str = Field(min_length=1, max_length=50, description="平台标识")
    account_name: str = Field(min_length=1, max_length=100, description="账号显示名称")
    account_group: str = Field(default="", description="账号组: 2113/2114/2119/9023")
    ws_token: str = Field(default="", description="Chrome 扩展 Token")
    credentials: str | None = Field(default=None, description="凭证明文(仅微信 direct_api)")
    credentials_type: CREDENTIALS_TYPE = Field(default="token")


class PlatformAccountUpdate(BaseModel):
    account_name: str | None = Field(default=None, min_length=1, max_length=100)
    account_group: str | None = Field(default=None, description="账号组")
    ws_token: str | None = Field(default=None, description="Chrome 扩展 Token（不传则不更新）")
    credentials: str | None = Field(default=None, description="凭证明文（不传则不更新）")
    credentials_type: CREDENTIALS_TYPE | None = None


class PlatformAccountResponse(BaseModel):
    id: int
    platform_id: str
    account_name: str
    account_group: str | None = None
    credentials_type: str
    status: str
    last_verified_at: datetime | None = None
    error_message: str | None = None
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformAccountDetailResponse(PlatformAccountResponse):
    credentials: str = Field(description="凭证明文 JSON 字符串")


class AccountVerifyResult(BaseModel):
    success: bool
    message: str
    account_id: int


# ============================================================
# Publishing Stats — 发布仪表板
# ============================================================

class PublishingStatsResponse(BaseModel):
    total_published: int = 0
    total_failed: int = 0
    total_pending: int = 0
    today_published: int = 0
    today_failed: int = 0
    by_platform: list[dict] = Field(default_factory=list)
    recent_records: list[PublishingRecordResponse] = Field(default_factory=list)


# ============================================================
# SSE — 实时进度事件
# ============================================================

class GenerationEvent(BaseModel):
    type: Literal["progress", "article_generated", "error", "completed"]
    batch_id: int
    message: str
    data: dict | None = None


# ============================================================
# Imitate — 模仿创作
# ============================================================

class ImitateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500, description="创作主题")
    source_text: str | None = Field(default=None, max_length=10000, description="参考文章全文")
    source_url: str | None = Field(default=None, max_length=2000, description="参考文章 URL（与 source_text 二选一）")
    photo_ids: list[int] | None = Field(default=None, min_length=1, max_length=100, description="从照片库选择的照片 ID 列表")
    batch_id: int | None = Field(default=None, description="已有批次 ID（含已选照片）")
    style_analysis: dict | None = Field(default=None, description="前端已分析好的风格结果，传入时跳过重复分析")
    word_count_min: int | None = Field(default=None, ge=100, le=10000, description="目标最小字数")
    word_count_max: int | None = Field(default=None, ge=100, le=20000, description="目标最大字数")


class ImitateResponse(BaseModel):
    batch_id: int
    article: ArticleDetailResponse


# ============================================================
# Style Analysis — 风格分析
# ============================================================

class AnalyzeStyleRequest(BaseModel):
    source_text: str = Field(min_length=100, max_length=10000, description="参考文章全文")


class StyleAnalysisResponse(BaseModel):
    tone: str
    opening_style: str
    structure: str
    argument_pattern: str
    closing_style: str
    style_description: str


# ============================================================
# Writing Template — 写作模板
# ============================================================

class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="模板名称")
    type: str = Field(default="structure", pattern="^(structure|style)$", description="模板类型")
    account_type: str | None = Field(
        default=None,
        description="适用账号类型: user/designer/dealer，None=通用",
    )
    prompt_instruction: str = Field(min_length=1, max_length=2000, description="模板提示指令")


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    prompt_instruction: str | None = Field(default=None, max_length=2000)


class TemplateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    type: str
    account_type: str | None = None
    prompt_instruction: str
    is_preset: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Photo Library — 照片库
# ============================================================

class PhotoUploadResponse(BaseModel):
    """照片上传后返回 AI 生成的标签和描述（用户确认前）"""
    photo_id: int
    object_name: str
    tags: list[str]
    description: str | None = None
    tagged: bool = True
    warning: str | None = None


class PhotoResponse(BaseModel):
    id: int
    object_name: str
    filename: str
    tags: list[str]
    description: str | None = None
    file_size: int
    content_type: str
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PhotoUpdate(BaseModel):
    tags: list[str] | None = Field(default=None, description="更新标签列表")


class PhotoMatchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500, description="文章主题")
    count: int = Field(default=5, ge=1, le=20, description="返回匹配数量")
    exclude_days: int = Field(default=30, ge=1, le=365, description="防重复窗口天数")


class PhotoMatchItem(BaseModel):
    photo_id: int
    object_name: str
    filename: str
    tags: list[str]
    description: str | None = None
    confidence: float
    reason: str


class PhotoMatchResponse(BaseModel):
    matches: list[PhotoMatchItem]


class BatchPhotoSelectRequest(BaseModel):
    photo_ids: list[int] = Field(min_length=1, max_length=100, description="选中的照片 ID 列表")


# ============================================================
# Topic Generate — 智能选题（热点 + 知识库 + 公司方向）
# ============================================================

class TopicGenerateRequest(BaseModel):
    company_direction: str = Field(
        default="",
        max_length=1000,
        description="公司创作方向（自由文本），例如：产品优势、技术原理、工程案例、招商加盟",
    )
    max_topics: int = Field(default=8, ge=1, le=20, description="最多推荐选题数")


class TopicRecommendItem(BaseModel):
    hot_title: str
    source: str
    reason: str
    suggested_topic: str
    titles: list[str]


class TopicGenerateResponse(BaseModel):
    recommendations: list[TopicRecommendItem] = Field(default_factory=list)
    hot_count: int = 0
    message: str = ""


# ============================================================
# Weighted Photo Match — 权重配图（LLM + 规则权重）
# ============================================================

class WeightedPhotoMatchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500, description="文章主题")
    template_instruction: str | None = Field(
        default=None,
        max_length=2000,
        description="写作模板指令（与主题一起参与权重评分）",
    )
    count: int = Field(default=5, ge=1, le=20, description="返回匹配数量")
    exclude_days: int = Field(default=30, ge=1, le=365, description="防重复窗口天数")


class WeightedPhotoMatchItem(BaseModel):
    photo_id: int
    object_name: str
    filename: str
    tags: list[str]
    description: str | None = None
    confidence: float
    reason: str
    weights: dict = Field(default_factory=dict, description="各权重明细")


class WeightedPhotoMatchResponse(BaseModel):
    matches: list[WeightedPhotoMatchItem]
