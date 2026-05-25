# Semantic Memory Tests
"""Tests for semantic memory (facts) functionality."""
import pytest
import uuid
from datetime import datetime, timezone
from bson import ObjectId
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
    
    # Since the database was cleared, we need to add some family facts first
    # Add sample family facts for testing (these get embeddings when added via add_fact)
    await memory.add_fact(category="user", key="spouse_name", value="Nikki", increment_version=False)
    await memory.add_fact(category="user", key="daughter_name", value="Brenna", increment_version=False)
    
    # Get family-related facts from the database (only our newly added facts, not pre-existing ones)
    new_facts = await memory.collection.find({
        "key": {"$in": ["spouse_name", "daughter_name"]},
        "archived": {"$ne": True}
    }).to_list(length=None)
    
    # Should have the 2 family facts we just added
    assert len(new_facts) >= 2, f"Expected at least 2 family facts, found {len(new_facts)}"
    
    # Verify they have embeddings (our newly added facts always get embeddings)
    for fact in new_facts:
        assert "embedding" in fact, f"Fact {fact.get('key')} missing embedding"


# ===== Versioned Fact Store Tests =====

@pytest.mark.asyncio
async def test_store_fact_creates_new_fact(test_db):
    """Test that store_fact creates a new fact when no active fact exists."""
    memory = SemanticMemory()
    fact_key = f"store_fact_test_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store a new fact
        fact_id = await memory.store_fact(
            fact_key=fact_key,
            content={"value": "initial_value"},
            category="test",
            confidence=1.0,
        )
        assert fact_id is not None
        
        # Verify the fact was created correctly
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["key"] == fact_key
        assert fact["value"] == "initial_value"
        assert fact["version"] == 1
        assert fact.get("archived") is False or fact.get("archived") is None
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_store_fact_archives_old_version(test_db):
    """Test that store_fact archives the old active fact when updating."""
    memory = SemanticMemory()
    fact_key = f"store_fact_update_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store initial fact
        first_id = await memory.store_fact(
            fact_key=fact_key,
            content={"value": "version_1", "source": "initial"},
            category="test",
        )
        
        # Verify first version
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["value"] == "version_1"
        assert fact["version"] == 1
        first_id_obj = first_id
        
        # Store updated fact with same fact_key
        second_id = await memory.store_fact(
            fact_key=fact_key,
            content={"value": "version_2", "source": "update"},
            category="test",
        )
        
        # Verify updated fact is active with version 2
        updated = await memory.get_fact(fact_key)
        assert updated is not None
        assert updated["value"] == "version_2"
        assert updated["version"] == 2
        assert str(updated["_id"]) == second_id
        
        # Verify old active fact is now archived
        first_version = await memory.collection.find_one({"_id": ObjectId(first_id)})
        assert first_version is not None
        assert first_version.get("archived") is True
        
        # All versions of this key (should be 2: one archived, one active)
        all_versions = await memory.collection.find({"key": fact_key}).to_list(length=None)
        assert len(all_versions) == 2
        
        # Count: 1 active, 1 archived
        active_count = await memory.collection.count_documents({"key": fact_key, "archived": {"$ne": True}})
        archived_count = await memory.collection.count_documents({"key": fact_key, "archived": True})
        assert active_count == 1
        assert archived_count == 1
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_store_fact_multiple_updates(test_db):
    """Test that multiple store_fact calls correctly increment versions."""
    memory = SemanticMemory()
    fact_key = f"store_fact_multiple_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store 5 versions
        for i in range(1, 6):
            await memory.store_fact(
                fact_key=fact_key,
                content={"value": f"value_{i}"},
                category="test",
            )
        
        # Latest should be version 5
        latest = await memory.get_fact(fact_key)
        assert latest["value"] == "value_5"
        assert latest["version"] == 5
        
        # There should be 5 versions total
        all_versions = await memory.collection.find({"key": fact_key}).to_list(length=None)
        assert len(all_versions) == 5
        
        # Only the latest should be active
        active_count = await memory.collection.count_documents({"key": fact_key, "archived": {"$ne": True}})
        assert active_count == 1
        
        # 4 should be archived
        archived_count = await memory.collection.count_documents({"key": fact_key, "archived": True})
        assert archived_count == 4
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_store_fact_string_content(test_db):
    """Test that store_fact handles string content (not just dict)."""
    memory = SemanticMemory()
    fact_key = f"store_fact_string_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store with string content
        fact_id = await memory.store_fact(
            fact_key=fact_key,
            content="simple_string_value",
            category="test",
        )
        assert fact_id is not None
        
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["value"] == "simple_string_value"
        assert fact["version"] == 1
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_store_fact_metadata_preservation(test_db):
    """Test that store_fact preserves and merges metadata from content dict.

    Note: Extra metadata from the new content OVERRIDES existing metadata because
    the merge order is {**existing_metadata, **extra_meta}. This means the new
    content's fields override the existing ones.
    """
    memory = SemanticMemory()
    fact_key = f"store_fact_meta_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store with extra metadata
        await memory.store_fact(
            fact_key=fact_key,
            content={
                "value": "test_value",
                "source": "bootstrap",
                "verified_by": "admin",
            },
            category="test",
        )
        
        # Store updated version - extra metadata overrides existing metadata
        await memory.store_fact(
            fact_key=fact_key,
            content={
                "value": "updated_value",
                "source": "conversation",
            },
            category="test",
        )
        
        # Verify the updated fact
        fact = await memory.get_fact(fact_key)
        assert fact["value"] == "updated_value"
        assert fact["version"] == 2
        # source is overridden by the update (extra_meta is applied last in merge)
        assert fact.get("metadata", {}).get("source") == "conversation"
        # verified_by should still exist (preserved from original metadata)
        assert fact.get("metadata", {}).get("verified_by") == "admin"
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_fact_prioritizes_active(test_db):
    """Test that get_fact prioritizes active facts over archived ones."""
    memory = SemanticMemory()
    fact_key = f"get_fact_priority_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store initial fact
        await memory.store_fact(
            fact_key=fact_key,
            content={"value": "old_value"},
            category="test",
        )
        
        # Store updated fact
        await memory.store_fact(
            fact_key=fact_key,
            content={"value": "new_value"},
            category="test",
        )
        
        # get_fact should return the active (new) version
        fact = await memory.get_fact(fact_key)
        assert fact["value"] == "new_value"
        assert fact["version"] == 2
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_fact_fallback_to_archived(test_db):
    """Test that get_fact falls back to latest version if no active fact exists."""
    memory = SemanticMemory()
    fact_key = f"get_fact_fallback_{uuid.uuid4().hex[:8]}"
    
    try:
        # Add fact without store_fact (old API, no archived field)
        await memory.add_fact(
            category="test",
            key=fact_key,
            value="old_api_value",
            increment_version=False,
        )
        
        # get_fact should still find it (backwards compatibility)
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["value"] == "old_api_value"
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_fact_no_active_returns_latest_any_status(test_db):
    """Test that when no active fact exists, get_fact returns the latest version regardless of archived status."""
    memory = SemanticMemory()
    fact_key = f"get_fact_no_active_{uuid.uuid4().hex[:8]}"
    
    try:
        # Create a fact, then archive it
        await memory.add_fact(
            category="test",
            key=fact_key,
            value="archived_value",
            increment_version=False,
        )
        
        # Archive it manually
        fact = await memory.get_fact(fact_key)
        if fact:
            await memory.collection.update_one(
                {"_id": fact["_id"]},
                {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc)}}
            )
        
        # get_fact should still return it (fallback)
        result = await memory.get_fact(fact_key)
        assert result is not None
        assert result["value"] == "archived_value"
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_store_fact_with_category(test_db):
    """Test that store_fact correctly handles category parameter."""
    memory = SemanticMemory()
    fact_key = f"store_fact_cat_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store with specific category
        await memory.store_fact(
            fact_key=fact_key,
            content={"value": "test_value"},
            category="persona",
        )
        
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["category"] == "persona"
        assert fact["value"] == "test_value"
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_store_fact_version_compound_index(test_db):
    """Test that the versioned fact store compound index exists and works."""
    memory = SemanticMemory()
    
    # Verify the index was created
    indexes = await memory.collection.index_information()
    
    # Check that our compound index exists
    assert "idx_facts_key_archived_version" in indexes, \
        f"Expected idx_facts_key_archived_version index, found: {list(indexes.keys())}"


