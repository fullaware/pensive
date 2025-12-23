"""Knowledge management routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from config import logger
from app.auth.models import User, UserRole
from app.knowledge.store import KnowledgeStore
from app.knowledge.models import KnowledgeItem

from api.models import (
    KnowledgeItemResponse,
    KnowledgeListResponse,
    CreateKnowledgeRequest,
    UpdateKnowledgeRequest,
)
from api.dependencies import (
    get_current_user,
    require_admin,
    get_user_manager,
)
from database import knowledge_collection


router = APIRouter()


def get_knowledge_store() -> Optional[KnowledgeStore]:
    """Get KnowledgeStore instance."""
    if knowledge_collection is None:
        return None
    return KnowledgeStore(knowledge_collection)


def _parse_timestamp(ts) -> str:
    """Parse timestamp to ISO string."""
    if isinstance(ts, str):
        return ts
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


@router.get("", response_model=KnowledgeListResponse)
async def list_knowledge(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """
    List knowledge items.
    Regular users can only see their own knowledge.
    Admins can see all knowledge or filter by user_id.
    """
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    # Determine effective user_id
    effective_user_id = current_user.id
    if user_id and user_id != current_user.id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to view other users' knowledge",
            )
        effective_user_id = user_id
    
    try:
        items = knowledge_store.list(
            user_id=effective_user_id,
            domain=domain,
            limit=limit,
            offset=offset,
        )
        
        response_items = [
            KnowledgeItemResponse(
                id=item.id or "",
                user_id=item.user_id,
                domain=item.domain,
                topic=item.topic,
                content=item.content,
                created_at=_parse_timestamp(item.created_at),
                updated_at=_parse_timestamp(item.updated_at),
                metadata=item.metadata,
            )
            for item in items
        ]
        
        total = knowledge_store.count(effective_user_id, domain)
        
        return KnowledgeListResponse(
            items=response_items,
            total=total,
        )
    except Exception as e:
        logger.error(f"Knowledge list error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list knowledge",
        )


@router.get("/domains")
async def get_domains(
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """Get all unique domains for a user."""
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    effective_user_id = current_user.id
    if user_id and user_id != current_user.id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )
        effective_user_id = user_id
    
    try:
        domains = knowledge_store.get_domains(effective_user_id)
        return {"domains": domains}
    except Exception as e:
        logger.error(f"Failed to get domains: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get domains",
        )


@router.get("/{domain}/{topic}", response_model=KnowledgeItemResponse)
async def get_knowledge(
    domain: str,
    topic: str,
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """Get a specific knowledge item."""
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    effective_user_id = current_user.id
    if user_id and user_id != current_user.id:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )
        effective_user_id = user_id
    
    try:
        item = knowledge_store.get(effective_user_id, domain, topic)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge item not found",
            )
        
        return KnowledgeItemResponse(
            id=item.id or "",
            user_id=item.user_id,
            domain=item.domain,
            topic=item.topic,
            content=item.content,
            created_at=_parse_timestamp(item.created_at),
            updated_at=_parse_timestamp(item.updated_at),
            metadata=item.metadata,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get knowledge",
        )


@router.post("", response_model=KnowledgeItemResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    request: CreateKnowledgeRequest,
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """Create or update a knowledge item."""
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    try:
        item_id = knowledge_store.upsert(
            user_id=current_user.id,
            domain=request.domain,
            topic=request.topic,
            content=request.content,
            metadata=request.metadata,
        )
        
        if not item_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create knowledge",
            )
        
        # Fetch the created/updated item
        item = knowledge_store.get(current_user.id, request.domain, request.topic)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created knowledge",
            )
        
        return KnowledgeItemResponse(
            id=item.id or "",
            user_id=item.user_id,
            domain=item.domain,
            topic=item.topic,
            content=item.content,
            created_at=_parse_timestamp(item.created_at),
            updated_at=_parse_timestamp(item.updated_at),
            metadata=item.metadata,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create knowledge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create knowledge",
        )


@router.put("/{domain}/{topic}", response_model=KnowledgeItemResponse)
async def update_knowledge(
    domain: str,
    topic: str,
    request: UpdateKnowledgeRequest,
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """Update a knowledge item."""
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    # Check item exists
    item = knowledge_store.get(current_user.id, domain, topic)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge item not found",
        )
    
    try:
        item_id = knowledge_store.upsert(
            user_id=current_user.id,
            domain=domain,
            topic=topic,
            content=request.content,
            metadata=request.metadata,
        )
        
        if not item_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update knowledge",
            )
        
        # Fetch updated item
        updated_item = knowledge_store.get(current_user.id, domain, topic)
        if not updated_item:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve updated knowledge",
            )
        
        return KnowledgeItemResponse(
            id=updated_item.id or "",
            user_id=updated_item.user_id,
            domain=updated_item.domain,
            topic=updated_item.topic,
            content=updated_item.content,
            created_at=_parse_timestamp(updated_item.created_at),
            updated_at=_parse_timestamp(updated_item.updated_at),
            metadata=updated_item.metadata,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update knowledge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update knowledge",
        )


@router.delete("/{domain}/{topic}")
async def delete_knowledge(
    domain: str,
    topic: str,
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """Delete a knowledge item."""
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    # Check item exists
    item = knowledge_store.get(current_user.id, domain, topic)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge item not found",
        )
    
    try:
        success = knowledge_store.delete(current_user.id, domain, topic)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete knowledge",
            )
        
        return {"success": True, "message": "Knowledge item deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete knowledge",
        )


@router.get("/search", response_model=KnowledgeListResponse)
async def search_knowledge(
    q: str = Query(..., description="Search query"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    knowledge_store: Optional[KnowledgeStore] = Depends(get_knowledge_store),
):
    """Search knowledge items by content."""
    if knowledge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge service unavailable",
        )
    
    try:
        items = knowledge_store.search(
            user_id=current_user.id,
            query_text=q,
            limit=limit,
        )
        
        # Filter by domain if provided
        if domain:
            items = [item for item in items if item.domain == domain]
        
        response_items = [
            KnowledgeItemResponse(
                id=item.id or "",
                user_id=item.user_id,
                domain=item.domain,
                topic=item.topic,
                content=item.content,
                created_at=_parse_timestamp(item.created_at),
                updated_at=_parse_timestamp(item.updated_at),
                metadata=item.metadata,
            )
            for item in items
        ]
        
        return KnowledgeListResponse(
            items=response_items,
            total=len(response_items),
        )
    except Exception as e:
        logger.error(f"Knowledge search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search knowledge",
        )

