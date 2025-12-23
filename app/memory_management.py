"""Memory management functions: decay, importance, monitoring, and maintenance."""
from datetime import datetime, timezone
from openai import OpenAI
from config import (
    LLM_URI, LLM_API_KEY, LLM_MODEL, CONVERSATION_ID,
    DEFAULT_IMPORTANCE_SCORE, DEFAULT_DECAY_SCORE, logger
)
from database import agent_memory_collection as collection
from app.memory_extraction import extract_topics_and_keywords, extract_entities

def calculate_decay_score(message: dict) -> float:
    """Calculate decay score based on age, importance, and access patterns."""
    if not message:
        return 0.0
    
    # Get message timestamp
    timestamp = message.get("timestamp")
    if not timestamp:
        # If no timestamp, use _id creation time (approximate)
        timestamp = message.get("_id").generation_time if hasattr(message.get("_id"), "generation_time") else datetime.now(timezone.utc)
    
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except:
            timestamp = datetime.now(timezone.utc)
    
    if not isinstance(timestamp, datetime):
        timestamp = datetime.now(timezone.utc)
    
    # Calculate age in days
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_days = (now - timestamp).days
    
    # Base decay: 50% decay after 1 year
    base_decay = max(0.0, 1.0 - (age_days / 365.0) * 0.5)
    
    # Adjust by importance (important messages decay slower)
    importance_score = message.get("importance_score", DEFAULT_IMPORTANCE_SCORE)
    decay_score = base_decay * (0.5 + importance_score * 0.5)
    
    # Adjust by access count (frequently accessed decay slower)
    access_count = message.get("access_count", 0)
    access_factor = 1.0 - min(access_count / 100.0, 0.3)
    decay_score *= access_factor
    
    return max(0.0, min(1.0, decay_score))

def update_importance_score(message_id, factors: dict = None) -> float:
    """Update importance score based on various factors."""
    if collection is None:
        return DEFAULT_IMPORTANCE_SCORE
    
    message = collection.find_one({"_id": message_id})
    if not message:
        return DEFAULT_IMPORTANCE_SCORE
    
    current_score = message.get("importance_score", DEFAULT_IMPORTANCE_SCORE)
    factors = factors or {}
    
    # Increase for explicit importance markers
    if factors.get("explicit_important"):
        current_score = min(1.0, current_score + 0.3)
    
    # Increase for frequent access
    access_count = message.get("access_count", 0)
    if access_count > 10:
        current_score = min(1.0, current_score + 0.1)
    
    # Increase for recent messages (within last 7 days)
    timestamp = message.get("timestamp")
    if timestamp:
        try:
            if isinstance(timestamp, str):
                msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                msg_time = timestamp
            age_days = (datetime.now(timezone.utc) - msg_time.replace(tzinfo=timezone.utc) if msg_time.tzinfo is None else msg_time).days
            if age_days < 7:
                current_score = min(1.0, current_score + 0.1)
        except:
            pass
    
    # Increase for entity mentions
    entities = message.get("entities", [])
    if len(entities) > 0:
        current_score = min(1.0, current_score + 0.05 * min(len(entities), 5))
    
    # Decrease for already summarized
    if message.get("summarized"):
        current_score = max(0.0, current_score - 0.2)
    
    # Update in database
    collection.update_one(
        {"_id": message_id},
        {"$set": {"importance_score": current_score}}
    )
    
    return current_score

def link_entities(entity_name: str, entity_type: str = None) -> list:
    """Find all messages mentioning a specific entity."""
    if collection is None:
        return []
    
    try:
        query = {
            "type": "message",
            "entities": {
                "$elemMatch": {
                    "name": {"$regex": entity_name, "$options": "i"}
                }
            }
        }
        if entity_type:
            query["entities"]["$elemMatch"]["type"] = entity_type
        
        messages = list(collection.find(query).sort("_id", -1).limit(50))
        return [msg["message_id"] for msg in messages if "message_id" in msg]
    except Exception as e:
        logger.error(f"Failed to link entities: {e}")
        return []