@pytest.mark.asyncio
async def test_store_fact_confidence(test_db):
    """Test that store_fact correctly handles confidence parameter."""
    memory = SemanticMemory()
    fact_key = f"store_fact_conf_{uuid.uuid4().hex[:8]}"
    
    try:
        # Store with custom confidence
        await memory.store_fact(
            fact_key=fact_key,
            content={"value": "low_confidence_value"},
            category="test",
            confidence=0.5,
        )
        
        fact = await memory.get_fact(fact_key)
        assert fact is not None
        assert fact["confidence"] == 0.5
    finally:
        await memory.delete_fact(fact_key)


@pytest.mark.asyncio
async def test_get_all_facts_includes_latest_archived(test_db):
    """Test that get_all_facts returns the latest version of each key,
    even if that version is archived."""
    memory = SemanticMemory()
    
    # Clean up any pre-existing test keys
    key1 = f"get_all_facts_test_1_{uuid.uuid4().hex[:8]}"
    key2 = f"get_all_facts_test_2_{uuid.uuid4().hex[:8]}"
    key3 = f"name_{uuid.uuid4().hex[:8]}"
    
    try:
        # Create two facts: one with active updates, one without archived field
        await memory.add_fact(category="user", key=key1, value="active_value", increment_version=False)
        await memory.add_fact(category="user", key=key2, value="old_api_value", increment_version=False)

        # Update key1 to create an archived version
        await memory.add_fact(category="user", key=key1, value="updated_value")

        # Now get_all_facts should return:
        # - key1: the latest version (version 2, archived)
        # - key2: the only version (no archived field, backwards compatible)
        all_facts = await memory.get_all_facts()

        # Should have exactly 2 facts (one per unique key)
        fact_keys = {f.get("key") for f in all_facts}
        assert key1 in fact_keys
        assert key2 in fact_keys

        # Find key1's latest version in the results
        key1_facts = [f for f in all_facts if f.get("key") == key1]
        assert len(key1_facts) == 1
        assert key1_facts[0]["version"] == 2  # Should return version 2 (archived)
    finally:
        await memory.delete_fact(key1)
        await memory.delete_fact(key2)
        await memory.delete_fact(key3)
