"""Chat routes with SSE streaming support."""

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from config import (
    logger,
    LLM_MODEL,
    LLM_URI,
    CONVERSATION_ID,
    DEFAULT_IMPORTANCE_SCORE,
)
from database import client
from app.auth.models import User
from app.memory import MemoryStore, MemoryType
from pydantic_ai import Agent
from app.agent_factory import Deps, create_agent, create_user_agent, ONBOARDING_SYSTEM_PROMPT
from app.context import get_recent_context_for_prompt
from app.memory_extraction import extract_topics_and_keywords, extract_entities
from app.profile import build_user_profile_context
from app.tools import register_tools

from api.models import ChatMessageRequest, ChatHistoryResponse, ChatMessageResponse
from api.dependencies import (
    get_current_user,
    get_memory_store,
    get_session_manager,
    get_metrics_collector,
)


router = APIRouter()

# Per-user agent cache (lazy init)
_agents: dict[str, Agent] = {}
_agent_lock = asyncio.Lock()


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation: ~4 chars per token)."""
    if not text:
        return 0
    return len(text) // 4


def log_tool_usage(tool_name: str, details: str = "") -> None:
    """Log tool usage."""
    logger.info(f"[tool] {tool_name} — {details}")


async def get_or_create_agent(user: User):
    """Get or create a user-specific agent with their preferences."""
    global _agents
    async with _agent_lock:
        user_id = user.id
        if user_id not in _agents:
            try:
                # Create user-specific agent with their preferences
                agent = create_user_agent(user)
                register_tools(agent, log_tool_usage)
                _agents[user_id] = agent
                logger.info(f"Chat agent created for user {user_id} with preferences")
            except Exception as e:
                logger.error(f"Failed to create agent for user {user_id}: {e}")
                raise
        return _agents[user_id]


def parse_thinking_content(text: str) -> tuple[str, str]:
    """
    Parse text for thinking/reasoning markers.
    Returns (thinking_content, final_content).
    
    Supports markers like:
    - <think>...</think>
    - <reasoning>...</reasoning>
    - **Thinking:** ... **Response:**
    """
    thinking = ""
    final = text
    
    # Check for <think> tags
    think_pattern = r'<think>(.*?)</think>'
    think_match = re.search(think_pattern, text, re.DOTALL | re.IGNORECASE)
    if think_match:
        thinking = think_match.group(1).strip()
        final = re.sub(think_pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        return thinking, final
    
    # Check for <reasoning> tags
    reasoning_pattern = r'<reasoning>(.*?)</reasoning>'
    reasoning_match = re.search(reasoning_pattern, text, re.DOTALL | re.IGNORECASE)
    if reasoning_match:
        thinking = reasoning_match.group(1).strip()
        final = re.sub(reasoning_pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        return thinking, final
    
    return thinking, final


async def stream_chat_response(
    message: str,
    user: User,
    memory_store: Optional[MemoryStore],
    session_id: Optional[str] = None,
    metrics_collector = None,
) -> AsyncGenerator[str, None]:
    """
    Stream chat response as Server-Sent Events.
    
    Event types:
    - thinking: Reasoning/thinking content from the model
    - token: Response content with tokens_per_second
    - done: Final statistics
    - error: Error message
    """
    start_time = time.time()
    token_count = 0
    full_response = ""
    thinking_content = ""
    
    try:
        # Check if this is a new user who needs onboarding
        needs_onboarding = not user.has_seen_onboarding
        is_onboarding = False
        
        # Determine if we should use onboarding prompt
        if needs_onboarding:
            # Check if display_name or assistant_name need to be set
            from app.auth.manager import UserManager
            from api.dependencies import get_user_manager
            user_manager = get_user_manager()
            
            # Check if display_name is default/empty (compare with username or check if it's a default)
            needs_display_name = not user.display_name or user.display_name.strip() == "" or user.display_name.lower() == user.username.lower()
            needs_assistant_name = not user.assistant_name
            
            if needs_display_name or needs_assistant_name:
                is_onboarding = True
        
        # Get or create user-specific agent
        agent = await get_or_create_agent(user)
        
        # If onboarding, temporarily use onboarding system prompt
        if is_onboarding:
            # Create a temporary agent with onboarding prompt for this conversation
            from app.agent_factory import create_agent
            onboarding_agent = create_agent(
                system_prompt=ONBOARDING_SYSTEM_PROMPT,
                temperature=user.temperature,
                assistant_name=user.assistant_name,
            )
            register_tools(onboarding_agent, log_tool_usage)
            agent = onboarding_agent
        
        # Store user message
        if memory_store is not None:
            user_extraction = extract_topics_and_keywords(message)
            user_entities = extract_entities(message)
            
            importance = DEFAULT_IMPORTANCE_SCORE
            importance_markers = ["remember this", "important", "don't forget", "keep this"]
            if any(marker in message.lower() for marker in importance_markers):
                importance = 0.8
            
            memory_store.store(
                memory_type=MemoryType.EPISODIC_CONVERSATION,
                content=message,
                user_id=user.id,
                session_id=session_id,
                conversation_id=CONVERSATION_ID,
                importance_score=importance,
                generate_vector=(importance >= 0.7),
                metadata={
                    "role": "user",
                    "topics": user_extraction.get("topics", []),
                    "keywords": user_extraction.get("keywords", []),
                    "entities": user_entities,
                },
            )
        
        # Build context
        recent_context = get_recent_context_for_prompt(
            user_id=user.id,
            message_limit=20,
            summary_limit=3,
        )
        
        profile_context = build_user_profile_context(user.display_name)
        
        # Build onboarding context if needed
        onboarding_context = ""
        if is_onboarding:
            onboarding_context = f"""
