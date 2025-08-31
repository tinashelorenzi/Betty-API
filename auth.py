# auth.py - FIXED VERSION
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    try:
        # Import here to avoid circular imports and use initialized services
        from main import auth_service
        
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
            print(f"❌ Failed to get user profile: {e}")
        
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
        print(f"❌ Authentication failed: {e}")
        print(f"❌ Error type: {type(e)}")
        
        # Provide more specific error messages
        error_msg = str(e)
        if "Token has expired" in error_msg:
            detail = "Authentication token has expired. Please login again."
        elif "Invalid token" in error_msg:
            detail = "Invalid authentication token. Please login again."
        elif "Token missing required fields" in error_msg:
            detail = "Malformed authentication token. Please login again."
        elif "not initialized" in error_msg.lower():
            detail = "Authentication service temporarily unavailable."
        else:
            detail = f"Authentication failed: {error_msg}"
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )