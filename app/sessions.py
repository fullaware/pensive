"""Session tracking and logging for parental oversight."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from bson import ObjectId
from pymongo.collection import Collection

from config import logger


class SessionManager:
    """Manages chat sessions for tracking and session audit."""
    
    def __init__(self, sessions_collection: Collection):
        """Initialize with MongoDB sessions collection.
        
        Args:
            sessions_collection: The sessions collection.
        """
        self.collection = sessions_collection
        self._ensure_indexes()
    
    def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        if self.collection is None:
            return
        
        try:
            self.collection.create_index([
                ("user_id", 1),
                ("started_at", -1),
            ], name="user_sessions_idx")
            
            self.collection.create_index([
                ("session_id", 1),
            ], name="session_id_idx", unique=True)
            
            self.collection.create_index([
                ("flagged", 1),
                ("reviewed_by", 1),
            ], name="flagged_review_idx")
            
            logger.info("Session collection indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create session indexes: {e}")
    
    # ==================== Session Lifecycle ====================
    
    def get_or_create_user_session(self, user_id: str) -> str:
        """Get the user's continuous session, or create one if it doesn't exist.
        
        Each user has ONE persistent session that continues across all logins.
        Context quality is managed through memory purging/summarization, not session resets.
        
        Args:
            user_id: The user ID.
        
        Returns:
            The session ID for this user.
        """
        if self.collection is None:
            return f"session_{user_id}"
        
        try:
            # Look for existing session for this user
            existing = self.collection.find_one(
                {"user_id": user_id},
                sort=[("started_at", -1)]  # Get most recent if multiple exist
            )
            
            if existing:
                logger.debug(f"Resuming continuous session for user {user_id}")
                return existing["session_id"]
            
            # Create new persistent session for this user
            session_id = f"session_{user_id}"
            now = datetime.now(timezone.utc)
            
            self.collection.insert_one({
                "session_id": session_id,
                "user_id": user_id,
                "started_at": now.isoformat(),
                "ended_at": None,  # Continuous sessions don't end
                "messages": [],
                "tools_used": [],
                "message_count": 0,
                "flagged": False,
                "reviewed_by": None,
                "reviewed_at": None,
                "notes": None,
            })
            
            logger.info(f"Created continuous session {session_id} for user {user_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to get/create session: {e}")
            return f"session_{user_id}"
    
    # Keep for backwards compatibility
    def start_session(
        self,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> str:
        """Alias for get_or_create_user_session for backwards compatibility."""
        return self.get_or_create_user_session(user_id)
    
    def end_session(self, session_id: str) -> bool:
        """End a chat session.
        
        Args:
            session_id: The session to end.
        
        Returns:
            True if successful.
        """
        if self.collection is None:
            return False
        
        try:
            result = self.collection.update_one(
                {"session_id": session_id},
                {"$set": {"ended_at": datetime.now(timezone.utc).isoformat()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
            return False
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list[str]] = None,
    ) -> bool:
        """Add a message to a session.
        
        Args:
            session_id: The session ID.
            role: user/assistant.
            content: The message content.
            tool_calls: List of tool names used.
        
        Returns:
            True if successful.
        """
        if self.collection is None:
            return False
        
        now = datetime.now(timezone.utc)
        
        message = {
            "role": role,
            "content": content[:5000],  # Truncate long messages
            "timestamp": now.isoformat(),
            "tool_calls": tool_calls or [],
        }
        
        try:
            update = {
                "$push": {"messages": message},
                "$inc": {"message_count": 1},
            }
            
            if tool_calls:
                update["$addToSet"] = {"tools_used": {"$each": tool_calls}}
            
            result = self.collection.update_one(
                {"session_id": session_id},
                update
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to add message to session: {e}")
            return False
    
    # ==================== Session Retrieval ====================
    
    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Get a session by ID.
        
        Args:
            session_id: The session ID.
        
        Returns:
            The session document, or None.
        """
        if self.collection is None:
            return None
        
        try:
            return self.collection.find_one({"session_id": session_id})
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None
    
    def get_user_sessions(
        self,
        user_id: str,
        limit: int = 50,
        include_messages: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Get sessions for a user.
        
        Args:
            user_id: The user ID.
            limit: Maximum sessions to return.
            include_messages: Whether to include message content.
            start_date: Optional filter by start date.
            end_date: Optional filter by end date.
        
        Returns:
            List of session documents.
        """
        if self.collection is None:
            return []
        
        query = {"user_id": user_id}
        
        if start_date or end_date:
            query["started_at"] = {}
            if start_date:
                query["started_at"]["$gte"] = start_date.isoformat()
            if end_date:
                query["started_at"]["$lte"] = end_date.isoformat()
        
        projection = None
        if not include_messages:
            projection = {"messages": 0}
        
        try:
            sessions = list(
                self.collection.find(query, projection)
                .sort("started_at", -1)
                .limit(limit)
            )
            return sessions
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []
    
    def get_sessions_for_review(
        self,
        user_ids: list[str],
        only_flagged: bool = False,
        only_unreviewed: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get sessions for session audit.
        
        Args:
            user_ids: List of user IDs to review.
            only_flagged: Only return flagged sessions.
            only_unreviewed: Only return unreviewed sessions.
            limit: Maximum sessions to return.
        
        Returns:
            List of session documents.
        """
        if self.collection is None:
            return []
        
        query = {"user_id": {"$in": user_ids}}
        
        if only_flagged:
            query["flagged"] = True
        
        if only_unreviewed:
            query["reviewed_by"] = None
        
        try:
            sessions = list(
                self.collection.find(query)
                .sort("started_at", -1)
                .limit(limit)
            )
            return sessions
        except Exception as e:
            logger.error(f"Failed to get sessions for review: {e}")
            return []
    
    # ==================== Session Review ====================
    
    def flag_session(
        self,
        session_id: str,
        flagged: bool = True,
        reason: Optional[str] = None,
    ) -> bool:
        """Flag or unflag a session.
        
        Args:
            session_id: The session to flag.
            flagged: Whether to flag or unflag.
            reason: Optional reason for flagging.
        
        Returns:
            True if successful.
        """
        if self.collection is None:
            return False
        
        update = {"flagged": flagged}
        if reason:
            update["flag_reason"] = reason
        
        try:
            result = self.collection.update_one(
                {"session_id": session_id},
                {"$set": update}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to flag session: {e}")
            return False
    
    def mark_reviewed(
        self,
        session_id: str,
        reviewer_id: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Mark a session as reviewed.
        
        Args:
            session_id: The session to mark.
            reviewer_id: The parent/admin who reviewed.
            notes: Optional review notes.
        
        Returns:
            True if successful.
        """
        if self.collection is None:
            return False
        
        now = datetime.now(timezone.utc)
        
        try:
            result = self.collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "reviewed_by": reviewer_id,
                        "reviewed_at": now.isoformat(),
                        "notes": notes,
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to mark session reviewed: {e}")
            return False
    
    # ==================== Statistics ====================
    
    def get_session_stats(
        self,
        user_id: Optional[str] = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get session statistics.
        
        Args:
            user_id: Optional filter by user.
            days: Number of days to include.
        
        Returns:
            Dictionary with session statistics.
        """
        if self.collection is None:
            return {"error": "Collection not available"}
        
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        match_stage = {"started_at": {"$gte": cutoff}}
        if user_id:
            match_stage["user_id"] = user_id
        
        try:
            pipeline = [
                {"$match": match_stage},
                {
                    "$group": {
                        "_id": "$user_id" if not user_id else None,
                        "total_sessions": {"$sum": 1},
                        "total_messages": {"$sum": "$message_count"},
                        "flagged_sessions": {
                            "$sum": {"$cond": ["$flagged", 1, 0]}
                        },
                        "reviewed_sessions": {
                            "$sum": {"$cond": [{"$ne": ["$reviewed_by", None]}, 1, 0]}
                        },
                        "avg_messages_per_session": {"$avg": "$message_count"},
                    }
                },
            ]
            
            results = list(self.collection.aggregate(pipeline))
            
            if not results:
                return {
                    "total_sessions": 0,
                    "total_messages": 0,
                    "flagged_sessions": 0,
                    "reviewed_sessions": 0,
                    "avg_messages_per_session": 0,
                }
            
            stats = results[0]
            stats.pop("_id", None)
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            return {"error": str(e)}
    
    def get_tool_usage_stats(
        self,
        user_id: Optional[str] = None,
        days: int = 30,
    ) -> dict[str, int]:
        """Get tool usage statistics from sessions.
        
        Args:
            user_id: Optional filter by user.
            days: Number of days to include.
        
        Returns:
            Dictionary mapping tool names to usage counts.
        """
        if self.collection is None:
            return {}
        
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        match_stage = {"started_at": {"$gte": cutoff}}
        if user_id:
            match_stage["user_id"] = user_id
        
        try:
            pipeline = [
                {"$match": match_stage},
                {"$unwind": "$tools_used"},
                {
                    "$group": {
                        "_id": "$tools_used",
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"count": -1}},
            ]
            
            results = list(self.collection.aggregate(pipeline))
            return {r["_id"]: r["count"] for r in results}
            
        except Exception as e:
            logger.error(f"Failed to get tool usage stats: {e}")
            return {}
    
    def export_session(self, session_id: str) -> Optional[str]:
        """Export a session as formatted text.
        
        Args:
            session_id: The session to export.
        
        Returns:
            Formatted session transcript, or None.
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        lines = [
            f"Session Export",
            f"==============",
            f"Session ID: {session.get('session_id')}",
            f"User ID: {session.get('user_id')}",
            f"Started: {session.get('started_at')}",
            f"Ended: {session.get('ended_at') or 'Active'}",
            f"Messages: {session.get('message_count', 0)}",
            f"Tools Used: {', '.join(session.get('tools_used', []))}",
            f"Flagged: {'Yes' if session.get('flagged') else 'No'}",
            "",
            "Messages:",
            "---------",
        ]
        
        for msg in session.get("messages", []):
            role = msg.get("role", "unknown").upper()
            timestamp = msg.get("timestamp", "")
            content = msg.get("content", "")
            tools = msg.get("tool_calls", [])
            
            lines.append(f"[{timestamp}] {role}:")
            lines.append(content)
            if tools:
                lines.append(f"  (Tools: {', '.join(tools)})")
            lines.append("")
        
        return "\n".join(lines)


