"""Admin routes for user management and system administration."""

from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from config import logger
from app.auth.manager import UserManager
from app.auth.models import User, UserRole, ToolPermissions, get_default_tool_permissions
from app.sessions import SessionManager

from api.models import (
    UserResponse,
    CreateUserRequest,
    UpdateUserRequest,
    ChangePasswordRequest,
    SessionLogResponse,
    ChatMessageResponse,
    SystemStatsResponse,
    ActivityLogItem,
    MemoryStatsResponse,
)
from api.dependencies import (
    require_admin,
    get_user_manager,
    get_memory_store,
    get_session_manager,
)
from api.routes.auth import user_to_response


router = APIRouter()


def _parse_timestamp(ts: Any) -> datetime:
    """Parse timestamp from ISO string or datetime object."""
    if ts is None:
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


# ==================== User Management ====================

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    active_only: bool = Query(True),
    role: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    List all users. Admin only.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    try:
        role_filter = UserRole(role) if role else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Valid roles: {[r.value for r in UserRole]}",
        )
    
    users = user_manager.list_users(active_only=active_only, role=role_filter)
    return [user_to_response(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Create a new user. Admin only.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    # Validate role
    try:
        role = UserRole(request.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Valid roles: {[r.value for r in UserRole]}",
        )
    
    # Parse tool permissions if provided
    tool_permissions = None
    if request.tool_permissions:
        try:
            tool_permissions = ToolPermissions(**request.tool_permissions)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tool permissions: {str(e)}",
            )
    
    user = user_manager.create_user(
        username=request.username,
        password=request.password,
        display_name=request.display_name,
        role=role,
        tool_permissions=tool_permissions,
    )
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with username '{request.username}' already exists",
        )
    
    logger.info(f"Admin {current_user.username} created user {request.username}")
    return user_to_response(user)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Get a specific user by ID. Admin only.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    user = user_manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user_to_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Update a user. Admin only.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    # Check user exists
    user = user_manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    updates = {}
    
    if request.display_name is not None:
        updates["display_name"] = request.display_name
    
    if request.role is not None:
        try:
            updates["role"] = UserRole(request.role).value
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Valid roles: {[r.value for r in UserRole]}",
            )
    
    if request.is_active is not None:
        updates["is_active"] = request.is_active
    
    if request.tool_permissions is not None:
        updates["tool_permissions"] = request.tool_permissions
    
    if updates:
        success = user_manager.update_user(user_id, updates)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user",
            )
    
    # Fetch updated user
    updated_user = user_manager.get_user_by_id(user_id)
    logger.info(f"Admin {current_user.username} updated user {user_id}")
    
    return user_to_response(updated_user)


@router.post("/users/{user_id}/password")
async def change_user_password(
    user_id: str,
    request: ChangePasswordRequest,
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Change a user's password. Admin only.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    # Check user exists
    user = user_manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    success = user_manager.change_password(user_id, request.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )
    
    logger.info(f"Admin {current_user.username} changed password for user {user_id}")
    
    return {"success": True, "message": "Password changed successfully"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    permanent: bool = Query(False),
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Delete a user. Admin only.
    By default, soft-deletes (deactivates). Use permanent=true to permanently delete.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    # Check user exists
    user = user_manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Prevent self-deletion
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    
    if permanent:
        success = user_manager.delete_user(user_id)
        action = "permanently deleted"
    else:
        success = user_manager.deactivate_user(user_id)
        action = "deactivated"
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action.split()[0]} user",
        )
    
    logger.info(f"Admin {current_user.username} {action} user {user_id}")
    
    return {"success": True, "message": f"User {action}"}


# ==================== Session Audit ====================

@router.get("/sessions/{user_id}", response_model=list[SessionLogResponse])
async def get_user_sessions(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
    session_manager: Optional[SessionManager] = Depends(get_session_manager),
):
    """
    Get session logs for a user (parental oversight). Admin only.
    """
    if session_manager is None:
        return []
    
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    # Get the target user
    target_user = user_manager.get_user_by_id(user_id)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        sessions = session_manager.get_user_sessions(
            user_id=user_id,
            start_date=cutoff,
            include_messages=True,
        )
        
        return [
            SessionLogResponse(
                id=str(s.get("_id", "")),
                user_id=user_id,
                username=target_user.username,
                started_at=_parse_timestamp(s.get("started_at")),
                ended_at=_parse_timestamp(s.get("ended_at")) if s.get("ended_at") else None,
                message_count=len(s.get("messages", [])),
                messages=[
                    ChatMessageResponse(
                        id=str(msg.get("_id", i)),
                        role=msg.get("role", "unknown"),
                        content=msg.get("content", ""),
                        timestamp=_parse_timestamp(msg.get("timestamp")),
                    )
                    for i, msg in enumerate(s.get("messages", []))
                ],
            )
            for s in sessions
        ]
        
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch sessions",
        )


# ==================== System Stats ====================

@router.get("/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
    memory_store = Depends(get_memory_store),
):
    """
    Get system-wide statistics. Admin only.
    """
    # User counts
    user_counts = {"admin": 0, "user": 0, "total": 0}
    if user_manager:
        user_counts = user_manager.get_user_count()
    
    # Memory stats
    memory_stats = MemoryStatsResponse(
        total_memories=0,
        by_type={},
        avg_importance=0.0,
    )
    
    if memory_store:
        try:
            stats = memory_store.get_stats()
            memory_stats = MemoryStatsResponse(
                total_memories=stats.get("total", 0),
                by_type=stats.get("by_type", {}),
                avg_importance=stats.get("avg_importance", 0.0),
                oldest_memory=stats.get("oldest_timestamp"),
                newest_memory=stats.get("newest_timestamp"),
            )
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
    
    # Recent activity (placeholder - would need activity logging)
    recent_activity: list[ActivityLogItem] = []
    
    return SystemStatsResponse(
        user_counts=user_counts,
        memory_stats=memory_stats,
        recent_activity=recent_activity,
    )


@router.get("/user-counts")
async def get_user_counts(
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Get user counts by role. Admin only.
    """
    if user_manager is None:
        return {"admin": 0, "user": 0, "total": 0}
    
    return user_manager.get_user_count()


@router.post("/migrate-users")
async def migrate_users(
    current_user: User = Depends(require_admin),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
):
    """
    Migrate users to the new schema (removes legacy fields). Admin only.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    stats = user_manager.migrate_users_to_new_schema()
    logger.info(f"Admin {current_user.username} triggered user migration: {stats}")
    
    return {
        "success": True,
        "migration_stats": stats,
    }


