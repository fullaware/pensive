# Query Router Tests
"""Tests for the query router functionality."""
import pytest
from memory_system import QueryRouter


@pytest.mark.asyncio
async def test_determine_intent_fact():
    """Test intent determination for factual queries."""
    router = QueryRouter()
    intent = await router.determine_intent("What is my name?")
    assert intent["intent"] == "fact"
    assert "name" in intent["query"].lower()


@pytest.mark.asyncio
async def test_determine_intent_task():
    """Test intent determination for task-related queries."""
    router = QueryRouter()
    intent = await router.determine_intent("What tasks do I have?")
    assert intent["intent"] == "task"


@pytest.mark.asyncio
async def test_determine_intent_conversation():
    """Test intent determination for conversation queries."""
    router = QueryRouter()
    intent = await router.determine_intent("Tell me about our previous chat")
    assert intent["intent"] == "conversation"


@pytest.mark.asyncio
async def test_generate_memory_query():
    """Test query generation for memory lookup."""
    router = QueryRouter()

    # Fact query
    intent = {"intent": "fact", "query": "user name"}
    query = await router.generate_memory_query("What is my name?", intent)
    assert "name" in query.lower()

    # Task query
    intent = {"intent": "task", "query": "due tasks"}
    query = await router.generate_memory_query("What's due?", intent)
    assert "task" in query.lower()


@pytest.mark.asyncio
async def test_route_query():
    """Test complete query routing."""
    router = QueryRouter()
    routing = await router.route_query("What is my name?")

    assert routing["intent"]["intent"] == "fact"
    assert "semantic" in routing["memory_systems"]
    assert routing["query"]


@pytest.mark.asyncio
async def test_close_router():
    """Test closing the router."""
    router = QueryRouter()
    await router.close()


@pytest.mark.asyncio
async def test_router_with_complex_query():
    """Test routing with a complex query."""
    router = QueryRouter()
    intent = await router.determine_intent(
        "Based on our conversation yesterday, what project are we working on?"
    )
    assert intent["intent"] in ["conversation", "task"]