ONBOARDING MODE: This is a new user who hasn't completed onboarding yet.
- Check if display_name needs updating: {needs_display_name}
- Check if assistant_name needs setting: {needs_assistant_name}
- If either is missing, ask the user for their preference and use the update_display_name or update_assistant_name tools.
- After both are set, explain the system capabilities and mark onboarding as complete.
"""
        
        augmented_prompt = f"""{onboarding_context}User Profile:
{profile_context}

Recent Context:
{recent_context}

Current message from {user.display_name}:
{message}"""
        
        # Create dependencies
        deps = Deps(mongo_client=client, current_user=user)
        
        # Stream response
        last_sent_length = 0
        
        async with agent.run_stream(augmented_prompt, deps=deps) as result:
            async for chunk in result.stream_text():
                if chunk:
                    # Handle incremental vs full updates
                    if chunk.startswith(full_response) and len(chunk) > len(full_response):
                        new_content = chunk[len(full_response):]
                        full_response = chunk
                    elif len(chunk) >= len(full_response):
                        full_response = chunk
                    
                    # Parse for thinking content
                    thinking, final = parse_thinking_content(full_response)
                    
                    # Emit thinking content if new
                    if thinking and thinking != thinking_content:
                        thinking_content = thinking
                        yield f"event: thinking\ndata: {json.dumps({'content': thinking_content})}\n\n"
                    
                    # Calculate metrics
                    token_count = estimate_tokens(final)
                    elapsed = time.time() - start_time
                    tps = token_count / elapsed if elapsed > 0 else 0
                    
                    # Only send if we have new content
                    if len(final) > last_sent_length:
                        new_text = final[last_sent_length:]
                        last_sent_length = len(final)
                        
                        yield f"event: token\ndata: {json.dumps({'content': new_text, 'tokens_per_second': round(tps, 1)})}\n\n"
        
        # Store assistant response
        final_thinking, final_response = parse_thinking_content(full_response)
        
        if memory_store is not None and final_response:
            response_extraction = extract_topics_and_keywords(final_response)
            response_entities = extract_entities(final_response)
            
            memory_store.store(
                memory_type=MemoryType.EPISODIC_CONVERSATION,
                content=final_response,
                user_id=user.id,
                session_id=session_id,
                conversation_id=CONVERSATION_ID,
                importance_score=DEFAULT_IMPORTANCE_SCORE,
                generate_vector=True,
                metadata={
                    "role": "assistant",
                    "topics": response_extraction.get("topics", []),
                    "keywords": response_extraction.get("keywords", []),
                    "entities": response_entities,
                    "has_thinking": bool(final_thinking),
                },
            )
        
        # Final done event
        total_elapsed = time.time() - start_time
        final_token_count = estimate_tokens(final_response)
        input_token_count = estimate_tokens(message)
        avg_tps = final_token_count / total_elapsed if total_elapsed > 0 else 0
        
        # Check if onboarding was completed (tools were called)
        # This is a simple check - in a more sophisticated implementation, we'd track tool calls
        # For now, we'll check if both display_name and assistant_name are set after the response
        if is_onboarding:
            from api.dependencies import get_user_manager
            user_manager = get_user_manager()
            if user_manager:
                # Refresh user to check if preferences were set
                updated_user = user_manager.get_user_by_id(user.id)
                if updated_user:
                    has_display_name = updated_user.display_name and updated_user.display_name.strip() and updated_user.display_name.lower() != updated_user.username.lower()
                    has_assistant_name = updated_user.assistant_name and updated_user.assistant_name.strip()
                    
                    # If both are set, mark onboarding as complete
                    if has_display_name and has_assistant_name and not updated_user.has_seen_onboarding:
                        user_manager.mark_onboarding_complete(user.id)
                        user.has_seen_onboarding = True
                        # Invalidate agent cache to pick up new preferences
                        global _agents
                        if user.id in _agents:
                            del _agents[user.id]
        
        # Record metrics
        if metrics_collector:
            try:
                metrics_collector.record_llm_usage(
                    tokens_in=input_token_count,
                    tokens_out=final_token_count,
                    duration_ms=total_elapsed * 1000,
                    model=LLM_MODEL or "unknown",
                    user_id=user.id,
                )
            except Exception as e:
                logger.error(f"Failed to record metrics: {e}")
        
        # Update realtime metrics (import here to avoid circular dependency)
        try:
            from api.routes.metrics import update_realtime_metrics
            update_realtime_metrics(avg_tps, final_token_count)
        except Exception as e:
            logger.debug(f"Could not update realtime metrics: {e}")
        
        yield f"event: done\ndata: {json.dumps({'total_tokens': final_token_count, 'duration_ms': int(total_elapsed * 1000), 'avg_tps': round(avg_tps, 1)})}\n\n"
        
    except Exception as e:
        logger.error(f"Chat streaming error: {e}")
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"


@router.post("/message")
async def send_message(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
    metrics_collector = Depends(get_metrics_collector),
):
    """
    Send a chat message and receive streaming response via SSE.
    
    Returns Server-Sent Events with the following event types:
    - thinking: Reasoning content (if model outputs thinking)
    - token: Response tokens with tokens_per_second
    - done: Final statistics
    - error: Error message
    """
    if not LLM_MODEL or not LLM_URI:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM not configured",
        )
    
    return StreamingResponse(
        stream_chat_response(
            message=request.message,
            user=current_user,
            memory_store=memory_store,
            session_id=request.conversation_id,
            metrics_collector=metrics_collector,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
):
    """
    Get paginated chat history for the current user.
    """
    if memory_store is None:
        return ChatHistoryResponse(
            messages=[],
            total=0,
            page=page,
            page_size=page_size,
            has_more=False,
        )
    
    try:
        # Get messages with pagination
        skip = (page - 1) * page_size
        
        messages = memory_store.find_by_type(
            MemoryType.EPISODIC_CONVERSATION,
            user_id=current_user.id,
            limit=page_size + 1,  # Fetch one extra to check if there are more
            include_shared=True,
        )
        
        # Simple offset-based pagination
        all_messages = list(messages)
        has_more = len(all_messages) > page_size
        paginated = all_messages[:page_size]
        
        response_messages = [
            ChatMessageResponse(
                id=msg.id or "",
                role=msg.metadata.get("role", "unknown"),
                content=msg.content,
                timestamp=msg.timestamp,
                metadata={
                    k: v for k, v in msg.metadata.items()
                    if k not in ["role"]
                },
            )
            for msg in reversed(paginated)  # Chronological order
        ]
        
        return ChatHistoryResponse(
            messages=response_messages,
            total=len(all_messages),
            page=page,
            page_size=page_size,
            has_more=has_more,
        )
        
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch chat history",
        )


@router.delete("/history")
async def clear_chat_history(
    current_user: User = Depends(get_current_user),
    memory_store: Optional[MemoryStore] = Depends(get_memory_store),
):
    """
    Clear chat history for the current user.
    Only clears episodic conversation memories, preserves summaries.
    """
    if memory_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service unavailable",
        )
    
    try:
        # Delete user's conversation memories
        deleted = memory_store.delete_by_type(
            MemoryType.EPISODIC_CONVERSATION,
            user_id=current_user.id,
        )
        
        logger.info(f"Cleared {deleted} messages for user {current_user.username}")
        
        return {
            "success": True,
            "deleted_count": deleted,
        }
        
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear chat history",
        )


