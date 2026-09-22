"""分类管理 Pydantic Schema"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CategoryScope = Literal["public", "customer", "internal"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    sort_order: int = 0
    scope: CategoryScope
    department: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None
    sort_order: int | None = None
    scope: CategoryScope | None = None
    status: Literal["enabled", "disabled"] | None = None


class CategoryResponse(BaseModel):
    id: int
    parent_id: int | None = None
    name: str
    sort_order: int
    scope: str
    status: str
    department: str | None = None
    created_at: datetime
    children: list["CategoryResponse"] = Field(default_factory=list)

    model_config = {"from_attributes": True}


CategoryResponse.model_rebuild()
