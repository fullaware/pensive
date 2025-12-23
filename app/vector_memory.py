"""Vector Memory module for semantic search using MongoDB vector indexes.

Uses qwen/qwen3-embedding-4b from OpenRouter for embedding generation.
Reference: https://www.mongodb.com/docs/atlas/atlas-vector-search/tutorials/vector-search-quick-start/?deployment-type=self
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.errors import OperationFailure

from config import logger, LLM_EMBEDDING_MODEL, LLM_URI, LLM_API_KEY, VECTOR_DIMENSIONS


def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding for text using OpenRouter's qwen/qwen3-embedding-4b model.
    
    Args:
        text: The text to generate an embedding for.
        
    Returns:
        A list of floats representing the embedding vector, or None if generation fails.
    """
    if not text or not text.strip():
        logger.warning("Cannot generate embedding for empty text")
        return None
    
    try:
        # OpenRouter uses OpenAI-compatible API for embeddings
        embeddings_url = f"{LLM_URI.rstrip('/')}/embeddings"
        
        # Use placeholder API key for local providers that don't require authentication
        api_key = LLM_API_KEY or "not-needed"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pensive-ai",  # Optional but recommended
        }
        
        payload = {
            "model": LLM_EMBEDDING_MODEL,
            "input": text[:8000],  # Limit text length to avoid token limits
        }
        
        # Request specific dimensions if configured (model must support this)
        if VECTOR_DIMENSIONS:
            payload["dimensions"] = VECTOR_DIMENSIONS
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(embeddings_url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # OpenAI-compatible response format
            if "data" in data and len(data["data"]) > 0:
                embedding = data["data"][0].get("embedding")
                if embedding and isinstance(embedding, list):
                    logger.debug(f"Generated embedding with {len(embedding)} dimensions")
                    return embedding
            
            logger.error(f"Unexpected embedding response format: {data}")
            return None
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error generating embedding: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error generating embedding: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating embedding: {e}")
        return None


def ensure_vector_index(collection: Collection) -> bool:
    """Ensure the vector search index exists on the collection.
    
    Creates both:
    1. A native MongoDB vectorSearch index for efficient ANN queries
    2. Standard indexes for metadata filtering
    
    Args:
        collection: The MongoDB collection to create the index on.
        
    Returns:
        True if indexes exist or were created successfully, False otherwise.
    """
    if collection is None:
        logger.error("Cannot create vector index: collection is None")
        return False
    
    try:
        # Check if standard indexes already exist
        existing_indexes = list(collection.list_indexes())
        has_metadata_idx = any(idx.get("name") == "embedding_metadata_idx" for idx in existing_indexes)
        has_sparse_idx = any(idx.get("name") == "embedding_vector_idx" for idx in existing_indexes)
        
        # Create metadata index if missing
        if not has_metadata_idx:
            collection.create_index(
                [
                    ("message_id", ASCENDING),
                    ("conversation_id", ASCENDING),
                    ("timestamp", ASCENDING),
                ],
                name="embedding_metadata_idx",
            )
            logger.info("Created embedding_metadata_idx")
        
        # Create sparse index if missing
        if not has_sparse_idx:
            collection.create_index(
                [("has_embedding", ASCENDING)],
                name="embedding_vector_idx",
                sparse=True,
            )
            logger.info("Created embedding_vector_idx")
        
        # Check if vector search index exists
        try:
            existing_search_indexes = list(collection.list_search_indexes())
            has_vector_search = any(
                idx.get("name") == "embedding_vector_search_idx" 
                for idx in existing_search_indexes
            )
            
            if not has_vector_search:
                # Create the vector search index for native $vectorSearch
                from pymongo.operations import SearchIndexModel
                
                # Determine dimensions from config or default
                dimensions = VECTOR_DIMENSIONS if VECTOR_DIMENSIONS else 4096
                
                search_index_model = SearchIndexModel(
                    definition={
                        "fields": [
                            {
                                "type": "vector",
                                "path": "embedding",
                                "numDimensions": dimensions,
                                "similarity": "cosine"
                            }
                        ]
                    },
                    name="embedding_vector_search_idx",
                    type="vectorSearch"
                )
                collection.create_search_index(search_index_model)
                logger.info(f"Created embedding_vector_search_idx with {dimensions} dimensions")
            else:
                logger.debug("Vector search index already exists")
                
        except Exception as search_idx_err:
            # Vector search indexes may not be supported on all MongoDB versions
            logger.warning(f"Could not create vector search index (may not be supported): {search_idx_err}")
        
        return True
        
    except OperationFailure as e:
        logger.error(f"Failed to create vector index: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error creating vector index: {e}")
        return False


def store_vector_embedding(
    collection: Collection,
    text: str,
    message_id: str,
    conversation_id: str,
    user_id: str = "default",
    doc_type: str = "message",
    importance_score: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Store text with its vector embedding in MongoDB.
    
    Args:
        collection: The MongoDB collection for vector storage.
        text: The text to embed and store.
        message_id: Unique identifier for the message.
        conversation_id: The conversation this message belongs to.
        user_id: The user who created/owns this message.
        doc_type: Type of document (message, summary, research).
        importance_score: Importance score for the message.
        metadata: Additional metadata to store with the embedding.
        
    Returns:
        The inserted document ID as string, or None if storage failed.
    """
    if collection is None:
        logger.error("Cannot store embedding: collection is None")
        return None
    
    if not text or not text.strip():
        logger.warning("Cannot store embedding for empty text")
        return None
    
    # Generate embedding
    embedding = generate_embedding(text)
    if embedding is None:
        logger.warning(f"Failed to generate embedding for message {message_id}")
        return None
    
    now = datetime.now(timezone.utc)
    
    document = {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "type": doc_type,
        "text": text[:2000],  # Store truncated text for reference
        "embedding": embedding,
        "has_embedding": True,
        "dimensions": len(embedding),
        "timestamp": now.isoformat(),
        "importance_score": importance_score,
        "metadata": metadata or {},
    }
    
    try:
        # Upsert to avoid duplicates
        result = collection.update_one(
            {"message_id": message_id},
            {"$set": document},
            upsert=True,
        )
        
        if result.upserted_id:
            logger.debug(f"Inserted new vector embedding for message {message_id}")
            return str(result.upserted_id)
        else:
            logger.debug(f"Updated vector embedding for message {message_id}")
            return message_id
            
    except Exception as e:
        logger.error(f"Failed to store vector embedding: {e}")
        return None


def semantic_search(
    collection: Collection,
    query: str,
    limit: int = 10,
    min_score: float = 0.3,
    conversation_id: str | None = None,
    doc_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Perform semantic search using MongoDB's native $vectorSearch.
    
    Uses the 'embedding_vector_search_idx' vector search index for efficient
    approximate nearest neighbor (ANN) search.
    
    Args:
        collection: The MongoDB collection containing vector embeddings.
        query: The search query text.
        limit: Maximum number of results to return.
        min_score: Minimum similarity score threshold (0-1).
        conversation_id: Optional filter by conversation.
        doc_types: Optional filter by document types.
        
    Returns:
        List of matching documents with similarity scores, sorted by relevance.
    """
    if collection is None:
        logger.error("Cannot perform semantic search: collection is None")
        return []
    
    if not query or not query.strip():
        logger.warning("Cannot perform semantic search with empty query")
        return []
    
    # Generate query embedding
    query_embedding = generate_embedding(query)
    if query_embedding is None:
        logger.error("Failed to generate query embedding for semantic search")
        return []
    
    try:
        # Build the $vectorSearch aggregation pipeline
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": "embedding_vector_search_idx",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,  # Search more candidates for better accuracy
                    "limit": limit * 2,  # Get more than needed for post-filtering
                }
            },
            {
                "$addFields": {
                    "similarity_score": {"$meta": "vectorSearchScore"}
                }
            },
        ]
        
        # Add filter stage if needed
        match_conditions = []
        if min_score > 0:
            match_conditions.append({"similarity_score": {"$gte": min_score}})
        if conversation_id:
            match_conditions.append({"conversation_id": conversation_id})
        if doc_types:
            match_conditions.append({"type": {"$in": doc_types}})
        
        if match_conditions:
            pipeline.append({"$match": {"$and": match_conditions} if len(match_conditions) > 1 else match_conditions[0]})
        
        # Project only needed fields (exclude large embedding array)
        pipeline.append({
            "$project": {
                "message_id": 1,
                "text": 1,
                "type": 1,
                "conversation_id": 1,
                "timestamp": 1,
                "importance_score": 1,
                "metadata": 1,
                "similarity_score": 1,
            }
        })
        
        # Limit final results
        pipeline.append({"$limit": limit})
        
        # Execute the aggregation
        cursor = collection.aggregate(pipeline)
        
        results = []
        for doc in cursor:
            results.append({
                "message_id": doc.get("message_id"),
                "text": doc.get("text"),
                "type": doc.get("type"),
                "conversation_id": doc.get("conversation_id"),
                "timestamp": doc.get("timestamp"),
                "importance_score": doc.get("importance_score", 0.5),
                "similarity_score": doc.get("similarity_score", 0.0),
                "metadata": doc.get("metadata", {}),
            })
        
        logger.debug(f"Vector search found {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        # Fall back to brute-force search if vector index not available
        return _fallback_semantic_search(collection, query_embedding, limit, min_score, conversation_id, doc_types)


def _fallback_semantic_search(
    collection: Collection,
    query_embedding: list[float],
    limit: int,
    min_score: float,
    conversation_id: str | None,
    doc_types: list[str] | None,
) -> list[dict[str, Any]]:
    """Fallback to application-side cosine similarity if $vectorSearch fails."""
    logger.warning("Using fallback brute-force semantic search")
    
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)
    
    filter_query: dict[str, Any] = {"has_embedding": True}
    if conversation_id:
        filter_query["conversation_id"] = conversation_id
    if doc_types:
        filter_query["type"] = {"$in": doc_types}
    
    try:
        cursor = collection.find(filter_query).limit(500)
        results = []
        for doc in cursor:
            doc_embedding = doc.get("embedding")
            if not doc_embedding:
                continue
            similarity = cosine_similarity(query_embedding, doc_embedding)
            if similarity >= min_score:
                results.append({
                    "message_id": doc.get("message_id"),
                    "text": doc.get("text"),
                    "type": doc.get("type"),
                    "conversation_id": doc.get("conversation_id"),
                    "timestamp": doc.get("timestamp"),
                    "importance_score": doc.get("importance_score", 0.5),
                    "similarity_score": similarity,
                    "metadata": doc.get("metadata", {}),
                })
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.error(f"Fallback semantic search failed: {e}")
        return []


