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