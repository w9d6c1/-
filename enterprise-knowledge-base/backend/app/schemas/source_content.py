"""多源内容管理 Pydantic Schema"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceLinkResponse(BaseModel):
    id: int
    doc_id: int
    platform: str
    external_id: str
    original_url: str | None = None
    source_name: str | None = None
    publish_time: datetime | None = None
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceContentResponse(BaseModel):
    id: int
    title: str
    scope: str
    status: str
    source_type: str
    source_name: str | None = None
    original_url: str | None = None
    publish_time: datetime | None = None
    word_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceContentDetailResponse(SourceContentResponse):
    source_links: list[SourceLinkResponse] = []


class SyncStateResponse(BaseModel):
    platform: str
    last_cursor: str | None = None
    last_sync_at: datetime | None = None
    last_status: str
    last_error: str | None = None

    model_config = {"from_attributes": True}


class SyncLogResponse(BaseModel):
    id: int
    platform: str
    started_at: datetime
    finished_at: datetime | None = None
    fetched_count: int
    ingested_count: int
    duplicated_count: int
    status: str
    error: str | None = None

    model_config = {"from_attributes": True}


class SyncTriggerRequest(BaseModel):
    platforms: list[str] | None = Field(default=None, description="为空则同步全部已注册平台")


class StatusUpdateRequest(BaseModel):
    status: Literal["online", "offline"]


class MergeRequest(BaseModel):
    primary_doc_id: int = Field(description="保留的主文档 ID")
    duplicate_doc_id: int = Field(description="被合并（删除）的重复文档 ID")


class SyncTriggerResponse(BaseModel):
    total_fetched: int
    total_ingested: int
    failed_platforms: list[str]
    all_ok: bool
