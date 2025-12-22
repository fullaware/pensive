"""Main Gradio application for Pensive Family Assistant."""

import os
import asyncio
import gradio as gr
from typing import Optional, Tuple, List, Dict, Any, Generator
from datetime import datetime, timezone, timedelta
from openai import OpenAI
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Import configuration and database
from config import (
    MONGODB_URI, LLM_MODEL, LLM_URI, LLM_API_KEY, CONVERSATION_ID,
    DEFAULT_IMPORTANCE_SCORE, MEMORY_MAINTENANCE_THRESHOLD, logger
)
from database import client, agent_memory_collection, users_collection, sessions_collection, metrics_collection
from app.memory import MemoryStore, MemoryType
from app.agent_factory import (
    Deps,
    create_agent,
    create_profile_agent,
    update_profile_from_message,
)
from app.context import get_recent_context_for_prompt
from app.memory_extraction import extract_topics_and_keywords, extract_entities
from app.profile import build_user_profile_context
from app.tools import register_tools
from app.auth.manager import UserManager
from app.auth.models import User, UserRole
from app.sessions import SessionManager
from app.metrics import MetricsCollector, MetricType

# Global application state
memory_store = None
agent = None
profile_agent = None
user_manager = None
session_manager = None
metrics_collector = None


def log_tool_usage(tool_name: str, details: str = "") -> None:
    """Record tool/agent usage for UI display."""
    logger.info(f"[tool] {tool_name} — {details}")


def initialize_app():
    """Initialize application components."""
    global memory_store, agent, profile_agent, user_manager, session_manager, metrics_collector
    
    # Debug environment variable loading
    for var, value in [
        ("MONGODB_URI", MONGODB_URI),
        ("LLM_MODEL", LLM_MODEL),
        ("LLM_URI", LLM_URI),
        ("LLM_API_KEY", LLM_API_KEY)
    ]:
        if not value:
            logger.error(f"{var} not found in .env file or environment variables")
        else:
            logger.info(f"{var} loaded: {value[:30]}...")
    
    # Initialize memory store (unified memory system)
    if agent_memory_collection is not None:
        try:
            memory_store = MemoryStore(agent_memory_collection)
            logger.info("Memory store initialized with agent_memory collection")
        except Exception as e:
            logger.warning(f"Could not initialize memory store: {e}")
    
    # Create agent and register tools
    try:
        agent = create_agent()
        register_tools(agent, log_tool_usage)
        logger.info("Agent created and tools registered successfully")
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
    
    # Create profile agent
    try:
        profile_agent = create_profile_agent(log_tool_usage)
        logger.info("Profile agent initialized")
    except Exception as e:
        logger.warning(f"Profile agent unavailable: {e}")
    
    # Initialize managers
    user_manager = UserManager(users_collection) if users_collection is not None else None
    session_manager = SessionManager(sessions_collection) if sessions_collection is not None else None
    metrics_collector = MetricsCollector(metrics_collection) if metrics_collection is not None else None
    
    # Ensure admin user exists and migrate legacy data
    if user_manager is not None:
        user_manager.create_admin_if_none_exists()
        migration_stats = user_manager.migrate_users_to_new_schema()
        if migration_stats.get("roles_updated", 0) > 0 or migration_stats.get("fields_removed", 0) > 0:
            logger.info(f"Migrated {migration_stats['total_users']} users: "
                       f"{migration_stats['roles_updated']} roles updated, "
                       f"{migration_stats['fields_removed']} fields removed")


# Initialize app on import
initialize_app()


# Session state class for Gradio
class SessionState:
    """Session state for Gradio app."""
    def __init__(self):
        self.user: Optional[User] = None
        self.chat_session_id: Optional[str] = None
        self.messages: List[Dict[str, str]] = []
        self.tool_usage: List[Tuple[str, str]] = []  # (timestamp, description)
        self.message_count_since_maintenance: int = 0
        self.ai_greeting: Optional[str] = None
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.user is not None
    
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.user is not None and self.user.role == UserRole.ADMIN


def get_ai_greeting(display_name: str) -> str:
    """Get a personalized greeting from the AI."""
    try:
        hour = datetime.now().hour
        time_of_day = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
        
        client_openai = OpenAI(base_url=LLM_URI, api_key=LLM_API_KEY)
        response = client_openai.chat.completions.create(
            model=LLM_MODEL,
            messages=[{
                "role": "user",
                "content": f"Generate a warm, sincere, brief greeting (1-2 sentences max) for {display_name}. It's {time_of_day}. Be friendly and personable, not robotic. No emojis. Just the greeting text, nothing else."
            }],
            max_tokens=100,
        )
        greeting = response.choices[0].message.content.strip()
        return greeting
    except Exception as e:
        logger.warning(f"Could not generate AI greeting: {e}")
        return f"Welcome back, {display_name}!"


