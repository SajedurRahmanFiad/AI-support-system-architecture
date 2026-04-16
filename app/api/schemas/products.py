from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProductImageUpdate(BaseModel):
    product_name: str | None = None
    category: str | None = None
    metadata: dict[str, Any] | None = Field(default=None)
