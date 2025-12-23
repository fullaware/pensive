"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ==================== Auth Models ====================

class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with user info."""
    success: bool
    message: str
    user: Optional["UserResponse"] = None
    session_token: Optional[str] = None


class UserResponse(BaseModel):
    """User data returned to frontend (excludes password_hash)."""
    id: str
    username: str
    display_name: str
    role: str
    tool_permissions: dict[str, bool]
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    assistant_name: Optional[str] = None
    has_seen_onboarding: bool = False


class CreateUserRequest(BaseModel):
    """Request to create a new user."""
    username: str
    password: str
    display_name: str
    role: str = "user"
    tool_permissions: Optional[dict[str, bool]] = None


class UpdateUserRequest(BaseModel):
    """Request to update a user."""
    display_name: Optional[str] = None
    role: Optional[str] = None
    tool_permissions: Optional[dict[str, bool]] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    """Request to change password."""
    user_id: Optional[str] = None  # Optional target user; omitted = current user
    current_password: Optional[str] = None  # Required when non-admin changes own password
    new_password: str


class UpdatePreferencesRequest(BaseModel):
    """Request to update user preferences."""
    system_prompt: Optional[str] = Field(None, max_length=5000, description="Custom system prompt (max 5000 chars)")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="AI temperature (0.0-2.0)")
    assistant_name: Optional[str] = Field(None, max_length=100, description="What user wants to call the assistant")


# ==================== Chat Models ====================

class ChatMessageRequest(BaseModel):
    """Chat message request."""
    message: str
    conversation_id: str = "main"


class ChatHistoryResponse(BaseModel):
    """Paginated chat history response."""
    messages: list["ChatMessageResponse"]
    total: int
    page: int
    page_size: int
    has_more: bool


class ChatMessageResponse(BaseModel):
    """Single chat message."""
    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    metadata: Optional[dict[str, Any]] = None


# ==================== Memory Models ====================

class MemorySearchRequest(BaseModel):
    """Memory search request."""
    query: str
    memory_types: Optional[list[str]] = None
    limit: int = 20
    include_shared: bool = True
    user_id: Optional[str] = None  # Admin-only: filter by specific user ID


class MemorySearchResponse(BaseModel):
    """Memory search results."""
    results: list["MemoryItemResponse"]
    total: int


class MemoryItemResponse(BaseModel):
    """Single memory item."""
    id: str
    content: str
    memory_type: str
    importance: float
    timestamp: datetime
    user_id: Optional[str] = None  # User who owns this memory
    username: Optional[str] = None  # Username for display (admin only)
    display_name: Optional[str] = None  # Display name for display (admin only)
    metadata: Optional[dict[str, Any]] = None


class MemoryStatsResponse(BaseModel):
    """Memory statistics."""
    total_memories: int
    by_type: dict[str, int]
    avg_importance: float
    oldest_memory: Optional[datetime] = None
    newest_memory: Optional[datetime] = None
    storage_recommendations: list[str] = []


class SummarizeRequest(BaseModel):
    """Request to summarize memories."""
    older_than_days: int = 7
    memory_types: Optional[list[str]] = None


class PurgeRequest(BaseModel):
    """Request to purge memories."""
    older_than_days: int = 30
    importance_below: float = 0.3
    dry_run: bool = True  # Safety: default to dry run


class PurgeResponse(BaseModel):
    """Purge operation result."""
    deleted_count: int
    dry_run: bool
    details: Optional[str] = None


# ==================== Metrics Models ====================

class RealtimeMetricsResponse(BaseModel):
    """Real-time metrics for the current session."""
    tokens_per_second: float = 0.0
    total_tokens_generated: int = 0
    active_users: int = 0
    requests_today: int = 0


class MetricsHistoryResponse(BaseModel):
    """Historical metrics data."""
    period: str  # "day", "week", "month"
    data_points: list["MetricDataPoint"]


class MetricDataPoint(BaseModel):
    """Single metric data point."""
    timestamp: datetime
    messages_count: int = 0
    tokens_generated: int = 0
    avg_response_time_ms: float = 0.0
    unique_users: int = 0


# ==================== Admin Models ====================

class SessionLogResponse(BaseModel):
    """Session log for parental review."""
    id: str
    user_id: str
    username: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    message_count: int
    messages: list[ChatMessageResponse] = []


class SystemStatsResponse(BaseModel):
    """System-wide statistics."""
    user_counts: dict[str, int]
    memory_stats: MemoryStatsResponse
    recent_activity: list["ActivityLogItem"]


class ActivityLogItem(BaseModel):
    """Single activity log entry."""
    timestamp: datetime
    user_id: str
    username: str
    action: str
    details: Optional[str] = None


# ==================== Knowledge Models ====================

class KnowledgeItemResponse(BaseModel):
    """Knowledge item response."""
    id: str
    user_id: str
    domain: str
    topic: str
    content: str
    created_at: str  # ISO format string
    updated_at: str  # ISO format string
    metadata: Optional[dict[str, Any]] = None


class KnowledgeListResponse(BaseModel):
    """Knowledge list response."""
    items: list[KnowledgeItemResponse]
    total: int


class CreateKnowledgeRequest(BaseModel):
    """Request to create/update knowledge."""
    domain: str = Field(..., description="Domain category (e.g., 'locations', 'preferences')")
    topic: str = Field(..., description="Topic within domain (e.g., 'key_location')")
    content: str = Field(..., description="Knowledge content")
    metadata: Optional[dict[str, Any]] = None


class UpdateKnowledgeRequest(BaseModel):
    """Request to update knowledge."""
    content: str = Field(..., description="Updated knowledge content")
    metadata: Optional[dict[str, Any]] = None


# Fix forward references
LoginResponse.model_rebuild()
ChatHistoryResponse.model_rebuild()
MemorySearchResponse.model_rebuild()
MetricsHistoryResponse.model_rebuild()


