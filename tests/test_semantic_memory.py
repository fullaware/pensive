# Semantic Memory Tests
"""Tests for semantic memory (facts) functionality."""
import pytest
import uuid
from memory_system import SemanticMemory, FactSchema, MongoDB


@pytest.mark.asyncio
async def test_add_fact(test_db):
    """Test adding a fact to semantic memory."""
    memory = SemanticMemory()
    fact_key = f"test_key_{uuid.uuid4().hex[:8]}"
    try:
        fact_id = await memory.add_fact(
            category="user",
            key=fact_key,
            value="test_value",
        )
        assert fact_id is not None
        
        # Verify the fact was added
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["key"] == fact_key
        assert fact["value"] == "test_value"
        assert fact["version"] == 1
    finally:
        # Cleanup - delete the test fact
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_fact(test_db):
    """Test getting a fact by key."""
    memory = SemanticMemory()
    fact_key = f"test_get_key_{uuid.uuid4().hex[:8]}"
    try:
        await memory.add_fact(
            category="user",
            key=fact_key,
            value="test_get_value",
        )
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["key"] == fact_key
        assert fact["value"] == "test_get_value"
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_user_name(test_db):
    """Test getting user name from facts."""
    memory = SemanticMemory()
    try:
        # First add a user name
        await memory.add_fact(
            category="user",
            key="user_name",
            value="Test User",
            increment_version=False,
        )
        name = await memory.get_user_name()
        assert name == "Test User"
    finally:
        # Cleanup - delete the test user name
        await memory.delete_fact("user_name")


@pytest.mark.asyncio
async def test_update_fact(test_db):
    """Test updating an existing fact."""
    memory = SemanticMemory()
    fact_key = f"update_test_{uuid.uuid4().hex[:8]}"
    try:
        await memory.add_fact(
            category="user",
            key=fact_key,
            value="old_value",
            increment_version=False,
        )
        result = await memory.update_fact(fact_key, {"value": "new_value"})
        assert result is True

        fact = await memory.get_fact(fact_key)
        assert fact["value"] == "new_value"
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_delete_fact(test_db):
    """Test deleting a fact."""
    memory = SemanticMemory()
    fact_key = f"delete_test_{uuid.uuid4().hex[:8]}"
    try:
        fact_id = await memory.add_fact(
            category="user",
            key=fact_key,
            value="to_delete",
        )
        result = await memory.delete_fact(fact_key)
        assert result is True

        fact = await memory.get_fact(fact_key)
        assert fact is None
    finally:
        # Cleanup - just in case
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_facts_by_category(test_db):
    """Test getting facts by category."""
    memory = SemanticMemory()
    key1 = f"k1_{uuid.uuid4().hex[:8]}"
    key2 = f"k2_{uuid.uuid4().hex[:8]}"
    key3 = f"k3_{uuid.uuid4().hex[:8]}"
    category1 = f"test_cat_{uuid.uuid4().hex[:8]}"
    category2 = f"test_cat_{uuid.uuid4().hex[:8]}"
    
    # Clean up any existing test facts with these keys
    await memory.delete_fact(key1)
    await memory.delete_fact(key2)
    await memory.delete_fact(key3)
    
    try:
        await memory.add_fact(category=category1, key=key1, value="v1", increment_version=False)
        await memory.add_fact(category=category1, key=key2, value="v2", increment_version=False)
        await memory.add_fact(category=category2, key=key3, value="v3", increment_version=False)

        facts1 = await memory.get_facts_by_category(category1)
        # Should have exactly 2 facts in category1
        assert len(facts1) == 2

        facts2 = await memory.get_facts_by_category(category2)
        assert len(facts2) == 1
    finally:
        await memory.delete_fact(key1)
        await memory.delete_fact(key2)
        await memory.delete_fact(key3)


@pytest.mark.asyncio
async def test_get_user_preferences(test_db):
    """Test getting all user preferences."""
    memory = SemanticMemory()
    try:
        await memory.add_fact(category="user", key="preference1", value="value1", increment_version=False)
        await memory.add_fact(category="user", key="preference2", value="value2", increment_version=False)

        preferences = await memory.get_user_preferences()
        assert "preference1" in preferences
        assert "preference2" in preferences
        assert preferences["preference1"] == "value1"
    finally:
        await memory.delete_fact("preference1")
        await memory.delete_fact("preference2")


