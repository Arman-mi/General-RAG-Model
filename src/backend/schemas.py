from pydantic import BaseModel
from typing import List

class ChatRequest(BaseModel):
    message: str
    site_id: str | None = None

class ChatResponse(BaseModel):
    response: str
    citations: List[str]


class SiteIndexRequest(BaseModel):
    url: str
    max_pages: int = 80


class SiteIndexResponse(BaseModel):
    site_id: str


class SiteStatusResponse(BaseModel):
    site_id: str
    status: str
    url: str | None = None
    message: str | None = None
    
