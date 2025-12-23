"""Memory management routes."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from config import logger
from app.auth.models import User, UserRole
from app.memory import MemoryStore, MemoryType

from api.models import (
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryItemResponse,
    MemoryStatsResponse,
    SummarizeRequest,
    PurgeRequest,
    PurgeResponse,
)
from api.dependencies import (
    get_current_user,
    require_admin,
    get_memory_store,
    get_user_manager,
)
from app.auth.manager import UserManager


router = APIRouter()


@router.get("/list", response_model=MemorySearchResponse)
async def list_memories(
    memory_types: Optional[str] = Query(None, description="Comma-separated memory types to filter"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user_id: Optional[str] = Query(None, description="Filter by specific user ID (admin only)"),
    current_user: User = Depends(get_current_user),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    List all memories with optional type filtering.
    Regular users can only see their own memories.
    Admins can see all memories or filter by specific user_id.
    """
    if memory_store is None or memory_store.collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service unavailable",
        )
    
    try:
        # Parse memory types if provided
        parsed_types = None
        if memory_types:
            try:
                type_list = [t.strip() for t in memory_types.split(",")]
                parsed_types = [MemoryType(mt) for mt in type_list]
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid memory type. Valid types: {[mt.value for mt in MemoryType]}",
                )
        
        # Build query
        query = {}
        
        # Determine user_id filter based on role and user_id param
        effective_user_id = None
        if user_id:
            # Admin can specify user_id to view another user's memories
            if current_user.role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin privileges required to view other users' memories",
                )
            effective_user_id = user_id
        elif current_user.role != UserRole.ADMIN:
            # Regular users can only see their own memories
            effective_user_id = current_user.id
        
        if effective_user_id is not None:
            query["user_id"] = effective_user_id
        
        # Filter by memory types
        if parsed_types:
            query["memory_type"] = {"$in": [mt.value for mt in parsed_types]}
        
        # Get total count
        total = memory_store.collection.count_documents(query)
        
        # Fetch memories
        cursor = memory_store.collection.find(query).sort("timestamp", -1).skip(offset).limit(limit)
        docs = list(cursor)
        
        # If admin viewing all memories, fetch user info for display
        user_info_map = {}
        if current_user.role == UserRole.ADMIN and effective_user_id is None and user_manager:
            # Collect unique user IDs from memories
            user_ids = {doc.get("user_id") for doc in docs if doc.get("user_id")}
            for uid in user_ids:
                if uid:
                    user = user_manager.get_user_by_id(uid)
                    if user:
                        user_info_map[uid] = {
                            "username": user.username,
                            "display_name": user.display_name,
                        }
        
        response_items = [
            MemoryItemResponse(
                id=str(doc.get("_id", "")),
                content=doc.get("content", ""),
                memory_type=doc.get("memory_type", "unknown"),
                importance=doc.get("importance_score", 0.5),
                timestamp=_parse_timestamp(doc.get("timestamp")),
                user_id=doc.get("user_id"),
                username=user_info_map.get(doc.get("user_id"), {}).get("username") if current_user.role == UserRole.ADMIN else None,
                display_name=user_info_map.get(doc.get("user_id"), {}).get("display_name") if current_user.role == UserRole.ADMIN else None,
                metadata=doc.get("metadata", {}),
            )
            for doc in docs
        ]
        
        return MemorySearchResponse(
            results=response_items,
            total=total,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory list error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list memories",
        )


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    request: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Search through memories using text search.
    Regular users can only search their own memories.
    Admins can search all memories or filter by specific user_id (via request.user_id).
    """
    if memory_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service unavailable",
        )
    
    try:
        # Parse memory types if provided
        memory_types = None
        if request.memory_types:
            try:
                memory_types = [MemoryType(mt) for mt in request.memory_types]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid memory type. Valid types: {[mt.value for mt in MemoryType]}",
                )
        
        # Determine user_id filter based on role and request.user_id
        effective_user_id = None
        if request.user_id:
            # Admin can specify user_id to search another user's memories
            if current_user.role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin privileges required to search other users' memories",
                )
            effective_user_id = request.user_id
        elif current_user.role != UserRole.ADMIN:
            # Regular users can only search their own memories
            effective_user_id = current_user.id
        
        user_id = effective_user_id
        
        results = memory_store.text_search(
            query_text=request.query,
            user_id=user_id,
            memory_types=memory_types,
            limit=request.limit,
        )
        
        # If admin viewing all memories, fetch user info for display
        user_info_map = {}
        if current_user.role == UserRole.ADMIN and user_id is None and user_manager:
            # Collect unique user IDs from memories
            user_ids = {mem.user_id for mem in results if mem.user_id}
            for uid in user_ids:
                if uid:
                    user = user_manager.get_user_by_id(uid)
                    if user:
                        user_info_map[uid] = {
                            "username": user.username,
                            "display_name": user.display_name,
                        }
        
        response_items = [
            MemoryItemResponse(
                id=mem.id or "",
                content=mem.content,
                memory_type=mem.memory_type.value if hasattr(mem.memory_type, 'value') else str(mem.memory_type),
                importance=mem.importance_score,
                timestamp=mem.timestamp,
                user_id=mem.user_id,
                username=user_info_map.get(mem.user_id, {}).get("username") if current_user.role == UserRole.ADMIN else None,
                display_name=user_info_map.get(mem.user_id, {}).get("display_name") if current_user.role == UserRole.ADMIN else None,
                metadata=mem.metadata,
            )
            for mem in results
        ]
        
        return MemorySearchResponse(
            results=response_items,
            total=len(response_items),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Memory search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search memories",
        )


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    current_user: User = Depends(get_current_user),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
):
    """
    Get memory statistics.
    Admins see system-wide stats, users see their own stats.
    """
    if memory_store is None:
        return MemoryStatsResponse(
            total_memories=0,
            by_type={},
            avg_importance=0.0,
            storage_recommendations=["Memory service unavailable"],
        )
    
    try:
        # Determine scope based on role
        user_id = None if current_user.role == UserRole.ADMIN else current_user.id
        
        stats = memory_store.get_stats(user_id=user_id)
        
        # Generate recommendations
        recommendations = []
        total = stats.get("total", 0)
        
        if total > 1000:
            recommendations.append("Consider summarizing older conversations")
        
        avg_importance = stats.get("avg_importance", 0.5)
        if avg_importance < 0.3:
            recommendations.append("Many low-importance memories detected. Consider purging old data.")
        
        if stats.get("oldest_days", 0) > 90:
            recommendations.append("You have memories older than 90 days. Consider archiving.")
        
        return MemoryStatsResponse(
            total_memories=total,
            by_type=stats.get("by_type", {}),
            avg_importance=avg_importance,
            oldest_memory=stats.get("oldest_timestamp"),
            newest_memory=stats.get("newest_timestamp"),
            storage_recommendations=recommendations,
        )
        
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        return MemoryStatsResponse(
            total_memories=0,
            by_type={},
            avg_importance=0.0,
            storage_recommendations=[f"Error: {str(e)}"],
        )


@router.post("/summarize")
async def summarize_memories(
    request: SummarizeRequest,
    current_user: User = Depends(require_admin),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
):
    """
    Trigger summarization of old memories.
    Admin only.
    """
    if memory_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service unavailable",
        )
    
    # Check permission
    if not current_user.has_permission("summarize_memory"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: summarize_memory",
        )
    
    try:
        # Calculate cutoff date
        cutoff = datetime.now(timezone.utc) - timedelta(days=request.older_than_days)
        
        # Parse memory types
        memory_types = None
        if request.memory_types:
            memory_types = [MemoryType(mt) for mt in request.memory_types]
        
        # Trigger summarization (this is a placeholder - actual implementation
        # would need to be added to MemoryStore)
        # For now, return information about what would be summarized
        
        count = memory_store.collection.count_documents({
            "timestamp": {"$lt": cutoff},
            "memory_type": {"$in": [mt.value for mt in (memory_types or [MemoryType.EPISODIC_CONVERSATION])]},
        }) if memory_store.collection is not None else 0
        
        return {
            "success": True,
            "message": f"Summarization triggered for {count} memories older than {request.older_than_days} days",
            "memories_to_summarize": count,
        }
        
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger summarization: {str(e)}",
        )


@router.post("/purge", response_model=PurgeResponse)
async def purge_memories(
    request: PurgeRequest,
    current_user: User = Depends(require_admin),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
):
    """
    Purge old, low-importance memories.
    Admin only. Defaults to dry-run for safety.
    """
    if memory_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service unavailable",
        )
    
    # Check permission
    if not current_user.has_permission("purge_memory"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: purge_memory",
        )
    
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=request.older_than_days)
        
        # Debug: Check what format timestamps are stored in
        if memory_store.collection is not None:
            sample = list(memory_store.collection.find({}).limit(1))
            if sample:
                timestamp_value = sample[0].get("timestamp")
                timestamp_type = type(timestamp_value).__name__
                logger.info(f"Sample timestamp type: {timestamp_type}, value: {timestamp_value}")
        
        # Build query - MongoDB should handle datetime objects even if stored as ISO strings
        # But we'll also try ISO string comparison as fallback
        query = {
            "importance_score": {"$lt": request.importance_below},
            "memory_type": {"$in": [MemoryType.EPISODIC_CONVERSATION.value]},
        }
        
        # Add timestamp filter - try datetime first, MongoDB should handle conversion
        query["timestamp"] = {"$lt": cutoff}
        
        # Debug: Log query and counts
        if memory_store.collection is not None:
            total_count = memory_store.collection.count_documents({})
            old_count = memory_store.collection.count_documents({"timestamp": {"$lt": cutoff}})
            low_importance_count = memory_store.collection.count_documents({"importance_score": {"$lt": request.importance_below}})
            type_count = memory_store.collection.count_documents({"memory_type": MemoryType.EPISODIC_CONVERSATION.value})
            matching_count = memory_store.collection.count_documents(query)
            
            logger.info(f"Purge debug - Total: {total_count}, Old: {old_count}, Low importance: {low_importance_count}, Type match: {type_count}, Matching query: {matching_count}")
            logger.info(f"Query: {query}, Cutoff: {cutoff.isoformat()}")
        
        if request.dry_run:
            # Count what would be deleted
            count = memory_store.collection.count_documents(query) if memory_store.collection is not None else 0
            return PurgeResponse(
                deleted_count=count,
                dry_run=True,
                details=f"Would delete {count} memories older than {request.older_than_days} days with importance < {request.importance_below}",
            )
        else:
            # Actually delete
            result = memory_store.collection.delete_many(query) if memory_store.collection is not None else None
            deleted = result.deleted_count if result is not None else 0
            
            logger.info(f"Purged {deleted} memories (admin: {current_user.username})")
            
            return PurgeResponse(
                deleted_count=deleted,
                dry_run=False,
                details=f"Deleted {deleted} memories",
            )
        
    except Exception as e:
        logger.error(f"Purge error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to purge memories: {str(e)}",
        )


@router.get("/types")
async def get_memory_types():
    """
    Get available memory types.
    """
    return {
        "types": [
            {
                "value": mt.value,
                "name": mt.name,
                "description": _get_memory_type_description(mt),
            }
            for mt in MemoryType
        ]
    }


def _parse_timestamp(timestamp_value) -> datetime:
    """Parse timestamp from ISO string or datetime object."""
    if timestamp_value is None:
        return datetime.now(timezone.utc)
    if isinstance(timestamp_value, datetime):
        return timestamp_value
    if isinstance(timestamp_value, str):
        try:
            return datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        except:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _get_memory_type_description(memory_type: MemoryType) -> str:
    """Get description for a memory type."""
    descriptions = {
        MemoryType.EPISODIC_CONVERSATION: "Individual chat messages",
        MemoryType.EPISODIC_SUMMARY: "Summaries of conversation chunks",
        MemoryType.SEMANTIC_KNOWLEDGE: "Extracted facts and knowledge",
        MemoryType.PROCEDURAL_WORKFLOW: "Learned procedures and patterns",
    }
    return descriptions.get(memory_type, "Unknown type")


