# auth.py - Authentication utilities for protected routes
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone
from services.auth_service import AuthService
from services.firebase_service import FirebaseService

# Initialize services
firebase_service = FirebaseService()
auth_service = AuthService(firebase_service)
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    try:
        token = credentials.credentials
        print(f"🔍 Validating JWT token for protected endpoint...")
        
        # Verify JWT token using auth_service
        payload = auth_service.verify_jwt_token(token)
        uid = payload['uid']
        email = payload['email']
        
        print(f"✅ JWT token valid for UID: {uid}")
        
        # Try to get user profile, but don't fail if it doesn't exist
        user_profile = None
        try:
            if hasattr(auth_service.firebase_service, 'get_user_profile'):
                user_profile = await auth_service.firebase_service.get_user_profile(uid)
                if user_profile:
                    print(f"✅ User profile found and loaded")
                    return user_profile
            else:
                print(f"⚠️ get_user_profile method not available in FirebaseService")
        except Exception as e:
            print(f"⚠️ Could not get user profile: {e}")
        
        # If profile doesn't exist or can't be retrieved, create minimal user object from JWT
        print(f"🆕 Using minimal user data from JWT payload")
        minimal_user = {
            "uid": uid,
            "email": email,
            "first_name": "",
            "last_name": "",
            "location": "Johannesburg, South Africa",
            "timezone": "Africa/Johannesburg", 
            "phone": None,
            "bio": None,
            "avatar_url": None,
            "avatar_filename": None,
            "is_verified": False,
            "google_connected": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_login": datetime.now(timezone.utc),
            "preferences": None
        }
        
        print(f"✅ Returning minimal user data for authenticated request")
        return minimal_user
        
    except Exception as e:
        print(f"❌ Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )