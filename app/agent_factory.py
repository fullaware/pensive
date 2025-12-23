"""Factories for the main conversational agent and profile agent."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pymongo import MongoClient
from pydantic_ai import Agent, RunContext, ModelRetry
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool

from config import (
    LLM_API_KEY,
    LLM_MODEL,
    LLM_URI,
    logger,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.auth.models import User

from app.profile import (
    profile_snapshot_json,
    upsert_profile_field,
    delete_profile_field,
)


class Deps(BaseModel):
    mongo_client: MongoClient
    current_user: object = None  # The authenticated user (app.auth.models.User)
    model_config = ConfigDict(arbitrary_types_allowed=True)


DEFAULT_SYSTEM_PROMPT = """You are a helpful, knowledgeable AI assistant with infinite memory capabilities.

Your primary goals:
- Provide accurate, helpful responses to user queries
- Use your memory tools to recall past conversations
- Maintain context across long conversations
- Be concise but thorough
- Ask clarifying questions when needed

Communication style:
- Friendly and professional
- Clear and direct
- Adapt to the user's communication style
- Use appropriate tone for the context

You have access to tools for memory management, web search, weather, and more. Use them appropriately to provide the best assistance."""

SYSTEM_PROMPT = """
You are a helpful chat assistant with infinite recall capabilities. You have access to tools that allow you to:

1. **retrieve_context**: Get recent context from the conversation history
2. **search_conversations**: Search through all past conversations by keywords, topics, or date ranges
3. **create_research_agent**: Spawn a sub-agent to research a specific topic deeply, keeping the main context window tidy
4. **summarize_memory**: Summarize old conversations and store them as summaries, then optionally purge the original messages
5. **purge_memory**: Delete old messages from memory based on criteria (age, topic, etc.)
6. **mark_important**: Mark specific messages as important for future recall
7. **remember_this**: Mark current conversation context as important
8. **search_by_entity**: Search conversations by entity (person, organization, project, location)
9. **get_memory_stats**: Get memory health statistics and recommendations
10. **duckduckgo_search**: Search the web for current information, news, or facts not in your memory
11. **get_weather**: Get current weather conditions and forecast for any city worldwide

Memory Management:
- Use summarize_memory to condense old conversations into summaries when memory gets large
- Use purge_memory to remove old, redundant, or irrelevant messages to keep the database manageable
- Always preserve important information in summaries before purging
- Monitor memory size and proactively manage it to maintain performance
- Use mark_important and remember_this to preserve important information

For each user query:
- Use retrieve_context to get immediate context from recent messages
- Use search_conversations to find relevant past conversations when the user asks about previous topics
- Use get_weather to get current weather conditions when the user asks about weather in any city
- Use duckduckgo_search to find current information, recent news, or facts that aren't in your memory
- If a query requires deep research or would clutter the main context, use create_research_agent to spawn a focused sub-agent
- Periodically use summarize_memory and purge_memory to maintain a clean, efficient memory system
- Always use the retrieved context to provide informed, context-aware responses

The goal is to maintain infinite recall while keeping the main conversation context clean and focused, and proactively managing memory. Use web search when you need current information that isn't in your memory.
"""

ONBOARDING_SYSTEM_PROMPT = """
You are helping a new user get started with the AI assistant. Your job is to:

1. Ask the user what they would like to be called (their preferred display name)
2. Ask the user what they would like to call you (the assistant name)
3. Use the update_display_name and update_assistant_name tools to save their preferences
4. After preferences are collected, explain the system capabilities:
   - How to ask to remember things (knowledge management)
   - Available tools and features
   - How conversations are saved as memory
   - The difference between knowledge (mutable facts) and memory (conversation history)

Be friendly, conversational, and helpful. Ask one question at a time and wait for the user's response before asking the next question.
"""

PROFILE_SYSTEM_PROMPT = """
You are the user's profile curator. Your job is to detect long-lived identity details
(name, pronouns, role) and communication preferences from new user messages.

Guidelines:
- Only store facts that the user stated explicitly.
- Keep entries concise (one short sentence or phrase per field).
- Prefer lower_snake_case field names (e.g., name, preferred_tone, favorite_topics).
- Update existing fields when the user revises them.
- Delete fields if the user says they no longer apply.
- Ignore transient mood or context that does not affect future responses.

