"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import logger, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD
from database import users_collection
from app.auth.manager import UserManager

from api.routes import (
    auth_router,
    chat_router,
    memory_router,
    admin_router,
    metrics_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Pensive API server...")
    
    # Create default admin if needed
    if users_collection is not None:
        user_manager = UserManager(users_collection)
        user_manager.create_default_admin_user(
            username=DEFAULT_ADMIN_USERNAME,
            password=DEFAULT_ADMIN_PASSWORD,
        )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Pensive API server...")


# Create FastAPI app
app = FastAPI(
    title="Pensive API",
    description="Family Assistant API with persistent memory",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for frontend
# In production, replace with specific origins
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,  # Required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(memory_router, prefix="/api/memory", tags=["Memory"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(metrics_router, prefix="/api/metrics", tags=["Metrics"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pensive-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


