# Environment Configuration
"""Configuration loader for environment variables."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Configuration class for the agentic memory system."""

    # MongoDB Configuration
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    MONGODB_DB = os.getenv("MONGODB_DB", "agentic_memory")

    # LLM Configuration
    LLM_URI = os.getenv("LLM_URI", "http://localhost:8080")
    LLM_EMBEDDING_URI = os.getenv("LLM_EMBEDDING_URI", "http://localhost:1234/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "default-model")
    LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "default-embedding")

    # Memory Configuration
    SHORT_TERM_MEMORY_SIZE = int(os.getenv("SHORT_TERM_MEMORY_SIZE", "10"))
    EPISODIC_MEMORY_LIMIT = int(os.getenv("EPISODIC_MEMORY_LIMIT", "100"))
    VECTOR_SEARCH_LIMIT = int(os.getenv("VECTOR_SEARCH_LIMIT", "5"))

    # Embedding Configuration
    EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

    # Automated Memory Management Configuration
    MEMORY_CLEANUP_INTERVAL_HOURS = float(os.getenv("MEMORY_CLEANUP_INTERVAL_HOURS", "24"))
    MAX_SYSTEM_PROMPT_VERSIONS = int(os.getenv("MAX_SYSTEM_PROMPT_VERSIONS", "5"))
    STALENESS_DAYS_THRESHOLD = int(os.getenv("STALENESS_DAYS_THRESHOLD", "14"))
    AUTO_TAG_ENABLED = os.getenv("AUTO_TAG_ENABLED", "true").lower() in ("true", "1", "yes")
    LOW_CONFIDENCE_THRESHOLD = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.3"))
    AUTO_ARCHIVE_AGE_DAYS = int(os.getenv("AUTO_ARCHIVE_AGE_DAYS", "90"))

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_UPDATE_METHOD = os.getenv("TELEGRAM_UPDATE_METHOD", "polling")  # "polling" or "webhook"
    TELEGRAM_POLL_INTERVAL = float(os.getenv("TELEGRAM_POLL_INTERVAL", "1.0"))
    TELEGRAM_ALLOWED_USER_IDS = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    TELEGRAM_BOT_OWNER_ID = os.getenv("TELEGRAM_BOT_OWNER_ID", "")

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration values."""
        errors = []
        if not cls.MONGODB_URI:
            errors.append("MONGODB_URI is required")
        if not cls.LLM_URI:
            errors.append("LLM_URI is required")
        if not cls.LLM_EMBEDDING_URI:
            errors.append("LLM_EMBEDDING_URI is required")
        return errors


def get_config() -> Config:
    """Get the configuration instance."""
    return Config()