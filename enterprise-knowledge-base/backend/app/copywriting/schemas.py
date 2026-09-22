"""短视频文案 — Pydantic 请求/响应模型"""

from datetime import datetime

from pydantic import BaseModel, Field

# ============================================================
# 手动热榜
# ============================================================

class HotManualCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500, description="热点标题")
    url: str | None = Field(default=None, max_length=1000, description="视频跳转链接")
    source: str = Field(default="chanmama", max_length=50, description="来源标识")
    sort_order: int = Field(default=0, ge=0, description="排序（越小越靠前）")


class HotManualItemResponse(BaseModel):
    id: int
    user_id: int
    title: str
    url: str | None = None
    rank: int
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# 文案标题推荐
# ============================================================

class TitlesRecommendRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=20, description="最多推荐标题数")
    include_manual: bool = Field(default=True, description="是否包含手动热榜")


class TitleRecommendItem(BaseModel):
    title: str
    hot_word: str = ""
    hot_url: str = ""
    cover: str = ""
    reason: str = ""


class TitlesRecommendResponse(BaseModel):
    recommendations: list[TitleRecommendItem] = Field(default_factory=list)
    hot_count: int = 0


# ============================================================
# 脚本
# ============================================================

class ScriptGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500, description="文案标题")
    hot_word: str | None = Field(default=None, max_length=200, description="关联热点词")
    hot_url: str | None = Field(default=None, max_length=1000, description="原视频链接")
    requirement: str | None = Field(default=None, max_length=2000, description="AI 创作要求")
    material_entries: list[dict] | None = Field(
        default=None, description="素材上传返回的 entries（含 description）"
    )
    material_notes: str | None = Field(
        default=None, max_length=5000,
        description="素材描述文本（重新生成时直接复用已存素材摘要，优先于 material_entries）",
    )


class ScriptUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    hot_word: str | None = Field(default=None, max_length=200)
    hot_url: str | None = Field(default=None, max_length=1000)
    voiceover: str | None = None
    storyboard: str | None = None
    material_notes: str | None = None
    requirement: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, max_length=20)


class ScriptResponse(BaseModel):
    id: int
    user_id: int
    title: str
    hot_word: str | None = None
    hot_url: str | None = None
    voiceover: str
    storyboard: str | None = None
    material_notes: str | None = None
    requirement: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# 素材
# ============================================================

class LinkImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000, description="网页/视频页链接")


class LinkImportResponse(BaseModel):
    url: str
    content: str
    content_length: int
