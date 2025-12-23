"""API route modules."""

from api.routes.auth import router as auth_router
from api.routes.chat import router as chat_router
from api.routes.memory import router as memory_router
from api.routes.admin import router as admin_router
from api.routes.metrics import router as metrics_router
from api.routes.knowledge import router as knowledge_router

__all__ = [
    "auth_router",
    "chat_router", 
    "memory_router",
    "admin_router",
    "metrics_router",
    "knowledge_router",
]


