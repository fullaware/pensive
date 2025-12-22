"""Authentication and user management package."""

from app.auth.models import User, UserRole
from app.auth.manager import UserManager
from app.auth.permissions import can_use_tool, get_default_permissions, require_permission
from app.auth.middleware import (
    get_current_user,
    set_current_user,
    clear_current_user,
    is_authenticated,
    require_auth,
    require_role,
)

__all__ = [
    # Models
    "User",
    "UserRole",
    # Manager
    "UserManager",
    # Permissions
    "can_use_tool",
    "get_default_permissions",
    "require_permission",
    # Middleware
    "get_current_user",
    "set_current_user",
    "clear_current_user",
    "is_authenticated",
    "require_auth",
    "require_role",
]



