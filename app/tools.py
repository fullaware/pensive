"""Tool registration for the main agent."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Callable, Optional
import calendar
import calendar

from openai import OpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from config import (
    CONVERSATION_ID,
    DEFAULT_DECAY_SCORE,
    DEFAULT_IMPORTANCE_SCORE,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_URI,
    logger,
)
from database import agent_memory_collection
from app.memory import MemoryStore, MemoryType
from app.memory_extraction import extract_entities, extract_topics_and_keywords
from app.weather import get_weather_report
from app.auth.permissions import check_permission_or_message
from app.auth.manager import UserManager
from database import users_collection, knowledge_collection
from app.knowledge.store import KnowledgeStore


def _get_user_from_context(ctx: RunContext) -> Optional["User"]:
    """Extract user from RunContext deps."""
    if hasattr(ctx, "deps") and hasattr(ctx.deps, "current_user"):
        return ctx.deps.current_user
    return None


def register_tools(agent: Agent, log_tool_usage: Callable[[str, str], None]) -> None:
    """Register all memory-related tools with the agent."""
    
    # Initialize memory store for tools
    memory_store = None
    if agent_memory_collection is not None:
        memory_store = MemoryStore(agent_memory_collection)
        logger.info("Memory store initialized for tools")
    
    # Initialize knowledge store for tools
    knowledge_store = None
    if knowledge_collection is not None:
        knowledge_store = KnowledgeStore(knowledge_collection)
        logger.info("Knowledge store initialized for tools")

    @agent.tool
    def retrieve_context(ctx: RunContext, search_query: str = "") -> str:
        """Get recent context from the conversation history (last 20 messages and recent summaries)."""
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "retrieve_context")
        if perm_error:
            return perm_error
        
        logger.debug("retrieve_context called with search_query: %s", search_query)
        log_tool_usage("retrieve_context", f"query='{search_query}'")

        if memory_store is None:
            logger.error("Memory store is not initialized")
            return "No relevant context found due to database unavailability."

        try:
            user_id = user.id if user and user.id else None
            contexts = []
            
            # Get recent episodic conversation memories
            recent_messages = memory_store.find_by_type(
                MemoryType.EPISODIC_CONVERSATION,
                user_id=user_id,
                limit=20,
                include_shared=True,
            )
            
            seen_messages = set()
            for msg in reversed(recent_messages):
                role = msg.metadata.get("role", "unknown")
                msg_key = f"{role}: {msg.content}"
                if msg_key not in seen_messages:
                    seen_messages.add(msg_key)
                    contexts.append(msg_key)

            # Get recent summaries
            recent_summaries = memory_store.find_by_type(
                MemoryType.EPISODIC_SUMMARY,
                user_id=user_id,
                limit=3,
                include_shared=True,
            )
            for summary in recent_summaries:
                if summary.content:
                    contexts.append(f"Summary: {summary.content}")

            return "\n".join(contexts) if contexts else "No recent context found."
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"Context retrieval failed: {exc}")
            return f"Error retrieving context: {exc}"

    @agent.tool
    def search_conversations(
        ctx: RunContext,
        keywords: str,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> str:
        """Search through all past conversations by keywords, topics, entities.
        
        Uses text search on the unified memory system.
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "search_conversations")
        if perm_error:
            return perm_error
        
        logger.debug("search_conversations called with keywords: %s, limit: %s", keywords, limit)
        log_tool_usage("search_conversations", f"keywords='{keywords}', limit={limit}")

        if memory_store is None:
            logger.error("Memory store is not initialized")
            return "Database unavailable. Cannot search conversations."

        results = []
        user_id = user.id if user and user.id else None

        try:
            # Use text search on the memory store
            matching_memories = memory_store.text_search(
                query_text=keywords,
                user_id=user_id,
                memory_types=[MemoryType.EPISODIC_CONVERSATION, MemoryType.EPISODIC_SUMMARY],
                limit=limit,
            )
            
            for memory in matching_memories:
                # Skip low importance memories if threshold is set
                if memory.importance_score < min_importance:
                    continue
                    
                role = memory.metadata.get("role", "unknown")
                memory_type = memory.memory_type
                
                if memory_type == MemoryType.EPISODIC_SUMMARY.value:
                    results.append(f"Summary: {memory.content}")
                else:
                    results.append(f"{role}: {memory.content} [Importance: {memory.importance_score:.2f}]")

            if results:
                return f"Found {len(results)} relevant results for '{keywords}':\n\n" + "\n".join(results)
            return f"No conversations found matching keywords: {keywords}"
        except Exception as exc:  # pragma: no cover
            logger.error(f"Conversation search failed: {exc}")
            return f"Error searching conversations: {exc}"

    @agent.tool
    def create_research_agent(ctx: RunContext, research_topic: str, research_question: str) -> str:
        """Create and execute a sub-agent to research a specific topic using memory.
        
        This tool spawns a research agent that:
        1. Searches through all stored memories for relevant information
        2. Synthesizes findings into a comprehensive answer
        3. Returns the research results immediately (not a background task)
        
        Use this for questions that require searching through past conversations.
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "create_research_agent")
        if perm_error:
            return perm_error
        
        logger.info(f"Research agent starting: topic='{research_topic}', question='{research_question}'")
        log_tool_usage("create_research_agent", f"topic='{research_topic}'")

        if memory_store is None:
            return "Database unavailable. Cannot perform research."

        try:
            if not LLM_MODEL or not LLM_URI:
                return "LLM configuration unavailable. Cannot create research agent."

            # First, do a direct memory search to gather relevant context
            user_id = user.id if user else None
            
            # Search for relevant memories
            search_results = memory_store.text_search(
                query_text=f"{research_topic} {research_question}",
                user_id=user_id,
                memory_types=[MemoryType.EPISODIC_CONVERSATION, MemoryType.EPISODIC_SUMMARY, MemoryType.SEMANTIC_KNOWLEDGE],
                limit=20,
            )
            
            if not search_results:
                return f"No relevant information found in memory about '{research_topic}'. I don't have any stored knowledge about this topic yet."
            
            # Format the found memories for analysis
            memory_context = []
            for mem in search_results:
                role = mem.metadata.get("role", "")
                if role:
                    memory_context.append(f"[{role}]: {mem.content}")
                else:
                    memory_context.append(f"[memory]: {mem.content}")
            
            memories_text = "\n\n".join(memory_context)
            
            logger.info(f"Research agent found {len(search_results)} relevant memories")
            log_tool_usage("research_memory_search", f"found {len(search_results)} memories")
            
            # Create the research agent to analyze the findings
            # Use placeholder API key for local providers that don't require authentication
            api_key = LLM_API_KEY or "not-needed"
            research_model = OpenAIChatModel(
                model_name=LLM_MODEL,
                provider=OpenAIProvider(base_url=LLM_URI, api_key=api_key),
            )

            research_agent = Agent(
                research_model,
                system_prompt=f"""You are a research analyst. Analyze the provided memories and answer the question.

