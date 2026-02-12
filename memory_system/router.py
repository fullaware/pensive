# Query Router Module
"""Query router that determines intent and routes to appropriate memory system."""
from typing import List, Dict, Optional
from memory_system.config import Config
from utils.llm import LLMClient


class QueryRouter:
    """Routes user queries to appropriate memory systems."""

    def __init__(self):
        self.llm_client = LLMClient()

    async def determine_intent(self, user_query: str) -> Dict:
        """Determine the intent of a user query.

        Args:
            user_query: The user's input query

        Returns:
            Intent classification with:
                - intent: The type of query (fact, task, time, conversation, location, other)
                - query: The query to use for memory lookup
                - confidence: Confidence score
                - filters: Optional filters for memory systems
        """
        system_prompt = """You are an intelligent query router. Analyze the user's query and determine:
1. The intent type (fact, task, time, conversation, location, other)
2. The key information needed to answer the query
3. Any filters or context needed

Respond in JSON format with:
{
    "intent": "fact|task|time|conversation|location|other",
    "query": "query for memory lookup",
    "confidence": 0.0-1.0,
    "filters": {"optional": "filters for memory systems"},
    "reasoning": "brief explanation of intent"
}

Examples:
- "What is my name?" -> intent: fact, query: "user name"
- "Where are my keys?" -> intent: location, query: "keys location"
- "Where are my glasses?" -> intent: location, query: "glasses location"
- "What tasks are due?" -> intent: task, query: "due tasks"
- "How long did I work on X?" -> intent: time, query: "time spent on X"
- "Tell me about yesterday" -> intent: conversation, query: "yesterday"
- "What projects have we worked on?" -> intent: fact, query: "projects"
- "Tell me about our current work?" -> intent: fact, query: "current work"
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Query: {user_query}"},
        ]

        response = await self.llm_client.generate(messages, temperature=0.1, max_tokens=500)
        return self._parse_intent_response(response)

    def _parse_intent_response(self, response: Optional[str], user_query: str = "") -> Dict:
        """Parse the LLM intent response.

        Args:
            response: Raw LLM response string
            user_query: Original user query for fallback parsing

        Returns:
            Parsed intent dictionary
        """
        if not response:
            return {
                "intent": "other",
                "query": "",
                "confidence": 0.0,
                "filters": {},
                "reasoning": "No response from LLM",
            }

        # Try to extract JSON from response
        import json
        import re

        try:
            # Try to find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                # Validate that intent is present
                if "intent" in parsed:
                    return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Return with LLM reasoning as fallback
        return {
            "intent": "other",
            "query": response[:200] if response else "",
            "confidence": 0.5,
            "filters": {},
            "reasoning": f"LLM response: {response[:200]}",
        }

    async def generate_memory_query(self, user_query: str, intent: Dict) -> str:
        """Generate an optimized query for memory systems.

        Args:
            user_query: Original user query
            intent: Intent classification from determine_intent

        Returns:
            Optimized query string for memory lookup
        """
        if intent["intent"] == "fact":
            # For factual queries, extract the key information
            return intent["query"] or user_query

        elif intent["intent"] == "task":
            # For task queries, focus on task-related terms
            return intent["query"] or f"tasks {user_query}"

        elif intent["intent"] == "time":
            # For time queries, focus on time-related terms
            return intent["query"] or f"time tracking {user_query}"

        elif intent["intent"] == "conversation":
            # For conversation queries, use session context
            return intent["query"] or user_query

        else:
            # Default: return the original query
            return user_query

    async def route_query(self, user_query: str) -> Dict:
        """Route a user query to the appropriate memory systems.

        Args:
            user_query: The user's input query

        Returns:
            Routing information with:
                - intent: The determined intent
                - memory_systems: List of memory systems to query
                - query: The query to use
                - filters: Any filters to apply
        """
        intent = await self.determine_intent(user_query)
        query = await self.generate_memory_query(user_query, intent)

        # Always query all memory systems - let the AI decide what's relevant
        memory_systems = ["short_term", "episodic", "semantic"]

        return {
            "intent": intent,
            "memory_systems": memory_systems,
            "query": query,
            "filters": intent.get("filters", {}),
        }

    async def close(self):
        """Close LLM client."""
        await self.llm_client.close()