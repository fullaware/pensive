"""Configuration and constants for the application."""
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv(override=True)

# Environment variables
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB")
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_URI = os.getenv("LLM_URI")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")
# Optional: Request specific embedding dimensions (set to 0 or omit to use model's native size)
# Smaller dimensions = less storage, faster search, slightly less accuracy
VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSIONS", "0")) or None

# Constants for memory management
CONVERSATION_ID = "main"  # Single continuous conversation
DEFAULT_IMPORTANCE_SCORE = 0.5
DEFAULT_DECAY_SCORE = 1.0
MEMORY_MAINTENANCE_THRESHOLD = 20  # Trigger maintenance after N messages

# Authentication configuration
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "480"))  # 8 hours default
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme")

# Metrics configuration
METRICS_RETENTION_DAYS = int(os.getenv("METRICS_RETENTION_DAYS", "90"))

# Google Calendar configuration
GOOGLE_CALENDAR_CREDENTIALS_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CALENDAR_TOKEN_FILE = os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "token.json")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")  # "primary" or specific calendar ID

# Set up logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logging.getLogger("pymongo").setLevel(logging.ERROR)






