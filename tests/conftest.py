# Test Configuration
"""Pytest configuration and fixtures for testing."""
import pytest
import pytest_asyncio
from memory_system import MongoDB


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Create a test MongoDB connection."""
    # Connect to MongoDB
    await MongoDB.connect()
    
    yield MongoDB

    # Cleanup - disconnect
    if MongoDB._client:
        await MongoDB.disconnect()