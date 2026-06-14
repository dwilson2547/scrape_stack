import json
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator


class ImageEntryOut(BaseModel):
    bucket: str = ""
    prefix: str | None = None
    url: str
    hash: str
    mime_type: str
    size_bytes: int
    filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    perceptual_hash: Optional[str] = None
    file_extension: Optional[str] = None
    client_name: str
    created_at: datetime
    retrieved_at: Optional[datetime] = None
    meta: Optional[Any] = None
    aliases: List[str] = []

    @field_validator("meta", mode="before")
    @classmethod
    def parse_meta_json(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v

    @model_validator(mode="after")
    def populate_aliases(self) -> "ImageEntryOut":
        if not self.aliases:
            self.aliases = [self.url]
        return self

    class Config:
        from_attributes = True


# Keep backward-compat alias used by tests
ImageEntryMeta = ImageEntryOut