Research Topic: {research_topic}
Question: {research_question}

Based ONLY on the memories provided below, synthesize a clear, comprehensive answer.
If the memories don't contain enough information to fully answer the question, say so clearly.
Do NOT make up information - only report what's in the memories.

MEMORIES FROM DATABASE:
{memories_text}

Provide your analysis now.""",
                retries=1,
            )

            # Run the research agent
            logger.info("Executing research agent analysis...")
            research_result = research_agent.run_sync("Analyze the memories and answer the research question.")
            
            # Extract the result text
            if hasattr(research_result, 'data'):
                result_text = str(research_result.data)
            elif hasattr(research_result, 'output'):
                result_text = str(research_result.output)
            else:
                result_text = str(research_result)
            
            # Clean up the result
            result_text = result_text.strip()
            if not result_text:
                return f"Research agent completed but produced no output for '{research_topic}'."
            
            logger.info(f"Research agent completed successfully, result length: {len(result_text)}")
            
            # Store research as semantic knowledge for future reference
            extraction = extract_topics_and_keywords(result_text)
            entities = extract_entities(result_text)

            memory_store.store(
                memory_type=MemoryType.SEMANTIC_KNOWLEDGE,
                content=f"Research on {research_topic}: {result_text}",
                user_id=user_id,
                conversation_id=CONVERSATION_ID,
                importance_score=0.8,
                generate_vector=True,
                metadata={
                    "research_topic": research_topic,
                    "research_question": research_question,
                    "sources_count": len(search_results),
                    "topics": extraction.get("topics", []),
                    "keywords": extraction.get("keywords", []),
                    "entities": entities,
                },
            )
            log_tool_usage("research_stored", f"saved to semantic knowledge")

            return f"**Research Results for '{research_topic}':**\n\n{result_text}\n\n*Based on {len(search_results)} relevant memories.*"
            
        except Exception as exc:
            logger.error(f"Research agent failed: {exc}", exc_info=True)
            return f"Research agent encountered an error: {exc}"

    @agent.tool
    def summarize_memory(ctx: RunContext, message_count: int = 50, keep_messages: bool = True) -> str:
        """Summarize old messages in memory and optionally purge them."""
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "summarize_memory")
        if perm_error:
            return perm_error
        
        logger.debug("summarize_memory called with message_count: %s, keep_messages: %s", message_count, keep_messages)
        log_tool_usage("summarize_memory", f"count={message_count}, keep={keep_messages}")

        if memory_store is None:
            return "Database unavailable. Cannot summarize memory."

        try:
            user_id = user.id if user and user.id else None
            
            # Get old episodic conversations that haven't been summarized
            old_messages = memory_store.find_by_type(
                MemoryType.EPISODIC_CONVERSATION,
                user_id=user_id,
                limit=message_count,
                include_shared=False,
            )
            
            # Filter to only non-summarized messages
            old_messages = [m for m in old_messages if not m.metadata.get("summarized")]

            if not old_messages:
                return "No old messages found to summarize."

            chunks = [old_messages[i : i + 20] for i in range(0, len(old_messages), 20)]
            summaries_created = 0
            messages_summarized = 0

            for chunk in chunks:
                formatted_messages = "\n".join(
                    f"{m.metadata.get('role', 'unknown')}: {m.content}" for m in chunk
                )
                summary_prompt = (
                    "Summarize the key points and important information from the following conversation:\n\n"
                    f"{formatted_messages}"
                )

                if not LLM_URI or not LLM_MODEL:
                    return "LLM configuration unavailable. Cannot generate summaries."

                client_openai = OpenAI(base_url=LLM_URI, api_key=LLM_API_KEY or "not-needed")
                response = client_openai.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that creates concise summaries of conversations, preserving all important information.",
                        },
                        {"role": "user", "content": summary_prompt},
                    ],
                )

                summary = response.choices[0].message.content
                if summary and isinstance(summary, str):
                    # Aggregate metadata
                    all_topics, all_keywords, all_entities = [], [], []
                    source_ids = []
                    for m in chunk:
                        all_topics.extend(m.metadata.get("topics", []))
                        all_keywords.extend(m.metadata.get("keywords", []))
                        all_entities.extend(m.metadata.get("entities", []))
                        if m.id:
                            source_ids.append(m.id)

                    unique_topics = list(dict.fromkeys(all_topics))[:10]
                    unique_keywords = list(dict.fromkeys(all_keywords))[:15]

                    # Store as episodic summary
                    memory_store.store(
                        memory_type=MemoryType.EPISODIC_SUMMARY,
                        content=summary,
                        user_id=user_id,
                        conversation_id=CONVERSATION_ID,
                        importance_score=0.7,
                        generate_vector=True,
                        metadata={
                            "source_message_count": len(chunk),
                            "source_message_ids": source_ids,
                            "topics": unique_topics,
                            "keywords": unique_keywords,
                            "entities": all_entities[:10],
                        },
                    )
                    summaries_created += 1
                    messages_summarized += len(chunk)

                    # Mark source messages as summarized
                    for m in chunk:
                        if m.id:
                            memory_store.update(m.id, {"metadata.summarized": True})

                    if not keep_messages:
                        for m in chunk:
                            if m.id:
                                memory_store.delete(m.id)

            result = f"Summarized {messages_summarized} messages into {summaries_created} summaries."
            if not keep_messages:
                result += f" Deleted {messages_summarized} original messages."

            return result
        except Exception as exc:  # pragma: no cover
            logger.error(f"Memory summarization failed: {exc}")
            return f"Error summarizing memory: {exc}"

    @agent.tool
    def mark_important(ctx: RunContext, message_id: str, importance: float = 0.9) -> str:
        """Mark a specific message as important."""
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "mark_important")
        if perm_error:
            return perm_error
        
        logger.debug("mark_important called with message_id: %s, importance: %s", message_id, importance)
        log_tool_usage("mark_important", f"id={message_id}, importance={importance}")

        if memory_store is None:
            return "Database unavailable. Cannot mark message as important."

        try:
            importance = max(0.0, min(1.0, importance))
            
            # Update importance in memory store
            success = memory_store.update(message_id, {"importance_score": importance})
            
            if not success:
                return f"Message with ID {message_id} not found or could not be updated."
            
            return f"Marked message {message_id} as important (score: {importance})."
        except Exception as exc:  # pragma: no cover
            logger.error(f"Failed to mark message as important: {exc}")
            return f"Error marking message as important: {exc}"

    @agent.tool
    def remember_this(ctx: RunContext, context: str) -> str:
        """Mark the current conversation context as important for future recall.
        
        Also stores the context as semantic knowledge for easy retrieval.
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "remember_this")
        if perm_error:
            return perm_error
        
        logger.debug("remember_this called with context: %s", context)
        log_tool_usage("remember_this", context)

        if memory_store is None:
            return "Database unavailable. Cannot remember context."

        try:
            user_id = user.id if user and user.id else None
            
            # Get recent messages
            recent_messages = memory_store.find_by_type(
                MemoryType.EPISODIC_CONVERSATION,
                user_id=user_id,
                limit=5,
                include_shared=False,
            )

            if not recent_messages:
                return "No recent messages found to mark as important."

            # Mark recent messages as important
            for msg in recent_messages:
                if msg.id:
                    memory_store.update(msg.id, {
                        "importance_score": 0.9,
                        "access_count": msg.access_count + 1,
                    })

            # Also store the context as semantic knowledge for easy recall
            extraction = extract_topics_and_keywords(context)
            entities = extract_entities(context)
            
            memory_store.store(
                memory_type=MemoryType.SEMANTIC_KNOWLEDGE,
                content=f"Important: {context}",
                user_id=user_id,
                conversation_id=CONVERSATION_ID,
                importance_score=0.9,
                generate_vector=True,
                metadata={
                    "remembered_context": context,
                    "topics": extraction.get("topics", []),
                    "keywords": extraction.get("keywords", []),
                    "entities": entities,
                },
            )

            return f"Marked {len(recent_messages)} recent messages as important. Context stored: {context}."
        except Exception as exc:  # pragma: no cover
            logger.error(f"Failed to remember context: {exc}")
            return f"Error remembering context: {exc}"

    @agent.tool
    def update_display_name(ctx: RunContext, display_name: str) -> str:
        """Update the user's display name (what they prefer to be called).
        
        This tool should be used during onboarding when asking the user what they'd like to be called.
        """
        user = _get_user_from_context(ctx)
        if not user:
            return "Error: User context not available."
        
        if not display_name or not display_name.strip():
            return "Error: Display name cannot be empty."
        
        try:
            user_manager = UserManager(users_collection) if users_collection is not None else None
            if user_manager is None:
                return "Error: User management service unavailable."
            
            success = user_manager.update_display_name(user.id, display_name.strip())
            if success:
                # Update the user object in context
                user.display_name = display_name.strip()
                log_tool_usage("update_display_name", display_name.strip())
                return f"Updated display name to '{display_name.strip()}'."
            else:
                return "Error: Failed to update display name."
        except Exception as exc:
            logger.error(f"Failed to update display name: {exc}")
            return f"Error updating display name: {exc}"

    @agent.tool
    def update_assistant_name(ctx: RunContext, assistant_name: str) -> str:
        """Update the assistant name (what the user wants to call the AI assistant).
        
        This tool should be used during onboarding when asking the user what they'd like to call the assistant.
        """
        user = _get_user_from_context(ctx)
        if not user:
            return "Error: User context not available."
        
        if not assistant_name or not assistant_name.strip():
            return "Error: Assistant name cannot be empty."
        
        try:
            user_manager = UserManager(users_collection) if users_collection is not None else None
            if user_manager is None:
                return "Error: User management service unavailable."
            
            success = user_manager.update_assistant_name(user.id, assistant_name.strip())
            if success:
                # Update the user object in context
                user.assistant_name = assistant_name.strip()
                log_tool_usage("update_assistant_name", assistant_name.strip())
                return f"Updated assistant name to '{assistant_name.strip()}'."
            else:
                return "Error: Failed to update assistant name."
        except Exception as exc:
            logger.error(f"Failed to update assistant name: {exc}")
            return f"Error updating assistant name: {exc}"

    @agent.tool
    def mark_onboarding_complete(ctx: RunContext) -> str:
        """Mark the user's onboarding as complete.
        
        Call this after the user has provided their display name and assistant name preferences.
        """
        user = _get_user_from_context(ctx)
        if not user:
            return "Error: User context not available."
        
        try:
            user_manager = UserManager(users_collection) if users_collection is not None else None
            if user_manager is None:
                return "Error: User management service unavailable."
            
            success = user_manager.mark_onboarding_complete(user.id)
            if success:
                user.has_seen_onboarding = True
                log_tool_usage("mark_onboarding_complete", "")
                return "Onboarding marked as complete."
            else:
                return "Error: Failed to mark onboarding as complete."
        except Exception as exc:
            logger.error(f"Failed to mark onboarding complete: {exc}")
            return f"Error marking onboarding complete: {exc}"

    @agent.tool
    def get_knowledge(ctx: RunContext, domain: str, topic: str) -> str:
        """Get a specific knowledge item by domain and topic.
        
        Knowledge items are mutable facts that users explicitly asked to remember.
        Examples:
        - domain: "locations", topic: "key_location" → "under the desk"
        - domain: "preferences", topic: "favorite_color" → "blue"
        """
        user = _get_user_from_context(ctx)
        if not user:
            return "Error: User context not available."
        
        if knowledge_store is None:
            return "Error: Knowledge service unavailable."
        
        try:
            item = knowledge_store.get(user.id, domain, topic)
            if item:
                log_tool_usage("get_knowledge", f"{domain}/{topic}")
                return f"Knowledge ({domain}/{topic}): {item.content}"
            else:
                return f"No knowledge found for {domain}/{topic}"
        except Exception as exc:
            logger.error(f"Failed to get knowledge: {exc}")
            return f"Error retrieving knowledge: {exc}"

    @agent.tool
    def update_knowledge(
        ctx: RunContext,
        domain: str,
        topic: str,
        content: str,
    ) -> str:
        """Create or update a knowledge item.
        
        Use this when the user explicitly asks to remember something or updates existing knowledge.
        Examples:
        - "Remember my key is under the desk" → domain: "locations", topic: "key_location", content: "under the desk"
        - "My key is now in the lockbox" → domain: "locations", topic: "key_location", content: "in the lockbox" (updates existing)
        
        Common domains: "locations", "preferences", "facts", "contacts"
        """
        user = _get_user_from_context(ctx)
        if not user:
            return "Error: User context not available."
        
        if knowledge_store is None:
            return "Error: Knowledge service unavailable."
        
        if not domain or not topic or not content:
            return "Error: Domain, topic, and content are required."
        
        try:
            item_id = knowledge_store.upsert(
                user_id=user.id,
                domain=domain.strip().lower(),
                topic=topic.strip().lower(),
                content=content.strip(),
            )
            if item_id:
                log_tool_usage("update_knowledge", f"{domain}/{topic}")
                return f"Knowledge updated: {domain}/{topic} = {content.strip()}"
            else:
                return "Error: Failed to update knowledge"
        except Exception as exc:
            logger.error(f"Failed to update knowledge: {exc}")
            return f"Error updating knowledge: {exc}"

    @agent.tool
    def list_knowledge(ctx: RunContext, domain: str = None) -> str:
        """List all knowledge items, optionally filtered by domain.
        
        Returns a formatted list of knowledge items for the user.
        """
        user = _get_user_from_context(ctx)
        if not user:
            return "Error: User context not available."
        
        if knowledge_store is None:
            return "Error: Knowledge service unavailable."
        
        try:
            items = knowledge_store.list(user.id, domain=domain, limit=50)
            if not items:
                domain_msg = f" in domain '{domain}'" if domain else ""
                return f"No knowledge items found{domain_msg}."
            
            log_tool_usage("list_knowledge", domain or "all")
            
            lines = []
            if domain:
                lines.append(f"Knowledge items in domain '{domain}':")
            else:
                lines.append("All knowledge items:")
            
            for item in items:
                lines.append(f"  - {item.domain}/{item.topic}: {item.content}")
            
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"Failed to list knowledge: {exc}")
            return f"Error listing knowledge: {exc}"

    @agent.tool
    def search_by_entity(ctx: RunContext, entity_name: str, entity_type: str = None) -> str:
        """Search conversations by entity."""
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "search_by_entity")
        if perm_error:
            return perm_error
        
        logger.debug("search_by_entity called with entity_name: %s, entity_type: %s", entity_name, entity_type)
        log_tool_usage("search_by_entity", f"entity='{entity_name}'")

        if memory_store is None:
            return "Database unavailable. Cannot search by entity."

        try:
            user_id = user.id if user and user.id else None
            
            # Use text search to find mentions of the entity
            matching_memories = memory_store.text_search(
                query_text=entity_name,
                user_id=user_id,
                memory_types=[MemoryType.EPISODIC_CONVERSATION, MemoryType.SEMANTIC_KNOWLEDGE, MemoryType.SHARED_ENTITY],
                limit=20,
            )

            if not matching_memories:
                return f"No conversations found mentioning entity '{entity_name}'"

            results = []
            for memory in matching_memories:
                role = memory.metadata.get("role", "unknown")
                
                # Check entities in metadata for more context
                entities = memory.metadata.get("entities", [])
                matching_entity = None
                for entity in entities:
                    if isinstance(entity, dict) and entity_name.lower() in entity.get("name", "").lower():
                        if not entity_type or entity.get("type") == entity_type:
                            matching_entity = entity
                            break

                entity_context = f" (context: {matching_entity.get('context', '')})" if matching_entity else ""
                results.append(f"{role}: {memory.content}{entity_context}")

            return f"Found {len(results)} messages mentioning '{entity_name}':\n\n" + "\n".join(results)
        except Exception as exc:  # pragma: no cover
            logger.error(f"Entity search failed: {exc}")
            return f"Error searching by entity: {exc}"

    @agent.tool
    def purge_memory(ctx: RunContext, criteria: str = "old", message_count: int = 100) -> str:
        """Delete memories based on criteria.

        Criteria options:
            - "old": Oldest low-importance memories
            - "summarized": Memories already summarized  
            - "decayed": Memories with low decay AND importance scores
            - "topic:<keyword>": Memories mentioning a keyword
            - "all/everything/reset": Remove ALL memories
            - "help": Show available options
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "purge_memory")
        if perm_error:
            return perm_error
        
        logger.debug("purge_memory called with criteria: %s, message_count: %s", criteria, message_count)
        log_tool_usage("purge_memory", f"criteria={criteria}, count={message_count}")

        if memory_store is None or agent_memory_collection is None:
            return "Database unavailable. Cannot purge memory."

        try:
            criteria_normalized = (criteria or "").strip().lower()
            user_id = user.id if user and user.id else None

            def describe_options() -> str:
                description = (
                    "Available criteria:\n"
                    "- old: Oldest low-importance memories.\n"
                    "- summarized: Memories already summarized.\n"
                    "- decayed: Memories with very low decay AND importance scores.\n"
                    "- topic:<keyword>: Memories mentioning a given keyword.\n"
                    "- all/everything/reset: Remove all stored memories.\n"
                )
                
                stats = memory_store.get_stats(user_id)
                if "error" not in stats:
                    description += f"\nCurrent memory: {stats.get('total', 0)} total memories"
                
                return description.strip()

            if not criteria_normalized or criteria_normalized in {"help", "options"}:
                return describe_options()

            if criteria_normalized in {"all", "everything", "reset", "clear"}:
                # Delete all memories for this user (or all if no user)
                query = {"user_id": user_id} if user_id else {}
                result = agent_memory_collection.delete_many(query)
                
                return f"Memory reset complete. Deleted {result.deleted_count} memories."

            # Build query based on criteria
            query = {}
            if user_id:
                query["$or"] = [{"user_id": user_id}, {"is_shared": True}]

            if criteria_normalized == "old":
                query["importance_score"] = {"$lt": 0.4}
            elif criteria_normalized == "summarized":
                query["metadata.summarized"] = True
            elif criteria_normalized == "decayed":
                query["decay_score"] = {"$lt": 0.2}
                query["importance_score"] = {"$lt": 0.5}
            elif criteria_normalized.startswith("topic"):
                keyword = criteria.split(":", 1)[1].strip() if ":" in criteria else ""
                if not keyword:
                    return describe_options()
                query["content"] = {"$regex": keyword, "$options": "i"}
            else:
                return f"Unknown criteria: {criteria}. Use 'help' to list options."

            # Find and delete matching memories
            memories_to_delete = list(
                agent_memory_collection.find(query).sort("timestamp", 1).limit(message_count)
            )

            if not memories_to_delete:
                return f"No memories found matching criteria: {criteria}"

            memory_ids = [m["_id"] for m in memories_to_delete]
            result = agent_memory_collection.delete_many({"_id": {"$in": memory_ids}})

            return f"Purged {result.deleted_count} memories using criteria: {criteria}"
        except Exception as exc:  # pragma: no cover
            logger.error(f"Memory purge failed: {exc}")
            return f"Error purging memory: {exc}"

    @agent.tool
    def get_memory_stats(ctx: RunContext) -> str:
        """Get current memory health statistics."""
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "get_memory_stats")
        if perm_error:
            return perm_error
        
        logger.debug("get_memory_stats called")
        log_tool_usage("get_memory_stats", "")

        if memory_store is None:
            return "Database unavailable. Cannot get memory stats."

        user_id = user.id if user and user.id else None
        stats_data = memory_store.get_stats(user_id)

        if "error" in stats_data:
            return f"Error getting memory stats: {stats_data['error']}"

        stats = f"""Memory Health Statistics:
