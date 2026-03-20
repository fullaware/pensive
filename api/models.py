# API Models
"""Pydantic models for API request/response validation."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# OpenAI-compatible request models
class ChatMessage(BaseModel):
    """A chat message."""
    role: str = Field(..., description="Role of the message sender (system, user, assistant)")
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    """Request model for chat completions."""
    model: str = Field(default="pensive", description="Model name")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0, description="Top P sampling")
    n: Optional[int] = Field(default=1, ge=1, le=128, description="Number of completions to generate")
    max_tokens: Optional[int] = Field(default=1000, ge=1, le=4096, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(default=False, description="Whether to stream the response")


class ChatCompletionResponse(BaseModel):
    """Response model for chat completions."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


class EmbeddingRequest(BaseModel):
    """Request model for embeddings."""
    model: str = Field(default="pensive", description="Model name")
    input: str | List[str] = Field(..., description="Input text or list of texts")
    encoding_format: Optional[str] = Field(default="float", description="Encoding format")


class EmbeddingResponse(BaseModel):
    """Response model for embeddings."""
    object: str = "list"
    data: List[Dict[str, Any]]
    model: str
    usage: Dict[str, int]


class ModelObject(BaseModel):
    """Model object for model listing."""
    id: str
    object: str = "model"
    created: int
    owned_by: str = "pensive"


class ModelsListResponse(BaseModel):
    """Response model for model listing."""
    object: str = "list"
    data: List[ModelObject]


# Custom API models
class QueryRequest(BaseModel):
    """Request model for custom query endpoint."""
    query: str = Field(..., description="Query string")
    session_id: Optional[str] = Field(default=None, description="Session identifier")


class QueryResponse(BaseModel):
    """Response model for custom query endpoint."""
    answer: str
    sources: List[str]
    memories: Dict[str, Any]
    session_id: str


class FactCreateRequest(BaseModel):
    """Request model for creating a fact."""
    category: str = Field(..., description="Fact category")
    key: str = Field(..., description="Fact key")
    value: str = Field(..., description="Fact value")
    confidence: Optional[float] = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class FactResponse(BaseModel):
    """Response model for fact operations."""
    id: str
    category: str
    key: str
    value: str
    confidence: float
    version: int
    created_at: str
    updated_at: Optional[str] = None


class TaskCreateRequest(BaseModel):
    """Request model for creating a task."""
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task description")
    status: Optional[str] = Field(default="pending", description="Task status")
    priority: Optional[str] = Field(default="medium", description="Task priority")
    due_date: Optional[str] = Field(default=None, description="Due date (ISO format)")
    tags: Optional[List[str]] = Field(default=None, description="Task tags")


class TaskResponse(BaseModel):
    """Response model for task operations."""
    id: str
    title: str
    description: str
    status: str
    priority: str
    due_date: Optional[str]
    created_at: str
    updated_at: str
    progress: int
    tags: List[str]


class MemoryManagementRunRequest(BaseModel):
    """Request model for running memory cleanup tasks."""
    task_names: Optional[List[str]] = Field(default=None, description="Specific task names to run. If None, runs all configured tasks.")
    run_compression: Optional[bool] = Field(default=True, description="Whether to run compression")
    compression_age_days: Optional[int] = Field(default=30, description="Age threshold for compression")
    run_staleness_check: Optional[bool] = Field(default=True, description="Whether to check for stale memories")
    staleness_threshold_days: Optional[int] = Field(default=14, description="Age threshold for staleness")
    archive_confidence_threshold: Optional[float] = Field(default=0.3, description="Confidence threshold for archiving")
    archive_age_days: Optional[int] = Field(default=90, description="Age threshold for archiving")


class MemoryManagementResponse(BaseModel):
    """Response model for memory management operations."""
    success: bool
    message: str
    results: Dict[str, Any] = Field(default_factory=dict)


class MemoryManagementStatusResponse(BaseModel):
    """Response model for memory management status."""
    is_running: bool
    last_cleanup: Optional[str]
    tasks_completed: int


class MemoryManagementMetricsResponse(BaseModel):
    """Response model for memory health metrics."""
    total_memories: int
    facts_count: int
    episodic_count: int
    age_distribution: Dict[str, int]
    hot_memories_count: int
    cold_memories_count: int
    search_success_rate: float
    total_searches_last_30_days: int
    memory_health: Optional[Dict[str, Any]] = Field(default_factory=dict)
    retrieved_recently_count: int
    stale_count: int
    archived_count: int
    run_timestamp: str


class MemoryManagementScheduleRequest(BaseModel):
    """Request model for memory management schedule endpoint."""
    cron_expression: str = Field(
        default="0 2 * * *", 
        description="Cron expression for scheduling (default: daily at 2 AM UTC)"
    )
    enabled: bool = Field(
        default=True, 
        description="Whether to enable automated scheduling"
    )
    tasks: List[str] = Field(
        default_factory=lambda: [
            "system_prompt_versions",
            "stale_memories", 
            "low_confidence_archival",
            "compression",
            "memory_health_metrics"
        ],
        description="List of tasks to run during scheduled execution"
    )


class MemoryManagementScheduleResponse(BaseModel):
    """Response model for memory management schedule endpoint."""
    cron_expression: str
    enabled: bool
    next_run_at: Optional[str] = None
    tasks: List[str]
    last_run_at: Optional[str] = None


class MemoryManagementTriggerRequest(BaseModel):
    """Request model for triggering memory management immediately."""
    tasks: List[str] = Field(
        default_factory=lambda: [
            "system_prompt_versions",
            "stale_memories", 
            "low_confidence_archival",
            "compression",
            "memory_health_metrics"
        ],
        description="List of tasks to run immediately"
    )


class MemoryManagementTriggerResponse(BaseModel):
    """Response model for immediate memory management trigger."""
    success: bool
    message: str
    tasks_triggered: List[str]
    executed_at: str
