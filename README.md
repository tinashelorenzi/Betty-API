# Betty API

A FastAPI application with SQLAdmin integration, Firebase Authentication, and subscription management.

## Features

- **FastAPI:** Modern, fast web framework for building APIs
- **SQLAdmin:** Admin interface for SQLAlchemy models
- **Firebase Authentication:** Secure user authentication and management
- **Subscription Management:** Track user subscriptions and payment records
- **SQLAlchemy ORM:** Database management with relationships
- **SQLite Database:** Lightweight database for development

## Setup

### 1. Prerequisites

- Python 3.8+
- Firebase project with Authentication enabled
- Firebase service account key (optional, for server-side operations)

### 2. Environment Setup

1. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Firebase:**
   
   Copy `env.example` to `.env` and configure your Firebase settings:
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` and set your Firebase service account path:
   ```
   FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/your/firebase-service-account-key.json
   ```

### 3. Firebase Configuration

1. **Get Firebase Service Account Key:**
   - Go to Firebase Console → Project Settings → Service Accounts
   - Click "Generate new private key"
   - Save the JSON file securely
   - Set the path in your `.env` file

2. **Enable Authentication:**
   - In Firebase Console, go to Authentication → Sign-in method
   - Enable the authentication providers you want to use (Email/Password, Google, etc.)

## Running the Application

1. **Start the FastAPI server:**
   ```bash
   python main.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn main:app --reload
   ```

2. **Access the application:**
   - **API Documentation:** http://localhost:8000/docs
   - **Alternative API Docs:** http://localhost:8000/redoc
   - **SQLAdmin Interface:** http://localhost:8000/admin
   - **Health Check:** http://localhost:8000/health

## Project Structure

```
Betty-API/
├── venv/                 # Virtual environment
├── models/              # Database models
│   ├── __init__.py
│   ├── base.py         # Base model and mixins
│   ├── user.py         # User model with Firebase integration
│   └── subscription.py # Subscription model
├── config/             # Configuration files
│   ├── __init__.py
│   └── firebase_config.py # Firebase configuration
├── credentials/        # Firebase credentials (if using service account)
├── main.py             # FastAPI application
├── requirements.txt    # Python dependencies
├── README.md          # This file
├── env.example        # Environment variables example
└── betty.db           # SQLite database (created on first run)
```

## Models

### User Model
- **Firebase Integration:** Links to Firebase Auth UID
- **Profile Fields:** Name, email, phone, photo URL
- **Account Status:** Active/inactive, admin privileges
- **Login Tracking:** Last login timestamp

### Subscription Model
- **Subscription Types:** Monthly (30 days), 6 months, Yearly
- **Payment Tracking:** Amount, currency, payment method, reference
- **Status Management:** Active, expired, cancelled, pending
- **Auto-renewal:** Support for automatic subscription renewal
- **Date Management:** Start/end dates, next billing date

## API Endpoints

### Public Endpoints
- `GET /`: Welcome message
- `GET /health`: Health check endpoint
- `GET /docs`: Interactive API documentation
- `GET /admin`: SQLAdmin interface

### Protected Endpoints (Require Firebase Auth)
- `GET /me`: Get current user information
- `GET /users/{user_id}`: Get user by ID (admin only)
- `GET /subscriptions/`: Get current user's subscriptions

## Authentication

The API uses Firebase Authentication with Bearer tokens:

1. **Client Authentication:**
   - Users authenticate through Firebase Auth (web/mobile)
   - Get Firebase ID token from client
   - Include token in Authorization header: `Bearer <token>`

2. **Server Verification:**
   - API verifies Firebase ID token
   - Creates/updates user record in local database
   - Returns user information

## SQLAdmin Interface

The SQLAdmin interface provides a web-based admin panel where you can:
- View and manage user records
- Monitor subscription status and payments
- Search and sort data
- Access it at http://localhost:8000/admin

## Development

### Adding New Models

1. Create a new model in the `models/` directory using SQLAlchemy
2. Import it in `models/__init__.py`
3. Create a corresponding ModelView class in `main.py`
4. Add the view to the admin instance

### Firebase Integration

The Firebase configuration is handled in `config/firebase_config.py`:
- Token verification
- User creation/updates
- Custom token generation

### Database Migrations

When you modify models, the database will automatically update on startup. For production, consider using Alembic for proper migrations. 