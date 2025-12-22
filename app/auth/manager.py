"""User management: CRUD operations, password hashing, session management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import bcrypt
from bson import ObjectId
from pymongo.collection import Collection

from config import logger
from app.auth.models import (
    User,
    UserRole,
    ToolPermissions,
    get_default_tool_permissions,
)


class UserManager:
    """Manages user operations including CRUD, authentication, and relationships."""
    
    def __init__(self, users_collection: Collection):
        """Initialize with MongoDB users collection."""
        self.collection = users_collection
        self._ensure_indexes()
    
    def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        try:
            self.collection.create_index("username", unique=True)
            self.collection.create_index("role")
            self.collection.create_index("is_active")
            logger.info("User collection indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create user indexes: {e}")
    
    # ==================== Password Hashing ====================
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8")
            )
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    # ==================== User CRUD ====================
    
    def create_user(
        self,
        username: str,
        password: str,
        display_name: str,
        role: UserRole = UserRole.USER,
        tool_permissions: Optional[ToolPermissions] = None,
    ) -> Optional[User]:
        """Create a new user."""
        # Check if username already exists
        if self.get_user_by_username(username):
            logger.warning(f"User with username '{username}' already exists")
            return None
        
        # Use default permissions for role if not specified
        if tool_permissions is None:
            tool_permissions = get_default_tool_permissions(role)
        
        password_hash = self.hash_password(password)
        
        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            tool_permissions=tool_permissions,
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        
        try:
            result = self.collection.insert_one(user.to_mongo_dict())
            user.id = str(result.inserted_id)
            logger.info(f"Created user '{username}' with role '{role}'")
            return user
        except Exception as e:
            logger.error(f"Failed to create user '{username}': {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by their ID."""
        try:
            doc = self.collection.find_one({"_id": ObjectId(user_id)})
            if doc:
                return User.from_mongo_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get user by ID '{user_id}': {e}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by their username."""
        try:
            doc = self.collection.find_one({"username": username})
            if doc:
                return User.from_mongo_dict(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get user by username '{username}': {e}")
            return None
    
    def update_user(self, user_id: str, updates: dict) -> bool:
        """Update a user's fields."""
        try:
            # Don't allow updating password_hash directly through this method
            updates.pop("password_hash", None)
            updates.pop("_id", None)
            
            result = self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update user '{user_id}': {e}")
            return False
    
    def change_password(self, user_id: str, new_password: str) -> bool:
        """Change a user's password."""
        try:
            password_hash = self.hash_password(new_password)
            result = self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"password_hash": password_hash}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to change password for user '{user_id}': {e}")
            return False
    
    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user (soft delete)."""
        return self.update_user(user_id, {"is_active": False})
    
    def activate_user(self, user_id: str) -> bool:
        """Reactivate a user."""
        return self.update_user(user_id, {"is_active": True})
    
    def delete_user(self, user_id: str) -> bool:
        """Permanently delete a user."""
        try:
            # First, remove this user from all relationships
            self.collection.update_many(
                {"relationships.user_id": user_id},
                {"$pull": {"relationships": {"user_id": user_id}}}
            )
            # Also remove from supervised_by lists
            self.collection.update_many(
                {"supervised_by": user_id},
                {"$pull": {"supervised_by": user_id}}
            )
            # Delete the user
            result = self.collection.delete_one({"_id": ObjectId(user_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete user '{user_id}': {e}")
            return False
    
    def list_users(self, active_only: bool = True, role: Optional[UserRole] = None) -> list[User]:
        """List all users, optionally filtered by active status and role."""
        query = {}
        if active_only:
            query["is_active"] = True
        if role:
            query["role"] = role.value
        
        try:
            docs = self.collection.find(query).sort("display_name", 1)
            return [User.from_mongo_dict(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []
    
    # ==================== Authentication ====================
    
    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password."""
        user = self.get_user_by_username(username)
        if not user:
            logger.warning(f"Authentication failed: user '{username}' not found")
            return None
        
        if not user.is_active:
            logger.warning(f"Authentication failed: user '{username}' is deactivated")
            return None
        
        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Authentication failed: invalid password for '{username}'")
            # Debug log - remove in production
            logger.debug(f"Input password: {password}, Hash: {user.password_hash}")
            return None
        
        # Update last login
        self.update_user(user.id, {"last_login": datetime.now(timezone.utc).isoformat()})
        
        logger.info(f"User '{username}' authenticated successfully")
        return user
    
    # ==================== Tool Permissions ====================
    
    def update_tool_permission(
        self,
        user_id: str,
        tool_name: str,
        allowed: bool
    ) -> bool:
        """Update a specific tool permission for a user."""
        try:
            result = self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {f"tool_permissions.{tool_name}": allowed}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update tool permission: {e}")
            return False
    
    def update_all_tool_permissions(
        self,
        user_id: str,
        permissions: ToolPermissions
    ) -> bool:
        """Update all tool permissions for a user."""
        try:
            result = self.collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"tool_permissions": permissions.to_dict()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update tool permissions: {e}")
            return False
    
    # ==================== Admin Operations ====================
    
    def create_default_admin_user(
        self,
        username: str = "admin",
        password: str = "changeme",
        display_name: str = "Administrator"
    ) -> Optional[User]:
        """Create an admin user if no admin exists. Returns the admin user."""
        # Check if any admin exists
        admin = self.collection.find_one({"role": UserRole.ADMIN.value, "is_active": True})
        if admin:
            logger.info("Admin user already exists")
            return User.from_mongo_dict(admin)
        
        # Create admin (with full privileges)
        return self.create_user(
            username=username,
            password=password,
            display_name=display_name,
            role=UserRole.ADMIN,
        )
    
    # Alias for backwards compatibility
    def create_admin_if_none_exists(self, **kwargs) -> Optional[User]:
        """Alias for create_default_admin_user."""
        return self.create_default_admin_user(**kwargs)
    
    def get_user_count(self) -> dict:
        """Get count of users by role."""
        try:
            pipeline = [
                {"$match": {"is_active": True}},
                {"$group": {"_id": "$role", "count": {"$sum": 1}}},
            ]
            results = list(self.collection.aggregate(pipeline))
            counts = {UserRole.ADMIN.value: 0, UserRole.USER.value: 0}
            for r in results:
                if r["_id"] in counts:
                    counts[r["_id"]] = r["count"]
            counts["total"] = sum(counts.values())
            return counts
        except Exception as e:
            logger.error(f"Failed to get user count: {e}")
            return {"admin": 0, "user": 0, "total": 0}
    
    def migrate_users_to_new_schema(self) -> dict:
        """Migrate all existing users to the new schema.
        
        Removes legacy fields: relationships, supervised_by, date_of_birth, is_minor
        Converts legacy roles: parent -> admin, child -> user
        
        Returns:
            Dictionary with migration statistics.
        """
        stats = {
            "total_users": 0,
            "roles_updated": 0,
            "fields_removed": 0,
            "errors": 0,
        }
        
        try:
            stats["total_users"] = self.collection.count_documents({})
            
            # Convert parent -> admin
            result1 = self.collection.update_many(
                {"role": "parent"},
                {"$set": {"role": UserRole.ADMIN.value}}
            )
            stats["roles_updated"] += result1.modified_count
            
            # Convert child -> user
            result2 = self.collection.update_many(
                {"role": "child"},
                {"$set": {"role": UserRole.USER.value}}
            )
            stats["roles_updated"] += result2.modified_count
            
            # Ensure admin role is correct (in case it was already "admin" but stored differently)
            # This also handles any users with unknown roles, defaulting them to USER
            result3 = self.collection.update_many(
                {"role": {"$nin": [UserRole.ADMIN.value, UserRole.USER.value]}},
                {"$set": {"role": UserRole.USER.value}}
            )
            stats["roles_updated"] += result3.modified_count
            
            # Remove all legacy fields from all users
            result4 = self.collection.update_many(
                {},
                {"$unset": {
                    "relationships": "",
                    "supervised_by": "",
                    "date_of_birth": "",
                    "is_minor": ""
                }}
            )
            stats["fields_removed"] = result4.modified_count
            
            logger.info(f"User migration completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"User migration failed: {e}")
            stats["errors"] += 1
            return stats


