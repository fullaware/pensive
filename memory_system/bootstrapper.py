# Bootstrapper Module
"""Bootstrapper for loading and updating SYSTEM prompt from MongoDB."""
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorCollection

from memory_system import (
    db, 
    SystemPromptsManager,
    SemanticMemory,
    EpisodicMemory,
    Config
)
from utils import LLMClient


class Bootstrapper:
    """Handles loading and updating the SYSTEM prompt for long-term memory persistence.
    
    The bootstrapper:
    1. Loads the latest SYSTEM prompt from MongoDB on startup
    2. Gathers recent facts, tasks, and conversation summaries
    3. Updates the SYSTEM prompt with new information after conversations
    4. Maintains version history for rollback capability
    """

    def __init__(self):
        self.system_prompts = SystemPromptsManager()
        self.semantic_memory = SemanticMemory()
        self.episodic_memory = EpisodicMemory()
        self._cached_bootstrap: Optional[str] = None
        self._last_updated: Optional[datetime] = None

    async def load_bootstrap(self) -> str:
        """Load the latest bootstrap prompt from MongoDB.
        
        Returns the current SYSTEM prompt content that persists across sessions.
        If no bootstrap exists, returns an empty string.
        
        Returns:
            The bootstrap prompt content string
        """
        content = await self.system_prompts.get_bootstrap_prompt_content()
        self._cached_bootstrap = content
        self._last_updated = datetime.now(timezone.utc)
        return content or ""

    async def get_cached_bootstrap(self) -> str:
        """Get the cached bootstrap prompt.
        
        Returns:
            The cached bootstrap prompt content string
        """
        if self._cached_bootstrap is None:
            return await self.load_bootstrap()
        return self._cached_bootstrap

    async def update_bootstrap(self, new_content: str) -> str:
        """Update the bootstrap prompt with new content.
        
        Creates a new version of the bootstrap prompt in MongoDB.
        
        Args:
            new_content: The new prompt content to save
            
        Returns:
            The ObjectId of the newly created prompt document
        """
        prompt_id = await self.system_prompts.update_bootstrap_prompt(new_content)
        self._cached_bootstrap = new_content
        self._last_updated = datetime.now(timezone.utc)
        return prompt_id

    async def build_bootstrap_content(self) -> str:
        """Build the bootstrap prompt content from current data.
        
        Gathers:
        - User facts from semantic memory
        - User preferences
        - Active tasks
        - Recent conversation summaries
        
        Returns:
            Formatted bootstrap prompt content string
        """
        # Get current date/time
        current_time = datetime.now(timezone.utc)
        current_date_str = current_time.strftime("%B %d, %Y at %I:%M %p UTC")
        day_of_week = current_time.strftime("%A")

        # Build sections
        sections = [
            "# SYSTEM PROMPT - Pensive AI Agent",
            f"## Last Updated: {current_time.isoformat()}",
            f"## Current Date: {day_of_week}, {current_date_str}",
            "",
            "## USER FACTS",
        ]

        # Get facts from semantic memory
        facts = await self._get_relevant_facts()
        if facts:
            for fact in facts:
                key = fact.get("key", "unknown")
                value = fact.get("value", "")
                sections.append(f"- {key}: {value}")
        else:
            sections.append("- No user facts stored yet.")

        # Get user preferences
        sections.append("")
        sections.append("## USER PREFERENCES")
        preferences = await self.system_prompts.get_user_preferences_context()
        if preferences:
            for key, value in preferences.items():
                sections.append(f"- {key}: {value}")
        else:
            sections.append("- No user preferences stored yet.")

        # Get active tasks
        sections.append("")
        sections.append("## ACTIVE TASKS")
        tasks = await self._get_active_tasks()
        if tasks:
            for task in tasks:
                title = task.get("title", "Unknown Task")
                status = task.get("status", "pending")
                due_date = task.get("due_date")
                due_str = ""
                if due_date:
                    if hasattr(due_date, 'isoformat'):
                        due_str = f" (Due: {due_date.strftime('%B %d')})"
                    else:
                        due_str = f" (Due: {due_date})"
                sections.append(f"- {title} [{status}]{due_str}")
        else:
            sections.append("- No active tasks.")

        # Get recent conversation summaries
        sections.append("")
        sections.append("## RECENT CONVERSATIONS")
        recent_events = await self._get_recent_conversation_summary()
        if recent_events:
            sections.append(recent_events)
        else:
            sections.append("- No recent conversations.")

        # Add instructions
        sections.append("")
        sections.append("## INSTRUCTIONS FOR AI")
        sections.append("1. Read this file first when processing queries")
        sections.append("2. Use this as your long-term memory context")
        sections.append("3. Update this file when important information is learned")
        sections.append("4. Be consistent with previously stored facts and preferences")
        sections.append("5. If user corrects you, update the relevant fact in semantic memory")

        return "\n".join(sections)

    async def _get_relevant_facts(self) -> List[Dict]:
        """Get all relevant facts from semantic memory.
        
        Returns:
            List of all facts (not filtered by category - all are relevant)
        """
        try:
            facts = await self.semantic_memory.get_all_facts()
            # Return all facts - they are all potentially relevant for the SYSTEM prompt
            return facts
        except Exception as e:
            print(f"Error getting facts: {e}")
            return []

    async def _get_active_tasks(self) -> List[Dict]:
        """Get active tasks from MongoDB.
        
        Returns:
            List of active tasks
        """
        from memory_system import COLLECTION_TASKS
        
        try:
            collection = db.get_collection(COLLECTION_TASKS)
            cursor = collection.find({
                "status": {"$ne": "completed"}
            }).sort("due_date", 1).limit(10)
            
            tasks = await cursor.to_list(length=10)
            return tasks
        except Exception as e:
            print(f"Error getting tasks: {e}")
            return []

    async def _get_recent_conversation_summary(self) -> str:
        """Get a summary of recent conversations, using LLM to extract key points.
        
        The LLM summarizes the conversation history and extracts only the most
        relevant points that should be stored in the SYSTEM prompt for long-term memory.
        
        Returns:
            A formatted summary of recent conversations with key points
        """
        try:
            # Get recent events (last 10 conversations)
            events = await self.episodic_memory.get_recent_events(limit=10, event_type="conversation")
            
            if not events:
                return "- No recent conversations."
            
            # Get unique sessions
            sessions = {}
            for event in events:
                session_id = event.get("session_id", "default")
                if session_id not in sessions:
                    sessions[session_id] = []
                sessions[session_id].append(event)
            
            # Build summary using LLM for intelligent summarization
            if len(sessions) > 0:
                # Get the most recent session for summarization
                session_items = list(sessions.items())
                most_recent_session = session_items[-1][1]
                
                # Build conversation context for LLM summarization
                conversation_context = []
                for event in most_recent_session[-5:]:
                    role = event.get("role", "")
                    content = event.get("content", "")
                    if content:
                        conversation_context.append(f"{role.upper()}: {content[:500]}")
                
                if conversation_context:
                    # Create a prompt for LLM to summarize key points
                    summary_prompt = f"""Analyze this conversation and extract key points that should be remembered for long-term memory.

Recent Conversation:
{chr(10).join(conversation_context)}

Respond in JSON format with:
{{
    "summary": "brief summary of key points",
    "key_points": [
        "point 1",
        "point 2",
        "point 3"
    ],
    "important_facts": [
        "fact 1",
        "fact 2"
    ]
}}
"""
                    
                    try:
                        llm = LLMClient()
                        response = await llm.generate([
                            {"role": "system", "content": "You are a helpful assistant that extracts key points from conversations."},
                            {"role": "user", "content": summary_prompt}
                        ], temperature=0.3, max_tokens=300)
                        
                        if response:
                            import re
                            import json as json_module
                            
                            # Try to extract JSON from response
                            json_match = re.search(r'\{[\s\S]*\}', response)
                            if json_match:
                                try:
                                    data = json_module.loads(json_match.group())
                                    summary = data.get("summary", "")
                                    key_points = data.get("key_points", [])
                                    
                                    if key_points:
                                        points = "\n".join([f"- {p}" for p in key_points[:5]])
                                        return f"Summary: {summary}\n\nKey Points:\n{points}"
                                except json_module.JSONDecodeError:
                                    pass
                    except Exception as e:
                        print(f"Error with LLM summarization: {e}")
                        # Fall back to simple summary if LLM fails
                        pass
            
            # Fall back to simple session summary if LLM summarization fails
            summaries = []
            for session_id, session_events in session_items[-3:]:  # Last 3 sessions
                # Sort by timestamp
                session_events.sort(key=lambda x: x.get("timestamp", datetime.min.replace(tzinfo=timezone.utc)))
                
                # Get the most recent messages
                user_messages = [e.get("content", "") for e in session_events[-3:] if e.get("role") == "user" and e.get("content")]
                
                if user_messages:
                    summary = f"- Session {session_id[:8]}: "
                    summary += f"User: {user_messages[-1][:100]}..."
                    summaries.append(summary)
            
            if summaries:
                return "\n".join(summaries)
            return "- No recent conversations."
            
        except Exception as e:
            print(f"Error getting conversation summary: {e}")
            return "- Error retrieving conversation history."

    async def auto_update_bootstrap(self) -> str:
        """Automatically update the bootstrap prompt with current data.
        
        This should be called after significant events (new facts learned,
        tasks updated, etc.) to keep the SYSTEM prompt current.
        
        Returns:
            The ObjectId of the updated prompt document
        """
        content = await self.build_bootstrap_content()
        prompt_id = await self.update_bootstrap(content)
        return prompt_id

    async def get_bootstrap_history(self, limit: int = 5) -> List[Dict]:
        """Get the version history of the bootstrap prompt.
        
        Args:
            limit: Maximum number of versions to return
            
        Returns:
            List of bootstrap prompt documents sorted by version (newest first)
        """
        return await self.system_prompts.get_bootstrap_history(limit=limit)

    async def revert_to_version(self, version: int) -> bool:
        """Revert to a previous version of the bootstrap prompt.
        
        Args:
            version: The version number to revert to
            
        Returns:
            True if successful, False otherwise
        """
        return await self.system_prompts.revert_to_version(version)

    async def get_last_updated(self) -> Optional[datetime]:
        """Get the timestamp of the last bootstrap update.
        
        Returns:
            The last updated timestamp or None if never updated
        """
        return self._last_updated