from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
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
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/keep',  # Note: Keep API is limited
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
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
                state=user_id  # Pass user_id as state parameter
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
    
    async def get_user_credentials(self, user_id: str) -> Optional[Credentials]:
        """Get and refresh user's Google credentials"""
        try:
            # Get stored tokens
            tokens_doc = await self.firebase_service.get_document("google_tokens", user_id)
            if not tokens_doc:
                return None
            
            # Create credentials object
            credentials = Credentials(
                token=tokens_doc["access_token"],
                refresh_token=tokens_doc["refresh_token"],
                token_uri=tokens_doc["token_uri"],
                client_id=tokens_doc["client_id"],
                client_secret=tokens_doc["client_secret"],
                scopes=tokens_doc["scopes"]
            )
            
            # Refresh if expired
            if credentials.expired:
                credentials.refresh(Request())
                
                # Update stored tokens
                await self.firebase_service.update_document("google_tokens", user_id, {
                    "access_token": credentials.token,
                    "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
                    "refreshed_at": datetime.utcnow()
                })
            
            return credentials
            
        except Exception as e:
            print(f"Failed to get user credentials: {e}")
            return None
    
    async def disconnect_google_account(self, user_id: str) -> bool:
        """Disconnect user's Google account"""
        try:
            # Delete stored tokens
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
            raise Exception(f"Failed to disconnect Google account: {e}")
    
    # ========================================================================
    # GOOGLE DOCS API
    # ========================================================================
    
    async def create_google_doc(
        self, 
        user_id: str, 
        title: str, 
        content: str
    ) -> Dict[str, Any]:
        """Create a Google Doc in user's Drive"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            # Create document
            docs_service = build('docs', 'v1', credentials=credentials)
            
            # Create empty document
            document = {
                'title': title
            }
            doc = docs_service.documents().create(body=document).execute()
            document_id = doc.get('documentId')
            
            # Add content to document
            if content.strip():
                # Convert content to Google Docs format
                requests = [
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
            
            # Get document URL
            doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            return {
                "document_id": document_id,
                "document_url": doc_url,
                "title": title,
                "created_at": datetime.utcnow().isoformat()
            }
            
        except HttpError as e:
            raise Exception(f"Google Docs API error: {e}")
        except Exception as e:
            raise Exception(f"Failed to create Google Doc: {e}")
    
    async def update_google_doc(
        self, 
        user_id: str, 
        document_id: str, 
        content: str
    ) -> Dict[str, Any]:
        """Update existing Google Doc"""
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
        """Get user's calendar events"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            calendar_service = build('calendar', 'v3', credentials=credentials)
            
            # Get events from primary calendar
            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=start_date,
                timeMax=end_date,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Format events
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                formatted_events.append({
                    'id': event['id'],
                    'title': event.get('summary', 'No Title'),
                    'description': event.get('description', ''),
                    'start_time': start,
                    'end_time': end,
                    'location': event.get('location', ''),
                    'attendees': [attendee.get('email') for attendee in event.get('attendees', [])],
                    'html_link': event.get('htmlLink', '')
                })
            
            return formatted_events
            
        except HttpError as e:
            raise Exception(f"Google Calendar API error: {e}")
        except Exception as e:
            raise Exception(f"Failed to get calendar events: {e}")
    
    async def create_calendar_event(
        self, 
        user_id: str, 
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create calendar event in user's Google Calendar"""
        try:
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                raise ValueError("Google account not connected")
            
            calendar_service = build('calendar', 'v3', credentials=credentials)
            
            # Format event for Google Calendar
            event = {
                'summary': event_data['title'],
                'description': event_data.get('description', ''),
                'start': {
                    'dateTime': event_data['start_time'],
                    'timeZone': 'Africa/Johannesburg',
                },
                'end': {
                    'dateTime': event_data['end_time'],
                    'timeZone': 'Africa/Johannesburg',
                },
                'attendees': [{'email': email} for email in event_data.get('attendees', [])],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': event_data.get('reminder_minutes', 15)},
                        {'method': 'popup', 'minutes': 10},
                    ],
                },
            }
            
            if event_data.get('location'):
                event['location'] = event_data['location']
            
            created_event = calendar_service.events().insert(
                calendarId='primary', 
                body=event
            ).execute()
            
            return {
                'google_event_id': created_event['id'],
                'event_url': created_event.get('htmlLink'),
                'created_at': datetime.utcnow().isoformat(),
                'success': True
            }
            
        except HttpError as e:
            raise Exception(f"Google Calendar API error: {e}")
        except Exception as e:
            raise Exception(f"Failed to create calendar event: {e}")
    
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