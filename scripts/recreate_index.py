#!/usr/bin/env python3
"""Script to recreate the MongoDB vector index with correct dimensions."""
import asyncio
import sys
from memory_system import MongoDB, Config


async def main():
    """Recreate vector indexes for all collections."""
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

        print("Done! Vector indexes have been recreated with the correct dimensions.")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await MongoDB.disconnect()


if __name__ == "__main__":
    asyncio.run(main())