def monitor_memory_health() -> dict:
    """Monitor memory health and return metrics."""
    if collection is None:
        return {"error": "Database unavailable"}
    
    try:
        # Count messages and summaries
        total_messages = collection.count_documents({"type": "message"})
        total_summaries = collection.count_documents({"type": "summary"})
        
        # Get message statistics
        messages = list(collection.find({"type": "message"}))
        
        # Calculate average age
        now = datetime.now(timezone.utc)
        ages = []
        importance_scores = []
        decay_scores = []
        access_counts = []
        
        for msg in messages:
            timestamp = msg.get("timestamp")
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        msg_time = timestamp
                    if msg_time.tzinfo is None:
                        msg_time = msg_time.replace(tzinfo=timezone.utc)
                    age_days = (now - msg_time).days
                    ages.append(age_days)
                except:
                    pass
            
            importance_scores.append(msg.get("importance_score", DEFAULT_IMPORTANCE_SCORE))
            decay_scores.append(msg.get("decay_score", DEFAULT_DECAY_SCORE))
            access_counts.append(msg.get("access_count", 0))
        
        avg_age = sum(ages) / len(ages) if ages else 0
        avg_importance = sum(importance_scores) / len(importance_scores) if importance_scores else DEFAULT_IMPORTANCE_SCORE
        avg_decay = sum(decay_scores) / len(decay_scores) if decay_scores else DEFAULT_DECAY_SCORE
        avg_access = sum(access_counts) / len(access_counts) if access_counts else 0
        
        # Find messages needing attention
        messages_needing_summary = collection.count_documents({
            "type": "message",
            "summarized": {"$ne": "true"},
            "$or": [
                {"decay_score": {"$lt": 0.3}},
                {"importance_score": {"$lt": 0.3}}
            ]
        })
        
        messages_ready_for_purge = collection.count_documents({
            "type": "message",
            "decay_score": {"$lt": 0.2},
            "importance_score": {"$lt": 0.4}
        })
        
        return {
            "total_messages": total_messages,
            "total_summaries": total_summaries,
            "average_age_days": avg_age,
            "average_importance_score": avg_importance,
            "average_decay_score": avg_decay,
            "average_access_count": avg_access,
            "messages_needing_summary": messages_needing_summary,
            "messages_ready_for_purge": messages_ready_for_purge
        }
    except Exception as e:
        logger.error(f"Memory health monitoring failed: {e}")
        return {"error": str(e)}

