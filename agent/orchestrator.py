# Agent Orchestrator Module
"""Main agent orchestrator that combines all memory systems."""
from typing import List, Dict, Optional
from datetime import datetime, timezone
import time
import asyncio

from memory_system import (
    ShortTermMemory,
    EpisodicMemory,
    SemanticMemory,
    QueryRouter,
    SystemPromptsManager,
    Bootstrapper,
)
from services import LLMClient, EmbeddingClient
from timemgmt import TaskManager, ReminderManager, TimeTracker


class OrchestratorLogger:
    """Logger for orchestrator stages with timing and metrics."""

    def __init__(self):
        self.stages: List[Dict] = []
        self.start_time: float = 0

    def start(self):
        """Start timing."""
        self.start_time = time.time()

    def log_stage(self, stage: str, details: Optional[Dict] = None):
        """Log a stage with timing."""
        elapsed = time.time() - self.start_time
        self.stages.append({
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "details": details or {}
        })
        print(f"[{stage}] elapsed={elapsed:.3f}s | {details}")

    def get_summary(self) -> Dict:
        """Get summary of all stages."""
        total_time = time.time() - self.start_time
        return {
            "total_time_seconds": round(total_time, 3),
            "stages": self.stages,
            "tokens_per_second": self._calculate_tps()
        }

    def _calculate_tps(self) -> Optional[float]:
        """Calculate tokens per second if we have token info."""
        total_tokens = sum(s.get("details", {}).get("tokens", 0) for s in self.stages)
        total_time = time.time() - self.start_time
        if total_tokens > 0 and total_time > 0:
            return round(total_tokens / total_time, 2)
        return None


