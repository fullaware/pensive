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

    # Pushover Configuration
    PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN", "")
    PUSHOVER_USER = os.getenv("PUSHOVER_USER", "")

    # Memory Configuration
    SHORT_TERM_MEMORY_SIZE = int(os.getenv("SHORT_TERM_MEMORY_SIZE", "10"))
    EPISODIC_MEMORY_LIMIT = int(os.getenv("EPISODIC_MEMORY_LIMIT", "100"))
    VECTOR_SEARCH_LIMIT = int(os.getenv("VECTOR_SEARCH_LIMIT", "5"))

    # Embedding Configuration
    EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

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