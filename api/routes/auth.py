"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from config import logger
from app.auth.manager import UserManager
from app.auth.models import User, UserRole

from api.models import LoginRequest, LoginResponse, UserResponse, ChangePasswordRequest, UpdatePreferencesRequest
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
        system_prompt=user.system_prompt,
        temperature=user.temperature,
        assistant_name=user.assistant_name,
        has_seen_onboarding=user.has_seen_onboarding,
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


@router.post("/password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Unified password management endpoint.

    - When user_id is omitted or matches current user:
      * Non-admins must provide current_password which is verified.
    - When user_id targets a different user:
      * Only admins may change the password, current_password is ignored.
    """
    if user_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable",
        )

    # Basic password validation
    new_password = request.new_password or ""
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long",
        )

    target_user_id = request.user_id or current_user.id

    # Determine if this is self-change or admin-changing-other
    is_self_change = target_user_id == current_user.id

    if is_self_change:
        # Require current_password for self-service
        if not request.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required",
            )

        # Verify current password using username + password
        authenticated = user_manager.authenticate(
            username=current_user.username,
            password=request.current_password,
        )
        if not authenticated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
    else:
        # Changing another user's password: only admins allowed
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change other users' passwords",
            )

        # Ensure target user exists
        target_user = user_manager.get_user_by_id(target_user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found",
            )

    # Perform the password change
    success = user_manager.change_password(target_user_id, new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password",
        )

    logger.info(
        "Password changed for user_id=%s by user_id=%s",
        target_user_id,
        current_user.id,
    )

    return {"success": True, "message": "Password updated successfully"}


@router.patch("/preferences", response_model=UserResponse)
async def update_preferences(
    request: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Update user preferences (system_prompt, temperature, assistant_name).
    Users can only update their own preferences.
    """
    if not user_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User management service unavailable",
        )

    # Validate temperature if provided
    if request.temperature is not None:
        if not (0.0 <= request.temperature <= 2.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Temperature must be between 0.0 and 2.0",
            )

    # Validate system_prompt length if provided
    if request.system_prompt is not None and len(request.system_prompt) > 5000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System prompt must be 5000 characters or less",
        )

    # Update preferences
    success = user_manager.update_preferences(
        user_id=current_user.id,
        system_prompt=request.system_prompt,
        temperature=request.temperature,
        assistant_name=request.assistant_name,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        )

    # Invalidate agent cache for this user
    from api.routes.chat import _agents
    if current_user.id in _agents:
        del _agents[current_user.id]

    # Fetch updated user
    updated_user = user_manager.get_user_by_id(current_user.id)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found after update",
        )

    logger.info(f"Preferences updated for user '{current_user.username}'")
    return user_to_response(updated_user)


