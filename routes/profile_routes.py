# routes/profile_routes.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import Optional
from models.user_models import UserResponse, UserUpdate, ProfileStats, NotificationSettings
from services.auth_service import AuthService
from services.firebase_service import FirebaseService
from services.profile_service import ProfileService
import os

router = APIRouter(prefix="/profile", tags=["Profile"])

# Dependencies
def get_profile_service() -> ProfileService:
    return ProfileService(firebase_service, auth_service)

@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: UserResponse = Depends(auth_service.get_current_user)
):
    """Get current user's profile information"""
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    profile_update: UserUpdate,
    current_user: UserResponse = Depends(auth_service.get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """Update current user's profile"""
    try:
        updated_user = await profile_service.update_profile(
            current_user.uid, 
            profile_update
        )
        return updated_user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(auth_service.get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """Upload user avatar image"""
    if not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )
    
    try:
        avatar_url = await profile_service.upload_avatar(
            current_user.uid, 
            file
        )
        return {"avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}"
        )

@router.get("/stats", response_model=ProfileStats)
async def get_profile_stats(
    current_user: UserResponse = Depends(auth_service.get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """Get user's activity statistics"""
    try:
        stats = await profile_service.get_user_stats(current_user.uid)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )

@router.get("/notifications", response_model=NotificationSettings)
async def get_notification_settings(
    current_user: UserResponse = Depends(auth_service.get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """Get user's notification preferences"""
    try:
        settings = await profile_service.get_notification_settings(current_user.uid)
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notification settings: {str(e)}"
        )

@router.put("/notifications", response_model=NotificationSettings)
async def update_notification_settings(
    settings: NotificationSettings,
    current_user: UserResponse = Depends(auth_service.get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """Update user's notification preferences"""
    try:
        updated_settings = await profile_service.update_notification_settings(
            current_user.uid, 
            settings
        )
        return updated_settings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.delete("/account")
async def delete_account(
    current_user: UserResponse = Depends(auth_service.get_current_user),
    profile_service: ProfileService = Depends(get_profile_service)
):
    """Delete user account (soft delete)"""
    try:
        await profile_service.delete_account(current_user.uid)
        return {"message": "Account scheduled for deletion"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )