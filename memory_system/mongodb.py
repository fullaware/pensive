# MongoDB connection and utilities
"""MongoDB connection and vector search utilities."""
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from .config import Config
import logging
import time

# Configure logging for MongoDB queries
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB connection manager with vector search support."""

    _client: Optional[AsyncIOMotorClient] = None
    _db = None
    _logging_enabled = True

    @classmethod
    def enable_logging(cls, enabled: bool = True) -> None:
        """Enable or disable MongoDB query logging."""
        cls._logging_enabled = enabled

    @classmethod
    async def connect(cls) -> None:
        """Initialize MongoDB connection."""
        if cls._client is None:
            try:
                cls._client = AsyncIOMotorClient(Config.MONGODB_URI)
                cls._db = cls._client[Config.MONGODB_DB]
                # Test connection
                await cls._client.admin.command("ping")
                if cls._logging_enabled:
                    logger.info("Connected to MongoDB successfully")
            except PyMongoError as e:
                raise ConnectionError(f"Failed to connect to MongoDB: {e}")

    @classmethod
    async def disconnect(cls) -> None:
        """Close MongoDB connection."""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            if cls._logging_enabled:
                logger.info("MongoDB connection closed")

    @classmethod
    def get_collection(cls, name: str) -> Collection:
        """Get a collection by name."""
        if cls._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return cls._db[name]

    @classmethod
    async def log_query(cls, collection_name: str, operation: str, filter_dict: Optional[dict] = None, 
                        extra_info: Optional[dict] = None, duration_ms: Optional[float] = None) -> None:
        """Log a MongoDB query while masking embeddings to avoid context overload.
        
        Args:
            collection_name: Name of the collection
            operation: Operation type (find, aggregate, insert, update, delete, vectorSearch)
            filter_dict: The filter/query dictionary (will have embeddings masked)
            extra_info: Additional info to log
            duration_ms: Query duration in milliseconds
        """
        if not cls._logging_enabled:
            return
            
        # Create a safe copy of filter_dict with embeddings masked
        safe_filter = None
        if filter_dict:
            safe_filter = {}
            for key, value in filter_dict.items():
                # Mask any field containing 'embedding' or 'vector' in the key
                if 'embedding' in key.lower() or 'vector' in key.lower():
                    safe_filter[key] = '<EMBEDDING_MASKED>'
                elif isinstance(value, dict):
                    # Recursively handle nested dicts
                    safe_filter[key] = cls._mask_embedding_in_dict(value)
                else:
                    safe_filter[key] = value
        
        # Build log message
        msg_parts = [f"[MongoDB] {collection_name}.{operation}"]
        if safe_filter:
            msg_parts.append(f"filter={safe_filter}")
        if extra_info:
            for key, value in extra_info.items():
                if 'embedding' in key.lower() or 'vector' in key.lower():
                    msg_parts.append(f"{key}=<EMBEDDING_MASKED>")
                else:
                    msg_parts.append(f"{key}={value}")
        if duration_ms is not None:
            msg_parts.append(f"duration={duration_ms:.2f}ms")
        
        logger.info(" | ".join(msg_parts))

    @classmethod
    def _mask_embedding_in_dict(cls, d: dict) -> dict:
        """Recursively mask embedding fields in a dictionary."""
        result = {}
        for key, value in d.items():
            if 'embedding' in key.lower() or 'vector' in key.lower():
                result[key] = '<EMBEDDING_MASKED>'
            elif isinstance(value, dict):
                result[key] = cls._mask_embedding_in_dict(value)
            elif isinstance(value, list):
                result[key] = cls._mask_embedding_in_list(value)
            else:
                result[key] = value
        return result

    @classmethod
    def _mask_embedding_in_list(cls, lst: list) -> list:
        """Recursively mask embedding fields in a list."""
        result = []
        for item in lst:
            if isinstance(item, dict):
                result.append(cls._mask_embedding_in_dict(item))
            elif isinstance(item, list):
                result.append(cls._mask_embedding_in_list(item))
            elif isinstance(item, str) and 'embedding' in item.lower():
                # Don't mask string values that just contain the word 'embedding'
                result.append(item)
            else:
                result.append(item)
        return result

    @classmethod
    async def create_vector_index(
        cls, collection_name: str, embedding_field: str = "embedding"
    ) -> None:
        """Create a vector search index on the specified collection.

        For MongoDB 8.x, use the createSearchIndex command.
        """
        if cls._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")

        num_dimensions = Config.EMBEDDING_DIMENSIONS

        # Use collection-specific index names for easier management
        if collection_name == "facts":
            index_name = "v_idx_facts"
        elif collection_name == "episodic_memories":
            index_name = "v_idx_episodic_memories"
        else:
            index_name = f"v_idx_{collection_name}"

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
            if cls._logging_enabled:
                logger.info(f"Vector index '{index_name}' created for collection '{collection_name}' with {num_dimensions} dimensions")
        except Exception as e:
            print(f"Vector index creation error: {e}")
            if cls._logging_enabled:
                logger.error(f"Vector index creation error for {collection_name}: {e}")

    @classmethod
    async def list_search_indexes(cls, collection_name: str) -> list:
        """List all search indexes on a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            List of index definitions
        """
        if cls._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        
        try:
            indexes = await cls._db[collection_name].list_search_indexes().to_list(length=None)
            if cls._logging_enabled:
                logger.info(f"Search indexes for '{collection_name}': {len(indexes)} found")
                for idx in indexes:
                    logger.info(f"  - {idx.get('name', 'unnamed')} ({idx.get('type', 'unknown')})")
            return indexes
        except Exception as e:
            if cls._logging_enabled:
                logger.error(f"Error listing search indexes for {collection_name}: {e}")
            return []

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
            # List and delete existing vector indexes (including old naming)
            indexes = await cls._db[collection_name].list_search_indexes().to_list(length=None)
            for idx in indexes:
                if idx.get("type") == "vectorSearch":
                    index_name = idx.get("name")
                    if index_name:
                        print(f"Deleting existing index: {index_name}")
                        if cls._logging_enabled:
                            logger.info(f"Deleting index '{index_name}' from '{collection_name}'")
                        await cls._db[collection_name].drop_search_index(index_name)

            # Use collection-specific index names for easier management
            if collection_name == "facts":
                new_index_name = "v_idx_facts"
            elif collection_name == "episodic_memories":
                new_index_name = "v_idx_episodic_memories"
            else:
                new_index_name = f"v_idx_{collection_name}"

            index_doc = {
                "name": new_index_name,
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
            print(f"Vector index '{new_index_name}' recreated for collection '{collection_name}' with {num_dimensions} dimensions")
            if cls._logging_enabled:
                logger.info(f"Vector index '{new_index_name}' recreated for '{collection_name}' with {num_dimensions} dimensions")
        except Exception as e:
            print(f"Error recreating vector index: {e}")
            if cls._logging_enabled:
                logger.error(f"Error recreating vector index for {collection_name}: {e}")

    @classmethod
    async def verify_indexes(cls) -> dict:
        """Verify that vector indexes exist for all relevant collections.
        
        Returns:
            Dictionary with collection names as keys and index status as values
        """
        if cls._db is None:
            return {"error": "MongoDB not connected"}
        
        collections = ["facts", "episodic_memories"]
        result = {}
        
        for collection_name in collections:
            try:
                indexes = await cls.list_search_indexes(collection_name)
                has_vector_index = any(idx.get("type") == "vectorSearch" for idx in indexes)
                result[collection_name] = {
                    "index_count": len(indexes),
                    "has_vector_index": has_vector_index
                }
            except Exception as e:
                result[collection_name] = {
                    "error": str(e)
                }
        
        return result


# Global instance for easy access
db = MongoDB()