class AgenticOrchestrator:
    """Main orchestrator for the agentic memory system."""

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.router = QueryRouter()
        self.system_prompts = SystemPromptsManager()
        self.llm = LLMClient()
        self.embedding_client = EmbeddingClient()
        self.tasks = TaskManager()
        self.reminders = ReminderManager()
        self.time_tracker = TimeTracker()
        self.logger = OrchestratorLogger()
        self.bootstrapper: Optional[Bootstrapper] = None
        self.bootstrap_prompt: Optional[str] = None

    async def process_query(self, user_query: str, session_id: str = None, commit_memories: bool = True) -> Dict:
        """Process a user query using all memory systems.

        Args:
            user_query: The user's input query
            session_id: Optional session identifier
            commit_memories: Whether to commit memories to long-term storage (default: True)

        Returns:
            Response dictionary with:
                - answer: The generated answer
                - sources: Sources of information
                - memories: Retrieved memories
                - session_id: Session identifier
                - timing: Timing information for each stage
        """
        from datetime import datetime

        self.logger.start()

        # Check if this is a test command (skip memory commitment)
        is_test_command = user_query.strip().startswith("/test")
        if is_test_command:
            commit_memories = False
            # Remove the /test prefix for processing
            user_query = user_query.strip()[5:].strip()

        # Generate session ID if not provided
        if not session_id:
            session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Route the query to determine intent
        self.logger.log_stage("intent_detection", {"query_length": len(user_query)})
        routing = await self.router.route_query(user_query)
        intent = routing["intent"]
        self.logger.log_stage("intent_complete", {"intent": intent.get("intent", "unknown")})

        # Handle web_search intent - execute skill and feed results to LLM
        search_results = None
        if intent.get("intent") == "web_search":
            self.logger.log_stage("web_search", {"search_query": routing.get("query", user_query)})
            search_results = await self._execute_web_search(routing.get("query", user_query))
            self.logger.log_stage("web_search_complete", {"results_length": len(search_results)})

        # Gather information from memory systems
        self.logger.log_stage("memory_gathering", {"memory_systems": routing.get("memory_systems", [])})
        memories = await self._gather_memories(routing, user_query, session_id)
        self.logger.log_stage("memory_complete", {"sources": memories.get("sources", [])})

        # Inject web search results into memories if available
        if search_results:
            memories["retrieved"]["web_search"] = search_results
            memories["sources"].append("web search")

        # Build system prompt with user preferences
        self.logger.log_stage("prompt_building", {"memories_count": len(memories.get("retrieved", {}))})
        system_prompt = await self._build_system_prompt(memories)
        self.logger.log_stage("prompt_complete", {"prompt_length": len(system_prompt)})

        # If the query is about time/date, override the user query to include the current date
        if intent.get("intent") == "time" or "today" in user_query.lower() or "current" in user_query.lower():
            current_time = datetime.now(timezone.utc)
            current_date_str = current_time.strftime("%B %d, %Y")
            current_day = current_time.strftime("%A")
            user_query = f"[CURRENT DATE: {current_day}, {current_date_str}] {user_query}"

        # Generate response using LLM
        self.logger.log_stage("llm_generation", {"prompt_length": len(system_prompt)})
        answer = await self._generate_response(
            user_query, memories, system_prompt, intent
        )
        self.logger.log_stage("llm_complete", {"response_length": len(answer)})

        # Add message to short-term memory (always add to short-term for conversation context)
        self.short_term.add_message("user", user_query)
        self.short_term.add_message("assistant", answer)

        # Commit to episodic memory (optional - controlled by commit_memories flag)
        if commit_memories:
            self.logger.log_stage("committing_episodic", {"event_count": 2})
            asyncio.create_task(self._commit_to_episodic_background(user_query, answer))
        else:
            self.logger.log_stage("committing_episodic", {"skipped": True, "reason": "test command"})

        # Detect and store any facts from the user query (optional - controlled by commit_memories flag)
        if commit_memories:
            self.logger.log_stage("fact_detection", {"query_length": len(user_query)})
            asyncio.create_task(self._detect_and_store_facts_background(user_query, answer))
        else:
            self.logger.log_stage("fact_detection", {"skipped": True, "reason": "test command"})

        summary = self.logger.get_summary()
        summary["answer_length"] = len(answer)
        summary["sources"] = memories.get("sources", [])

        return {
            "answer": answer,
            "sources": memories.get("sources", []),
            "memories": memories.get("retrieved", {}),
            "session_id": session_id,
            "timing": summary,
            "is_test_command": is_test_command,
        }

    async def _commit_to_episodic_background(self, user_query: str, answer: str) -> None:
        """Commit events to episodic memory in the background (non-blocking)."""
        try:
            await self.episodic.add_event(
                role="user",
                content=user_query,
            )
            await self.episodic.add_event(
                role="assistant",
                content=answer,
            )
        except Exception as e:
            print(f"Error committing to episodic memory: {e}")

    async def _detect_and_store_facts_background(self, user_query: str, answer: str) -> None:
        """Detect and store facts in the background (non-blocking)."""
        try:
            # Generate a session ID for fact detection
            from datetime import datetime
            session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            await self._detect_and_store_facts(user_query, answer, session_id)
            
            # Trigger bootstrap update after fact detection
            await self.trigger_bootstrap_update()
        except Exception as e:
            print(f"Error detecting/storing facts: {e}")

    async def _gather_memories(
        self, routing: Dict, user_query: str, session_id: str
    ) -> Dict:
        """Gather information from all memory systems.

        Args:
            routing: Routing information from query router
            user_query: Original user query
            session_id: Session identifier

        Returns:
            Dictionary with retrieved memories and sources
        """
        memories = {"sources": [], "retrieved": {}}

        if "semantic" in routing["memory_systems"]:
            facts = await self._query_semantic_memory(routing["query"])
            if facts:
                memories["retrieved"]["semantic"] = facts
                memories["sources"].append("semantic memory")

        if "short_term" in routing["memory_systems"]:
            context = self.short_term.get_context()
            if context:
                memories["retrieved"]["short_term"] = context
                memories["sources"].append("short-term memory")

        if "episodic" in routing["memory_systems"]:
            events = await self._query_episodic_memory(routing["query"], session_id)
            if events:
                # Enhance recalled events with time context for the LLM
                current_time = datetime.now(timezone.utc)
                enhanced_events = self._enhance_recall_with_time(events, current_time)
                memories["retrieved"]["episodic"] = enhanced_events
                memories["sources"].append("episodic memory (time-enhanced)")

        if "time" in routing["memory_systems"]:
            time_data = await self._query_time_data(routing["query"])
            if time_data:
                memories["retrieved"]["time"] = time_data
                memories["sources"].append("time tracking")

        return memories

    async def _query_semantic_memory(self, query: str) -> List[Dict]:
        """Query semantic memory for relevant facts using vector search.

        Args:
            query: Query string

        Returns:
            List of relevant facts
        """
        # Use vector search for semantic memory - it will find relevant facts based on similarity
        # Don't filter by category - let the vector search determine relevance
        facts = await self.semantic.vector_search(query)
        return facts

    async def _query_episodic_memory(
        self, query: str, session_id: str
    ) -> List[Dict]:
        """Query episodic memory for relevant events.

        Args:
            query: Query string
            session_id: Session identifier

        Returns:
            List of relevant events
        """
        # Don't filter by session_id for general queries - we want all relevant memories
        # Only filter by session_id if explicitly provided
        filters = None
        events = await self.episodic.vector_search(query, filters)
        return events

    def _ensure_utc_datetime(self, dt: datetime) -> datetime:
        """Ensure a datetime is timezone-aware and in UTC.
        
        Args:
            dt: The datetime to convert
            
        Returns:
            UTC timezone-aware datetime
        """
        if dt is None:
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            # If timezone-naive, assume it's UTC
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _enhance_recall_with_time(self, events: List[Dict], current_time: datetime) -> List[Dict]:
        """Enhance recalled events with time context for the LLM.

        This method processes retrieved memories and adds time-based context
        to help the LLM make time-based realizations about the data.

        Args:
            events: List of events from episodic memory
            current_time: Current UTC datetime for time calculations

        Returns:
            List of events with enhanced time context
        """
        enhanced_events = []
        
        for event in events:
            event_copy = dict(event)
            
            # Get event timestamp (default to current time if not available)
            event_time = event.get("timestamp", current_time)
            
            # Ensure both datetimes are timezone-aware UTC
            event_time = self._ensure_utc_datetime(event_time)
            current_time = self._ensure_utc_datetime(current_time)
            
            # Calculate time relative to now
            diff = current_time - event_time
            diff_seconds = abs(diff.total_seconds())
            
            # Calculate time components
            days = int(diff_seconds // 86400)
            hours = int((diff_seconds % 86400) // 3600)
            minutes = int((diff_seconds % 3600) // 60)
            
            # Format time relative to now
            if diff.total_seconds() < 0:
                # Future event
                if days > 0:
                    time_relative = f"in {days} days"
                elif hours > 0:
                    time_relative = f"in {hours} hours"
                else:
                    time_relative = f"in {minutes} minutes"
            else:
                # Past event
                if days > 30:
                    # More than a month ago - use date
                    time_relative = event_time.strftime("%B %d, %Y")
                elif days > 0:
                    time_relative = f"{days} day{'s' if days != 1 else ''} ago"
                elif hours > 0:
                    time_relative = f"{hours} hour{'s' if hours != 1 else ''} ago"
                elif minutes > 0:
                    time_relative = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                else:
                    time_relative = "just now"
            
            # Add time context to event
            event_copy["time_context"] = {
                "event_timestamp": event_time.isoformat() if hasattr(event_time, 'isoformat') else str(event_time),
                "time_relative_to_now": time_relative,
                "seconds_ago": int(diff_seconds) if diff.total_seconds() >= 0 else -1,
                "is_recent": diff_seconds < 3600,  # Within the last hour
                "is_today": event_time.date() == current_time.date() if hasattr(event_time, 'date') else False
            }
            
            enhanced_events.append(event_copy)
        
        return enhanced_events

    def _format_time_relative_to_now(self, dt: datetime, now: datetime) -> str:
        """Format a datetime relative to now for human understanding.
        
        Args:
            dt: The datetime to format
            now: The current datetime (UTC)
            
        Returns:
            Human-readable time relative string (e.g., "2 hours ago", "in 3 days")
        """
        from datetime import timedelta
        
        # Ensure both datetimes are timezone-aware UTC
        dt = self._ensure_utc_datetime(dt)
        now = self._ensure_utc_datetime(now)
        
        diff = now - dt
        diff_seconds = abs(diff.total_seconds())
        
        # Calculate time components
        days = int(diff_seconds // 86400)
        hours = int((diff_seconds % 86400) // 3600)
        minutes = int((diff_seconds % 3600) // 60)
        
        if diff.total_seconds() < 0:
            # Future time
            if days > 0:
                return f"in {days} days" if days < 7 else f"in {days} days ({dt.strftime('%B %d')})"
            elif hours > 0:
                return f"in {hours} hours"
            else:
                return f"in {minutes} minutes"
        else:
            # Past time
            if days > 30:
                # More than a month ago - use date
                return dt.strftime("%B %d, %Y")
            elif days > 0:
                return f"{days} day{'s' if days != 1 else ''} ago"
            elif hours > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif minutes > 0:
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                return "just now"

    async def _query_time_data(self, query: str) -> Dict:
        """Query time tracking data with temporal context.

        Args:
            query: Query string

        Returns:
            Time tracking data with relative time information
        """
        from datetime import datetime, timedelta

        # Get current UTC time (stored as ISODate in MongoDB)
        current_time = datetime.now(timezone.utc)
        
        # Format current date/time for display
        current_date_str = current_time.strftime("%B %d, %Y at %I:%M %p UTC")
        
        # Get current day of week
        day_of_week = current_time.strftime("%A")
        
        # Get tasks - including upcoming ones
        tasks = await self.tasks.list_tasks(limit=20)
        
        # Filter for upcoming tasks (due within next 7 days)
        tomorrow = current_time + timedelta(days=1)
        upcoming_tasks = [
            t for t in tasks 
            if t.get("due_date") and t.get("due_date") <= tomorrow
        ]
        
        # Get active time tracking sessions
        active_sessions = await self.time_tracker.get_active_sessions()
        
        # Calculate time relative to now for each task/session
        tasks_with_time_context = []
        for task in tasks:
            task_copy = dict(task)
            created_at = task.get("created_at", current_time)
            task_copy["time_relative"] = self._format_time_relative_to_now(created_at, current_time)
            if task.get("due_date"):
                task_copy["due_relative"] = self._format_time_relative_to_now(task["due_date"], current_time)
            tasks_with_time_context.append(task_copy)
        
        sessions_with_time_context = []
        for session in active_sessions:
            session_copy = dict(session)
            session_copy["duration_minutes"] = round(session.get("duration_seconds", 0) / 60, 2)
            start_relative = self._format_time_relative_to_now(session.get("start_time", current_time), current_time)
            session_copy["started_relative"] = start_relative
            sessions_with_time_context.append(session_copy)
        
        return {
            "recent_tasks": tasks_with_time_context[:5],
            "upcoming_tasks": upcoming_tasks,
            "current_date": current_date_str,
            "current_day": day_of_week,
            "current_timestamp": current_time.isoformat(),
            "time_relative_context": {
                "now_utc": current_time.isoformat(),
                "now_formatted": f"{day_of_week}, {current_time.strftime('%B %d, %Y at %I:%M %p UTC')}",
                "active_sessions_count": len(active_sessions),
                "active_sessions_with_time": sessions_with_time_context
            }
        }

    async def _execute_web_search(self, search_query: str) -> str:
        """Execute the web_search skill to search the web via SearXNG.

        Args:
            search_query: The search query extracted from user intent

        Returns:
            Formatted search results as a string
        """
        try:
            from skills.system.web_search import execute as web_search_execute
            results = await web_search_execute(search_query)
            return results
        except Exception as e:
            print(f"Error executing web search: {e}")
            return f"Web search failed: {str(e)}"

    async def _build_system_prompt(self, memories: Dict) -> str:
        """Build a system prompt using user preferences and memories.

        Args:
            memories: Retrieved memories

        Returns:
            System prompt string
        """
        from datetime import datetime

        # Get user preferences
        preferences = await self.system_prompts.get_user_preferences_context()

        # Build context for prompt with current date
        current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
        context = {
            "preferences": preferences,
            "current_date": current_date,
        }

        # Get base system prompt
        base_prompt = await self.system_prompts.build_system_prompt(context)
        
        # Add bootstrap prompt content if available
        if self.bootstrap_prompt:
            base_prompt = f"{base_prompt}\n\n## LONG-TERM MEMORY (Bootstrap)\nThis section contains important long-term information about the user that persists across sessions.\n\n{self.bootstrap_prompt}"
        
        # Add instruction to not output JSON for responses
        base_prompt = f"{base_prompt}\n\nIMPORTANT: When responding to the user, always use natural language. Do not output JSON or any other structured data format unless explicitly asked to do so."

        # Add memory context
        memory_context = []
        if memories.get("retrieved", {}).get("semantic"):
            memory_context.append("User Facts:")
            
            # Handle location facts - sort by timestamp and only show most recent
            location_facts = []
            other_facts = []
            for fact in memories["retrieved"]["semantic"]:
                if fact.get("key", "").lower().endswith("_location") or "location" in fact.get("key", "").lower():
                    location_facts.append(fact)
                else:
                    other_facts.append(fact)
            
            # Sort location facts by timestamp (most recent first) and only include the most recent
            location_facts.sort(key=lambda x: x.get("created_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
            for fact in location_facts[:1]:  # Only include most recent location
                memory_context.append(f"- {fact.get('key', '')}: {fact.get('value', '')}")
            
            # Include all other facts
            for fact in other_facts:
                memory_context.append(f"- {fact.get('key', '')}: {fact.get('value', '')}")

        if memories.get("retrieved", {}).get("short_term"):
            memory_context.append("\nRecent Conversation:")
            for msg in memories["retrieved"]["short_term"][-5:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if content:
                    memory_context.append(f"- {role}: {content[:100]}...")

        if memories.get("retrieved", {}).get("time"):
            time_data = memories["retrieved"]["time"]
            memory_context.append("\n=== CURRENT DATE AND TIME (UTC) ===")
            memory_context.append(f"Current UTC Timestamp: {time_data.get('current_timestamp', '')}")
            memory_context.append(f"Current Date/Time: {time_data.get('current_date', '')}")
            
            # Add temporal context for the LLM
            time_relative = time_data.get("time_relative_context", {})
            if time_relative:
                memory_context.append(f"Active Time Tracking Sessions: {time_relative.get('active_sessions_count', 0)}")
                memory_context.append("")
                memory_context.append("=== TIME RELATIVE CONTEXT ===")
                memory_context.append(f"Current moment (UTC): {time_relative.get('now_utc', '')}")
                memory_context.append(f"Formatted for user: {time_relative.get('now_formatted', '')}")
            
            memory_context.append("")
            memory_context.append("=== TIME-ENHANCED TASKS ===")
            for task in time_data.get("recent_tasks", []):
                task_name = task.get('title', 'Unknown Task')
                task_time = task.get('time_relative', 'created recently')
                due_relative = task.get('due_relative', '')
                memory_context.append(f"- {task_name} ({task_time}")
                if due_relative:
                    memory_context.append(f", due: {due_relative})")
                else:
                    memory_context.append(")")
            
            memory_context.append("")
            memory_context.append("IMPORTANT: All timestamps above are stored in MongoDB as UTC ISODate. Use the current UTC time as your reference point for time-based reasoning.")

        if memories.get("retrieved", {}).get("web_search"):
            web_results = memories["retrieved"]["web_search"]
            memory_context.append("\n=== WEB SEARCH RESULTS ===")
            memory_context.append(web_results)
            memory_context.append("\nINSTRUCTION: The above are web search results. Summarize the key findings in a clear, helpful way for the user. Include relevant URLs when citing sources. If the results don't contain useful information, let the user know.")

        if memory_context:
            return f"{base_prompt}\n\n## Context:\n" + "\n".join(memory_context)
        return base_prompt

    async def _generate_response(
        self,
        user_query: str,
        memories: Dict,
        system_prompt: str,
        intent: Dict,
    ) -> str:
        """Generate a response using the LLM.

        Args:
            user_query: Original user query
            memories: Retrieved memories
            system_prompt: System prompt
            intent: Intent classification

        Returns:
            Generated response string
        """
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add current date/time as a dedicated system message if time data is available
        if memories.get("retrieved", {}).get("time"):
            time_data = memories["retrieved"]["time"]
            current_day = time_data.get("current_day", "")
            current_date = time_data.get("current_date", "")
            date_message = f"IMPORTANT: The current date and time is {current_day}, {current_date}. Always use this date when answering questions about today, now, or the current time."
            messages.append({"role": "system", "content": date_message})

        # Add conversation history from short-term memory
        for msg in self.short_term.get_recent_messages(5):
            messages.append(msg)

        # Add user query
        messages.append({"role": "user", "content": user_query})

        # Add intent information for context (but not as system message to avoid JSON formatting)
        intent_str = f"\n\nUser Intent: {intent.get('intent', 'unknown')}"
        intent_str += f"\nReasoning: {intent.get('reasoning', 'N/A')}"
        messages.append({"role": "user", "content": f"User query context: {intent_str}"})

        response = await self.llm.generate(messages, temperature=0, max_tokens=None)
        if not response:
            print("Warning: LLM returned empty response, using fallback")
            return "I'm not sure how to answer that."
        return response

    async def update_user_preference(self, key: str, value: str) -> str:
        """Update a user preference.

        Args:
            key: Preference key
            value: Preference value

        Returns:
            Fact ID
        """
        # Generate embedding for the preference
        preference_text = f"{key}: {value}"
        embedding = await self.embedding_client.generate_embedding(preference_text)
        
        return await self.semantic.add_fact(
            category="user",
            key=key,
            value=value,
            confidence=1.0,
            metadata={"preference": True},
            embedding=embedding,
        )

    async def delete_facts(self, query: Dict) -> Dict:
        """Delete facts matching a query and return proof.

        Args:
            query: MongoDB query to match facts to delete

        Returns:
            Dictionary with deleted facts and count
        """
        deleted_facts = await self.semantic.delete_facts_by_query(query)
        return {
            "deleted_facts": deleted_facts,
            "count": len(deleted_facts),
        }

    async def _detect_and_store_facts(self, user_query: str, answer: str, session_id: str) -> None:
        """Detect important facts from user queries and store them in semantic memory using LLM.

        This method identifies and stores important information including:
        - Important dates (birthdays, anniversaries)
        - Relationships (who is related to whom, who's a friend/colleague)
        - Personas (personal preferences, communication style, habits)
        - Projects (current work, ongoing projects, tech stack)
        - Location facts (where things are kept)
        - Contact information (phone, email, address)

        Args:
            user_query: The user's input query
            answer: The AI's response
            session_id: Session identifier
        """
        if not user_query:
            return

        # Use LLM to determine if user is providing an important fact
        fact_detection_prompt = """Analyze the user's message and identify any important personal or factual information that should be remembered.

IMPORTANT: Extract ALL important information about:
1. People - names, relationships (daughter, son, wife, husband, friend, colleague, etc.)
2. Dates - birthdays, anniversaries, deadlines, important dates
3. Projects - current work, ongoing projects, tech stack
4. Preferences - favorite things, habits, likes/dislikes
5. Contact info - phone, email, address
6. Location info - where things are kept

User Message: {user_query}

Respond in JSON format:
{{
    "type": "fact"|"not_fact",
    "facts": [
        {{
            "category": "date|relationship|persona|project|location|contact|other",
            "key": "unique_fact_key",
            "value": "the_fact_value",
            "confidence": 0.0-1.0
        }}
    ]
}}

Rules for extraction:
- Extract information about ANY person mentioned, including their name and relationship to user
- Extract ANY important date mentioned (especially if it's the user's or their family member's birthday)
- Extract any project or work the user is doing
- Extract any preference or habit the user mentions
- Always use descriptive, unique keys (e.g., "child_name_daughter", "birthday_spouse", "current_project")
- Only extract information that is explicitly stated, not inferred
"""

        messages = [
            {"role": "system", "content": fact_detection_prompt.format(user_query=user_query)},
            {"role": "user", "content": "Identify all important facts from the message above."},
        ]

        try:
            response = await self.llm.generate(messages, temperature=0, max_tokens=None)

            if response:
                import json
                import re
                
                # Try to parse JSON from response
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    fact_data = json.loads(json_match.group())
                    fact_type = fact_data.get("type", "")
                    facts = fact_data.get("facts", [])
                    
                    if fact_type == "fact" and isinstance(facts, list):
                        for fact in facts:
                            category = fact.get("category", "other")
                            key = fact.get("key", "")
                            value = fact.get("value", "")
                            confidence = fact.get("confidence", 0.9)
                            
                            if key and value:
                                # Generate embedding for the fact (key + value for better search)
                                fact_text = f"{key}: {value}"
                                embedding = await self.embedding_client.generate_embedding(fact_text)
                                
                                await self.semantic.add_fact(
                                    category=category,
                                    key=key,
                                    value=value,
                                    confidence=confidence,
                                    embedding=embedding,
                                )
        except Exception:
            pass

    async def close(self):
        """Close all clients and connections."""
        await self.episodic.close()
        await self.router.close()
        await self.llm.close()

    async def initialize_bootstrap(self) -> None:
        """Initialize the bootstrapper and load the bootstrap prompt from MongoDB.
        
        This should be called after MongoDB connection is established and before
        processing queries.
        """
        self.bootstrapper = Bootstrapper()
        self.bootstrap_prompt = await self.bootstrapper.load_bootstrap()
        print(f"[Bootstrap] Loaded bootstrap prompt ({len(self.bootstrap_prompt)} chars)")

    async def trigger_bootstrap_update(self) -> None:
        """Trigger an update of the bootstrap prompt in the background.
        
        This should be called after significant events (new facts learned,
        important conversations, etc.) to keep the SYSTEM prompt current.
        """
        if self.bootstrapper:
            asyncio.create_task(self.bootstrapper.auto_update_bootstrap())