def delete_vector_embeddings(
    collection: Collection,
    message_ids: list[str] | None = None,
    conversation_id: str | None = None,
    delete_all: bool = False,
) -> int:
    """Delete vector embeddings from the collection.
    
    Args:
        collection: The MongoDB collection containing vector embeddings.
        message_ids: List of specific message IDs to delete.
        conversation_id: Delete all embeddings for a conversation.
        delete_all: Delete all embeddings in the collection.
        
    Returns:
        Number of documents deleted.
    """
    if collection is None:
        logger.error("Cannot delete embeddings: collection is None")
        return 0
    
    try:
        if delete_all:
            result = collection.delete_many({"has_embedding": True})
            logger.info(f"Deleted all {result.deleted_count} vector embeddings")
            return result.deleted_count
        
        if message_ids:
            result = collection.delete_many({"message_id": {"$in": message_ids}})
            logger.debug(f"Deleted {result.deleted_count} vector embeddings by message_id")
            return result.deleted_count
        
        if conversation_id:
            result = collection.delete_many({"conversation_id": conversation_id})
            logger.debug(f"Deleted {result.deleted_count} vector embeddings for conversation {conversation_id}")
            return result.deleted_count
        
        logger.warning("No deletion criteria specified")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to delete vector embeddings: {e}")
        return 0