- Total Memories: {stats_data.get('total', 0)}
- Short-Term Memory (STM): {stats_data.get('stm', {}).get('total', 0)}
- Long-Term Memory (LTM): {stats_data.get('ltm', {}).get('total', 0)}

Memory Types:
"""
        
        # STM breakdown
        stm_types = stats_data.get('stm', {}).get('types', {})
        for mtype, info in stm_types.items():
            stats += f"  - {mtype}: {info.get('count', 0)} (avg importance: {info.get('avg_importance', 0.5):.2f})\n"
        
        # LTM breakdown
        ltm_types = stats_data.get('ltm', {}).get('types', {})
        for mtype, info in ltm_types.items():
            stats += f"  - {mtype}: {info.get('count', 0)} (avg importance: {info.get('avg_importance', 0.5):.2f})\n"

        stats += "\nRecommendations:\n"
        
        total = stats_data.get('total', 0)
        if total > 100:
            stats += "- Consider running summarize_memory to condense old conversations\n"
        elif total == 0:
            stats += "- Memory is empty. Start chatting to build up memories!\n"
        else:
            stats += "- Memory health is good\n"

        return stats

    @agent.tool
    def get_weather(ctx: RunContext, city: str) -> str:
        """Get the current weather for any city."""
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "get_weather")
        if perm_error:
            return perm_error
        
        logger.debug("get_weather called with city: %s", city)
        log_tool_usage("get_weather", city)
        return get_weather_report(city)

    # ==================== CALENDAR TOOLS ====================
    
    @agent.tool
    def calendar_create_event(
        ctx: RunContext,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        all_day: bool = False,
    ) -> str:
        """Create a new calendar event.
        
        Args:
            summary: Event title/summary (e.g., "Doctor Appointment")
            start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS) or date (YYYY-MM-DD for all-day)
            end_time: End time in ISO format or date
            description: Optional event description
            location: Optional event location
            all_day: Whether this is an all-day event (default: False)
            
        Returns:
            Success message with event ID or error message
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "calendar_create_event")
        if perm_error:
            return perm_error
        
        logger.debug("calendar_create_event called: %s", summary)
        log_tool_usage("calendar_create_event", summary)
        
        from app.calendar import calendar_create_event as _create_event
        return _create_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            all_day=all_day,
        )

    @agent.tool
    def calendar_list_events(
        ctx: RunContext,
        days: int = 7,
        search_query: str = None,
    ) -> str:
        """List upcoming calendar events.
        
        Args:
            days: Number of days to look ahead (default: 7)
            search_query: Optional text to search for in events
            
        Returns:
            Formatted list of events or message if no events found
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "calendar_list_events")
        if perm_error:
            return perm_error
        
        logger.debug("calendar_list_events called: days=%d, query=%s", days, search_query)
        log_tool_usage("calendar_list_events", f"days={days}")
        
        from app.calendar import calendar_list_events as _list_events
        return _list_events(days=days, search_query=search_query)

    @agent.tool
    def calendar_update_event(
        ctx: RunContext,
        event_id: str,
        summary: str = None,
        start_time: str = None,
        end_time: str = None,
        description: str = None,
        location: str = None,
    ) -> str:
        """Update an existing calendar event.
        
        Args:
            event_id: The ID of the event to update (from calendar_list_events)
            summary: New event title (optional)
            start_time: New start time in ISO format (optional)
            end_time: New end time in ISO format (optional)
            description: New description (optional)
            location: New location (optional)
            
        Returns:
            Success or error message
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "calendar_update_event")
        if perm_error:
            return perm_error
        
        logger.debug("calendar_update_event called: %s", event_id)
        log_tool_usage("calendar_update_event", event_id)
        
        from app.calendar import calendar_update_event as _update_event
        return _update_event(
            event_id=event_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
        )

    @agent.tool
    def calendar_delete_event(ctx: RunContext, event_id: str) -> str:
        """Delete a calendar event.
        
        Args:
            event_id: The ID of the event to delete (from calendar_list_events)
            
        Returns:
            Success or error message
        """
        # Permission check
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "calendar_delete_event")
        if perm_error:
            return perm_error
        
        logger.debug("calendar_delete_event called: %s", event_id)
        log_tool_usage("calendar_delete_event", event_id)
        
        from app.calendar import calendar_delete_event as _delete_event
        return _delete_event(event_id=event_id)

    @agent.tool
    def calendar_get_event(ctx: RunContext, event_id: str) -> str:
        """Get details of a specific calendar event.
        
        Args:
            event_id: The ID of the event to retrieve
            
        Returns:
            Event details or error message
        """
        # Permission check (use list permission for reading)
        user = _get_user_from_context(ctx)
        perm_error = check_permission_or_message(user, "calendar_list_events")
        if perm_error:
            return perm_error
        
        logger.debug("calendar_get_event called: %s", event_id)
        log_tool_usage("calendar_get_event", event_id)
        
        from app.calendar import calendar_get_event as _get_event
        return _get_event(event_id=event_id)

    @agent.tool
    def get_current_datetime(ctx: RunContext, timezone_name: str = "UTC") -> str:
        """Get the current date and time with timezone information.
        
        This tool provides the current date and time, which is essential for:
        - Understanding relative dates like "tomorrow", "next week", "in 3 days"
        - Making chronological decisions
        - Recognizing significant dates (holidays, special occasions)
        - Scheduling and time-sensitive tasks
        
        Args:
            timezone_name: Optional timezone name (e.g., "America/New_York", "Europe/London").
                          Defaults to "UTC". Common timezones: UTC, America/New_York, 
                          America/Los_Angeles, Europe/London, Asia/Tokyo.
        
        Returns:
            A formatted string with current date, time, day of week, and timezone information.
        """
        user = _get_user_from_context(ctx)
        log_tool_usage("get_current_datetime", f"timezone={timezone_name}")
        
        try:
            # Get current UTC time
            now_utc = datetime.now(timezone.utc)
            
            # Try to convert to requested timezone if pytz is available
            try:
                import pytz
                tz = pytz.timezone(timezone_name)
                now_local = now_utc.astimezone(tz)
                tz_name = now_local.tzname()
                tz_offset = now_local.strftime("%z")
            except (ImportError, Exception):
                # Fallback to UTC if pytz not available or invalid timezone
                try:
                    # Try using zoneinfo (Python 3.9+)
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(timezone_name)
                    now_local = now_utc.astimezone(tz)
                    tz_name = now_local.tzname()
                    tz_offset = now_local.strftime("%z")
                except (ImportError, Exception):
                    now_local = now_utc
                    tz_name = "UTC"
                    tz_offset = "+0000"
            
            # Format date and time
            date_str = now_local.strftime("%Y-%m-%d")
            time_str = now_local.strftime("%H:%M:%S")
            day_of_week = calendar.day_name[now_local.weekday()]
            month_name = calendar.month_name[now_local.month]
            day_of_year = now_local.timetuple().tm_yday
            week_number = now_local.isocalendar()[1]
            
            # Check for significant dates
            significant_dates = []
            
            # Major holidays (US-centric, but can be expanded)
            month_day = (now_local.month, now_local.day)
            holiday_map = {
                (1, 1): "New Year's Day",
                (2, 14): "Valentine's Day",
                (3, 17): "St. Patrick's Day",
                (4, 1): "April Fool's Day",
                (5, 1): "May Day / International Workers' Day",
                (7, 4): "Independence Day (US)",
                (10, 31): "Halloween",
                (11, 1): "All Saints' Day",
                (11, 11): "Veterans Day (US) / Remembrance Day",
                (12, 24): "Christmas Eve",
                (12, 25): "Christmas Day",
                (12, 31): "New Year's Eve",
            }
            
            if month_day in holiday_map:
                significant_dates.append(holiday_map[month_day])
            
            # Easter calculation (simplified - uses Western Easter)
            year = now_local.year
            # Easter calculation using algorithm
            a = year % 19
            b = year // 100
            c = year % 100
            d = b // 4
            e = b % 4
            f = (b + 8) // 25
            g = (b - f + 1) // 3
            h = (19 * a + b - d - g + 15) % 30
            i = c // 4
            k = c % 4
            l = (32 + 2 * e + 2 * i - h - k) % 7
            m = (a + 11 * h + 22 * l) // 451
            month_easter = (h + l - 7 * m + 114) // 31
            day_easter = ((h + l - 7 * m + 114) % 31) + 1
            
            if (now_local.month, now_local.day) == (month_easter, day_easter):
                significant_dates.append("Easter Sunday")
            
            # Thanksgiving (US - 4th Thursday of November)
            if now_local.month == 11:
                # Find 4th Thursday
                first_day = datetime(year, 11, 1).weekday()
                thursday_offset = (3 - first_day) % 7
                thanksgiving_day = 1 + thursday_offset + 21  # 4th Thursday
                if now_local.day == thanksgiving_day:
                    significant_dates.append("Thanksgiving (US)")
            
            # Build response
            result = f"""Current Date and Time:
📅 Date: {date_str} ({day_of_week})
🕐 Time: {time_str} {tz_name} (UTC{tz_offset})
📆 Month: {month_name} {now_local.year}
📊 Day of year: {day_of_year} / 365
📅 Week number: {week_number}
🌍 Timezone: {tz_name}"""
            
            if significant_dates:
                result += f"\n🎉 Today is: {', '.join(significant_dates)}"
            
            # Add relative date information
            tomorrow = now_local + timedelta(days=1)
            tomorrow_holiday = holiday_map.get((tomorrow.month, tomorrow.day))
            if tomorrow_holiday:
                result += f"\n📅 Tomorrow ({tomorrow.strftime('%Y-%m-%d')}) is: {tomorrow_holiday}"
            
            next_week = now_local + timedelta(days=7)
            next_week_holiday = holiday_map.get((next_week.month, next_week.day))
            if next_week_holiday:
                result += f"\n📅 Next week ({next_week.strftime('%Y-%m-%d')}) is: {next_week_holiday}"
            
            return result
            
        except Exception as exc:
            logger.error(f"Failed to get current datetime: {exc}")
            return f"Error getting current datetime: {exc}"

    @agent.tool
    def get_date_info(ctx: RunContext, date_str: str = None) -> str:
        """Get detailed information about a specific date.
        
        This tool helps understand dates mentioned in conversation, including:
        - Day of week
        - Whether it's a holiday or significant date
        - Relative position (past, present, future)
        - Days until/from the date
        
        Args:
            date_str: Date in format YYYY-MM-DD. If not provided, uses today's date.
        
        Returns:
            Detailed information about the requested date.
        """
        user = _get_user_from_context(ctx)
        log_tool_usage("get_date_info", f"date={date_str or 'today'}")
        
        try:
            now = datetime.now(timezone.utc)
            
            if date_str:
                try:
                    target_date = datetime.strptime(date_str, "%Y-%m-%d")
                    target_date = target_date.replace(tzinfo=timezone.utc)
                except ValueError:
                    return f"Invalid date format: {date_str}. Use YYYY-MM-DD format."
            else:
                target_date = now
            
            # Calculate relative information
            days_diff = (target_date.date() - now.date()).days
            if days_diff < 0:
                relative = f"{abs(days_diff)} days ago"
            elif days_diff == 0:
                relative = "today"
            elif days_diff == 1:
                relative = "tomorrow"
            else:
                relative = f"in {days_diff} days"
            
            # Get date information
            day_of_week = calendar.day_name[target_date.weekday()]
            month_name = calendar.month_name[target_date.month]
            
            # Check for holidays
            month_day = (target_date.month, target_date.day)
            holiday_map = {
                (1, 1): "New Year's Day",
                (2, 14): "Valentine's Day",
                (3, 17): "St. Patrick's Day",
                (4, 1): "April Fool's Day",
                (5, 1): "May Day / International Workers' Day",
                (7, 4): "Independence Day (US)",
                (10, 31): "Halloween",
                (11, 1): "All Saints' Day",
                (11, 11): "Veterans Day (US) / Remembrance Day",
                (12, 24): "Christmas Eve",
                (12, 25): "Christmas Day",
                (12, 31): "New Year's Eve",
            }
            
            holiday = holiday_map.get(month_day)
            
            result = f"""Date Information:
📅 Date: {target_date.strftime('%Y-%m-%d')} ({day_of_week})
📆 {month_name} {target_date.day}, {target_date.year}
⏰ Relative: {relative}"""
            
            if holiday:
                result += f"\n🎉 Holiday: {holiday}"
            
            # Add context about significance
            if days_diff == 0:
                result += "\n📍 This is today!"
            elif days_diff == 1:
                result += "\n📍 This is tomorrow!"
            elif days_diff < 0:
                result += f"\n📍 This date was in the past ({abs(days_diff)} days ago)"
            else:
                result += f"\n📍 This date is in the future ({days_diff} days from now)"
            
            return result
            
        except Exception as exc:
            logger.error(f"Failed to get date info: {exc}")
            return f"Error getting date information: {exc}"
