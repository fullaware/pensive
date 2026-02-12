#!/usr/bin/env python3
"""Script to add embeddings to existing facts in MongoDB."""
import asyncio
import sys
from memory_system import MongoDB, Config, SemanticMemory


async def add_embeddings_to_facts():
    """Add embeddings to existing facts that don't have them."""
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

        semantic = SemanticMemory()
        collection = semantic.collection

        # Find all facts without embeddings
        facts_without_embeddings = await collection.find({
            "embedding": {"$exists": False},
            "archived": {"$ne": True}
        }).to_list(length=None)

        print(f"Found {len(facts_without_embeddings)} facts without embeddings")
        print()

        for fact in facts_without_embeddings:
            key = fact.get("key", "unknown")
            value = fact.get("value", "")
            fact_id = str(fact["_id"])

            # Generate embedding for the fact
            fact_text = f"{key}: {value}"
            embedding = await semantic.embedding_client.generate_embedding(fact_text)

            if embedding:
                # Update the fact with the embedding
                await collection.update_one(
                    {"_id": fact["_id"]},
                    {"$set": {"embedding": embedding}}
                )
                print(f"  Added embedding to fact: {key} = {value[:50]}...")
            else:
                print(f"  Failed to generate embedding for: {key}")

        print()
        print("Done! All facts now have embeddings.")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await MongoDB.disconnect()


if __name__ == "__main__":
    asyncio.run(add_embeddings_to_facts())