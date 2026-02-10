# Agent Orchestrator Module
"""Main agent orchestrator that combines all memory systems."""
from typing import List, Dict, Optional
from datetime import datetime, timezone

from memory_system import (
    ShortTermMemory,
    EpisodicMemory,
    SemanticMemory,
    QueryRouter,
    SystemPromptsManager,
)
from utils import LLMClient
from time_management import TaskManager, ReminderManager, TimeTracker


class AgenticOrchestrator:
    """Main orchestrator for the agentic memory system."""

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.router = QueryRouter()
        self.system_prompts = SystemPromptsManager()
        self.llm = LLMClient()
        self.tasks = TaskManager()
        self.reminders = ReminderManager()
        self.time_tracker = TimeTracker()

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
        """
        # Generate session ID if not provided
        if not session_id:
            session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Route the query to determine intent
        routing = await self.router.route_query(user_query)
        intent = routing["intent"]

        # Gather information from memory systems
        memories = await self._gather_memories(routing, user_query, session_id)

        # Build system prompt with user preferences
        system_prompt = await self._build_system_prompt(memories)

        # Generate response using LLM
        answer = await self._generate_response(
            user_query, memories, system_prompt, intent
        )

        # Add message to short-term memory
        self.short_term.add_message("user", user_query)
        self.short_term.add_message("assistant", answer)

        # Commit to episodic memory
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
        await self._detect_and_store_facts(user_query, answer, session_id)

        return {
            "answer": answer,
            "sources": memories.get("sources", []),
            "memories": memories.get("retrieved", {}),
            "session_id": session_id,
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
        """Query semantic memory for relevant facts.

        Args:
            query: Query string

        Returns:
            List of relevant facts
        """
        # For location-based queries, return all location facts
        if "where" in query.lower() or "location" in query.lower():
            facts = await self.semantic.get_facts_by_category("location")
            if facts:
                return facts

        # For birthday queries
        if "birthday" in query.lower():
            facts = await self.semantic.get_facts_by_category("user")
            if facts:
                # Filter for birthday-related facts
                birthday_facts = [f for f in facts if "birthday" in f.get("key", "").lower()]
                if birthday_facts:
                    return birthday_facts

        # For other queries, look up specific facts
        if "name" in query.lower():
            name = await self.semantic.get_user_name()
            if name:
                return [{"key": "user_name", "value": name}]
        elif "tech" in query.lower() or "stack" in query.lower():
            stack = await self.semantic.get_tech_stack()
            if stack:
                return [{"key": "tech_stack", "value": stack}]

        return []

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
        filters = {"session_id": session_id} if session_id else None
        events = await self.episodic.vector_search(query, filters)
        return events

    async def _query_time_data(self, query: str) -> Dict:
        """Query time tracking data.

        Args:
            query: Query string

        Returns:
            Time tracking data
        """
        # For now, return recent tasks
        tasks = await self.tasks.list_tasks(limit=5)
        return {"recent_tasks": tasks}

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

        # Add memory context
        memory_context = []
        if memories.get("retrieved", {}).get("semantic"):
            memory_context.append("User Facts:")
            for fact in memories["retrieved"]["semantic"]:
                memory_context.append(f"- {fact.get('key', '')}: {fact.get('value', '')}")

        if memories.get("retrieved", {}).get("short_term"):
            memory_context.append("\nRecent Conversation:")
            for msg in memories["retrieved"]["short_term"][-5:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if content:
                    memory_context.append(f"- {role}: {content[:100]}...")

        if memories.get("retrieved", {}).get("time"):
            memory_context.append("\nTime Tracking:")
            for task in memories["retrieved"]["time"].get("recent_tasks", []):
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

        # Add conversation history from short-term memory
        for msg in self.short_term.get_recent_messages(5):
            messages.append(msg)

        # Add user query
        messages.append({"role": "user", "content": user_query})

        # Add intent information for context
        intent_str = f"\n\nUser Intent: {intent.get('intent', 'unknown')}"
        intent_str += f"\nReasoning: {intent.get('reasoning', 'N/A')}"
        messages.append({"role": "system", "content": intent_str})

        response = await self.llm.generate(messages, temperature=0.7, max_tokens=1000)
        return response or "I'm not sure how to answer that."

    async def update_user_preference(self, key: str, value: str) -> str:
        """Update a user preference.

        Args:
            key: Preference key
            value: Preference value

        Returns:
            Fact ID
        """
        return await self.semantic.add_fact(
            category="user",
            key=key,
            value=value,
            confidence=1.0,
            metadata={"preference": True},
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
        - Relationships (family, friends, colleagues)
        - Personas (personal preferences, communication style)
        - Projects (current work, ongoing projects)
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
        fact_detection_prompt = """Analyze the user's message and identify any important information that should be remembered.

Important information includes:
- Important dates (birthdays, anniversaries, deadlines)
- Relationships (who is related to whom, who's a friend/colleague)
- Personas (personal preferences, communication style, habits)
- Projects (current work, ongoing projects, tech stack)
- Locations (where things are kept, home address)
- Contact information (phone, email, address)
- Important facts about people (names, nicknames, titles)

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

Examples:
- "My birthday is Nov 5, 1981" -> {{"category": "date", "key": "birthday", "value": "November 5, 1981", "confidence": 0.95}}
- "My wife is Sarah" -> {{"category": "relationship", "key": "spouse", "value": "Sarah", "confidence": 0.9}}
- "My son is John" -> {{"category": "relationship", "key": "son", "value": "John", "confidence": 0.9}}
- "I'm working on the AI project using Python" -> {{"category": "project", "key": "current_project", "value": "AI project with Python", "confidence": 0.85}}
- "My keys are under the table" -> {{"category": "location", "key": "keys_location", "value": "under the table", "confidence": 0.9}}
- "My phone number is 555-1234" -> {{"category": "contact", "key": "phone", "value": "555-1234", "confidence": 0.9}}
"""

        messages = [
            {"role": "system", "content": fact_detection_prompt.format(user_query=user_query)},
            {"role": "user", "content": "Identify any important facts from the message above."},
        ]

        try:
            response = await self.llm.generate(messages, temperature=0.1, max_tokens=500)

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
                                await self.semantic.add_fact(
                                    category=category,
                                    key=key,
                                    value=value,
                                    confidence=confidence,
                                )
        except Exception:
            pass

    async def close(self):
        """Close all clients and connections."""
        await self.episodic.close()
        await self.router.close()
        await self.llm.close()
