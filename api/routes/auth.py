"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from config import logger
from app.auth.manager import UserManager
from app.auth.models import User

from api.models import LoginRequest, LoginResponse, UserResponse
from api.dependencies import (
    get_user_manager,
    get_current_user,
    create_session,
    invalidate_session,
)

router = APIRouter()


def user_to_response(user: User) -> UserResponse:
    """Convert User model to UserResponse (exclude sensitive fields)."""
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value if hasattr(user.role, 'value') else user.role,
        tool_permissions=user.tool_permissions.to_dict(),
        created_at=user.created_at,
        last_login=user.last_login,
        is_active=user.is_active,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Authenticate user and create session.
    Sets session_token cookie on success.
    """
    if not user_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    
    user = user_manager.authenticate(request.username, request.password)
    
    if not user:
        return LoginResponse(
            success=False,
            message="Invalid username or password",
        )
    
    # Create session and set cookie
    session_token = create_session(user)
    
    # Set HTTP-only cookie for security
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=60 * 60 * 8,  # 8 hours
    )
    
    logger.info(f"User '{user.username}' logged in successfully")
    
    return LoginResponse(
        success=True,
        message="Login successful",
        user=user_to_response(user),
        session_token=session_token,  # Also return in body for non-cookie clients
    )


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """
    Logout current user and invalidate session.
    """
    # Clear the cookie
    response.delete_cookie(key="session_token")
    
    logger.info(f"User '{current_user.username}' logged out")
    
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user's information.
    """
    return user_to_response(current_user)


@router.post("/validate")
async def validate_session(
    current_user: User = Depends(get_current_user),
):
    """
    Validate current session is active.
    Returns user info if valid, raises 401 if not.
    """
    return {
        "valid": True,
        "user": user_to_response(current_user),
    }


