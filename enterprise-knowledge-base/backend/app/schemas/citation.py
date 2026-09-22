"""引用溯源 Pydantic Schema"""

from pydantic import BaseModel


class CitationResponse(BaseModel):
    index: int
    title: str
    platform: str
    url: str = ""
    source_name: str = ""
    is_internal: bool = True

    model_config = {"from_attributes": True}
