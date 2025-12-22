"""Database connection and operations."""
import streamlit as st
from pymongo import MongoClient
from config import MONGODB_URI, MONGODB_DB, logger

# Initialize MongoDB variables
client = None
db = None
users_collection = None
sessions_collection = None
metrics_collection = None
agent_memory_collection = None

# Set up MongoDB
if MONGODB_URI:
    try:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DB]
        users_collection = db["users"]
        sessions_collection = db["sessions"]
        metrics_collection = db["metrics"]
        agent_memory_collection = db["agent_memory"]
        logger.info("Successfully connected to MongoDB (all collections initialized)")
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        logger.error(f"Failed to connect to MongoDB: {e}")
        client = None
        users_collection = None
        sessions_collection = None
        metrics_collection = None
        agent_memory_collection = None
else:
    st.error("Cannot connect to MongoDB without MONGODB_URI")
    logger.error("MongoDB connection skipped due to missing MONGODB_URI")






