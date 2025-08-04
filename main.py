from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqladmin import Admin, ModelView
from datetime import datetime
from typing import Optional

# Import our models and Firebase config
from models import Base, User, Subscription
from config.firebase_config import firebase_config

# Create FastAPI app
app = FastAPI(title="Betty API", description="A FastAPI application with SQLAdmin and Firebase Auth")

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./betty.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Firebase authentication
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Get current user from Firebase token"""
    token = credentials.credentials
    
    # Verify Firebase token
    decoded_token = firebase_config.verify_token(token)
    if not decoded_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get or create user in our database
    firebase_uid = decoded_token.get('uid')
    email = decoded_token.get('email')
    
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    
    if not user:
        # Create new user from Firebase data
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            email_verified=decoded_token.get('email_verified', False),
            display_name=decoded_token.get('name'),
            first_name=decoded_token.get('given_name'),
            last_name=decoded_token.get('family_name'),
            photo_url=decoded_token.get('picture')
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update last login
        user.update_last_login()
        db.commit()
    
    return user

# SQLAdmin setup
admin = Admin(app, engine)

# ModelView for User
class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.display_name, User.is_active, User.last_login_at, User.created_at]
    column_searchable_list = [User.email, User.display_name, User.first_name, User.last_name]
    column_sortable_list = [User.id, User.email, User.created_at, User.last_login_at]
    column_exclude_list = [User.firebase_uid]  # Hide sensitive data

# ModelView for Subscription
class SubscriptionAdmin(ModelView, model=Subscription):
    column_list = [Subscription.id, Subscription.user_id, Subscription.subscription_type, 
                   Subscription.status, Subscription.amount_paid, Subscription.start_date, 
                   Subscription.end_date, Subscription.is_active]
    column_searchable_list = [Subscription.payment_reference]
    column_sortable_list = [Subscription.id, Subscription.start_date, Subscription.end_date, Subscription.amount_paid]
    column_exclude_list = [Subscription.payment_reference]  # Hide sensitive data

# Add the model views to admin
admin.add_view(UserAdmin)
admin.add_view(SubscriptionAdmin)

@app.get("/")
async def root():
    return {"message": "Welcome to Betty API with SQLAdmin and Firebase Auth!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.get("/me", response_model=dict)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user.to_dict()

@app.get("/users/{user_id}", response_model=dict)
async def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get user by ID (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.to_dict()

@app.get("/subscriptions/", response_model=list)
async def get_user_subscriptions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get current user's subscriptions"""
    subscriptions = db.query(Subscription).filter(Subscription.user_id == current_user.id).all()
    return [sub.to_dict() for sub in subscriptions]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 