def auto_memory_maintenance() -> str:
    """Automatically maintain memory based on health metrics."""
    if collection is None:
        return "Database unavailable. Cannot perform maintenance."
    
    try:
        health = monitor_memory_health()
        if "error" in health:
            return f"Cannot perform maintenance: {health['error']}"
        
        actions_taken = []
        
        # If too many messages, trigger summarization
        if health["total_messages"] > 100:
            messages_to_summarize = health["messages_needing_summary"]
            if messages_to_summarize > 20:
                # Trigger summarize_memory for oldest messages
                try:
                    old_messages = list(collection.find({
                        "type": "message",
                        "summarized": {"$ne": "true"}
                    }).sort("_id", 1).limit(50))
                    
                    if old_messages:
                        # Call summarize_memory logic inline
                        chunks = []
                        for i in range(0, len(old_messages), 20):
                            chunks.append(old_messages[i:i+20])
                        
                        summaries_created = 0
                        for chunk in chunks:
                            formatted_messages = "\n".join([
                                f"{msg['role']}: {msg['message']}" 
                                for msg in chunk
                            ])
                            
                            if not LLM_URI or not LLM_MODEL:
                                break
                            
                            client_openai = OpenAI(base_url=LLM_URI, api_key=LLM_API_KEY or "not-needed")
                            response = client_openai.chat.completions.create(
                                model=LLM_MODEL,
                                messages=[
                                    {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                                    {"role": "user", "content": f"Summarize: {formatted_messages}"}
                                ]
                            )
                            
                            summary = response.choices[0].message.content
                            if summary:
                                # Aggregate metadata
                                all_topics = []
                                all_keywords = []
                                all_entities = []
                                for msg in chunk:
                                    all_topics.extend(msg.get("topics", []))
                                    all_keywords.extend(msg.get("keywords", []))
                                    all_entities.extend(msg.get("entities", []))
                                
                                unique_topics = list(dict.fromkeys(all_topics))[:10]
                                unique_keywords = list(dict.fromkeys(all_keywords))[:15]
                                
                                seen_entity_names = set()
                                unique_entities = []
                                for entity in all_entities:
                                    if isinstance(entity, dict) and "name" in entity:
                                        entity_name = entity["name"].lower()
                                        if entity_name not in seen_entity_names:
                                            seen_entity_names.add(entity_name)
                                            unique_entities.append(entity)
                                unique_entities = unique_entities[:10]
                                
                                collection.insert_one({
                                    "type": "summary",
                                    "conversation_id": CONVERSATION_ID,
                                    "summary": summary,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "message_count": len(chunk),
                                    "message_ids": [msg["_id"] for msg in chunk],
                                    "topics": unique_topics,
                                    "keywords": unique_keywords,
                                    "entities": unique_entities
                                })
                                
                                # Mark as summarized
                                message_ids = [msg["_id"] for msg in chunk]
                                for msg_id in message_ids:
                                    collection.update_one(
                                        {"_id": msg_id},
                                        {"$set": {"summarized": "true"}}
                                    )
                                
                                summaries_created += 1
                        
                        if summaries_created > 0:
                            actions_taken.append(f"Created {summaries_created} summaries")
                except Exception as e:
                    logger.error(f"Auto-summarization failed: {e}")
        
        # Update decay scores ONLY for messages that need it:
        # - Messages older than 7 days (recent messages haven't decayed much)
        # - Messages not updated in the last 24 hours (avoid redundant updates)
        # - Limit to 50 per maintenance cycle for efficiency
        try:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            seven_days_ago = (now - timedelta(days=7)).isoformat()
            one_day_ago = (now - timedelta(days=1)).isoformat()
            
            # Only fetch messages that are old enough to have meaningful decay
            # and haven't had their decay updated recently
            messages = list(collection.find({
                "type": "message",
                "timestamp": {"$lt": seven_days_ago},  # Older than 7 days
                "$or": [
                    {"decay_last_updated": {"$exists": False}},  # Never updated
                    {"decay_last_updated": {"$lt": one_day_ago}}  # Not updated in 24h
                ]
            }).sort("timestamp", 1).limit(50))  # Process oldest first, limit batch size
            
            if messages:
                from pymongo import UpdateOne
                bulk_updates = []
                
                for msg in messages:
                    new_decay = calculate_decay_score(msg)
                    old_decay = msg.get("decay_score", DEFAULT_DECAY_SCORE)
                    
                    # Only update if decay changed significantly (>0.05)
                    if abs(new_decay - old_decay) > 0.05:
                        bulk_updates.append(UpdateOne(
                            {"_id": msg["_id"]},
                            {"$set": {
                                "decay_score": new_decay,
                                "decay_last_updated": now.isoformat()
                            }}
                        ))
                    else:
                        # Just mark as checked even if no change
                        bulk_updates.append(UpdateOne(
                            {"_id": msg["_id"]},
                            {"$set": {"decay_last_updated": now.isoformat()}}
                        ))
                
                if bulk_updates:
                    result = collection.bulk_write(bulk_updates)
                    updated_count = result.modified_count
                    if updated_count > 0:
                        actions_taken.append(f"Updated decay for {updated_count}/{len(messages)} eligible messages")
        except Exception as e:
            logger.error(f"Decay score update failed: {e}")
        
        # Suggest purging if many messages ready
        if health["messages_ready_for_purge"] > 50:
            actions_taken.append(f"{health['messages_ready_for_purge']} messages ready for purging (low decay + low importance)")
        
        if actions_taken:
            return "Auto-maintenance completed: " + "; ".join(actions_taken)
        else:
            return "Memory health is good. No maintenance needed."
            
    except Exception as e:
        logger.error(f"Auto-memory maintenance failed: {e}")
        return f"Error in auto-maintenance: {e}"


