"""HTTP request models."""

from pydantic import BaseModel, Field


class ExtraCategoryItem(BaseModel):
    category: str
    subtype: str | None = None


class DocumentCategoryUpdate(BaseModel):
    category: str
    subtype: str | None = None
    extra_categories: list[ExtraCategoryItem] = Field(default_factory=list)
