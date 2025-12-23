"""Metrics routes for real-time and historical analytics."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from config import logger
from app.auth.models import User
from app.metrics import MetricsCollector, MetricType

from api.models import (
    RealtimeMetricsResponse,
    MetricsHistoryResponse,
    MetricDataPoint,
)
from api.dependencies import (
    get_current_user,
    require_admin,
    get_metrics_collector,
    get_memory_store,
)


router = APIRouter()

# In-memory metrics for real-time display
_realtime_metrics = {
    "current_tps": 0.0,
    "total_tokens": 0,
    "requests_today": 0,
    "last_updated": None,
}


def update_realtime_metrics(tokens_per_second: float, tokens_generated: int):
    """Update real-time metrics (called from chat endpoint)."""
    global _realtime_metrics
    _realtime_metrics["current_tps"] = tokens_per_second
    _realtime_metrics["total_tokens"] += tokens_generated
    _realtime_metrics["requests_today"] += 1
    _realtime_metrics["last_updated"] = datetime.now(timezone.utc)


@router.get("/realtime", response_model=RealtimeMetricsResponse)
async def get_realtime_metrics(
    current_user: User = Depends(get_current_user),
    metrics_collector: Optional[MetricsCollector] = Depends(get_metrics_collector),
):
    """
    Get real-time metrics for the current session.
    """
    # Get active user count from sessions (simplified)
    active_users = 1  # At minimum, current user
    
    # Get today's request count from metrics if available
    requests_today = _realtime_metrics.get("requests_today", 0)
    
    if metrics_collector:
        try:
            today_metrics = metrics_collector.get_metrics(
                MetricType.RESPONSE_TIME_MS,
                days=1,
            )
            requests_today = len(today_metrics)
        except Exception as e:
            logger.error(f"Error fetching today's metrics: {e}")
    
    return RealtimeMetricsResponse(
        tokens_per_second=_realtime_metrics.get("current_tps", 0.0),
        total_tokens_generated=_realtime_metrics.get("total_tokens", 0),
        active_users=active_users,
        requests_today=requests_today,
    )


@router.get("/history", response_model=MetricsHistoryResponse)
async def get_metrics_history(
    period: str = Query("week", regex="^(day|week|month)$"),
    current_user: User = Depends(require_admin),
    metrics_collector: Optional[MetricsCollector] = Depends(get_metrics_collector),
):
    """
    Get historical metrics data. Admin only.
    """
    # Calculate time range based on period
    now = datetime.now(timezone.utc)
    
    if period == "day":
        start_time = now - timedelta(days=1)
        interval_hours = 1
    elif period == "week":
        start_time = now - timedelta(weeks=1)
        interval_hours = 6
    else:  # month
        start_time = now - timedelta(days=30)
        interval_hours = 24
    
    data_points: list[MetricDataPoint] = []
    
    if metrics_collector:
        try:
            # Calculate days for the period
            days = 1 if period == "day" else (7 if period == "week" else 30)
            
            # Fetch response time metrics (one per message)
            response_metrics = metrics_collector.get_metrics(
                MetricType.RESPONSE_TIME_MS,
                days=days,
            )
            
            # Fetch token metrics
            token_metrics = metrics_collector.get_metrics(
                MetricType.TOKENS_GENERATED,
                days=days,
            )
            
            # Group metrics by interval
            intervals: dict[datetime, dict] = {}
            
            # Process response time metrics (each represents a message)
            for metric in response_metrics:
                metric_time = metric.get("timestamp", now.isoformat())
                if isinstance(metric_time, str):
                    metric_time = datetime.fromisoformat(metric_time.replace("Z", "+00:00"))
                
                # Round to interval
                if interval_hours == 1:
                    interval_start = metric_time.replace(minute=0, second=0, microsecond=0)
                elif interval_hours == 6:
                    hour = (metric_time.hour // 6) * 6
                    interval_start = metric_time.replace(hour=hour, minute=0, second=0, microsecond=0)
                else:  # 24 hours
                    interval_start = metric_time.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if interval_start not in intervals:
                    intervals[interval_start] = {
                        "messages_count": 0,
                        "tokens_generated": 0,
                        "response_times": [],
                        "users": set(),
                    }
                
                interval_data = intervals[interval_start]
                interval_data["messages_count"] += 1
                interval_data["response_times"].append(metric.get("value", 0))
                
                user_id = metric.get("user_id")
                if user_id:
                    interval_data["users"].add(user_id)
            
            # Process token metrics
            for metric in token_metrics:
                metric_time = metric.get("timestamp", now.isoformat())
                if isinstance(metric_time, str):
                    metric_time = datetime.fromisoformat(metric_time.replace("Z", "+00:00"))
                
                # Round to interval (same logic)
                if interval_hours == 1:
                    interval_start = metric_time.replace(minute=0, second=0, microsecond=0)
                elif interval_hours == 6:
                    hour = (metric_time.hour // 6) * 6
                    interval_start = metric_time.replace(hour=hour, minute=0, second=0, microsecond=0)
                else:  # 24 hours
                    interval_start = metric_time.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if interval_start in intervals:
                    intervals[interval_start]["tokens_generated"] += metric.get("value", 0)
            
            # Convert to data points
            for timestamp, data in sorted(intervals.items()):
                response_times = data["response_times"]
                avg_response_time = (
                    sum(response_times) / len(response_times)
                    if response_times else 0
                )
                
                data_points.append(MetricDataPoint(
                    timestamp=timestamp,
                    messages_count=data["messages_count"],
                    tokens_generated=int(data["tokens_generated"]),
                    avg_response_time_ms=avg_response_time,
                    unique_users=len(data["users"]),
                ))
                
        except Exception as e:
            logger.error(f"Error fetching metrics history: {e}")
    
    # If no real data, generate placeholder data points
    if not data_points:
        current = start_time
        while current < now:
            data_points.append(MetricDataPoint(
                timestamp=current,
                messages_count=0,
                tokens_generated=0,
                avg_response_time_ms=0,
                unique_users=0,
            ))
            current += timedelta(hours=interval_hours)
    
    return MetricsHistoryResponse(
        period=period,
        data_points=data_points,
    )


@router.get("/summary")
async def get_metrics_summary(
    current_user: User = Depends(require_admin),
    metrics_collector: Optional[MetricsCollector] = Depends(get_metrics_collector),
    memory_store = Depends(get_memory_store),
):
    """
    Get a summary of key metrics. Admin only.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    
    summary = {
        "today": {
            "messages": 0,
            "tokens": 0,
            "active_users": 0,
        },
        "week": {
            "messages": 0,
            "tokens": 0,
            "active_users": 0,
        },
        "total_memories": 0,
    }
    
    if metrics_collector:
        try:
            # Get response time metrics (one per message)
            today_response_metrics = metrics_collector.get_metrics(
                MetricType.RESPONSE_TIME_MS,
                days=1,
            )
            week_response_metrics = metrics_collector.get_metrics(
                MetricType.RESPONSE_TIME_MS,
                days=7,
            )
            
            # Get token metrics
            today_token_metrics = metrics_collector.get_metrics(
                MetricType.TOKENS_GENERATED,
                days=1,
            )
            week_token_metrics = metrics_collector.get_metrics(
                MetricType.TOKENS_GENERATED,
                days=7,
            )
            
            # Process today's metrics
            today_users = set()
            for m in today_response_metrics:
                summary["today"]["messages"] += 1
                if m.get("user_id"):
                    today_users.add(m["user_id"])
            for m in today_token_metrics:
                summary["today"]["tokens"] += m.get("value", 0)
            summary["today"]["active_users"] = len(today_users)
            
            # Process week's metrics
            week_users = set()
            for m in week_response_metrics:
                summary["week"]["messages"] += 1
                if m.get("user_id"):
                    week_users.add(m["user_id"])
            for m in week_token_metrics:
                summary["week"]["tokens"] += m.get("value", 0)
            summary["week"]["active_users"] = len(week_users)
                
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
    
    if memory_store:
        try:
            stats = memory_store.get_stats()
            summary["total_memories"] = stats.get("total", 0)
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
    
    return summary


