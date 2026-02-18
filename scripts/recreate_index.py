#!/usr/bin/env python3
"""Script to recreate the MongoDB vector index with correct dimensions and re-embed all documents."""
import asyncio
import sys
from memory_system import MongoDB, Config
from utils import EmbeddingClient


async def reembed_facts(embedding_client: EmbeddingClient):
    """Re-embed all facts in the facts collection."""
    print("Re-embedding facts...")
    collection = MongoDB.get_collection("facts")
    
    # Get all non-archived facts
    cursor = collection.find({"archived": {"$ne": True}})
    facts = await cursor.to_list(length=None)
    
    print(f"  Found {len(facts)} facts to re-embed")
    
    for fact in facts:
        key = fact.get("key", "")
        value = fact.get("value", "")
        fact_text = f"{key}: {value}"
        
        # Generate new embedding
        embedding = await embedding_client.generate_embedding(fact_text)
        if embedding:
            # Update the fact with the new embedding
            await collection.update_one(
                {"_id": fact["_id"]},
                {"$set": {"embedding": embedding}}
            )
            print(f"  Updated fact: {key[:50]}...")
        else:
            print(f"  Warning: Failed to generate embedding for fact: {key[:50]}...")
    
    print(f"  Completed re-embedding {len(facts)} facts")


async def reembed_episodic_memories(embedding_client: EmbeddingClient):
    """Re-embed all episodic memories in the episodic_memories collection."""
    print("Re-embedding episodic memories...")
    collection = MongoDB.get_collection("episodic_memories")
    
    # Get all documents with embeddings
    cursor = collection.find({"embedding": {"$ne": None}})
    memories = await cursor.to_list(length=None)
    
    print(f"  Found {len(memories)} episodic memories to re-embed")
    
    for memory in memories:
        content = memory.get("content", "")
        
        # Generate new embedding
        embedding = await embedding_client.generate_embedding(content)
        if embedding:
            # Update the memory with the new embedding
            await collection.update_one(
                {"_id": memory["_id"]},
                {"$set": {"embedding": embedding}}
            )
            print(f"  Updated memory: {content[:50]}...")
        else:
            print(f"  Warning: Failed to generate embedding for memory: {content[:50]}...")
    
    print(f"  Completed re-embedding {len(memories)} episodic memories")


async def main():
    """Recreate vector indexes and re-embed all documents."""
    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    print(f"Using EMBEDDING_DIMENSIONS: {Config.EMBEDDING_DIMENSIONS}")
    print()

    try:
        # Connect to MongoDB
        await MongoDB.connect()
        print("Connected to MongoDB successfully!")
        print()

        # Collections to recreate indexes for
        collections = ["episodic_memories", "facts"]

        for collection_name in collections:
            print(f"Recreating index for collection: {collection_name}")
            await MongoDB.recreate_vector_index(collection_name)
            print()

        # Create embedding client for re-embedding
        embedding_client = EmbeddingClient()

        # Re-embed all documents
        await reembed_facts(embedding_client)
        print()
        await reembed_episodic_memories(embedding_client)
        print()

        # Close embedding client
        await embedding_client.close()

        print("Done! Vector indexes have been recreated and all documents have been re-embedded.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await MongoDB.disconnect()


if __name__ == "__main__":
    asyncio.run(main())