def generate_summary(user_id: str = None) -> None:
    """Generate a summary of recent messages."""
    if memory_store is None:
        return
    
    try:
        messages = memory_store.find_by_type(
            MemoryType.EPISODIC_CONVERSATION,
            user_id=user_id,
            limit=20,
            include_shared=False,
        )
        
        if len(messages) < 10:
            return
        
        formatted_messages = "\n".join(
            f"{msg.metadata.get('role', 'unknown')}: {msg.content}" 
            for msg in reversed(messages[:10])
        )
        summary_prompt = f"Summarize the key points from the following conversation:\n\n{formatted_messages}"
        
        if not LLM_URI or not LLM_API_KEY or not LLM_MODEL:
            logger.error("LLM_URI, LLM_API_KEY, or LLM_MODEL not configured. Cannot generate summary.")
            return
        
        client_openai = OpenAI(base_url=LLM_URI, api_key=LLM_API_KEY)
        response = client_openai.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": summary_prompt}
            ]
        )
        summary = response.choices[0].message.content
        if not summary or not isinstance(summary, str):
            logger.error(f"Invalid summary generated: {summary}")
            return
        
        all_topics = []
        all_keywords = []
        all_entities = []
        source_ids = []
        for msg in messages[:10]:
            all_topics.extend(msg.metadata.get("topics", []))
            all_keywords.extend(msg.metadata.get("keywords", []))
            all_entities.extend(msg.metadata.get("entities", []))
            if msg.id:
                source_ids.append(msg.id)
        
        unique_topics = list(dict.fromkeys(all_topics))[:10]
        unique_keywords = list(dict.fromkeys(all_keywords))[:15]
        
        memory_store.store(
            memory_type=MemoryType.EPISODIC_SUMMARY,
            content=summary,
            user_id=user_id,
            conversation_id=CONVERSATION_ID,
            importance_score=0.7,
            generate_vector=True,
            metadata={
                "source_message_count": len(messages[:10]),
                "source_message_ids": source_ids,
                "topics": unique_topics,
                "keywords": unique_keywords,
                "entities": all_entities[:10],
            },
        )
        logger.info("Generated and stored summary in new memory system")
    except Exception as e:
        logger.error(f"Failed to generate or store summary: {e}")


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough: ~4 chars per token)."""
    return len(text) // 4


def login(username: str, password: str, state: SessionState) -> Tuple[str, SessionState, str]:
    """Handle user login."""
    if not username or not password:
        return "Please enter both username and password.", state, gr.update(visible=False)
    
    if user_manager is None:
        return "Database connection unavailable. Please try again later.", state, gr.update(visible=False)
    
    user = user_manager.authenticate(username, password)
    if user:
        state.user = user
        state.messages = []
        state.tool_usage = []
        state.message_count_since_maintenance = 0
        
        # Get or create session
        if session_manager is not None:
            state.chat_session_id = session_manager.get_or_create_user_session(user_id=user.id)
        
        # Get AI greeting
        state.ai_greeting = get_ai_greeting(user.display_name)
        
        logger.info(f"User '{user.username}' logged in")
        return f"Welcome, {user.display_name}!", state, gr.update(visible=True)
    else:
        return "Invalid username or password.", state, gr.update(visible=False)


def logout(state: SessionState) -> Tuple[str, SessionState, str]:
    """Handle user logout."""
    if state.user:
        logger.info(f"User '{state.user.username}' logged out")
    state.user = None
    state.chat_session_id = None
    state.messages = []
    state.tool_usage = []
    state.ai_greeting = None
    return "You have been logged out.", state, gr.update(visible=False)


def chat_stream(message: str, history: List[List[str]], state: SessionState) -> Generator[Tuple[List[List[str]], str, SessionState, str], None, None]:
    """Handle chat message with streaming response."""
    if not state.is_authenticated():
        yield history, "", state, "Please log in first."
        return
    
    if not message.strip():
        yield history, "", state, ""
        return
    
    current_user = state.user
    if agent is None:
        yield history, "", state, "Agent not initialized. Please check configuration."
        return
    
    # Add user message to history
    history.append([message, None])
    
    # Store user message in memory
    if memory_store is not None:
        user_extraction = extract_topics_and_keywords(message)
        user_entities = extract_entities(message)
        
        importance = DEFAULT_IMPORTANCE_SCORE
        if any(marker in message.lower() for marker in ["remember this", "important", "don't forget", "keep this"]):
            importance = 0.8
        
        user_msg_id = memory_store.store(
            memory_type=MemoryType.EPISODIC_CONVERSATION,
            content=message,
            user_id=current_user.id if current_user else None,
            session_id=state.chat_session_id,
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
        logger.info(f"Stored user message in memory system: {user_msg_id}")
    
    # Log user message to session
    if session_manager is not None and state.chat_session_id:
        session_manager.add_message(
            session_id=state.chat_session_id,
            role="user",
            content=message,
        )
    
    # Update profile
    if profile_agent:
        deps = Deps(mongo_client=client, current_user=current_user)
        try:
            update_profile_from_message(profile_agent, message, deps, log_tool_usage)
        except Exception as profile_exc:
            logger.error(f"Failed to update profile: {profile_exc}")
    
    # Get context and build augmented prompt
    recent_context = get_recent_context_for_prompt(user_id=current_user.id if current_user else None)
    user_profile = build_user_profile_context()
    augmentation_blocks = []
    if user_profile:
        augmentation_blocks.append(
            "User profile and preferences:\n"
            f"{user_profile}"
        )
    if recent_context:
        augmentation_blocks.append(
            "Recent context to remember:\n"
            f"{recent_context}"
        )
    if augmentation_blocks:
        augmented_prompt = (
            "\n\n".join(augmentation_blocks)
            + "\n\nCurrent user input:\n"
            + message
        )
    else:
        augmented_prompt = message
    
    # Stream agent response
    full_response = ""
    start_time = datetime.now(timezone.utc)
    token_count = 0
    
    try:
        deps = Deps(mongo_client=client, current_user=current_user)
        
        # Use asyncio to handle async streaming
        async def stream_response():
            nonlocal full_response, token_count
            async with agent.run_stream(augmented_prompt, deps=deps) as result:
                async for message_chunk in result.stream_text():
                    if message_chunk:
                        if full_response and message_chunk.startswith(full_response):
                            new_content = message_chunk[len(full_response):]
                            full_response += new_content
                        elif len(message_chunk) >= len(full_response):
                            full_response = message_chunk
                        
                        token_count = estimate_tokens(full_response)
                        current_time = datetime.now(timezone.utc)
                        elapsed = (current_time - start_time).total_seconds()
                        
                        if elapsed > 0:
                            tokens_per_sec = token_count / elapsed
                            yield (history + [[None, full_response]], f"⚡ {tokens_per_sec:.1f} tokens/sec ({token_count} tokens)")
                        else:
                            yield (history + [[None, full_response]], "Generating...")
        
        # Run the async generator
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        gen = stream_response()
        
        # Yield chunks as they come
        last_token_info = "Generating..."
        while True:
            try:
                updated_history, token_info = loop.run_until_complete(gen.__anext__())
                last_token_info = token_info
                yield updated_history, "", state, token_info
            except StopAsyncIteration:
                break
        loop.close()
        
        # Final response
        final_time = datetime.now(timezone.utc)
        total_elapsed = (final_time - start_time).total_seconds()
        if total_elapsed > 0:
            final_rate = token_count / total_elapsed
            token_info = f"✓ {final_rate:.1f} tokens/sec ({token_count} tokens, {total_elapsed:.1f}s)"
        else:
            token_info = f"✓ {token_count} tokens"
        
        # Store assistant message
        if memory_store is not None and full_response and isinstance(full_response, str):
            assistant_extraction = extract_topics_and_keywords(full_response)
            assistant_entities = extract_entities(full_response)
            is_substantive = bool(assistant_entities or assistant_extraction.get("topics"))
            
            assistant_msg_id = memory_store.store(
                memory_type=MemoryType.EPISODIC_CONVERSATION,
                content=full_response,
                user_id=current_user.id if current_user else None,
                session_id=state.chat_session_id,
                conversation_id=CONVERSATION_ID,
                importance_score=DEFAULT_IMPORTANCE_SCORE,
                generate_vector=is_substantive,
                metadata={
                    "role": "assistant",
                    "topics": assistant_extraction.get("topics", []),
                    "keywords": assistant_extraction.get("keywords", []),
                    "entities": assistant_entities,
                },
            )
            logger.info(f"Stored assistant message in memory system: {assistant_msg_id}")
        
        # Log assistant message to session
        if session_manager is not None and state.chat_session_id:
            session_manager.add_message(
                session_id=state.chat_session_id,
                role="assistant",
                content=full_response[:5000],
                tool_calls=[],
            )
        
        # Generate summary if needed
        try:
            generate_summary(user_id=current_user.id if current_user else None)
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
        
        # Auto memory maintenance
        state.message_count_since_maintenance += 1
        if state.message_count_since_maintenance >= MEMORY_MAINTENANCE_THRESHOLD:
            state.message_count_since_maintenance = 0
        
        yield history, "", state, token_info
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        error_msg = f"I encountered an error: {str(e)}"
        history[-1][1] = error_msg
        yield history, "", state, "Error occurred"


def get_tool_usage_display(state: SessionState) -> str:
    """Get formatted tool usage for display."""
    if not state.tool_usage:
        return "No tools invoked yet."
    return "\n".join(f"[{ts}] {desc}" for ts, desc in reversed(state.tool_usage[-10:]))


def get_profile_display(state: SessionState) -> str:
    """Get formatted profile for display."""
    profile = build_user_profile_context()
    if profile:
        return profile
    return "No preferences captured yet."


def create_chat_interface(state: SessionState):
    """Create the main chat interface."""
    with gr.Row():
        with gr.Column(scale=1, min_width=250):
            # Sidebar
            user_info = gr.Markdown("")
            tool_usage_display = gr.Textbox(
                label="🛠️ Tool Usage",
                value=get_tool_usage_display(state),
                lines=10,
                interactive=False
            )
            profile_display = gr.Markdown(
                value=get_profile_display(state),
                label="📝 Profile"
            )
            
            if state.is_admin():
                with gr.Row():
                    gr.Button("📋 Session Audit", link="/?tab=session_audit")
                    gr.Button("⚙️ Admin Dashboard", link="/?tab=admin")
        
        with gr.Column(scale=3):
            # Main chat area
            greeting = gr.Markdown(
                value=state.ai_greeting or f"Welcome, {state.user.display_name}!" if state.user else "Please log in."
            )
            token_rate = gr.Textbox(
                label="Token Rate",
                value="",
                interactive=False,
                visible=False
            )
            
            chatbot = gr.Chatbot(
                label="Chat",
                height=500,
                show_copy_button=True
            )
            
            msg = gr.Textbox(
                label="Type your message",
                placeholder="Type your message here...",
                lines=2
            )
            
            with gr.Row():
                submit_btn = gr.Button("Send", variant="primary")
                clear_btn = gr.Button("Clear")
    
    return chatbot, msg, submit_btn, clear_btn, greeting, token_rate, user_info, tool_usage_display, profile_display


def load_user_list(state: SessionState) -> Tuple[str, pd.DataFrame]:
    """Load user list for admin dashboard."""
    if not state.is_admin() or user_manager is None:
        return "Access denied.", pd.DataFrame()
    
    users = user_manager.list_users(active_only=False)
    counts = user_manager.get_user_count()
    
    counts_text = f"""
    **User Statistics:**
    - Total Users: {counts.get('total', 0)}
    - Admins: {counts.get('admin', 0)}
    - Regular Users: {counts.get('user', 0)}
    """
    
    user_data = []
    for user in users:
        user_data.append({
            "Username": user.username,
            "Display Name": user.display_name,
            "Role": user.role.title(),
            "Active": "Yes" if user.is_active else "No",
            "Last Login": str(user.last_login) if user.last_login else "Never"
        })
    
    df = pd.DataFrame(user_data)
    return counts_text, df


def create_user_handler(username: str, password: str, display_name: str, role: str, state: SessionState) -> Tuple[str, pd.DataFrame]:
    """Handle user creation."""
    if not state.is_admin() or user_manager is None:
        return "Access denied.", pd.DataFrame()
    
    if not username or not password or not display_name:
        return "All fields are required.", pd.DataFrame()
    
    try:
        role_enum = UserRole(role)
        new_user = user_manager.create_user(
            username=username,
            password=password,
            display_name=display_name,
            role=role_enum,
        )
        
        if new_user:
            return f"Created user {new_user.display_name} successfully!", load_user_list(state)[1]
        else:
            return "Failed to create user (username may already exist).", pd.DataFrame()
    except Exception as e:
        return f"Error: {str(e)}", pd.DataFrame()


def load_metrics(state: SessionState) -> Tuple[str, go.Figure]:
    """Load metrics for admin dashboard."""
    if not state.is_admin():
        return "Access denied.", go.Figure()
    
    try:
        from database import db
        db_stats = db.command("dbStats")
        
        storage_mb = db_stats.get("storageSize", 0) / (1024 * 1024)
        data_mb = db_stats.get("dataSize", 0) / (1024 * 1024)
        index_mb = db_stats.get("indexSize", 0) / (1024 * 1024)
        
        metrics_text = f"""
        **Database Statistics:**
        - Storage Size: {storage_mb:.2f} MB
        - Data Size: {data_mb:.2f} MB
        - Index Size: {index_mb:.2f} MB
        - Collections: {db_stats.get('collections', 0)}
        """
        
        # Create a simple bar chart
        fig = go.Figure(data=[
            go.Bar(x=["Storage", "Data", "Index"], y=[storage_mb, data_mb, index_mb])
        ])
        fig.update_layout(title="Database Size (MB)")
        
        return metrics_text, fig
    except Exception as e:
        return f"Error loading metrics: {str(e)}", go.Figure()


def load_memory_stats(state: SessionState) -> Tuple[str, go.Figure]:
    """Load memory statistics."""
    if not state.is_admin() or memory_store is None:
        return "Access denied or memory store unavailable.", go.Figure()
    
    try:
        # Get memory counts by type
        memory_types = [
            MemoryType.WORKING,
            MemoryType.SEMANTIC_CACHE,
            MemoryType.PROCEDURAL,
            MemoryType.EPISODIC_CONVERSATION,
            MemoryType.EPISODIC_SUMMARY,
            MemoryType.SEMANTIC_KNOWLEDGE,
            MemoryType.SHARED,
        ]
        
        counts = {}
        for mem_type in memory_types:
            try:
                memories = memory_store.find_by_type(mem_type, limit=10000)
                counts[mem_type.value] = len(memories)
            except:
                counts[mem_type.value] = 0
        
        stats_text = f"""
        **Memory Statistics:**
        - Working: {counts.get('working', 0)}
        - Semantic Cache: {counts.get('semantic_cache', 0)}
        - Procedural: {counts.get('procedural', 0)}
        - Episodic Conversation: {counts.get('episodic_conversation', 0)}
        - Episodic Summary: {counts.get('episodic_summary', 0)}
        - Semantic Knowledge: {counts.get('semantic_knowledge', 0)}
        - Shared: {counts.get('shared', 0)}
        """
        
        # Create bar chart
        fig = go.Figure(data=[
            go.Bar(x=list(counts.keys()), y=list(counts.values()))
        ])
        fig.update_layout(title="Memory Counts by Type", xaxis_title="Memory Type", yaxis_title="Count")
        
        return stats_text, fig
    except Exception as e:
        return f"Error loading memory stats: {str(e)}", go.Figure()


def create_admin_dashboard(state: SessionState):
    """Create the admin dashboard interface."""
    if not state.is_admin():
        return gr.Markdown("Access denied. This page is only available to administrators.")
    
    with gr.Tabs():
        with gr.Tab("👥 Users"):
            user_counts = gr.Markdown("")
            user_list = gr.Dataframe(
                headers=["Username", "Display Name", "Role", "Active", "Last Login"],
                label="User List",
                interactive=False
            )
            
            with gr.Row():
                new_username = gr.Textbox(label="Username")
                new_password = gr.Textbox(label="Password", type="password")
                new_display_name = gr.Textbox(label="Display Name")
                new_role = gr.Dropdown(
                    choices=["admin", "user"],
                    value="user",
                    label="Role"
                )
            
            with gr.Row():
                create_user_btn = gr.Button("Create User", variant="primary")
                refresh_users_btn = gr.Button("Refresh")
            
            create_status = gr.Markdown("")
        
        with gr.Tab("📈 Metrics"):
            metrics_display = gr.Markdown("")
            metrics_plot = gr.Plot(label="Metrics Over Time")
        
        with gr.Tab("Memory"):
            memory_stats = gr.Markdown("")
            memory_plot = gr.Plot(label="Memory Visualization")
    
    # Load initial data
    counts_text, user_df = load_user_list(state)
    metrics_text, metrics_fig = load_metrics(state)
    mem_text, mem_fig = load_memory_stats(state)
    
    user_counts.value = counts_text
    user_list.value = user_df
    metrics_display.value = metrics_text
    metrics_plot.value = metrics_fig
    memory_stats.value = mem_text
    memory_plot.value = mem_fig
    
    return user_counts, user_list, new_username, new_password, new_display_name, new_role, create_user_btn, refresh_users_btn, metrics_display, metrics_plot, memory_stats, memory_plot, create_status


def load_sessions(state: SessionState, user_filter: str, date_range: str, flagged_only: bool, unreviewed_only: bool) -> Tuple[str, pd.DataFrame]:
    """Load sessions based on filters."""
    if not state.is_admin() or session_manager is None or user_manager is None:
        return "Access denied or database unavailable.", pd.DataFrame()
    
    try:
        # Get user options
        all_users = user_manager.list_users()
        user_options = {u.username: u.id for u in all_users}
        
        # Determine user filter
        selected_user_id = None
        if user_filter != "All":
            selected_user_id = user_options.get(user_filter)
        
        # Determine date range
        days_map = {
            "Last 7 days": 7,
            "Last 30 days": 30,
            "Last 90 days": 90,
            "All time": 365 * 10,
        }
        days = days_map.get(date_range, 30)
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Build query
        query = {"started_at": {"$gte": start_date.isoformat()}}
        if selected_user_id:
            query["user_id"] = selected_user_id
        if flagged_only:
            query["flagged"] = True
        if unreviewed_only:
            query["reviewed_by"] = None
        
        # Get sessions
        sessions = list(session_manager.collection.find(query).sort("started_at", -1).limit(100))
        
        # Calculate stats
        total_sessions = len(sessions)
        total_messages = sum(len(s.get("messages", [])) for s in sessions)
        flagged_count = sum(1 for s in sessions if s.get("flagged", False))
        unreviewed_count = sum(1 for s in sessions if not s.get("reviewed_by"))
        
        stats_text = f"""
        **Session Statistics:**
        - Total Sessions: {total_sessions}
        - Total Messages: {total_messages}
        - Flagged: {flagged_count}
        - Unreviewed: {unreviewed_count}
        """
        
        # Build dataframe
        session_data = []
        for session in sessions:
            user_id = session.get("user_id")
            user = user_manager.get_user_by_id(user_id) if user_id else None
            username = user.username if user else "Unknown"
            
            session_data.append({
                "Session ID": str(session.get("session_id", ""))[:20] + "...",
                "User": username,
                "Started": session.get("started_at", "")[:19] if session.get("started_at") else "",
                "Messages": len(session.get("messages", [])),
                "Flagged": "Yes" if session.get("flagged") else "No"
            })
        
        df = pd.DataFrame(session_data)
        return stats_text, df
    except Exception as e:
        return f"Error loading sessions: {str(e)}", pd.DataFrame()


def create_session_audit(state: SessionState):
    """Create the session audit interface."""
    if not state.is_admin():
        return gr.Markdown("Access denied. This page is only available to administrators.")
    
    with gr.Row():
        with gr.Column(scale=1):
            # Filters
            user_options = ["All"]
            if user_manager:
                user_options.extend([u.username for u in user_manager.list_users()])
            
            filter_user = gr.Dropdown(
                choices=user_options,
                value="All",
                label="Select User"
            )
            filter_date_range = gr.Dropdown(
                choices=["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
                value="Last 30 days",
                label="Date Range"
            )
            filter_flagged = gr.Checkbox(label="Only flagged sessions", value=False)
            filter_unreviewed = gr.Checkbox(label="Only unreviewed", value=True)
            apply_filters_btn = gr.Button("Apply Filters", variant="primary")
        
        with gr.Column(scale=3):
            session_stats = gr.Markdown("")
            session_list = gr.Dataframe(
                headers=["Session ID", "User", "Started", "Messages", "Flagged"],
                label="Sessions",
                interactive=False
            )
            session_details = gr.JSON(label="Session Details", visible=False)
    
    # Load initial data
    stats_text, session_df = load_sessions(state, "All", "Last 30 days", False, True)
    session_stats.value = stats_text
    session_list.value = session_df
    
    return filter_user, filter_date_range, filter_flagged, filter_unreviewed, apply_filters_btn, session_stats, session_list, session_details


def build_gradio_app():
    """Build the Gradio application."""
    # Note: some Gradio versions do not support the 'theme' argument on Blocks,
    # so we only set the title here for compatibility.
    with gr.Blocks(title="Pensive - Family Assistant") as app:
        # Session state
        session_state = gr.State(value=SessionState())
        
        # Login interface (wrapped in Group so visibility updates work reliably)
        with gr.Group(visible=True) as login_interface:
            with gr.Column():
                gr.Markdown("# 🔐 Login to Pensive - Family Assistant")
                login_username = gr.Textbox(label="Username", placeholder="Enter your username")
                login_password = gr.Textbox(label="Password", type="password", placeholder="Enter your password")
                login_btn = gr.Button("Login", variant="primary")
                login_status = gr.Markdown("")
                
                with gr.Accordion("First time here?", open=False):
                    gr.Markdown("""
                    **Default Admin Credentials:**
                    - Username: `admin`
                    - Password: `changeme`
                    
                    Please change the admin password after your first login!
                    """)
        
        # Main interface (hidden until login, also wrapped in Group for visibility control)
        with gr.Group(visible=False) as main_interface:
            with gr.Column():
                # Header
                with gr.Row():
                    gr.Markdown("# Pensive - Family Assistant")
                    logout_btn = gr.Button("Logout", variant="secondary")
                
                # Tabs for different views
                with gr.Tabs() as tabs:
                    with gr.Tab("💬 Chat", id="chat"):
                        with gr.Row():
                            # Admin sidebar: hidden for regular users, shown for admins via login handler
                            with gr.Column(scale=1, min_width=250, visible=False) as admin_sidebar:
                                # Sidebar
                                user_info = gr.Markdown("")
                                tool_usage_display = gr.Textbox(
                                    label="🛠️ Tool Usage",
                                    value="No tools invoked yet.",
                                    lines=10,
                                    interactive=False
                                )
                                profile_display = gr.Markdown(
                                    value="No preferences captured yet.",
                                    label="📝 Profile"
                                )
                                
                                admin_nav = gr.Row()
                                with admin_nav:
                                    gr.Markdown("**Navigation:**")
                                    gr.Markdown("- 📋 Session Audit")
                                    gr.Markdown("- ⚙️ Admin Dashboard")
                            
                            with gr.Column(scale=3):
                                # Main chat area
                                greeting = gr.Markdown("Please log in.")
                                token_rate = gr.Textbox(
                                    label="Token Rate",
                                    value="",
                                    interactive=False,
                                    visible=True
                                )
                                
                                chatbot = gr.Chatbot(
                                    label="Chat",
                                    height=500,
                                )
                                
                                msg = gr.Textbox(
                                    label="Type your message",
                                    placeholder="Type your message here...",
                                    lines=2
                                )
                                
                                with gr.Row():
                                    submit_btn = gr.Button("Send", variant="primary")
                                    clear_btn = gr.Button("Clear")
                
                with gr.Tab("⚙️ Admin Dashboard", id="admin", visible=False) as admin_tab:
                    # Admin dashboard components
                    with gr.Tabs():
                        with gr.Tab("👥 Users"):
                            user_counts = gr.Markdown("")
                            user_list = gr.Dataframe(
                                headers=["Username", "Display Name", "Role", "Active", "Last Login"],
                                label="User List",
                                interactive=False
                            )
                            
                            with gr.Row():
                                new_username = gr.Textbox(label="Username")
                                new_password = gr.Textbox(label="Password", type="password")
                                new_display_name = gr.Textbox(label="Display Name")
                                new_role = gr.Dropdown(
                                    choices=["admin", "user"],
                                    value="user",
                                    label="Role"
                                )
                            
                            with gr.Row():
                                create_user_btn = gr.Button("Create User", variant="primary")
                                refresh_users_btn = gr.Button("Refresh")
                            
                            create_status = gr.Markdown("")
                        
                        with gr.Tab("📈 Metrics"):
                            metrics_display = gr.Markdown("")
                            metrics_plot = gr.Plot(label="Metrics Over Time")
                        
                        with gr.Tab("Memory"):
                            memory_stats = gr.Markdown("")
                            memory_plot = gr.Plot(label="Memory Visualization")
                    
                    # Wire up admin dashboard handlers
                    def refresh_users(state):
                        counts_text, user_df = load_user_list(state)
                        return counts_text, user_df
                    
                    def create_user(username, password, display_name, role, state):
                        status, df = create_user_handler(username, password, display_name, role, state)
                        counts_text, _ = load_user_list(state)
                        return status, counts_text, df, "", "", "", ""
                    
                    def load_admin_data(state):
                        counts_text, user_df = load_user_list(state)
                        metrics_text, metrics_fig = load_metrics(state)
                        mem_text, mem_fig = load_memory_stats(state)
                        return counts_text, user_df, metrics_text, metrics_fig, mem_text, mem_fig
                    
                    refresh_users_btn.click(
                        refresh_users,
                        inputs=[session_state],
                        outputs=[user_counts, user_list]
                    )
                    
                    create_user_btn.click(
                        create_user,
                        inputs=[new_username, new_password, new_display_name, new_role, session_state],
                        outputs=[create_status, user_counts, user_list, new_username, new_password, new_display_name, new_role]
                    )
                    
                    # Load initial admin data when tab becomes visible
                    admin_tab.select(
                        load_admin_data,
                        inputs=[session_state],
                        outputs=[user_counts, user_list, metrics_display, metrics_plot, memory_stats, memory_plot]
                    )
                
                with gr.Tab("📋 Session Audit", id="session_audit", visible=False) as audit_tab:
                    # Session audit components
                    with gr.Row():
                        with gr.Column(scale=1):
                            # Filters
                            user_options = ["All"]
                            if user_manager:
                                user_options.extend([u.username for u in user_manager.list_users()])
                            
                            filter_user = gr.Dropdown(
                                choices=user_options,
                                value="All",
                                label="Select User"
                            )
                            filter_date_range = gr.Dropdown(
                                choices=["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
                                value="Last 30 days",
                                label="Date Range"
                            )
                            filter_flagged = gr.Checkbox(label="Only flagged sessions", value=False)
                            filter_unreviewed = gr.Checkbox(label="Only unreviewed", value=True)
                            apply_filters_btn = gr.Button("Apply Filters", variant="primary")
                        
                        with gr.Column(scale=3):
                            session_stats = gr.Markdown("")
                            session_list = gr.Dataframe(
                                headers=["Session ID", "User", "Started", "Messages", "Flagged"],
                                label="Sessions",
                                interactive=False
                            )
                            session_details = gr.JSON(label="Session Details", visible=False)
                    
                    # Wire up session audit handlers
                    def apply_filters(user_filter, date_range, flagged_only, unreviewed_only, state):
                        stats_text, session_df = load_sessions(state, user_filter, date_range, flagged_only, unreviewed_only)
                        return stats_text, session_df
                    
                    def load_audit_data(state):
                        stats_text, session_df = load_sessions(state, "All", "Last 30 days", False, True)
                        return stats_text, session_df
                    
                    apply_filters_btn.click(
                        apply_filters,
                        inputs=[filter_user, filter_date_range, filter_flagged, filter_unreviewed, session_state],
                        outputs=[session_stats, session_list]
                    )
                    
                    # Load initial audit data when tab becomes visible
                    audit_tab.select(
                        load_audit_data,
                        inputs=[session_state],
                        outputs=[session_stats, session_list]
                    )
        
        # Chat handlers
        def chat_submit(message, history, state):
            if not message.strip():
                return history, "", state, "", "", ""
            
            for updated_history, _, updated_state, token_info in chat_stream(message, history, state):
                yield (
                    updated_history,
                    "",
                    updated_state,
                    token_info,
                    get_tool_usage_display(updated_state),
                    get_profile_display(updated_state)
                )
        
        submit_btn.click(
            chat_submit,
            inputs=[msg, chatbot, session_state],
            outputs=[chatbot, msg, session_state, token_rate, tool_usage_display, profile_display]
        )
        
        msg.submit(
            chat_submit,
            inputs=[msg, chatbot, session_state],
            outputs=[chatbot, msg, session_state, token_rate, tool_usage_display, profile_display]
        )
        
        clear_btn.click(
            lambda state: ([], state),
            inputs=[session_state],
            outputs=[chatbot, session_state]
        )
        
        # Login handler
        def handle_login(username, password, state):
            status_msg, updated_state, visibility = login(username, password, state)
            if updated_state.is_authenticated():
                # Update user info
                user_md = f"👤 **{updated_state.user.display_name}**\nRole: {updated_state.user.role.title()}"
                greeting_md = updated_state.ai_greeting or f"Welcome, {updated_state.user.display_name}!"
                is_admin = updated_state.is_admin()
                return (
                    status_msg,
                    updated_state,
                    gr.update(visible=False),  # Hide login
                    gr.update(visible=True),   # Show main
                    gr.update(value=user_md),
                    gr.update(value=greeting_md),
                    gr.update(visible=is_admin),  # Admin nav visibility
                    gr.update(visible=is_admin),  # Admin dashboard tab
                    gr.update(visible=is_admin)   # Session audit tab
                )
            else:
                return (
                    status_msg,
                    updated_state,
                    gr.update(visible=True),   # Show login
                    gr.update(visible=False),  # Hide main
                    gr.update(),
                    gr.update(),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )
        
        login_btn.click(
            handle_login,
            inputs=[login_username, login_password, session_state],
            outputs=[login_status, session_state, login_interface, main_interface, user_info, greeting, admin_sidebar, admin_tab, audit_tab]
        )
        
        # Logout handler
        def handle_logout(state):
            status_msg, updated_state, _ = logout(state)
            new_state = SessionState()
            return (
                status_msg,
                new_state,
                gr.update(visible=True),   # Show login
                gr.update(visible=False),  # Hide main
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value="No tools invoked yet."),
                gr.update(value="No preferences captured yet.")
            )
        
        logout_btn.click(
            handle_logout,
            inputs=[session_state],
            outputs=[login_status, session_state, login_interface, main_interface, chatbot, greeting, user_info, tool_usage_display, profile_display]
        )
    
    return app


if __name__ == "__main__":
    app = build_gradio_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=8080,
        share=False,
        favicon_path="favicon.ico" if os.path.exists("favicon.ico") else None
    )

