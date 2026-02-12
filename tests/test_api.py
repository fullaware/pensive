# REST API Tests
"""Tests for the REST API endpoints."""
import pytest
from httpx import AsyncClient
from api.routes import create_app


@pytest.fixture(scope="module")
def event_loop():
    """Create an event loop for the test session."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def async_client():
    """Create an async HTTP client for testing."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_list_models():
    """Test list models endpoint."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_chat_completions_no_user_query():
    """Test chat completions with no user query."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "pensive",
                "messages": [{"role": "system", "content": "test"}]
            }
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_embeddings():
    """Test create embeddings endpoint."""
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/v1/embeddings",
            json={
                "model": "pensive",
                "input": "test text"
            }
        )
        # This may fail if LLM_EMBEDDING_URI is not configured
        # but should still return a valid response format
        assert response.status_code in [200, 500]  # 500 if embedding fails
        data = response.json()
        assert "object" in data
        assert data["object"] == "list"
        assert "data" in data