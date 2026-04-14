# API Routes
"""FastAPI routes for the agentic memory system."""
from typing import List, Dict, Any
from datetime import datetime, timezone
import time
import uuid

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from memory_system import (
    Config,
    MongoDB,
    ShortTermMemory,
    EpisodicMemory,
    SemanticMemory,
    QueryRouter,
    SystemPromptsManager,
)
from agent import AgenticOrchestrator
from services import LLMClient, EmbeddingClient
from api.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelsListResponse,
    ModelObject,
    QueryRequest,
    QueryResponse,
    FactCreateRequest,
    FactResponse,
    TaskCreateRequest,
    TaskResponse,
    MemoryManagementRunRequest,
    MemoryManagementResponse,
    MemoryManagementStatusResponse,
    MemoryManagementMetricsResponse,
    MemoryManagementScheduleRequest,
    MemoryManagementScheduleResponse,
)


# Create FastAPI app
app = FastAPI(
    title="Pensive API",
    description="Agentic Memory System API with OpenAI-compatible endpoints",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get orchestrator
async def get_orchestrator() -> AgenticOrchestrator:
    """Get or create orchestrator instance."""
    if not hasattr(app.state, "orchestrator"):
        app.state.orchestrator = AgenticOrchestrator()
        # Initialize bootstrap when orchestrator is created
        await app.state.orchestrator.initialize_bootstrap()
    return app.state.orchestrator


# Dependency to verify MongoDB connection
async def verify_mongodb() -> None:
    """Verify MongoDB is connected."""
    if not MongoDB._client:
        raise HTTPException(status_code=503, detail="MongoDB not connected")


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize MongoDB connection, enable logging, create vector indexes, and verify status."""
    await MongoDB.connect()
    
    # Enable MongoDB query logging (embeddings will be masked)
    MongoDB.enable_logging(True)
    
    # Create vector indexes for collections that need them
    print("Creating vector indexes...")
    await MongoDB.create_vector_index("facts")
    await MongoDB.create_vector_index("episodic_memories")
    
    # Verify and log index status
    print("\nVerifying vector indexes...")
    await MongoDB.verify_indexes()


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if hasattr(app.state, "orchestrator"):
        await app.state.orchestrator.close()


# ===== OPENAI-COMPATIBLE ENDPOINTS =====

@app.get("/v1/models")
async def list_models() -> ModelsListResponse:
    """List available models (OpenAI-compatible)."""
    return ModelsListResponse(
        data=[
            ModelObject(id="pensive", created=int(time.time())),
        ]
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> ChatCompletionResponse:
    """Create chat completion (OpenAI-compatible)."""
    try:
        # Convert messages to orchestrator format
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        # Extract user query from last message
        user_query = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_query = msg["content"]
                break
        
        if not user_query:
            raise HTTPException(status_code=400, detail="No user query found in messages")
        
        # Process query through orchestrator
        result = await orchestrator.process_query(user_query)
        
        # Extract timing info
        timing = result.get("timing", {})
        
        # Build response in OpenAI format
        response = ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model="pensive",
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result["answer"]},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": len(user_query) // 4,
                "completion_tokens": len(result["answer"]) // 4,
                "total_tokens": (len(user_query) + len(result["answer"])) // 4,
            },
            extra={
                "timing": timing,
                "sources": result.get("sources", []),
            },
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/embeddings")
async def create_embeddings(
    request: EmbeddingRequest,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> EmbeddingResponse:
    """Create embeddings (OpenAI-compatible)."""
    try:
        embedding_client = EmbeddingClient()
        
        # Handle both string and list inputs
        input_texts = [request.input] if isinstance(request.input, str) else request.input
        
        embeddings = []
        for text in input_texts:
            embedding = await embedding_client.generate_embedding(text)
            if embedding:
                embeddings.append({
                    "object": "embedding",
                    "embedding": embedding,
                    "index": len(embeddings),
                })
        
        return EmbeddingResponse(
            object="list",
            data=embeddings,
            model=Config.LLM_EMBEDDING_MODEL,
            usage={
                "prompt_tokens": sum(len(t) for t in input_texts) // 4,
                "total_tokens": sum(len(t) for t in input_texts) // 4,
            },
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== CUSTOM API ENDPOINTS =====

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/v1/query")
async def custom_query(
    request: QueryRequest,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> QueryResponse:
    """Custom query endpoint."""
    try:
        result = await orchestrator.process_query(request.query, request.session_id)
        # Sanitize MongoDB ObjectIds in the result to make it JSON-serializable
        result = _sanitize_bson(result)
        return QueryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sanitize_bson(obj):
    """Recursively convert bson.ObjectId and other non-serializable types to strings."""
    from bson import ObjectId
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _sanitize_bson(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_bson(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


@app.get("/api/v1/facts")
async def list_facts(
    category: str = None,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> List[Dict[str, Any]]:
    """List facts with optional category filter."""
    try:
        semantic = orchestrator.semantic
        if category:
            facts = await semantic.get_facts_by_category(category)
        else:
            facts = await semantic.get_all_facts()
        return facts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/facts")
async def create_fact(
    request: FactCreateRequest,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> FactResponse:
    """Create a new fact."""
    try:
        fact_id = await orchestrator.semantic.add_fact(
            category=request.category,
            key=request.key,
            value=request.value,
            confidence=request.confidence,
            metadata=request.metadata,
        )
        return FactResponse(
            id=fact_id,
            category=request.category,
            key=request.key,
            value=request.value,
            confidence=request.confidence,
            version=1,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/facts/{key}")
async def get_fact(
    key: str,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Get a fact by key."""
    try:
        fact = await orchestrator.semantic.get_fact(key)
        if not fact:
            raise HTTPException(status_code=404, detail=f"Fact '{key}' not found")
        return fact
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/facts/{key}")
async def delete_fact(
    key: str,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> Dict[str, bool]:
    """Delete a fact by key."""
    try:
        result = await orchestrator.semantic.delete_fact(key)
        return {"success": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tasks")
async def list_tasks(
    status: str = None,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> List[Dict[str, Any]]:
    """List tasks with optional status filter."""
    try:
        tasks = await orchestrator.tasks.list_tasks(status=status)
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/tasks")
async def create_task(
    request: TaskCreateRequest,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> TaskResponse:
    """Create a new task."""
    try:
        from datetime import datetime
        from bson import ObjectId
        
        task_id = await orchestrator.tasks.create_task(
            title=request.title,
            description=request.description,
            status=request.status,
            priority=request.priority,
            tags=request.tags,
        )
        
        # Get the created task to return full details
        task = await orchestrator.tasks.get_task(task_id)
        
        return TaskResponse(
            id=str(task.get("_id", task_id)),
            title=task.get("title", request.title),
            description=task.get("description", ""),
            status=task.get("status", "pending"),
            priority=task.get("priority", "medium"),
            due_date=task.get("due_date"),
            created_at=task.get("created_at", datetime.now(timezone.utc)).isoformat(),
            updated_at=task.get("updated_at", datetime.now(timezone.utc)).isoformat(),
            progress=task.get("progress", 0),
            tags=task.get("tags", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tasks/{task_id}")
async def get_task(
    task_id: str,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Get a task by ID."""
    try:
        task = await orchestrator.tasks.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/tasks/{task_id}")
async def delete_task(
    task_id: str,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> Dict[str, bool]:
    """Delete a task by ID."""
    try:
        result = await orchestrator.tasks.delete_task(task_id)
        return {"success": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memories/episodic")
async def list_episodic_memories(
    session_id: str = None,
    limit: int = 10,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> List[Dict[str, Any]]:
    """List episodic memories with optional session filter."""
    try:
        if session_id:
            memories = await orchestrator.episodic.get_session_history(session_id, limit)
        else:
            memories = await orchestrator.episodic.get_recent_events(limit)
        return memories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/memories/episodic")
async def add_episodic_memory(
    role: str,
    content: str,
    session_id: str,
    orchestrator: AgenticOrchestrator = Depends(get_orchestrator),
) -> Dict[str, str]:
    """Add an episodic memory."""
    try:
        event_id = await orchestrator.episodic.add_event(
            session_id=session_id,
            role=role,
            content=content,
        )
        return {"id": event_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== MEMORY MANAGEMENT API ENDPOINTS =====

@app.post("/api/v1/memory-management/run")
async def run_memory_management(
    request: MemoryManagementRunRequest,
) -> MemoryManagementResponse:
    """Run memory management tasks manually or on a schedule.
    
    This endpoint allows you to run memory management tasks either:
    - On-demand: Set schedule=None and tasks to run immediately
    - Scheduled: Set a cron schedule to run periodically
    
    Args:
        request: Request with optional task_names to specify which tasks to run
                If empty, runs all configured tasks.
    """
    try:
        from memory_system import AutomatedMemoryManager
        
        manager = AutomatedMemoryManager()
        
        # Determine which tasks to run
        task_names = request.task_names if hasattr(request, 'task_names') and request.task_names else None
        
        # Run cleanup tasks (optionally filtering to specific tasks)
        result = await manager.run_cleanup_tasks(task_names=task_names)
        
        return MemoryManagementResponse(
            success=True,
            message="Memory management tasks completed",
            results=result,
            executed_at=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/memory-management/schedule")
async def schedule_memory_management(
    request: MemoryManagementScheduleRequest,
) -> Dict[str, Any]:
    """Configure automated memory management scheduling.
    
    This endpoint allows you to set up automatic periodic execution of
    memory management tasks using cron-style scheduling.
    
    Args:
        request: Schedule configuration with cron expression and enabled flag
        
    Returns:
        Schedule status and next scheduled run time
    """
    try:
        from memory_system import AutomatedMemoryManager
        
        manager = AutomatedMemoryManager()
        
        # Update schedule configuration
        manager.update_schedule(
            cron_expression=request.cron_expression,
            enabled=request.enabled,
            tasks_to_run=request.tasks
        )
        
        # Get next scheduled run time
        next_run = manager.get_next_run_time()
        
        return {
            "success": True,
            "message": f"Memory management {'enabled' if request.enabled else 'disabled'}",
            "schedule": {
                "cron_expression": manager.cron_expression,
                "enabled": manager.is_enabled(),
                "next_run_at": next_run.isoformat() if next_run else None,
                "tasks": manager.tasks_to_run
            },
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory-management/schedule")
async def get_memory_management_schedule() -> MemoryManagementScheduleResponse:
    """Get current memory management schedule configuration."""
    try:
        from memory_system import AutomatedMemoryManager
        
        manager = AutomatedMemoryManager()
        
        next_run = manager.get_next_run_time()
        
        return MemoryManagementScheduleResponse(
            cron_expression=manager.cron_expression,
            enabled=manager.is_enabled(),
            next_run_at=next_run.isoformat() if next_run else None,
            tasks=manager.tasks_to_run,
            last_run_at=manager.last_cleanup.isoformat() if manager.last_cleanup else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory-management/status")
async def get_memory_management_status() -> MemoryManagementStatusResponse:
    """Get the status of automated memory management."""
    try:
        from memory_system import AutomatedMemoryManager
        
        manager = AutomatedMemoryManager()
        
        last_cleanup = getattr(manager, "last_cleanup", None)
        
        return MemoryManagementStatusResponse(
            is_running=False,  # Will be updated if background task is running
            last_cleanup=last_cleanup.isoformat() if last_cleanup else None,
            tasks_run=[
                "system_prompt_versions",
                "stale_memories",
                "low_confidence_archival",
                "compression",
                "memory_health_metrics"
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/memory-management/metrics")
async def get_memory_management_metrics() -> MemoryManagementMetricsResponse:
    """Get memory management metrics."""
    try:
        from memory_system import MemoryMetrics
        
        metrics = MemoryMetrics()
        stats = await metrics.get_memory_health_summary()
        
        return MemoryManagementMetricsResponse(
            memory_health=stats,
            retrieved_recently_count=stats.get("retrieved_recently", 0) if stats else 0,
            stale_count=stats.get("stale_memories", {}).get("tagged_stale", 0) if stats else 0,
            archived_count=stats.get("archived_memories", {}).get("total_archived", 0) if stats else 0,
            run_timestamp=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def create_app() -> FastAPI:
    """Create and return the FastAPI app."""
    return app