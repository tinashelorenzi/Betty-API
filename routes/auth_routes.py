from fastapi import APIRouter, Depends
from services.google_service import GoogleService
from auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

def get_google_service():
    from main import google_service
    return google_service

@router.get("/google/status")
async def get_google_connection_status(
    user=Depends(get_current_user),
    google_service: GoogleService = Depends(get_google_service)
):
    """Check if user has a valid Google connection"""
    try:
        status = await google_service.check_google_connection_status(user["uid"])
        return status
    except Exception as e:
        print(f"Error checking Google connection status: {e}")
        return {
            "connected": False,
            "user_info": None,
            "error": str(e)
        }