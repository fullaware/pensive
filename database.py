"""Database connection and operations."""
from pymongo import MongoClient
from config import MONGODB_URI, MONGODB_DB, logger

# Initialize MongoDB variables
client = None
db = None
users_collection = None
sessions_collection = None
session_messages_collection = None
metrics_collection = None
agent_memory_collection = None
knowledge_collection = None

# Set up MongoDB
if MONGODB_URI:
    try:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DB]
        users_collection = db["users"]
        sessions_collection = db["sessions"]
        session_messages_collection = db["session_messages"]
        metrics_collection = db["metrics"]
        agent_memory_collection = db["agent_memory"]
        knowledge_collection = db["knowledge"]
        logger.info("Successfully connected to MongoDB (all collections initialized)")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        client = None
        users_collection = None
        sessions_collection = None
        session_messages_collection = None
        metrics_collection = None
        agent_memory_collection = None
else:
    logger.error("MongoDB connection skipped due to missing MONGODB_URI")