You have tools to read, add/update, and delete profile data. Always inspect the current
profile before writing to avoid duplication. If a message contains no identity or preference
information, simply respond with a short acknowledgement and do not call tools.
"""


def create_agent(
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    assistant_name: Optional[str] = None,
) -> Agent:
    """Create and configure the main agent with optional user-specific settings.
    
    Args:
        system_prompt: Custom system prompt. If None, uses default SYSTEM_PROMPT.
        temperature: Model temperature (0.0-2.0). If None, uses default.
        assistant_name: Name to use in place of "Pensive" in prompts.
    """
    llm_model = None
    try:
        if not LLM_MODEL or not LLM_URI:
            logger.error("LLM_MODEL or LLM_URI not configured")
            raise RuntimeError("LLM configuration missing.")
        # Use placeholder API key for local providers that don't require authentication
        api_key = LLM_API_KEY or "not-needed"
        llm_model = OpenAIChatModel(
            model_name=LLM_MODEL,
            provider=OpenAIProvider(base_url=LLM_URI, api_key=api_key),
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(f"Failed to initialize LLM model: {exc}")
        llm_model = None

    if llm_model is None:
        raise RuntimeError("Failed to initialize LLM model")

    # Use custom system prompt or default
    effective_prompt = system_prompt or SYSTEM_PROMPT
    
    # Replace "Pensive" with assistant_name if provided
    if assistant_name:
        effective_prompt = effective_prompt.replace("Pensive", assistant_name)
        effective_prompt = effective_prompt.replace("pensive", assistant_name.lower())

    # Build model settings
    model_settings = {}
    if temperature is not None:
        model_settings["temperature"] = temperature

    agent = Agent(
        llm_model,
        system_prompt=effective_prompt,
        retries=1,
        deps_type=Deps,
        tools=[duckduckgo_search_tool()],
        model_settings=model_settings if model_settings else None,
    )

    @agent.output_validator
    async def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if not output:
            logger.warning("Empty output received")
            raise ModelRetry("Response is empty. Please provide an answer.")
        return output

    return agent


def create_user_agent(user: "User") -> Agent:
    """Create an agent with user-specific preferences.
    
    Args:
        user: User model with preferences (system_prompt, temperature, assistant_name)
    
    Returns:
        Configured Agent instance
    """
    return create_agent(
        system_prompt=user.system_prompt,
        temperature=user.temperature,
        assistant_name=user.assistant_name,
    )


def create_profile_agent(log_tool_usage) -> Agent:
    """Create a lightweight agent dedicated to managing the user profile."""
    if not LLM_MODEL or not LLM_URI:
        raise RuntimeError("LLM configuration missing. Cannot initialize profile agent.")

    # Use placeholder API key for local providers that don't require authentication
    api_key = LLM_API_KEY or "not-needed"
    profile_model = OpenAIChatModel(
        model_name=LLM_MODEL,
        provider=OpenAIProvider(base_url=LLM_URI, api_key=api_key),
    )

    profile_agent = Agent(
        profile_model,
        system_prompt=PROFILE_SYSTEM_PROMPT,
        deps_type=Deps,
        retries=1,
    )

    @profile_agent.tool
    def read_profile(ctx: RunContext[Deps]) -> str:
        """Return the current stored profile."""
        log_tool_usage("profile_read")
        snapshot = profile_snapshot_json()
        return snapshot

    @profile_agent.tool
    def upsert_profile(ctx: RunContext[Deps], field_name: str, field_value: str) -> str:
        """Add or update a profile field."""
        log_tool_usage("profile_upsert", f"{field_name}={field_value}")
        return upsert_profile_field(field_name, field_value)

    @profile_agent.tool
    def delete_profile(ctx: RunContext[Deps], field_name: str) -> str:
        """Delete a profile field."""
        log_tool_usage("profile_delete", field_name)
        return delete_profile_field(field_name)

    return profile_agent


def update_profile_from_message(profile_agent: Agent, user_text: str, deps: Deps, log_tool_usage) -> None:
    """Run the profile agent against the latest user message."""
    if not user_text or profile_agent is None:
        return
    # Don't log here - the individual profile tools (profile_upsert, profile_delete) will log when actually used
    snapshot = profile_snapshot_json()
    profile_prompt = (
        "You will decide whether the following user message contains identity or preference updates.\n"
        "Existing profile entries:\n"
        f"{snapshot}\n\n"
        "User message:\n"
        f"{user_text}\n\n"
        "If the message contains relevant details, call the profile tools to add/update/delete entries. "
        "If nothing applies, respond with a brief acknowledgement without calling any tools."
    )
    try:
        profile_agent.run_sync(profile_prompt, deps=deps)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(f"Profile agent failed: {exc}")








