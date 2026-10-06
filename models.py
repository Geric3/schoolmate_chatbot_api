from typing import Optional, List
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    file_path: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    source: str  # "structured_data" | "faq" | "documents" | "llm_general" | "blocked"


class FaqIn(BaseModel):
    question_key: str = Field(..., max_length=50)
    answer: str
    lang: str = "fr"


class FaqOut(FaqIn):
    id: int


class DocumentIn(BaseModel):
    title: str
    content: str  # plain text; PDFs are extracted server-side before this model is built


class DocumentOut(BaseModel):
    id: int
    title: str
    chunk_count: int
    created_at: Optional[str] = None


class AnnouncementIn(BaseModel):
    title: str
    content: str
    audience: str = "all"  # all | students | teachers


class UnansweredOut(BaseModel):
    id: int
    question: str
    answer: str
    timestamp: Optional[str] = None
