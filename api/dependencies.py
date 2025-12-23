"""FastAPI dependencies for authentication and shared resources."""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from pymongo.collection import Collection

from config import SESSION_TIMEOUT_MINUTES, logger
from database import users_collection, sessions_collection, session_messages_collection, agent_memory_collection
from app.auth.manager import UserManager
from app.auth.models import User, UserRole
from app.memory import MemoryStore
from app.sessions import SessionManager
from app.metrics import MetricsCollector


# In-memory session store (in production, use Redis or database)
_sessions: dict[str, dict] = {}


def get_user_manager() -> Optional[UserManager]:
    """Get UserManager instance."""
    if users_collection is None:
        return None
    return UserManager(users_collection)


def get_memory_store() -> Optional[MemoryStore]:
    """Get MemoryStore instance."""
    if agent_memory_collection is None:
        return None
    return MemoryStore(agent_memory_collection)


def get_session_manager() -> Optional[SessionManager]:
    """Get SessionManager instance."""
    if sessions_collection is None:
        return None
    return SessionManager(sessions_collection, session_messages_collection)


def get_metrics_collector() -> Optional[MetricsCollector]:
    """Get MetricsCollector instance (lazy import to avoid circular deps)."""
    from database import metrics_collection
    if metrics_collection is None:
        return None
    return MetricsCollector(metrics_collection)


def create_session(user: User) -> str:
    """Create a new session for a user, returns session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=SESSION_TIMEOUT_MINUTES),
    }
    logger.info(f"Created session for user '{user.username}'")
    return token


def invalidate_session(token: str) -> bool:
    """Invalidate a session token."""
    if token in _sessions:
        del _sessions[token]
        return True
    return False


def get_session(token: str) -> Optional[dict]:
    """Get session data if valid and not expired."""
    session = _sessions.get(token)
    if not session:
        return None
    
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _sessions[token]
        return None
    
    return session


async def get_current_user(
    session_token: Optional[str] = Cookie(default=None, alias="session_token"),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
) -> User:
    """
    Get the current authenticated user from session cookie.
    Raises HTTPException if not authenticated.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    session = get_session(session_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    
    if not user_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )
    
    user = user_manager.get_user_by_id(session["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    
    return user


async def get_current_user_optional(
    session_token: Optional[str] = Cookie(default=None, alias="session_token"),
    user_manager: Optional[UserManager] = Depends(get_user_manager),
) -> Optional[User]:
    """
    Get the current user if authenticated, otherwise return None.
    Does not raise exception for unauthenticated requests.
    """
    if not session_token or not user_manager:
        return None
    
    session = get_session(session_token)
    if not session:
        return None
    
    user = user_manager.get_user_by_id(session["user_id"])
    if not user or not user.is_active:
        return None
    
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require the current user to be an admin.
    Raises HTTPException if not admin.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


