"""FAQ Pydantic Schema"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FAQCreate(BaseModel):
    category_id: int
    question: str = Field(min_length=1, max_length=500)
    similar_questions: list[str] | None = None
    answer: str = Field(min_length=1)
    tags: list[str] | None = None
    scope: Literal["public", "customer", "internal"] = "public"
    department: str | None = None
    effective_start: datetime | None = None
    effective_end: datetime | None = None


class FAQUpdate(BaseModel):
    category_id: int | None = None
    question: str | None = Field(default=None, min_length=1, max_length=500)
    similar_questions: list[str] | None = None
    answer: str | None = None
    tags: list[str] | None = None
    scope: Literal["public", "customer", "internal"] | None = None
    status: Literal["online", "offline", "draft"] | None = None
    department: str | None = None
    effective_start: datetime | None = None
    effective_end: datetime | None = None


class FAQResponse(BaseModel):
    id: int
    category_id: int
    question: str
    similar_questions: list | None = None
    answer: str
    tags: list | None = None
    scope: str
    status: str
    version: int
    review_status: str
    reviewer_id: int | None = None
    review_comment: str | None = None
    department: str | None = None
    effective_start: datetime | None = None
    effective_end: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FAQReviewAction(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = None


class FAQBulkImport(BaseModel):
    items: list[FAQCreate]
