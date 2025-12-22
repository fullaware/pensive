"""Authentication middleware for NiceGUI application."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Callable, Optional, TYPE_CHECKING

from config import logger, SESSION_TIMEOUT_MINUTES
from ui.state import app_state

if TYPE_CHECKING:
    from app.auth.models import User, UserRole


def get_current_user() -> Optional["User"]:
    """Get the currently authenticated user."""
    return app_state.get_user()


def set_current_user(user: "User") -> None:
    """Set the current authenticated user."""
    app_state.set_user(user)


def clear_current_user() -> None:
    """Clear the current user (logout)."""
    app_state.clear_user()


def is_authenticated() -> bool:
    """Check if a user is currently authenticated."""
    return app_state.is_authenticated()


def is_session_expired() -> bool:
    """Check if the current session has expired."""
    if not app_state.is_authenticated():
        return True
    
    session_info = app_state.get_session_info()
    if not session_info.get("authenticated"):
        return True
    
    remaining = session_info.get("remaining_minutes", 0)
    return remaining <= 0


def get_session_id() -> str:
    """Get or create a unique session ID for the current session."""
    return app_state.get_client_id()


def refresh_session() -> None:
    """Refresh the session login time to prevent timeout."""
    app_state.refresh_session()


def get_session_info() -> dict:
    """Get information about the current session."""
    return app_state.get_session_info()


def require_auth(func: Callable) -> Callable:
    """Decorator to require authentication for a function."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not is_authenticated():
            from nicegui import ui
            ui.notify("Please log in to access this feature.", type="warning")
            ui.navigate.to("/login")
            return
        return await func(*args, **kwargs)
    return wrapper


def require_role(*roles: "UserRole") -> Callable:
    """Decorator to require specific role(s) for a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                from nicegui import ui
                ui.notify("Please log in to access this feature.", type="warning")
                ui.navigate.to("/login")
                return
            
            if user.role not in roles:
                from nicegui import ui
                role_names = ", ".join(r.value for r in roles)
                ui.notify(f"Access denied. Required role: {role_names}", type="negative")
                ui.navigate.to("/")
                return
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
