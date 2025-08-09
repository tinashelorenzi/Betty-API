from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os

from services.firebase_service import FirebaseService

class GoogleService:
    """Service for Google Workspace API integrations"""
    
    def __init__(self, firebase_service: FirebaseService):
        self.firebase_service = firebase_service
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
        
        # OAuth scopes for Google Workspace
        self.scopes = [
            'openid',  # Add openid first to prevent scope mismatch
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/calendar'
        ]
    
    # ========================================================================
    # OAUTH FLOW
    # ========================================================================
    
    def get_authorization_url(self, user_id: str) -> str:
        """Get Google OAuth authorization URL"""
        try:
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri]
                    }
                },
                scopes=self.scopes
            )
            flow.redirect_uri = self.redirect_uri
            
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=user_id,  # Pass user_id as state parameter
                prompt='consent'
            )
            
            return authorization_url
            
        except Exception as e:
            raise Exception(f"Failed to get authorization URL: {e}")
    
    async def handle_oauth_callback(self, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and store tokens"""
        try:
            user_id = state  # user_id was passed as state
            
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri]
                    }
                },
                scopes=self.scopes
            )
            flow.redirect_uri = self.redirect_uri
            
            # Exchange code for tokens
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Get user info from Google
            user_info_service = build('oauth2', 'v2', credentials=credentials)
            user_info = user_info_service.userinfo().get().execute()
            
            # Store tokens in Firebase
            tokens_data = {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
                "google_user_info": user_info,
                "connected_at": datetime.utcnow()
            }
            
            await self.firebase_service.create_document(
                "google_tokens", 
                tokens_data, 
                doc_id=user_id
            )
            
            # Update user profile
            await self.firebase_service.update_user_profile(user_id, {
                "google_connected": True,
                "google_email": user_info.get("email"),
                "google_name": user_info.get("name"),
                "google_picture": user_info.get("picture"),
                "google_connected_at": datetime.utcnow()
            })
            
            return {
                "success": True,
                "user_info": user_info,
                "message": "Google account connected successfully"
            }
            
        except Exception as e:
            raise Exception(f"OAuth callback failed: {e}")
    
    async def _get_user_credentials(self, user_id: str):
        """Get user's Google credentials for API calls - Private method (calls public method)"""
        return await self.get_user_credentials(user_id)
    
    async def get_user_credentials(self, user_id: str) -> Optional[Credentials]:
        """Get and validate user's Google credentials"""
        try:
            print(f"✅ Found credentials in google_tokens for user {user_id}")
            
            # Get stored tokens from Firebase
            tokens_doc = await self.firebase_service.get_document("google_tokens", user_id)
            if not tokens_doc:
                print(f"❌ No Google tokens found for user {user_id}")
                return None
            
            token_data = tokens_doc.get("tokens")
            if not token_data:
                print(f"❌ Invalid token data for user {user_id}")
                return None
            
            # Create credentials object
            credentials = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes", [])
            )
            
            # Refresh if needed
            if credentials.expired:
                try:
                    credentials.refresh()
                    
                    # Update stored tokens
                    updated_tokens = {
                        **token_data,
                        "access_token": credentials.token,
                        "refresh_token": credentials.refresh_token,
                        "expiry": credentials.expiry.isoformat() if credentials.expiry else None
                    }
                    
                    await self.firebase_service.update_document("google_tokens", user_id, {
                        "tokens": updated_tokens,
                        "updated_at": datetime.utcnow().isoformat()
                    })
                    
                except RefreshError as e:
                    print(f"Failed to refresh credentials: {e}")
                    return None
            
            return credentials
            
        except Exception as e:
            print(f"Error getting user credentials: {e}")
            return None
    
    async def handle_mobile_oauth_callback(self, code: str, user_id: str, redirect_uri: str) -> Dict[str, Any]:
        """Handle OAuth callback from mobile app with custom redirect URI"""
        try:
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri]
                    }
                },
                scopes=self.scopes
            )
            flow.redirect_uri = redirect_uri
            
            # Exchange code for tokens
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Get user info from Google
            user_info_service = build('oauth2', 'v2', credentials=credentials)
            user_info = user_info_service.userinfo().get().execute()
            
            # Store tokens in Firebase
            tokens_data = {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
                "google_user_info": user_info,
                "connected_at": datetime.utcnow(),
                "connection_type": "mobile"
            }
            
            await self.firebase_service.create_document(
                "google_tokens", 
                tokens_data, 
                doc_id=user_id
            )
            
            # Update user profile
            await self.firebase_service.update_user_profile(user_id, {
                "google_connected": True,
                "google_email": user_info.get("email"),
                "google_name": user_info.get("name"),
                "google_picture": user_info.get("picture"),
                "google_connected_at": datetime.utcnow()
            })
            
            return {
                "success": True,
                "user_info": {
                    "email": user_info.get("email"),
                    "name": user_info.get("name"),
                    "picture": user_info.get("picture")
                },
                "message": "Google account connected successfully"
            }
            
        except Exception as e:
            print(f"Failed to handle mobile OAuth callback: {e}")
            raise Exception(f"Failed to complete Google authentication: {e}")
    
    async def disconnect_google_account(self, user_id: str) -> bool:
        """Disconnect and revoke Google account access"""
        try:
            # Get current credentials
            credentials = await self.get_user_credentials(user_id)
            
            if credentials and credentials.token:
                # Revoke the token
                revoke_url = f"https://oauth2.googleapis.com/revoke?token={credentials.token}"
                import requests
                response = requests.post(revoke_url)
                print(f"Token revocation response: {response.status_code}")
            
            # Remove tokens from Firebase
            await self.firebase_service.delete_document("google_tokens", user_id)
            
            # Update user profile
            await self.firebase_service.update_user_profile(user_id, {
                "google_connected": False,
                "google_email": None,
                "google_name": None,
                "google_picture": None,
                "google_disconnected_at": datetime.utcnow()
            })
            
            return True
            
        except Exception as e:
            print(f"Failed to disconnect Google account: {e}")
            return False
    
    # ========================================================================
    # GOOGLE DOCS API
    # ========================================================================
    


    async def check_google_connection_status(self, user_id: str) -> Dict[str, Any]:
        """Check if user has a valid Google connection - FIXED METHOD NAME"""
        try:
            credentials = await self.get_user_credentials(user_id)
            
            if not credentials:
                return {
                    "connected": False,
                    "user_info": None
                }
            
            # Get stored user info
            tokens_doc = await self.firebase_service.get_document("google_tokens", user_id)
            user_info = tokens_doc.get("google_user_info") if tokens_doc else None
            
            return {
                "connected": True,
                "user_info": {
                    "email": user_info.get("email") if user_info else None,
                    "name": user_info.get("name") if user_info else None,
                    "picture": user_info.get("picture") if user_info else None
                } if user_info else None
            }
            
        except Exception as e:
            print(f"Failed to check connection status: {e}")
            return {
                "connected": False,
                "user_info": None
            }

    async def create_google_doc(self, user_id: str, title: str, content: str) -> Dict[str, Any]:
        """Create a Google Doc with the provided content"""
        try:
            credentials = await self.get_user_credentials(user_id)
            
            if not credentials:
                raise Exception("Google account not connected")
            
            # Create the document using Google Docs API
            docs_service = build('docs', 'v1', credentials=credentials)
            doc = {
                'title': title
            }
            
            # Create the document
            document = docs_service.documents().create(body=doc).execute()
            document_id = document.get('documentId')
            
            # Insert content into the document
            requests_body = {
                'requests': [
                    {
                        'insertText': {
                            'location': {
                                'index': 1,
                            },
                            'text': content
                        }
                    }
                ]
            }
            
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body=requests_body
            ).execute()
            
            # Generate the shareable URL
            document_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            return {
                "success": True,
                "document_id": document_id,
                "document_url": document_url,
                "title": title,
                "message": f"Document '{title}' created successfully"
            }
            
        except Exception as e:
            print(f"Failed to create Google Doc: {e}")
            raise Exception(f"Failed to create Google Doc: {e}")
    
    async def update_google_doc(
        self, 
        user_id: str, 
        document_id: str, 
        content: str
    ) -> Dict[str, Any]:
        """Update an existing Google Document"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            docs_service = build('docs', 'v1', credentials=credentials)
            
            # Get current document
            doc = docs_service.documents().get(documentId=document_id).execute()
            
            # Clear existing content and add new content
            doc_length = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)
            
            requests = [
                {
                    'deleteContentRange': {
                        'range': {
                            'startIndex': 1,
                            'endIndex': doc_length - 1
                        }
                    }
                },
                {
                    'insertText': {
                        'location': {
                            'index': 1,
                        },
                        'text': content
                    }
                }
            ]
            
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            return {
                "document_id": document_id,
                "updated_at": datetime.utcnow().isoformat(),
                "success": True
            }
            
        except HttpError as e:
            raise Exception(f"Google Docs API error: {e}")
        except Exception as e:
            raise Exception(f"Failed to update Google Doc: {e}")
    
    # ========================================================================
    # GOOGLE DRIVE API
    # ========================================================================
    
    async def list_user_drive_files(
        self, 
        user_id: str, 
        file_type: str = 'application/vnd.google-apps.document'
    ) -> List[Dict[str, Any]]:
        """List user's Google Drive files"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Query files
            query = f"mimeType='{file_type}' and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name, createdTime, modifiedTime, webViewLink)",
                orderBy="modifiedTime desc"
            ).execute()
            
            files = results.get('files', [])
            
            return files
            
        except HttpError as e:
            raise Exception(f"Google Drive API error: {e}")
        except Exception as e:
            raise Exception(f"Failed to list Drive files: {e}")
    
    # ========================================================================
    # GOOGLE CALENDAR API
    # ========================================================================
    
    async def get_calendar_events(
        self, 
        user_id: str, 
        start_date: str, 
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Get calendar events from Google Calendar with proper timezone handling"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                print(f"❌ No valid credentials for user {user_id}")
                return []
            
            service = build('calendar', 'v3', credentials=credentials)
            
            # ✅ FIX: Proper date parsing and timezone handling
            try:
                # Parse input dates and ensure they have timezone info
                if 'T' in start_date:
                    start_datetime = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                else:
                    start_datetime = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
                
                if 'T' in end_date:
                    end_datetime = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                else:
                    end_datetime = datetime.fromisoformat(f"{end_date}T23:59:59+00:00")
                
                # Ensure timezone awareness
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
                if end_datetime.tzinfo is None:
                    end_datetime = end_datetime.replace(tzinfo=timezone.utc)
                
                time_min = start_datetime.isoformat()
                time_max = end_datetime.isoformat()
                
                print(f"🔍 Fetching events from {time_min} to {time_max}")
                
            except (ValueError, TypeError) as e:
                print(f"Date parsing error: {e}")
                # Fallback to safe string format
                time_min = f"{start_date}T00:00:00Z" if 'T' not in start_date else start_date
                time_max = f"{end_date}T23:59:59Z" if 'T' not in end_date else end_date
            
            # Call Google Calendar API
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            print(f"📅 Retrieved {len(events)} events from Google Calendar")
            
            # Format events for our API
            formatted_events = []
            for event in events:
                try:
                    start_time = event.get('start', {})
                    end_time = event.get('end', {})
                    
                    formatted_event = {
                        'id': event.get('id'),
                        'title': event.get('summary', 'No Title'),
                        'description': event.get('description', ''),
                        'start_time': start_time.get('dateTime') or start_time.get('date'),
                        'end_time': end_time.get('dateTime') or end_time.get('date'),
                        'location': event.get('location', ''),
                        'attendees': [
                            attendee.get('email') for attendee in event.get('attendees', [])
                        ],
                        'event_type': 'google_calendar',
                        'user_id': user_id,
                        'google_event_id': event.get('id')
                    }
                    formatted_events.append(formatted_event)
                except Exception as e:
                    print(f"Error formatting event {event.get('id', 'unknown')}: {e}")
                    continue
            
            return formatted_events
            
        except HttpError as e:
            print(f"Google Calendar API error: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error getting calendar events: {e}")
            return []
    
    async def update_calendar_event(
        self, 
        user_id: str, 
        event_id: str, 
        event_update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update existing calendar event"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            service = build('calendar', 'v3', credentials=credentials)
            
            # Get existing event
            existing_event = service.events().get(
                calendarId='primary', 
                eventId=event_id
            ).execute()
            
            # Update fields
            for key, value in event_update.items():
                existing_event[key] = value
            
            # Update the event
            updated_event = service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=existing_event
            ).execute()
            
            return {
                'id': updated_event['id'],
                'updated_at': datetime.utcnow().isoformat(),
                'success': True
            }
            
        except HttpError as e:
            raise Exception(f"Google Calendar API error: {e}")
        except Exception as e:
            raise Exception(f"Failed to update calendar event: {e}")
    
    async def delete_calendar_event(
        self, 
        user_id: str, 
        event_id: str
    ) -> Dict[str, Any]:
        """Delete calendar event from Google Calendar"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            service = build('calendar', 'v3', credentials=credentials)
            
            # Delete the event
            service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            print(f"✅ Deleted Google Calendar event: {event_id}")
            
            return {
                'id': event_id,
                'deleted_at': datetime.utcnow().isoformat(),
                'success': True
            }
            
        except HttpError as e:
            if e.resp.status == 404:
                # Event already doesn't exist, consider it success
                print(f"⚠️ Calendar event {event_id} not found, already deleted")
                return {
                    'id': event_id,
                    'deleted_at': datetime.utcnow().isoformat(),
                    'success': True,
                    'message': 'Event already deleted'
                }
            else:
                error_message = f"Google Calendar API error: {e}"
                print(f"❌ {error_message}")
                raise Exception(error_message)
        except Exception as e:
            error_message = f"Failed to delete calendar event: {e}"
            print(f"❌ {error_message}")
            raise Exception(error_message)
    
    async def _check_google_credentials(self, user_id: str) -> bool:
        """Check if user has valid Google credentials - IMPROVED VERSION"""
        try:
            # Check google_tokens collection first
            tokens_doc = await self.firebase_service.get_document("google_tokens", user_id)
            
            if tokens_doc:
                access_token = tokens_doc.get("access_token")
                refresh_token = tokens_doc.get("refresh_token")
                
                if access_token and refresh_token:
                    print(f"✅ Found credentials in google_tokens for user {user_id}")
                    return True
            
            # Fallback to users collection
            user_doc = await self.firebase_service.get_document("users", user_id)
            if user_doc:
                google_tokens = user_doc.get("google_tokens")
                if google_tokens:
                    access_token = google_tokens.get("access_token")
                    refresh_token = google_tokens.get("refresh_token")
                    
                    if access_token and refresh_token:
                        print(f"✅ Found credentials in users collection for user {user_id}")
                        return True
            
            print(f"❌ No valid credentials found for user {user_id}")
            return False
            
        except Exception as e:
            print(f"Error checking Google credentials: {e}")
            return False
    
    async def get_user_credentials(self, user_id: str) -> Optional[Credentials]:
        """Get user's stored Google credentials - Public method"""
        try:
            print(f"🔍 Getting credentials for user {user_id}")
            
            # First try the new storage location (google_tokens collection)
            tokens_doc = await self.firebase_service.get_document("google_tokens", user_id)
            
            google_tokens = None
            
            if tokens_doc:
                print(f"✅ Found credentials in google_tokens for user {user_id}")
                
                # The tokens are stored DIRECTLY in the document, not wrapped in a "tokens" field
                # This matches how they are stored in the OAuth callback methods
                google_tokens = tokens_doc
                
            if not google_tokens:
                # Fallback to old storage location (users collection)
                print(f"🔄 Falling back to users collection for user {user_id}")
                user_doc = await self.firebase_service.get_document("users", user_id)
                if not user_doc:
                    print(f"❌ No user document found for {user_id}")
                    return None
                
                google_tokens = user_doc.get("google_tokens")
                if not google_tokens:
                    print(f"❌ No google_tokens found in user document for {user_id}")
                    return None
                
                print(f"✅ Found credentials in users collection for user {user_id}")
            
            # Validate required token fields
            access_token = google_tokens.get("access_token")
            refresh_token = google_tokens.get("refresh_token")
            
            if not access_token or not refresh_token:
                print(f"❌ Missing required tokens for user {user_id}")
                print(f"🔍 access_token exists: {bool(access_token)}")
                print(f"🔍 refresh_token exists: {bool(refresh_token)}")
                print(f"🔍 Available keys: {list(google_tokens.keys())}")
                return None
            
            # Create credentials object using the stored values OR environment variables
            client_id = google_tokens.get("client_id") or os.getenv("GOOGLE_CLIENT_ID")
            client_secret = google_tokens.get("client_secret") or os.getenv("GOOGLE_CLIENT_SECRET")
            token_uri = google_tokens.get("token_uri") or "https://oauth2.googleapis.com/token"
            scopes = google_tokens.get("scopes") or [
                'https://www.googleapis.com/auth/calendar.readonly',
                'https://www.googleapis.com/auth/calendar',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile'
            ]
            
            credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri=token_uri,
                client_id=client_id,
                client_secret=client_secret,
                scopes=scopes
            )
            
            # Set expiry if available
            expiry_str = google_tokens.get("expiry") or google_tokens.get("expires_at")
            if expiry_str:
                try:
                    from datetime import datetime
                    credentials.expiry = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"⚠️ Could not parse expiry date: {e}")
            
            # Check if credentials are expired and refresh if needed
            if credentials.expired and credentials.refresh_token:
                try:
                    print(f"🔄 Refreshing expired credentials for user {user_id}")
                    request = Request()
                    credentials.refresh(request)
                    
                    # Update stored tokens
                    updated_tokens = {
                        "access_token": credentials.token,
                        "refresh_token": credentials.refresh_token,
                        "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                    
                    # Update in google_tokens collection if that's where we found it
                    if tokens_doc:
                        await self.firebase_service.update_document("google_tokens", user_id, updated_tokens)
                    else:
                        # Update in users collection
                        await self.firebase_service.update_document("users", user_id, {
                            "google_tokens.access_token": credentials.token,
                            "google_tokens.refresh_token": credentials.refresh_token,
                            "google_tokens.expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                            "google_tokens.updated_at": datetime.utcnow().isoformat()
                        })
                    
                    print(f"✅ Successfully refreshed credentials for user {user_id}")
                    
                except Exception as e:
                    print(f"❌ Failed to refresh credentials for user {user_id}: {e}")
                    return None
            
            print(f"✅ Successfully created credentials object for user {user_id}")
            return credentials
            
        except Exception as e:
            print(f"❌ Error getting user credentials for {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def create_calendar_event(
        self, 
        user_id: str, 
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create calendar event in user's Google Calendar with proper date handling"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            service = build('calendar', 'v3', credentials=credentials)
            
            # ✅ FIX: Handle different date formats for start/end times
            def format_datetime_for_google(dt_input, default_timezone='Africa/Johannesburg'):
                """Convert various datetime formats to Google Calendar format"""
                if isinstance(dt_input, str):
                    try:
                        # Try parsing ISO format
                        dt = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        # Fallback: assume it's already in correct format
                        return dt_input
                elif isinstance(dt_input, datetime):
                    dt = dt_input
                else:
                    raise ValueError(f"Invalid datetime format: {dt_input}")
                
                # Ensure timezone awareness
                if dt.tzinfo is None:
                    # Assume local timezone if none specified
                    dt = dt.replace(tzinfo=timezone.utc)
                
                return {
                    'dateTime': dt.isoformat(),
                    'timeZone': default_timezone
                }
            
            # Format event for Google Calendar
            event = {
                'summary': event_data.get('title', event_data.get('summary', 'No Title')),
                'description': event_data.get('description', ''),
                'location': event_data.get('location', ''),
            }
            
            # Handle start/end times with proper formatting
            if 'start_time' in event_data:
                event['start'] = format_datetime_for_google(event_data['start_time'])
            elif 'start' in event_data:
                event['start'] = event_data['start']
            
            if 'end_time' in event_data:
                event['end'] = format_datetime_for_google(event_data['end_time'])
            elif 'end' in event_data:
                event['end'] = event_data['end']
            
            # Add attendees if provided
            if event_data.get('attendees'):
                event['attendees'] = [
                    {'email': email} for email in event_data['attendees']
                ]
            
            # Add reminders
            event['reminders'] = {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': event_data.get('reminder_minutes', 15)},
                    {'method': 'popup', 'minutes': 10},
                ],
            }
            
            # Create the event
            created_event = service.events().insert(
                calendarId='primary', 
                body=event
            ).execute()
            
            print(f"✅ Created Google Calendar event: {created_event.get('id')}")
            
            return {
                'id': created_event['id'],
                'google_event_id': created_event['id'],
                'event_url': created_event.get('htmlLink'),
                'created_at': datetime.utcnow().isoformat(),
                'success': True
            }
            
        except HttpError as e:
            error_message = f"Google Calendar API error: {e}"
            print(f"❌ {error_message}")
            raise Exception(error_message)
        except Exception as e:
            error_message = f"Failed to create calendar event: {e}"
            print(f"❌ {error_message}")
            raise Exception(error_message)
    
    # ========================================================================
    # GOOGLE KEEP API (Note: Limited availability)
    # ========================================================================
    
    async def create_keep_note(
        self, 
        user_id: str, 
        title: str, 
        content: str
    ) -> Dict[str, Any]:
        """Create note in Google Keep (if available)"""
        try:
            # Note: Google Keep API has limited availability
            # For now, we'll create a Google Doc instead as a workaround
            
            doc_result = await self.create_google_doc(
                user_id, 
                f"Note: {title}", 
                f"{title}\n\n{content}"
            )
            
            return {
                "note_id": doc_result["document_id"],
                "note_url": doc_result["document_url"],
                "title": title,
                "created_at": datetime.utcnow().isoformat(),
                "note": "Created as Google Doc (Keep API not available)"
            }
            
        except Exception as e:
            raise Exception(f"Failed to create Keep note: {e}")
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    async def get_user_google_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's Google account information"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                return None
            
            oauth2_service = build('oauth2', 'v2', credentials=credentials)
            user_info = oauth2_service.userinfo().get().execute()
            
            return user_info
            
        except Exception as e:
            print(f"Failed to get Google user info: {e}")
            return None
    
    async def check_google_connection_status(self, user_id: str) -> Dict[str, Any]:
        """Check if user's Google connection is active and valid"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                return {"connected": False, "error": "No credentials found"}
            
            # Test the connection by making a simple API call
            oauth2_service = build('oauth2', 'v2', credentials=credentials)
            user_info = oauth2_service.userinfo().get().execute()
            
            return {
                "connected": True,
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                "scopes": credentials.scopes,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None
            }
            
        except Exception as e:
            return {"connected": False, "error": str(e)}