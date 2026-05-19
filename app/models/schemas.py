"""Pydantic schemas for the API and structured LLM outputs."""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EmailCategory(StrEnum):
    """Supported inbox categories."""

    SUPPORT = "support"
    INVOICE = "invoice"
    URGENT = "urgent"
    MEETING = "meeting"
    SPAM = "spam"
    PERSONAL = "personal"


class Priority(StrEnum):
    """Normalized priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Sentiment(StrEnum):
    """Sentiment / tone labels."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"


class EntityBucket(BaseModel):
    """Entities extracted from the message."""

    people: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)


class EmailAnalysisResult(BaseModel):
    """Strict schema returned by the LLM for full analysis."""

    category: EmailCategory
    priority: Priority
    sentiment: Sentiment
    summary: str = Field(..., min_length=1, max_length=4000)
    action_items: list[str] = Field(default_factory=list)
    deadlines: list[str] = Field(default_factory=list)
    entities: EntityBucket = Field(default_factory=EntityBucket)
    suggested_reply: str = Field(..., min_length=1, max_length=8000)


class ReplyGenerationResult(BaseModel):
    """Standalone generated reply body."""

    suggested_reply: str = Field(..., min_length=1, max_length=8000)


class EmailHeaders(BaseModel):
    """Parsed headers from a fake `.txt` email file."""

    model_config = ConfigDict(populate_by_name=True)

    sender: str
    subject: str
    date: Optional[str] = None
    to_field: Optional[str] = Field(default=None, alias="to")
    attachments: list[str] = Field(default_factory=list)
    thread_id: Optional[str] = None


class EmailMeta(BaseModel):
    """Metadata row for the inbox list."""

    id: str
    folder: str
    filename: str
    sender: str
    subject: str
    date: Optional[str] = None
    to_field: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)
    thread_id: Optional[str] = None
    heuristic_priority_signal: Optional[str] = None


class EmailDetail(EmailMeta):
    """Full email including body."""

    body: str


class AnalyzeRequest(BaseModel):
    """Payload to analyze one message."""

    email_id: Optional[str] = Field(
        default=None,
        description="Id of the email stored on disk",
    )
    sender: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    regenerate: bool = Field(
        default=False,
        description="If true, bypass server cache for this email",
    )


class AnalyzeResponse(BaseModel):
    """Analysis response including the email snapshot."""

    email: EmailDetail
    analysis: EmailAnalysisResult
    cached: bool = False


class ReplyRequest(BaseModel):
    """Request body for targeted reply generation."""

    email_id: Optional[str] = None
    sender: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    tone: str = Field(
        default="professional and concise",
        description="Desired tone for the reply",
    )


class ReplyResponse(BaseModel):
    """Response containing only the suggested reply text."""

    suggested_reply: str


class HealthResponse(BaseModel):
    """Simple service health payload."""

    status: str
    emails_loaded: int