def get_embedding_stats(collection: Collection) -> dict[str, Any]:
    """Get statistics about stored vector embeddings.
    
    Args:
        collection: The MongoDB collection containing vector embeddings.
        
    Returns:
        Dictionary with embedding statistics.
    """
    if collection is None:
        return {"error": "Collection not available"}
    
    try:
        total_embeddings = collection.count_documents({"has_embedding": True})
        
        # Get breakdown by type
        pipeline = [
            {"$match": {"has_embedding": True}},
            {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        ]
        type_counts = {doc["_id"]: doc["count"] for doc in collection.aggregate(pipeline)}
        
        # Get average importance
        avg_pipeline = [
            {"$match": {"has_embedding": True}},
            {"$group": {"_id": None, "avg_importance": {"$avg": "$importance_score"}}},
        ]
        avg_result = list(collection.aggregate(avg_pipeline))
        avg_importance = avg_result[0]["avg_importance"] if avg_result else 0.5
        
        return {
            "total_embeddings": total_embeddings,
            "by_type": type_counts,
            "average_importance": avg_importance,
        }
        
    except Exception as e:
        logger.error(f"Failed to get embedding stats: {e}")
        return {"error": str(e)}


def update_embedding_importance(
    collection: Collection,
    message_id: str,
    importance_score: float,
) -> bool:
    """Update the importance score of a stored embedding.
    
    Args:
        collection: The MongoDB collection containing vector embeddings.
        message_id: The message ID to update.
        importance_score: New importance score (0.0-1.0).
        
    Returns:
        True if update was successful, False otherwise.
    """
    if collection is None:
        return False
    
    try:
        importance_score = max(0.0, min(1.0, importance_score))
        result = collection.update_one(
            {"message_id": message_id},
            {"$set": {"importance_score": importance_score}},
        )
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f"Failed to update embedding importance: {e}")
        return False