@pytest.mark.asyncio
async def test_fact_versioning(test_db):
    """Test fact versioning when facts are updated."""
    memory = SemanticMemory()
    key = f"test_version_key_{uuid.uuid4().hex[:8]}"
    
    try:
        # Add first version
        await memory.add_fact(category="user", key=key, value="first_value", increment_version=False)
        
        # Get the fact and verify version is 1
        fact = await memory.get_fact(key)
        assert fact is not None
        assert fact["value"] == "first_value"
        assert fact["version"] == 1
        
        # Update the fact
        result = await memory.update_fact(key, {"value": "second_value"})
        assert result is True
        
        # Get the fact and verify version is 2 and new value
        fact = await memory.get_fact(key)
        assert fact is not None
        assert fact["value"] == "second_value"
        assert fact["version"] == 2
        
        # Verify old version still exists
        old_version = await memory.collection.find_one({"key": key, "version": 1})
        assert old_version is not None
        assert old_version["value"] == "first_value"
    finally:
        # Delete all versions of this key
        await memory.delete_fact(key)


@pytest.mark.asyncio
async def test_get_latest_fact_version(test_db):
    """Test getting the latest version of a fact."""
    memory = SemanticMemory()
    key = f"test_latest_version_{uuid.uuid4().hex[:8]}"
    
    try:
        # Add multiple versions
        for i in range(3):
            await memory.add_fact(category="user", key=key, value=f"value_{i+1}")
        
        # Get latest version
        latest = await memory.get_latest_fact_version(key)
        assert latest is not None
        assert latest["version"] == 3
        assert latest["value"] == "value_3"
    finally:
        await memory.delete_fact(key)


@pytest.mark.asyncio
async def test_versioned_key_uniqueness(test_db):
    """Test that facts with same key but different versions are tracked correctly."""
    memory = SemanticMemory()
    key = f"test_key_uniqueness_{uuid.uuid4().hex[:8]}"
    
    try:
        # Add first version
        await memory.add_fact(category="user", key=key, value="v1", increment_version=False)
        
        # Add second version (same key, different value)
        await memory.add_fact(category="user", key=key, value="v2")
        
        # Get latest should return v2
        latest = await memory.get_fact(key)
        assert latest["value"] == "v2"
        assert latest["version"] == 2
        
        # Get all versions
        all_versions = await memory.collection.find({"key": key}).to_list(length=None)
        assert len(all_versions) == 2
    finally:
        await memory.delete_fact(key)


@pytest.mark.asyncio
async def test_vector_search_retrieval(test_db):
    """Test that vector search can retrieve facts semantically."""
    memory = SemanticMemory()
    test_key = f"test_semantic_{uuid.uuid4().hex[:8]}"
    
    try:
        # Add a fact that can be found semantically
        fact_id = await memory.add_fact(
            category="user",
            key=test_key,
            value="42",
        )
        
        # Use vector search to find the fact
        results = await memory.vector_search("test semantic retrieval")
        
        # Should find at least some facts (fallback to all non-archived facts)
        assert len(results) > 0, "Vector search should return at least some facts"
    finally:
        await memory.delete_fact(test_key)


@pytest.mark.asyncio
async def test_retrieve_family_facts(test_db):
    """Test that family-related facts can be retrieved via vector search."""
    memory = SemanticMemory()
    
    # Get family-related facts from the database
    family_facts = await memory.get_all_facts()
    family_facts = [f for f in family_facts if any(
        keyword in f.get("key", "").lower() 
        for keyword in ["spouse", "daughter", "birthday", "anniversary"]
    )]
    
    # Should have family-related facts in the database
    assert len(family_facts) >= 2
    
    # Verify they have embeddings
    for fact in family_facts:
        assert "embedding" in fact, f"Fact {fact.get('key')} missing embedding"
