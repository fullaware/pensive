"""Metrics collection and storage for performance monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from enum import Enum

from pymongo.collection import Collection

from config import logger


class MetricType(str, Enum):
    """Types of metrics to track."""
    # Token metrics
    TOKENS_PROCESSED = "tokens_processed"
    TOKENS_GENERATED = "tokens_generated"
    TOKENS_PER_SECOND = "tokens_per_second"
    
    # Storage metrics
    DB_SIZE_BYTES = "db_size_bytes"
    COLLECTION_SIZE = "collection_size"
    MEMORY_COUNT = "memory_count"
    EMBEDDING_COUNT = "embedding_count"
    
    # Session metrics
    SESSION_COUNT = "session_count"
    MESSAGE_COUNT = "message_count"
    SESSION_DURATION = "session_duration"
    
    # Performance metrics
    RESPONSE_TIME_MS = "response_time_ms"
    EMBEDDING_TIME_MS = "embedding_time_ms"
    SEARCH_TIME_MS = "search_time_ms"


class MetricsCollector:
    """Collects and stores metrics for monitoring."""
    
    def __init__(self, metrics_collection: Collection):
        """Initialize with MongoDB metrics collection.
        
        Args:
            metrics_collection: The metrics collection.
        """
        self.collection = metrics_collection
        self._ensure_indexes()
    
    def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        if self.collection is None:
            return
        
        try:
            self.collection.create_index([
                ("metric_type", 1),
                ("timestamp", -1),
            ], name="metric_time_idx")
            
            self.collection.create_index([
                ("user_id", 1),
                ("metric_type", 1),
                ("timestamp", -1),
            ], name="user_metric_time_idx")
            
            # TTL index for automatic cleanup (90 days)
            self.collection.create_index(
                "timestamp",
                expireAfterSeconds=90 * 24 * 60 * 60,
                name="metrics_ttl_idx",
            )
            
            logger.info("Metrics collection indexes ensured")
        except Exception as e:
            logger.error(f"Failed to create metrics indexes: {e}")
    
    # ==================== Recording Metrics ====================
    
    def record(
        self,
        metric_type: MetricType,
        value: float | int | dict,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Record a metric.
        
        Args:
            metric_type: The type of metric.
            value: The metric value.
            user_id: Optional user ID.
            metadata: Additional context.
        
        Returns:
            True if successful.
        """
        if self.collection is None:
            return False
        
        now = datetime.now(timezone.utc)
        
        try:
            self.collection.insert_one({
                "metric_type": metric_type.value,
                "value": value,
                "user_id": user_id,
                "timestamp": now.isoformat(),
                "metadata": metadata or {},
            })
            return True
        except Exception as e:
            logger.error(f"Failed to record metric: {e}")
            return False
    
    def record_llm_usage(
        self,
        tokens_in: int,
        tokens_out: int,
        duration_ms: float,
        model: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Record LLM usage metrics.
        
        Args:
            tokens_in: Input tokens processed.
            tokens_out: Output tokens generated.
            duration_ms: Response time in milliseconds.
            model: The model used.
            user_id: Optional user ID.
        """
        metadata = {"model": model}
        
        self.record(MetricType.TOKENS_PROCESSED, tokens_in, user_id, metadata)
        self.record(MetricType.TOKENS_GENERATED, tokens_out, user_id, metadata)
        
        if duration_ms > 0:
            tps = (tokens_out / (duration_ms / 1000)) if duration_ms > 0 else 0
            self.record(MetricType.TOKENS_PER_SECOND, tps, user_id, metadata)
            self.record(MetricType.RESPONSE_TIME_MS, duration_ms, user_id, metadata)
    
    def record_embedding_generation(
        self,
        duration_ms: float,
        dimensions: int,
        text_length: int,
        user_id: Optional[str] = None,
    ) -> None:
        """Record embedding generation metrics.
        
        Args:
            duration_ms: Time to generate embedding.
            dimensions: Embedding dimensions.
            text_length: Input text length.
            user_id: Optional user ID.
        """
        self.record(
            MetricType.EMBEDDING_TIME_MS,
            duration_ms,
            user_id,
            {"dimensions": dimensions, "text_length": text_length},
        )
    
    def record_search(
        self,
        duration_ms: float,
        result_count: int,
        search_type: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Record search metrics.
        
        Args:
            duration_ms: Search time.
            result_count: Number of results.
            search_type: vector/text/hybrid.
            user_id: Optional user ID.
        """
        self.record(
            MetricType.SEARCH_TIME_MS,
            duration_ms,
            user_id,
            {"result_count": result_count, "search_type": search_type},
        )
    
    # ==================== Querying Metrics ====================
    
    def get_metrics(
        self,
        metric_type: MetricType,
        user_id: Optional[str] = None,
        days: int = 7,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Get metrics of a specific type.
        
        Args:
            metric_type: The type to query.
            user_id: Optional user filter.
            days: Number of days to include.
            limit: Maximum results.
        
        Returns:
            List of metric documents.
        """
        if self.collection is None:
            return []
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        query = {
            "metric_type": metric_type.value,
            "timestamp": {"$gte": cutoff},
        }
        
        if user_id:
            query["user_id"] = user_id
        
        try:
            return list(
                self.collection.find(query)
                .sort("timestamp", -1)
                .limit(limit)
            )
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return []
    
    def get_aggregated_metrics(
        self,
        metric_type: MetricType,
        user_id: Optional[str] = None,
        days: int = 7,
        interval: str = "day",
    ) -> list[dict[str, Any]]:
        """Get aggregated metrics by time interval.
        
        Args:
            metric_type: The type to aggregate.
            user_id: Optional user filter.
            days: Number of days.
            interval: day/hour.
        
        Returns:
            List of aggregated values.
        """
        if self.collection is None:
            return []
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        match_stage = {
            "metric_type": metric_type.value,
            "timestamp": {"$gte": cutoff},
        }
        
        if user_id:
            match_stage["user_id"] = user_id
        
        # Date format for grouping
        if interval == "hour":
            date_format = "%Y-%m-%d %H:00"
        else:
            date_format = "%Y-%m-%d"
        
        try:
            pipeline = [
                {"$match": match_stage},
                {
                    "$addFields": {
                        "parsed_time": {"$dateFromString": {"dateString": "$timestamp"}}
                    }
                },
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": date_format, "date": "$parsed_time"}},
                        "avg_value": {"$avg": "$value"},
                        "sum_value": {"$sum": "$value"},
                        "count": {"$sum": 1},
                        "min_value": {"$min": "$value"},
                        "max_value": {"$max": "$value"},
                    }
                },
                {"$sort": {"_id": 1}},
            ]
            
            return list(self.collection.aggregate(pipeline))
            
        except Exception as e:
            logger.error(f"Failed to get aggregated metrics: {e}")
            return []
    
    def get_summary(
        self,
        user_id: Optional[str] = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get summary of all metrics.
        
        Args:
            user_id: Optional user filter.
            days: Number of days.
        
        Returns:
            Summary dictionary.
        """
        if self.collection is None:
            return {"error": "Collection not available"}
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        match_stage = {"timestamp": {"$gte": cutoff}}
        if user_id:
            match_stage["user_id"] = user_id
        
        try:
            pipeline = [
                {"$match": match_stage},
                {
                    "$group": {
                        "_id": "$metric_type",
                        "total": {"$sum": "$value"},
                        "avg": {"$avg": "$value"},
                        "count": {"$sum": 1},
                    }
                },
            ]
            
            results = list(self.collection.aggregate(pipeline))
            
            summary = {}
            for r in results:
                metric_name = r["_id"]
                summary[metric_name] = {
                    "total": r["total"],
                    "average": r["avg"],
                    "count": r["count"],
                }
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {"error": str(e)}
    
    # ==================== Storage Projections ====================
    
    def estimate_storage_growth(
        self,
        days: int = 30,
    ) -> dict[str, Any]:
        """Estimate storage growth rate.
        
        Args:
            days: Days of history to analyze.
        
        Returns:
            Growth estimates.
        """
        metrics = self.get_aggregated_metrics(
            MetricType.DB_SIZE_BYTES,
            days=days,
            interval="day",
        )
        
        if len(metrics) < 2:
            return {
                "daily_growth_bytes": 0,
                "projected_days_until_full": float("inf"),
                "error": "Insufficient data",
            }
        
        # Calculate daily growth
        first_size = metrics[0].get("avg_value", 0)
        last_size = metrics[-1].get("avg_value", 0)
        days_span = len(metrics)
        
        if days_span > 0:
            daily_growth = (last_size - first_size) / days_span
        else:
            daily_growth = 0
        
        # Estimate time until reaching a limit (e.g., 10GB)
        limit_bytes = 10 * 1024 * 1024 * 1024  # 10 GB
        remaining = limit_bytes - last_size
        
        if daily_growth > 0:
            days_until_full = remaining / daily_growth
        else:
            days_until_full = float("inf")
        
        return {
            "current_size_bytes": last_size,
            "daily_growth_bytes": daily_growth,
            "daily_growth_mb": daily_growth / (1024 * 1024),
            "projected_days_until_full": days_until_full,
            "limit_bytes": limit_bytes,
        }
    
    def record_db_size(self, db) -> bool:
        """Record current database size.
        
        Args:
            db: MongoDB database object.
        
        Returns:
            True if successful.
        """
        try:
            stats = db.command("dbStats")
            storage_size = stats.get("storageSize", 0)
            
            return self.record(
                MetricType.DB_SIZE_BYTES,
                storage_size,
                metadata={
                    "data_size": stats.get("dataSize", 0),
                    "index_size": stats.get("indexSize", 0),
                    "collections": stats.get("collections", 0),
                },
            )
        except Exception as e:
            logger.error(f"Failed to record DB size: {e}")
            return False







