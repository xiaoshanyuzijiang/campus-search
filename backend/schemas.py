"""Request and response models for school notice research."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_name: str = Field(min_length=1, max_length=120)
    website: str = Field(default="", max_length=300)
    keywords: str = Field(default="", max_length=180)


class SchoolIdentity(BaseModel):
    name: str
    website: str = ""
    domain: str = ""


class Notice(BaseModel):
    number: int
    title: str
    url: str
    content: str
    kind: Literal["page", "file"] = "page"


class Attachment(BaseModel):
    number: int
    title: str
    url: str
    source_url: str = ""
    filename: str
    content: str = ""
    status: str = "待读取"
    download_url: str = ""


class ToolStep(BaseModel):
    tool: str
    detail: str


class ResearchResponse(BaseModel):
    school: SchoolIdentity
    summary: str
    notices: list[Notice]
    queries: list[str]
    model: str = ""
    keywords: str = ""
    files: list[Attachment] = Field(default_factory=list)
    steps: list[ToolStep] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
