# Agent Orchestrator Module
"""Main agent orchestrator that combines all memory systems."""
from typing import List, Dict, Optional
from datetime import datetime, timezone
import time

from memory_system import (
    ShortTermMemory,
    EpisodicMemory,
    SemanticMemory,
    QueryRouter,
    SystemPromptsManager,
)
from utils import LLMClient, EmbeddingClient
from time_management import TaskManager, ReminderManager, TimeTracker


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

    async def process_query(self, user_query: str, session_id: str = None) -> Dict:
        """Process a user query using all memory systems.

        Args:
            user_query: The user's input query
            session_id: Optional session identifier

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

        # Generate session ID if not provided
        if not session_id:
            session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Route the query to determine intent
        self.logger.log_stage("intent_detection", {"query_length": len(user_query)})
        routing = await self.router.route_query(user_query)
        intent = routing["intent"]
        self.logger.log_stage("intent_complete", {"intent": intent.get("intent", "unknown")})

        # Gather information from memory systems
        self.logger.log_stage("memory_gathering", {"memory_systems": routing.get("memory_systems", [])})
        memories = await self._gather_memories(routing, user_query, session_id)
        self.logger.log_stage("memory_complete", {"sources": memories.get("sources", [])})

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

        # Add message to short-term memory
        self.short_term.add_message("user", user_query)
        self.short_term.add_message("assistant", answer)

        # Commit to episodic memory
        self.logger.log_stage("committing_episodic", {"event_count": 2})
        await self.episodic.add_event(
            session_id=session_id,
            role="user",
            content=user_query,
        )
        await self.episodic.add_event(
            session_id=session_id,
            role="assistant",
            content=answer,
        )

        # Detect and store any facts from the user query
        self.logger.log_stage("fact_detection", {"query_length": len(user_query)})
        await self._detect_and_store_facts(user_query, answer, session_id)

        summary = self.logger.get_summary()
        summary["answer_length"] = len(answer)
        summary["sources"] = memories.get("sources", [])

        return {
            "answer": answer,
            "sources": memories.get("sources", []),
            "memories": memories.get("retrieved", {}),
            "session_id": session_id,
            "timing": summary,
        }

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
                memories["retrieved"]["episodic"] = events
                memories["sources"].append("episodic memory")

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

    async def _query_time_data(self, query: str) -> Dict:
        """Query time tracking data.

        Args:
            query: Query string

        Returns:
            Time tracking data
        """
        from datetime import datetime, timedelta

        # Get current date and time in the local timezone (America/New_York)
        current_time = datetime.now(timezone.utc)
        current_date_str = current_time.strftime("%B %d, %Y at %I:%M %p")
        
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
        
        return {
            "recent_tasks": tasks[:5],
            "upcoming_tasks": upcoming_tasks,
            "current_date": current_date_str,
            "current_day": day_of_week,
            "current_timestamp": current_time.isoformat()
        }

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
            memory_context.append("\n=== CURRENT DATE AND TIME ===")
            memory_context.append(f"Today is {time_data.get('current_day', '')}, {time_data.get('current_date', '')}")
            memory_context.append(f"(Timestamp: {time_data.get('current_timestamp', '')})")
            memory_context.append("")
            memory_context.append("Time Tracking:")
            for task in time_data.get("recent_tasks", []):
                memory_context.append(f"- Task: {task.get('title', '')}")

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
        return response or "I'm not sure how to answer that."

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
