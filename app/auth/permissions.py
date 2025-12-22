"""Tool permission checks and decorators."""

from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, TYPE_CHECKING

from config import logger

if TYPE_CHECKING:
    from app.auth.models import User, UserRole, ToolPermissions


# List of all tools that can have permissions
ALL_TOOLS = [
    "retrieve_context",
    "search_conversations",
    "get_weather",
    "web_search",
    "create_research_agent",
    "summarize_memory",
    "purge_memory",
    "mark_important",
    "remember_this",
    "search_by_entity",
    "get_memory_stats",
]


def get_default_permissions(role: "UserRole") -> dict[str, bool]:
    """Get default tool permissions for a role as a dictionary."""
    from app.auth.models import UserRole, get_default_tool_permissions
    
    permissions = get_default_tool_permissions(role)
    return permissions.to_dict()


def can_use_tool(user: Optional["User"], tool_name: str) -> bool:
    """Check if a user has permission to use a specific tool.
    
    Args:
        user: The user to check. If None, returns False.
        tool_name: The name of the tool to check permission for.
        
    Returns:
        True if the user can use the tool, False otherwise.
    """
    if user is None:
        logger.warning(f"Permission check for '{tool_name}' failed: no user")
        return False
    
    # Check if tool exists in permissions
    has_permission = user.has_permission(tool_name)
    
    if not has_permission:
        logger.info(f"User '{user.username}' denied access to tool '{tool_name}'")
    
    return has_permission


def require_permission(tool_name: str) -> Callable:
    """Decorator factory to require permission for a specific tool.
    
    Usage:
        @require_permission("web_search")
        def web_search(ctx, query):
            ...
    
    Args:
        tool_name: The name of the tool requiring permission.
        
    Returns:
        A decorator that checks permission before calling the function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to get user from various sources
            user = _extract_user_from_context(args, kwargs)
            
            if not can_use_tool(user, tool_name):
                return f"You don't have permission to use {tool_name}. Please ask a parent or administrator for access."
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def _extract_user_from_context(args: tuple, kwargs: dict) -> Optional["User"]:
    """Try to extract the current user from function arguments.
    
    This looks for the user in:
    1. kwargs["user"]
    2. First argument if it has a .user attribute
    3. Streamlit session state
    """
    # Check kwargs
    if "user" in kwargs:
        return kwargs["user"]
    
    # Check first argument for user attribute (e.g., RunContext with deps)
    if args:
        ctx = args[0]
        if hasattr(ctx, "deps") and hasattr(ctx.deps, "current_user"):
            return ctx.deps.current_user
        if hasattr(ctx, "user"):
            return ctx.user
    
    # Fall back to session state
    try:
        from app.auth.middleware import get_current_user
        return get_current_user()
    except Exception:
        return None


def check_permission_or_message(user: Optional["User"], tool_name: str) -> Optional[str]:
    """Check if user has permission, returning error message if not.
    
    Args:
        user: The user to check.
        tool_name: The tool name to check permission for.
        
    Returns:
        None if user has permission, error message string if not.
    """
    if can_use_tool(user, tool_name):
        return None
    
    if user is None:
        return "You must be logged in to use this feature."
    
    return f"You don't have permission to use {tool_name}. Please ask a parent or administrator for access."


def list_available_tools(user: Optional["User"]) -> list[str]:
    """List all tools available to a user.
    
    Args:
        user: The user to check permissions for.
        
    Returns:
        List of tool names the user can access.
    """
    if user is None:
        return []
    
    available = []
    for tool_name in ALL_TOOLS:
        if can_use_tool(user, tool_name):
            available.append(tool_name)
    
    return available


def list_denied_tools(user: Optional["User"]) -> list[str]:
    """List all tools denied to a user.
    
    Args:
        user: The user to check permissions for.
        
    Returns:
        List of tool names the user cannot access.
    """
    if user is None:
        return ALL_TOOLS.copy()
    
    denied = []
    for tool_name in ALL_TOOLS:
        if not can_use_tool(user, tool_name):
            denied.append(tool_name)
    
    return denied


def get_permission_summary(user: Optional["User"]) -> dict[str, bool]:
    """Get a summary of all tool permissions for a user.
    
    Args:
        user: The user to check permissions for.
        
    Returns:
        Dictionary mapping tool names to boolean permission status.
    """
    if user is None:
        return {tool: False for tool in ALL_TOOLS}
    
    return {tool: can_use_tool(user, tool) for tool in ALL_TOOLS}







