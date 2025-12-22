"""User and authentication models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User roles for access control.
    
    Admins have full privileges and can see any data for any user.
    Users have restricted access based on tool_permissions.
    """
    ADMIN = "admin"  # Full admin privileges, can see all user data
    USER = "user"    # Restricted access based on tool_permissions


class ToolPermissions(BaseModel):
    """Tool-level permissions for a user."""
    retrieve_context: bool = True
    search_conversations: bool = True
    get_weather: bool = True
    web_search: bool = True
    create_research_agent: bool = True
    summarize_memory: bool = True
    purge_memory: bool = False
    mark_important: bool = True
    remember_this: bool = True
    search_by_entity: bool = True
    get_memory_stats: bool = True
    # Calendar permissions
    calendar_create_event: bool = True
    calendar_list_events: bool = True
    calendar_update_event: bool = True
    calendar_delete_event: bool = False  # Dangerous - disabled by default for children
    
    def to_dict(self) -> dict[str, bool]:
        """Convert to dictionary."""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: dict[str, bool]) -> "ToolPermissions":
        """Create from dictionary."""
        return cls(**data)


class User(BaseModel):
    """User model for authentication and authorization."""
    id: Optional[str] = Field(default=None, alias="_id")  # MongoDB ObjectId as string
    username: str
    password_hash: str
    display_name: str
    role: UserRole = UserRole.USER
    tool_permissions: ToolPermissions = Field(default_factory=ToolPermissions)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    is_active: bool = True
    
    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }
    
    def to_mongo_dict(self) -> dict[str, Any]:
        """Convert to MongoDB document format."""
        data = self.model_dump(by_alias=True, exclude={"id"})
        # Convert nested models
        data["tool_permissions"] = self.tool_permissions.to_dict()
        # Convert datetimes to ISO strings
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        if data.get("last_login"):
            data["last_login"] = data["last_login"].isoformat()
        return data
    
    @classmethod
    def from_mongo_dict(cls, data: dict[str, Any]) -> "User":
        """Create User from MongoDB document."""
        if data is None:
            raise ValueError("Cannot create User from None")
        
        # Handle _id
        if "_id" in data:
            data["_id"] = str(data["_id"])
        
        # Handle tool_permissions
        if "tool_permissions" in data and isinstance(data["tool_permissions"], dict):
            data["tool_permissions"] = ToolPermissions.from_dict(data["tool_permissions"])
        
        # Handle datetimes
        for field in ["created_at", "last_login"]:
            if field in data and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field].replace("Z", "+00:00"))
        
        # Remove old fields that no longer exist
        data.pop("relationships", None)
        data.pop("supervised_by", None)
        data.pop("date_of_birth", None)
        data.pop("is_minor", None)
        
        return cls(**data)
    
    def has_permission(self, tool_name: str) -> bool:
        """Check if user has permission to use a specific tool."""
        return getattr(self.tool_permissions, tool_name, False)
    
    def can_supervise(self, user_id: str) -> bool:
        """Check if this user can supervise (view sessions of) another user.
        
        Admins can see any data for any user.
        """
        return self.role == UserRole.ADMIN


def get_default_tool_permissions(role: UserRole) -> ToolPermissions:
    """Get default tool permissions for a role."""
    if role == UserRole.ADMIN:
        # Admins have full privileges
        return ToolPermissions(
            retrieve_context=True,
            search_conversations=True,
            get_weather=True,
            web_search=True,
            create_research_agent=True,
            summarize_memory=True,
            purge_memory=True,
            mark_important=True,
            remember_this=True,
            search_by_entity=True,
            get_memory_stats=True,
            # Calendar - full access for admins
            calendar_create_event=True,
            calendar_list_events=True,
            calendar_update_event=True,
            calendar_delete_event=True,
        )
    else:  # USER
        return ToolPermissions(
            retrieve_context=True,
            search_conversations=True,
            get_weather=True,
            web_search=False,
            create_research_agent=False,
            summarize_memory=False,
            purge_memory=False,
            mark_important=True,
            remember_this=True,
            search_by_entity=True,
            get_memory_stats=False,
            # Calendar - limited access for users
            calendar_create_event=True,  # Can create events
            calendar_list_events=True,   # Can view events
            calendar_update_event=False, # Cannot modify
            calendar_delete_event=False, # Cannot delete
        )


