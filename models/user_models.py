from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    """Base user model with common fields"""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    location: Optional[str] = "Johannesburg, South Africa"
    timezone: Optional[str] = "Africa/Johannesburg"

class UserCreate(UserBase):
    """Model for creating a new user"""
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)
    
    def passwords_match(self) -> bool:
        return self.password == self.confirm_password

class UserUpdate(BaseModel):
    """Model for updating user information"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    location: Optional[str] = None
    timezone: Optional[str] = None

class UserResponse(BaseModel):
    """Model for user response (excludes sensitive data)"""
    uid: str
    email: str
    first_name: str
    last_name: str
    location: Optional[str]
    timezone: Optional[str]
    is_verified: bool = False
    google_connected: bool = False
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    """Model for user login"""
    email: EmailStr
    password: str

class AuthToken(BaseModel):
    """Model for authentication token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class GoogleAuthUser(BaseModel):
    """Model for Google OAuth user data"""
    google_id: str
    email: EmailStr
    first_name: str
    last_name: str
    picture_url: Optional[str] = None
    verified_email: bool = False