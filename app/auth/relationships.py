"""Simplified user access utilities - admins can see any data for any user."""

from __future__ import annotations

from app.auth.manager import UserManager
from app.auth.models import UserRole


def can_view_sessions(
    manager: UserManager,
    viewer_id: str,
    target_id: str
) -> bool:
    """Check if a user can view another user's sessions.
    
    Admins can see any data for any user.
    Users can only see their own data.
    
    Args:
        manager: The UserManager instance.
        viewer_id: ID of the user trying to view sessions.
        target_id: ID of the user whose sessions are being viewed.
    
    Returns:
        True if the viewer can view the target's sessions.
    """
    # Users can always view their own sessions
    if viewer_id == target_id:
        return True
    
    viewer = manager.get_user_by_id(viewer_id)
    if not viewer:
        return False
    
    # Admins can view anyone's sessions
    return viewer.role == UserRole.ADMIN


def get_all_users_for_admin(manager: UserManager, admin_id: str) -> list[dict]:
    """Get all users that an admin can view.
    
    Args:
        manager: The UserManager instance.
        admin_id: ID of the admin user.
    
    Returns:
        List of user dictionaries with id and display_name.
    """
    admin = manager.get_user_by_id(admin_id)
    if not admin or admin.role != UserRole.ADMIN:
        return []
    
    users = manager.list_users(active_only=True)
    return [
        {"id": u.id, "display_name": u.display_name}
        for u in users
        if u.id != admin_id
    ]
