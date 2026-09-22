"""文档管理 Pydantic Schema"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    category_id: int
    title: str = Field(min_length=1, max_length=500)
    scope: Literal["public", "customer", "internal"] = "public"
    chunk_strategy: Literal["fixed", "semantic", "recursive"] = "recursive"
    chunk_size: int = Field(default=512, ge=128, le=2048)
    chunk_overlap: int = Field(default=80, ge=0, le=1024)
    department: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: Literal["online", "offline", "draft"] | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class DocumentResponse(BaseModel):
    id: int
    category_id: int
    title: str
    file_type: str
    file_size: int
    word_count: int
    scope: str
    status: str
    chunk_strategy: str
    chunk_count: int
    review_status: str
    review_comment: str | None = None
    department: str | None = None
    clean_status: str = "pending"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    plain_text: str | None = None
    raw_text: str | None = None
    clean_report: str | None = None


class DocumentReviewAction(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = None


class ChunkResponse(BaseModel):
    id: int
    doc_id: int
    chunk_index: int
    content: str
    page_number: int | None = None
    heading_path: str | None = None
    vector_id: str | None = None
    bm25_id: str | None = None
    last_sync_at: datetime | None = None

    model_config = {"from_attributes": True}
