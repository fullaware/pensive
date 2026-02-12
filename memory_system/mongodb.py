# MongoDB connection and utilities
"""MongoDB connection and vector search utilities."""
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from .config import Config


class MongoDB:
    """MongoDB connection manager with vector search support."""

    _client: Optional[AsyncIOMotorClient] = None
    _db = None

    @classmethod
    async def connect(cls) -> None:
        """Initialize MongoDB connection."""
        if cls._client is None:
            try:
                cls._client = AsyncIOMotorClient(Config.MONGODB_URI)
                cls._db = cls._client[Config.MONGODB_DB]
                # Test connection
                await cls._client.admin.command("ping")
            except PyMongoError as e:
                raise ConnectionError(f"Failed to connect to MongoDB: {e}")

    @classmethod
    async def disconnect(cls) -> None:
        """Close MongoDB connection."""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None

    @classmethod
    def get_collection(cls, name: str) -> Collection:
        """Get a collection by name."""
        if cls._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return cls._db[name]

    @classmethod
    async def create_vector_index(
        cls, collection_name: str, embedding_field: str = "embedding"
    ) -> None:
        """Create a vector search index on the specified collection.

        For MongoDB 8.x, use the createSearchIndex command.
        """
        if cls._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")

        # Use embedding dimensions from config
        num_dimensions = Config.EMBEDDING_DIMENSIONS

        from pymongo.operations import SearchIndexModel
        from pymongo import IndexModel

        # Create a vector search index using the modern approach
        index_name = "vector_index"
        index_doc = {
            "name": index_name,
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "path": embedding_field,
                        "numDimensions": num_dimensions,
                        "similarity": "cosine",
                        "type": "vector"
                    }
                ]
            },
        }

        try:
            # Try using createSearchIndex (MongoDB 7.0+)
            await cls._db[collection_name].create_search_index(index_doc)
            print(f"Vector index '{index_name}' created for collection '{collection_name}' with {num_dimensions} dimensions")
        except Exception as e:
            print(f"Vector index creation: {e}")


    @classmethod
    async def recreate_vector_index(
        cls, collection_name: str, embedding_field: str = "embedding"
    ) -> None:
        """Recreate a vector search index with the correct dimensions.

        This will delete the existing index and create a new one with the current
        EMBEDDING_DIMENSIONS configuration.

        Args:
            collection_name: Name of the collection
            embedding_field: Name of the embedding field
        """
        if cls._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")

        num_dimensions = Config.EMBEDDING_DIMENSIONS

        try:
            # List and delete existing vector indexes
            indexes = await cls._db[collection_name].list_search_indexes().to_list(length=None)
            for idx in indexes:
                if idx.get("type") == "vectorSearch":
                    index_name = idx.get("name")
                    if index_name:
                        print(f"Deleting existing index: {index_name}")
                        await cls._db[collection_name].drop_search_index(index_name)

            # Create new index with correct dimensions
            index_name = "vector_index"
            index_doc = {
                "name": index_name,
                "type": "vectorSearch",
                "definition": {
                    "fields": [
                        {
                            "path": embedding_field,
                            "numDimensions": num_dimensions,
                            "similarity": "cosine",
                            "type": "vector"
                        }
                    ]
                },
            }

            await cls._db[collection_name].create_search_index(index_doc)
            print(f"Vector index '{index_name}' recreated for collection '{collection_name}' with {num_dimensions} dimensions")
        except Exception as e:
            print(f"Error recreating vector index: {e}")


# Global instance for easy access
db = MongoDB()
