"""HTTP request models."""

from pydantic import BaseModel


class DocumentCategoryUpdate(BaseModel):
    category: str
    subtype: str | None = None
