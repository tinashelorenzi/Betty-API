# services/ai_service.py - COMPLETE FIXED VERSION WITH ALL YOUR FUNCTIONALITY
import google.generativeai as genai
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import os
import time
import json
import re
import uuid
from datetime import datetime, timezone

from models.chat_models import ChatMessage, ChatResponse, MessageHistory, MessageRole, MessageType, AIContext, EnhancedChatResponse
from services.firebase_service import FirebaseService

class AIService:
    """Service for AI operations using Google Gemini"""
    
    def __init__(self, firebase_service: Optional[FirebaseService] = None):
        self.firebase_service = firebase_service
        self.model = None
        self._initialize_ai()
    
    def _normalize_datetime(self, dt) -> datetime:
        """Normalize datetime to UTC timezone-aware format"""
        if dt is None:
            return datetime.now(timezone.utc)
        
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                # Naive datetime - assume UTC
                return dt.replace(tzinfo=timezone.utc)
            else:
                # Already timezone-aware - convert to UTC
                return dt.astimezone(timezone.utc)
        
        # If it's a string or other format, try to parse it
        if isinstance(dt, str):
            try:
                parsed_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                return parsed_dt.astimezone(timezone.utc)
            except:
                return datetime.now(timezone.utc)
        
        return datetime.now(timezone.utc)

    def _get_utc_now(self) -> datetime:
        """Get current UTC time as timezone-aware datetime"""
        return datetime.now(timezone.utc)
    
    def _get_today_start_utc(self) -> datetime:
        """Get start of today in UTC as timezone-aware datetime"""
        now = self._get_utc_now()
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _initialize_ai(self):
        """Initialize Google Gemini AI"""
        try:
            api_key = os.getenv("GOOGLE_AI_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_AI_API_KEY environment variable not set")
            
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            print("✅ Google Gemini AI initialized successfully")
            
        except Exception as e:
            print(f"❌ AI initialization failed: {e}")
            # Use fallback mock response for development
            self.model = None
    
    async def process_message(self, message: ChatMessage, user_id: str, conversation_id: Optional[str] = None) -> EnhancedChatResponse:
        """Process user message and return AI response with conversation context - FIXED VERSION"""
        try:
            start_time = time.time()
            
            # Create conversation if not provided
            if not conversation_id:
                conversation_id = await self.create_conversation_session(user_id)
            
            # Get user context with conversation history - FIXED: proper parameter passing
            context = await self._get_user_context(user_id, conversation_id)
            
            # Build prompt with context
            system_prompt = self._build_system_prompt(context)
            full_prompt = f"{system_prompt}\n\nUser message: {message.content}"
            
            # Generate AI response
            if self.model:
                response = await self._generate_ai_response(full_prompt)
            else:
                response = await self._generate_mock_response(message.content)
            
            processing_time = time.time() - start_time
            
            # Parse response for special actions
            parsed_response = self._parse_ai_response(response)
            
            # Save message history with conversation context
            if self.firebase_service:
                await self._save_message_history(
                    user_id, message.content, response, processing_time, conversation_id
                )
            
            # Return complete EnhancedChatResponse with all fields
            return EnhancedChatResponse(
                content=parsed_response["content"],
                message_type=MessageType(parsed_response.get("message_type", "text")),
                document_created=parsed_response.get("document_created", False),
                document_title=parsed_response.get("document_title"),
                document_content=parsed_response.get("document_content"),
                document_type=parsed_response.get("document_type"),
                task_created=parsed_response.get("task_created", False),
                task_data=parsed_response.get("task_data"),
                calendar_event_created=parsed_response.get("calendar_event_created", False),
                event_data=parsed_response.get("event_data"),
                processing_time=processing_time,
                tokens_used=parsed_response.get("tokens_used"),
                confidence_score=parsed_response.get("confidence_score", 0.9),
                conversation_id=conversation_id
            )
            
        except Exception as e:
            print(f"Error in process_message: {e}")
            return EnhancedChatResponse(
                content=f"I apologize, but I'm having trouble processing your request right now. Error: {str(e)}",
                message_type=MessageType.TEXT,
                processing_time=time.time() - start_time if 'start_time' in locals() else 0,
                conversation_id=conversation_id
            )
    
    async def _generate_ai_response(self, prompt: str) -> str:
        """Generate response using Google Gemini"""
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    max_output_tokens=2048,
                    temperature=0.7,
                )
            )
            return response.text
        except Exception as e:
            raise Exception(f"AI generation failed: {e}")
    
    async def _generate_mock_response(self, user_message: str) -> str:
        """Generate mock response for development/fallback"""
        user_message = user_message.lower()
        
        if "create" in user_message and any(doc_type in user_message for doc_type in ["contract", "invoice", "nda", "template"]):
            doc_type = "contract" if "contract" in user_message else "invoice" if "invoice" in user_message else "document"
            return f"I'll create a {doc_type} template for you. You can find it in the Documents section.|||**{doc_type.title()} Template**\n\n**TITLE:** Sample {doc_type.title()}\n\n**Content:** This is a sample {doc_type} template generated by Betty AI.\n\n**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n[Template content would go here...]"
        
        elif "task" in user_message and "create" in user_message:
            return "I can help you create tasks! What specific task would you like me to add to your planner?"
        
        elif "help" in user_message or "what can you do" in user_message:
            return """Hello! I'm Betty, your AI business assistant. I can help you with:

📝 **Document Creation**: Create contracts, invoices, business plans, NDAs, and more
📋 **Task Management**: Create and manage your tasks and to-do lists  
📅 **Calendar**: Help with scheduling and event planning
📊 **Business Analysis**: Provide insights and advice for your business
🔍 **Research**: Find information and answer business questions
📈 **Planning**: Assist with project planning and strategy

Just ask me anything business-related, or tell me to create a specific document or task!"""
        
        else:
            return f"Thank you for your message: '{user_message}'. As your AI business assistant, I'm here to help with documents, tasks, planning, and business advice. How can I assist you today?"
    
    def _build_system_prompt(self, context: AIContext) -> str:
        """Build system prompt with user context"""
        current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p SAST")
        
        prompt = f"""You are "Betty", an expert AI business assistant specifically designed for South African businesses. 

**CURRENT CONTEXT:**
- Time: {current_time}  
- User Location: {context.user_location}
- User Timezone: {context.user_timezone}

**YOUR CAPABILITIES:**
- Business strategy and planning advice
- South African business law and regulations (CIPC, SARS, etc.)
- Document creation (contracts, MOIs, business plans, invoices, etc.)
- Task and project management
- Financial analysis and accounting guidance
- Marketing and sales strategies
- HR and employment law (South African context)

**DOCUMENT CREATION INSTRUCTIONS:**
When a user asks you to create a document or template, you MUST respond in two parts separated by '|||':
1. A user-facing confirmation message
2. The complete document content

Example format:
"I've created the [Document Name] for you. You can find it in the Documents section.|||**[DOCUMENT TITLE]**\n\n[Full document content here]"

**COMMUNICATION STYLE:**
- Professional but friendly and approachable
- Use South African business terminology where appropriate
- Provide actionable, practical advice
- Be concise but thorough
- Always consider South African legal and business context

**RECENT CONTEXT:**
- Recent documents: {len(context.recent_documents)} documents
- Recent tasks: {len(context.recent_tasks)} tasks
- Conversation history: {len(context.conversation_history)} previous messages"""

        return prompt
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Parse AI response for special actions and content"""
        parsed = {
            "content": response,
            "message_type": "text",
            "document_created": False,
            "task_created": False,
            "calendar_event_created": False
        }
        
        # Check for document creation (|||separator)
        if "|||" in response:
            parts = response.split("|||", 1)
            parsed["content"] = parts[0].strip()
            parsed["document_created"] = True
            parsed["message_type"] = "document_creation"
            
            # Extract document content
            doc_content = parts[1].strip()
            
            # Extract title from content
            title_match = re.search(r'\*\*([^*]+)\*\*', doc_content)
            parsed["document_title"] = title_match.group(1) if title_match else "AI Generated Document"
            parsed["document_content"] = doc_content
            
            # Determine document type based on content
            content_lower = doc_content.lower()
            if "contract" in content_lower:
                parsed["document_type"] = "contract"
            elif "invoice" in content_lower:
                parsed["document_type"] = "invoice"
            elif "business plan" in content_lower:
                parsed["document_type"] = "business_plan"
            elif "nda" in content_lower or "non-disclosure" in content_lower:
                parsed["document_type"] = "nda"
            else:
                parsed["document_type"] = "ai_generated"
        
        # Check for task creation indicators
        task_indicators = ["create task", "add task", "new task", "task:"]
        if any(indicator in response.lower() for indicator in task_indicators):
            parsed["task_created"] = True
            parsed["message_type"] = "task_creation"
            # Extract task data if found
            # This is a simplified extraction - could be made more sophisticated
            parsed["task_data"] = {"title": "AI Generated Task", "priority": "medium"}
        
        return parsed
    
    async def _get_user_context(self, user_id: str, conversation_id: Optional[str] = None) -> AIContext:
        """Get user context for AI conversation - FIXED METHOD SIGNATURE"""
        try:
            context = AIContext(
                current_time=datetime.now(),
                user_location="Johannesburg, South Africa",
                user_timezone="Africa/Johannesburg"
            )
            
            if self.firebase_service:
                # Get user profile
                user_profile = await self.firebase_service.get_user_profile(user_id)
                if user_profile:
                    context.user_location = user_profile.get("location", context.user_location)
                    context.user_timezone = user_profile.get("timezone", context.user_timezone)
                
                # Get recent conversation history - use conversation_id if provided
                if conversation_id:
                    recent_messages = await self.get_conversation_messages(user_id, conversation_id)
                    context.conversation_history = recent_messages[-5:] if recent_messages else []
                else:
                    recent_messages = await self.get_chat_history(user_id, limit=5)
                    context.conversation_history = recent_messages
                
                # Get recent documents and tasks
                recent_docs = await self.firebase_service.get_user_documents(
                    user_id, "documents", limit=5
                )
                context.recent_documents = [doc["id"] for doc in recent_docs]
                
                recent_tasks = await self.firebase_service.get_user_documents(
                    user_id, "tasks", limit=5
                )
                context.recent_tasks = [task["id"] for task in recent_tasks]
            
            return context
            
        except Exception as e:
            print(f"Error getting user context: {e}")
            # Return default context if error
            return AIContext(
                current_time=datetime.now(),
                user_location="Johannesburg, South Africa",
                user_timezone="Africa/Johannesburg"
            )
    
    async def _save_message_history(
        self, 
        user_id: str, 
        user_message: str, 
        ai_response: str, 
        processing_time: float,
        conversation_id: Optional[str] = None
    ):
        """Save conversation to message history with conversation context - FIXED DATETIME"""
        try:
            if not self.firebase_service:
                return
            
            # Generate conversation_id if not provided
            if not conversation_id:
                conversation_id = await self.create_conversation_session(user_id)
            
            # Use timezone-aware UTC timestamp
            timestamp = self._get_utc_now()
            
            # Save user message
            user_msg_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": MessageRole.USER.value,
                "content": user_message,
                "message_type": MessageType.TEXT.value,
                "timestamp": timestamp,
                "processing_time": None,
                "context": {}
            }
            
            await self.firebase_service.create_document("chat_history", user_msg_data)
            
            # Save AI response
            ai_msg_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": MessageRole.ASSISTANT.value,
                "content": ai_response,
                "message_type": MessageType.TEXT.value,
                "timestamp": timestamp,
                "processing_time": processing_time,
                "context": {}
            }
            
            await self.firebase_service.create_document("chat_history", ai_msg_data)
            
            # Update conversation metadata
            await self._update_conversation_metadata(user_id, conversation_id, ai_response)
            
        except Exception as e:
            print(f"Failed to save message history: {e}")
    
    async def _update_conversation_metadata(self, user_id: str, conversation_id: str, last_message: str):
        """Update conversation metadata with last message - FIXED DATETIME"""
        try:
            if not self.firebase_service:
                return
            
            # Generate title from first sentence of last message
            title = "New Chat"
            if last_message:
                sentences = last_message.split('.')
                if sentences and len(sentences[0]) > 10:
                    title = sentences[0][:50] + "..."
                elif len(last_message) > 10:
                    title = last_message[:30] + "..."
            
            # Find and update the conversation
            conversations = await self.firebase_service.query_documents(
                "conversations",
                filters=[
                    ("user_id", "==", user_id),
                    ("conversation_id", "==", conversation_id)
                ]
            )
            
            if conversations:
                conv_id = conversations[0]["id"]
                update_data = {
                    "updated_at": self._get_utc_now(),  # Use timezone-aware datetime
                    "title": title,
                    "message_count": conversations[0].get("message_count", 0) + 2  # +2 for user and AI message
                }
                await self.firebase_service.update_document("conversations", conv_id, update_data)
        
        except Exception as e:
            print(f"Failed to update conversation metadata: {e}")
    
    async def get_chat_history(self, user_id: str, limit: int = 50) -> List[MessageHistory]:
        """Get user's chat history"""
        try:
            if not self.firebase_service:
                return []
            
            messages = await self.firebase_service.query_documents(
                "chat_history",
                filters=[("user_id", "==", user_id)],
                order_by="-timestamp",
                limit=limit
            )
            
            return [MessageHistory(**msg) for msg in messages]
            
        except Exception as e:
            print(f"Failed to get chat history: {e}")
            return []
    
    async def clear_chat_history(self, user_id: str) -> bool:
        """Clear user's chat history"""
        try:
            if not self.firebase_service:
                return False
            
            # Get all user messages
            messages = await self.firebase_service.query_documents(
                "chat_history",
                filters=[("user_id", "==", user_id)]
            )
            
            # Delete all messages
            for msg in messages:
                await self.firebase_service.delete_document("chat_history", msg["id"])
            
            return True
            
        except Exception as e:
            print(f"Failed to clear chat history: {e}")
            return False
    
    async def get_conversation_summary(self, user_id: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Get conversation summary for user"""
        try:
            if conversation_id:
                messages = await self.get_conversation_messages(user_id, conversation_id)
            else:
                messages = await self.get_chat_history(user_id, limit=100)
            
            if not messages:
                return {
                    "total_messages": 0,
                    "last_message_at": None,
                    "topics_discussed": [],
                    "documents_created": 0,
                    "tasks_created": 0
                }
            
            # Analyze messages
            user_messages = [msg for msg in messages if msg.role == MessageRole.USER]
            ai_messages = [msg for msg in messages if msg.role == MessageRole.ASSISTANT]
            
            # Count document and task creations
            documents_created = len([msg for msg in ai_messages if "|||" in msg.content])
            tasks_created = len([msg for msg in ai_messages if msg.message_type == MessageType.TASK_CREATION])
            
            # Extract topics (simplified)
            topics = set()
            for msg in user_messages:
                content = msg.content.lower()
                if "contract" in content:
                    topics.add("contracts")
                if "invoice" in content:
                    topics.add("invoices")
                if "task" in content:
                    topics.add("tasks")
                if "business plan" in content:
                    topics.add("business planning")
                if "help" in content:
                    topics.add("general help")
            
            return {
                "total_messages": len(messages),
                "last_message_at": messages[0].timestamp if messages else None,
                "topics_discussed": list(topics),
                "documents_created": documents_created,
                "tasks_created": tasks_created
            }
            
        except Exception as e:
            print(f"Failed to get conversation summary: {e}")
            return {
                "total_messages": 0,
                "last_message_at": None,
                "topics_discussed": [],
                "documents_created": 0,
                "tasks_created": 0
            }
    
    async def create_conversation_session(self, user_id: str) -> str:
        """Create a new conversation session - FIXED DATETIME"""
        try:
            conversation_id = str(uuid.uuid4())
            now = self._get_utc_now()
            
            session_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
                "title": "New Chat",
                "status": "active"
            }
            
            if self.firebase_service:
                await self.firebase_service.create_document("conversations", session_data)
            
            return conversation_id
        except Exception as e:
            print(f"Failed to create conversation session: {e}")
            return str(uuid.uuid4())
    
    async def get_user_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's conversation list with metadata - FIXED VERSION"""
        try:
            if not self.firebase_service:
                return []
            
            # Get conversations from top-level collection
            conversations = await self.firebase_service.query_documents(
                "conversations",
                filters=[("user_id", "==", user_id)],
                order_by="-updated_at",
                limit=50
            )
            
            print(f"Found {len(conversations)} conversations for user {user_id}")
            
            # Add recent message preview for each conversation
            for conv in conversations:
                try:
                    # Get the most recent message for this conversation
                    recent_messages = await self.firebase_service.query_documents(
                        "chat_history",
                        filters=[
                            ("user_id", "==", user_id),
                            ("conversation_id", "==", conv.get("conversation_id"))
                        ],
                        order_by="-timestamp",
                        limit=1
                    )
                    
                    if recent_messages and len(recent_messages) > 0:
                        last_msg = recent_messages[0]["content"]
                        conv["last_message"] = last_msg[:100] + "..." if len(last_msg) > 100 else last_msg
                        conv["last_message_at"] = recent_messages[0]["timestamp"]
                    else:
                        conv["last_message"] = "Start chatting..."
                        conv["last_message_at"] = conv.get("created_at", datetime.utcnow())
                        
                except Exception as e:
                    print(f"Error getting recent message for conversation {conv.get('conversation_id')}: {e}")
                    conv["last_message"] = "Start chatting..."
                    conv["last_message_at"] = conv.get("created_at", datetime.utcnow())
            
            print(f"Returning {len(conversations)} conversations with message previews")
            return conversations
            
        except Exception as e:
            print(f"Failed to get user conversations: {e}")
            return []
    
    async def get_conversation_messages(self, user_id: str, conversation_id: str) -> List[MessageHistory]:
        """Get messages for a specific conversation - FIXED VERSION"""
        try:
            if not self.firebase_service:
                return []
            
            # Get messages from top-level collection
            messages = await self.firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("conversation_id", "==", conversation_id)
                ],
                order_by="timestamp",  # Ascending order for conversation view
                limit=100
            )
            
            print(f"Found {len(messages)} messages for conversation {conversation_id}")
            
            return [MessageHistory(**msg) for msg in messages]
            
        except Exception as e:
            print(f"Failed to get conversation messages: {e}")
            return []
    
    async def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Delete a conversation and all its messages"""
        try:
            if not self.firebase_service:
                return False
            
            # Delete all messages in the conversation
            messages = await self.firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("conversation_id", "==", conversation_id)
                ]
            )
            
            for msg in messages:
                await self.firebase_service.delete_document("chat_history", msg["id"])
            
            # Delete the conversation metadata
            conversations = await self.firebase_service.query_documents(
                "conversations",
                filters=[
                    ("user_id", "==", user_id),
                    ("conversation_id", "==", conversation_id)
                ]
            )
            
            for conv in conversations:
                await self.firebase_service.delete_document("conversations", conv["id"])
            
            return True
        except Exception as e:
            print(f"Failed to delete conversation: {e}")
            return False
    
    async def get_user_chat_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user's chat statistics - FIXED DATETIME VERSION"""
        try:
            if not self.firebase_service:
                return {"total_conversations": 0, "total_messages": 0, "messages_today": 0}
            
            print(f"Getting chat stats for user: {user_id}")
            
            # Count total conversations from top-level conversations collection
            conversations = await self.firebase_service.query_documents(
                "conversations",
                filters=[("user_id", "==", user_id)]
            )
            total_conversations = len(conversations)
            print(f"Found {total_conversations} conversations")
            
            # Count total messages from top-level chat_history collection
            messages = await self.firebase_service.query_documents(
                "chat_history",
                filters=[("user_id", "==", user_id)]
            )
            total_messages = len(messages)
            print(f"Found {total_messages} total messages")
            
            # Count messages today - FIXED: Use timezone-aware datetime comparison
            today_start = self._get_today_start_utc()
            print(f"Today start (UTC): {today_start}")
            
            messages_today = 0
            for message in messages:
                try:
                    msg_timestamp = message.get("timestamp")
                    if msg_timestamp:
                        # Normalize the message timestamp
                        normalized_timestamp = self._normalize_datetime(msg_timestamp)
                        
                        # Now we can safely compare timezone-aware datetimes
                        if normalized_timestamp >= today_start:
                            messages_today += 1
                except Exception as e:
                    print(f"Error processing message timestamp: {e}")
                    continue
            
            print(f"Found {messages_today} messages today")
            
            # Calculate last chat time
            last_chat_at = None
            if messages:
                try:
                    # Get the most recent message
                    latest_messages = await self.firebase_service.query_documents(
                        "chat_history",
                        filters=[("user_id", "==", user_id)],
                        order_by="-timestamp",
                        limit=1
                    )
                    if latest_messages:
                        last_timestamp = latest_messages[0].get("timestamp")
                        last_chat_at = self._normalize_datetime(last_timestamp)
                except Exception as e:
                    print(f"Error getting last chat time: {e}")
            
            result = {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "messages_today": messages_today,
                "avg_messages_per_conversation": round(total_messages / max(total_conversations, 1), 1),
                "last_chat_at": last_chat_at.isoformat() if last_chat_at else None
            }
            
            print(f"Returning chat stats: {result}")
            return result
            
        except Exception as e:
            print(f"Failed to get chat stats: {e}")
            import traceback
            traceback.print_exc()
            return {
                "total_conversations": 0, 
                "total_messages": 0, 
                "messages_today": 0,
                "avg_messages_per_conversation": 0.0,
                "last_chat_at": None
            }
    
    async def create_conversation_session_indexed(self, user_id: str) -> str:
        """Create conversation session using indexed approach"""
        try:
            conversation_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            session_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
                "title": "New Chat",
                "status": "active"
            }
            
            # Create conversation document and update user index
            doc_id = await self.firebase_service.create_document_with_index(
                collection="conversations",
                data=session_data,
                user_id=user_id,
                index_type="conversation_ids"
            )
            
            return conversation_id
        except Exception as e:
            print(f"Failed to create conversation session: {e}")
            raise e
    
    async def get_user_conversations_indexed(
        self, 
        user_id: str, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user conversations using index - much faster!"""
        try:
            # Get conversations using the user's index
            conversations = await self.firebase_service.get_user_items_by_index(
                uid=user_id,
                collection="conversations",
                index_type="conversation_ids",
                limit=limit,
                offset=offset
            )
            
            # Sort by updated_at (most recent first)
            conversations.sort(key=lambda x: x.get("updated_at", datetime.min), reverse=True)
            
            # Add recent message preview for each conversation
            for conv in conversations:
                try:
                    # Get recent messages for this specific conversation
                    recent_messages = await self.firebase_service.query_documents(
                        "chat_history",
                        filters=[
                            ("user_id", "==", user_id),
                            ("conversation_id", "==", conv.get("conversation_id"))
                        ],
                        order_by="-timestamp",
                        limit=1
                    )
                    
                    if recent_messages:
                        last_msg = recent_messages[0]["content"]
                        conv["last_message"] = last_msg[:100] + "..." if len(last_msg) > 100 else last_msg
                        conv["last_message_at"] = recent_messages[0]["timestamp"]
                    else:
                        conv["last_message"] = "Start chatting..."
                        conv["last_message_at"] = conv.get("created_at", datetime.utcnow())
                        
                except Exception as e:
                    print(f"Error getting recent message: {e}")
                    conv["last_message"] = "Start chatting..."
                    conv["last_message_at"] = conv.get("created_at", datetime.utcnow())
            
            return conversations
            
        except Exception as e:
            print(f"Failed to get user conversations: {e}")
            return []
    
    async def get_user_chat_stats_indexed(self, user_id: str) -> Dict[str, Any]:
        """Get chat stats using user's cached statistics - O(1) operation!"""
        try:
            # Get user document with pre-calculated stats
            user_profile = await self.firebase_service.get_user_profile(user_id)
            
            if not user_profile or "stats" not in user_profile:
                # Initialize if missing
                await self.firebase_service.initialize_user_indexes(user_id)
                return {
                    "total_conversations": 0,
                    "total_messages": 0,
                    "messages_today": 0,
                    "avg_messages_per_conversation": 0.0,
                    "last_chat_at": None
                }
            
            stats = user_profile["stats"]
            
            # Calculate messages today (this is the only dynamic calculation needed)
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            messages_today = 0
            
            # You could also cache this in a separate field updated by a background job
            try:
                today_messages = await self.firebase_service.query_documents(
                    "chat_history",
                    filters=[
                        ("user_id", "==", user_id),
                        ("timestamp", ">=", today_start)
                    ]
                )
                messages_today = len(today_messages)
                
                # Update the cached value
                await self.firebase_service.update_user_stats(user_id, {
                    "messages_today": messages_today,
                    "last_activity": datetime.utcnow()
                })
                
            except Exception as e:
                print(f"Could not calculate today's messages: {e}")
                messages_today = stats.get("messages_today", 0)
            
            total_conversations = stats.get("total_conversations", 0)
            total_messages = stats.get("total_messages", 0)
            
            return {
                "total_conversations": total_conversations,
                "total_messages": total_messages, 
                "messages_today": messages_today,
                "avg_messages_per_conversation": (
                    total_messages / total_conversations if total_conversations > 0 else 0.0
                ),
                "last_chat_at": stats.get("last_message_at")
            }
            
        except Exception as e:
            print(f"Failed to get chat stats: {e}")
            return {
                "total_conversations": 0,
                "total_messages": 0,
                "messages_today": 0,
                "avg_messages_per_conversation": 0.0,
                "last_chat_at": None
            }
    
    async def delete_conversation_indexed(self, user_id: str, conversation_id: str) -> bool:
        """Delete conversation and update indexes"""
        try:
            # Find the conversation document
            conversations = await self.firebase_service.query_documents(
                "conversations",
                filters=[
                    ("user_id", "==", user_id),
                    ("conversation_id", "==", conversation_id)
                ]
            )
            
            if not conversations:
                return False
            
            conv_doc_id = conversations[0]["id"]
            
            # Delete all messages in the conversation
            messages = await self.firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("conversation_id", "==", conversation_id)
                ]
            )
            
            # Delete messages (could batch this)
            for msg in messages:
                await self.firebase_service.delete_document("chat_history", msg["id"])
            
            # Delete conversation document and update index
            success = await self.firebase_service.delete_document_with_index(
                collection="conversations",
                doc_id=conv_doc_id,
                user_id=user_id,
                index_type="conversation_ids"
            )
            
            # Update message count stat
            if success:
                current_stats = await self.firebase_service.get_user_profile(user_id)
                current_total = current_stats.get("stats", {}).get("total_messages", 0)
                new_total = max(0, current_total - len(messages))
                
                await self.firebase_service.update_user_stats(user_id, {
                    "total_messages": new_total
                })
            
            return success
            
        except Exception as e:
            print(f"Failed to delete conversation: {e}")
            return False

class SmartDocumentDecisionMixin:
    """Mixin for intelligent document creation decisions"""
    
    # Document creation keywords that are strong indicators
    STRONG_DOCUMENT_INDICATORS = [
        "create a document", "make a document", "generate a document",
        "write a contract", "create a contract", "draft a contract",
        "create an invoice", "generate an invoice", "make an invoice",
        "write a business plan", "create a business plan",
        "draft an nda", "create an nda", "make an nda",
        "write a proposal", "create a proposal", "draft a proposal",
        "create a template", "make a template", "generate a template",
        "write a policy", "create a policy", "draft a policy"
    ]
    
    # Weak indicators that need context analysis
    WEAK_DOCUMENT_INDICATORS = [
        "create", "make", "write", "draft", "generate", "prepare"
    ]
    
    # Words that indicate it's NOT a document request
    NON_DOCUMENT_CONTEXT = [
        "task", "reminder", "appointment", "meeting", "calendar", "event",
        "explain", "how to", "what is", "tell me", "help me understand",
        "advice", "recommend", "suggest", "opinion", "think", "question"
    ]
    
    # Document types and their keywords
    DOCUMENT_TYPES = {
        "contract": ["contract", "agreement", "terms", "conditions"],
        "invoice": ["invoice", "bill", "payment", "charge", "cost"],
        "business_plan": ["business plan", "strategy", "market analysis"],
        "nda": ["nda", "non-disclosure", "confidentiality"],
        "proposal": ["proposal", "pitch", "offer", "quotation"],
        "template": ["template", "format", "layout"],
        "policy": ["policy", "procedure", "guideline", "rule"],
        "moi": ["moi", "memorandum of incorporation", "articles"]
    }

    def should_create_document(self, user_message: str) -> Tuple[bool, str]:
        """
        Intelligently decide if the user wants a document created
        Returns: (should_create, document_type)
        """
        message_lower = user_message.lower()
        
        # 1. Check for strong document indicators (high confidence)
        for indicator in self.STRONG_DOCUMENT_INDICATORS:
            if indicator in message_lower:
                doc_type = self._extract_document_type(message_lower)
                return True, doc_type
        
        # 2. Check for non-document context (immediate no)
        if any(context in message_lower for context in self.NON_DOCUMENT_CONTEXT):
            return False, ""
        
        # 3. Analyze weak indicators with context
        has_weak_indicator = any(word in message_lower for word in self.WEAK_DOCUMENT_INDICATORS)
        
        if has_weak_indicator:
            # Check if it's asking for document creation specifically
            doc_keywords = ["document", "contract", "invoice", "template", "policy", 
                          "business plan", "proposal", "nda", "agreement", "moi"]
            
            has_doc_keyword = any(keyword in message_lower for keyword in doc_keywords)
            
            if has_doc_keyword:
                doc_type = self._extract_document_type(message_lower)
                return True, doc_type
        
        # 4. Check for implicit document requests
        if self._is_implicit_document_request(message_lower):
            doc_type = self._extract_document_type(message_lower)
            return True, doc_type
        
        return False, ""
    
    def _extract_document_type(self, message_lower: str) -> str:
        """Extract the specific document type from the message"""
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            if any(keyword in message_lower for keyword in keywords):
                return doc_type
        return "template"  # Default type
    
    def _is_implicit_document_request(self, message_lower: str) -> bool:
        """Check for implicit document requests"""
        implicit_patterns = [
            r"i need a .* (contract|invoice|template|policy)",
            r"can you .* (contract|invoice|template|policy)",
            r"help me with .* (contract|invoice|template|policy)",
            r"(contract|invoice|template|policy) for",
        ]
        
        return any(re.search(pattern, message_lower) for pattern in implicit_patterns)

# Enhanced AI Service with smart decision making
class EnhancedAIService(AIService, SmartDocumentDecisionMixin):
    """Enhanced AI Service with intelligent document creation"""
    
    async def process_message(self, message: ChatMessage, user_id: str, conversation_id: Optional[str] = None) -> EnhancedChatResponse:
        """Process user message with smart document creation decisions"""
        try:
            start_time = time.time()
            
            # Create conversation if not provided
            if not conversation_id:
                conversation_id = await self.create_conversation_session(user_id)
            
            # SMART DECISION: Should we create a document?
            should_create_doc, doc_type = self.should_create_document(message.content)
            
            # Get user context with conversation history
            context = await self._get_user_context(user_id, conversation_id)
            
            # Build prompt with context and document creation instructions
            system_prompt = self._build_enhanced_system_prompt(context, should_create_doc, doc_type)
            full_prompt = f"{system_prompt}\n\nUser message: {message.content}"
            
            # Generate AI response
            if self.model:
                response = await self._generate_ai_response(full_prompt)
            else:
                response = await self._generate_enhanced_mock_response(
                    message.content, should_create_doc, doc_type
                )
            
            processing_time = time.time() - start_time
            
            # Parse response for special actions
            parsed_response = self._parse_ai_response(response)
            
            # Override document creation based on smart decision
            if not should_create_doc:
                parsed_response["document_created"] = False
                parsed_response["document_title"] = None
                parsed_response["document_content"] = None
                parsed_response["message_type"] = "text"
            
            # Save message history
            if self.firebase_service:
                await self._save_message_history(
                    user_id, message.content, response, processing_time, conversation_id
                )
            
            return EnhancedChatResponse(
                content=parsed_response["content"],
                message_type=MessageType(parsed_response.get("message_type", "text")),
                document_created=parsed_response.get("document_created", False),
                document_title=parsed_response.get("document_title"),
                document_content=parsed_response.get("document_content"),
                document_type=parsed_response.get("document_type"),
                task_created=parsed_response.get("task_created", False),
                task_data=parsed_response.get("task_data"),
                calendar_event_created=parsed_response.get("calendar_event_created", False),
                event_data=parsed_response.get("event_data"),
                processing_time=processing_time,
                tokens_used=parsed_response.get("tokens_used"),
                confidence_score=parsed_response.get("confidence_score", 0.9),
                conversation_id=conversation_id
            )
            
        except Exception as e:
            print(f"Error in enhanced process_message: {e}")
            return EnhancedChatResponse(
                content=f"I apologize, but I'm having trouble processing your request right now. Error: {str(e)}",
                message_type=MessageType.TEXT,
                processing_time=time.time() - start_time if 'start_time' in locals() else 0,
                conversation_id=conversation_id
            )
    
    def _build_enhanced_system_prompt(self, context: AIContext, should_create_doc: bool, doc_type: str) -> str:
        """Build enhanced system prompt with document creation logic"""
        current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p SAST")
        
        base_prompt = f"""You are "Betty", an expert AI business assistant for South African businesses.

**CURRENT CONTEXT:**
- Time: {current_time}  
- User Location: {context.user_location}
- User Timezone: {context.user_timezone}

**SMART DOCUMENT CREATION:**"""
        
        if should_create_doc:
            base_prompt += f"""
DOCUMENT CREATION REQUIRED: YES - {doc_type.upper()}
When responding, you MUST use this format:
1. User-facing confirmation message
2. '|||' separator  
3. Complete {doc_type} document content

Example: "I'll create a {doc_type} for you.|||**{doc_type.title()}**\n\n[Full document content]"
"""
        else:
            base_prompt += """
DOCUMENT CREATION REQUIRED: NO
Provide a helpful response without creating any documents. Do NOT use the '|||' separator.
Focus on answering the user's question or providing advice.
"""
        
        base_prompt += f"""

**YOUR CAPABILITIES:**
- Business advice and strategy
- South African business law guidance
- Task and project management  
- Financial planning and analysis
- Only create documents when explicitly requested

**COMMUNICATION STYLE:**
- Professional but friendly
- Practical and actionable advice
- Consider South African business context

**RECENT CONTEXT:**
- Recent documents: {len(context.recent_documents)}
- Recent tasks: {len(context.recent_tasks)}
- Conversation history: {len(context.conversation_history)} messages"""

        return base_prompt
    
    async def _generate_enhanced_mock_response(self, user_message: str, should_create_doc: bool, doc_type: str) -> str:
        """Generate enhanced mock response with smart document creation"""
        user_message = user_message.lower()
        
        if should_create_doc:
            return self._create_mock_document(doc_type, user_message)
        
        # Non-document responses
        if "help" in user_message or "what can you do" in user_message:
            return """Hello! I'm Betty, your AI business assistant. I can help you with:

📝 **Document Creation**: Create contracts, invoices, business plans, NDAs (when you specifically request them)
📋 **Task Management**: Help organize your tasks and projects
📅 **Business Planning**: Strategic advice and planning
📊 **Analysis**: Business insights and recommendations
🔍 **Information**: Answer questions and provide guidance
💡 **Advice**: South African business context and best practices

What would you like assistance with today?"""
        
        elif any(word in user_message for word in ["advice", "recommend", "suggest", "help"]):
            return "I'd be happy to help! Could you provide more details about what specific advice or assistance you're looking for? I can help with business strategy, planning, South African regulations, or general business guidance."
        
        elif any(word in user_message for word in ["task", "remind", "todo"]):
            return "I can help you organize tasks and reminders. What specific task would you like help with? I can assist with planning, prioritization, or breaking down complex projects."
        
        else:
            return f"Thank you for your message. As your AI business assistant, I'm here to help with business advice, planning, and document creation when needed. How can I assist you today?"
    
    def _create_mock_document(self, doc_type: str, user_message: str) -> str:
        """Create mock document based on type"""
        templates = {
            "contract": f"I'll create a service contract template for you.|||**Service Contract Template**\n\n**PARTIES:**\nService Provider: [Your Company Name]\nClient: [Client Name]\n\n**SERVICES:**\n[Description of services to be provided]\n\n**TERMS:**\n- Duration: [Contract duration]\n- Payment: [Payment terms]\n- Cancellation: [Cancellation policy]\n\n**SIGNATURES:**\n\nService Provider: ___________________ Date: ___________\nClient: ___________________ Date: ___________",
            
            "invoice": f"I'll create an invoice template for you.|||**Invoice Template**\n\n**INVOICE #:** [Invoice Number]\n**DATE:** {datetime.now().strftime('%Y-%m-%d')}\n\n**FROM:**\n[Your Company Name]\n[Address]\n[Contact Details]\n\n**TO:**\n[Client Name]\n[Client Address]\n\n**SERVICES:**\n| Description | Quantity | Rate | Amount |\n|-------------|----------|------|--------|\n| [Service 1] | 1 | R[Rate] | R[Amount] |\n\n**TOTAL:** R[Total Amount]\n\n**PAYMENT TERMS:** [Payment terms]",
            
            "business_plan": f"I'll create a business plan outline for you.|||**Business Plan Template**\n\n**1. EXECUTIVE SUMMARY**\n[Brief overview of your business]\n\n**2. COMPANY DESCRIPTION**\n[Detailed business description]\n\n**3. MARKET ANALYSIS**\n[Target market and competition analysis]\n\n**4. ORGANIZATION & MANAGEMENT**\n[Company structure and team]\n\n**5. SERVICE/PRODUCT LINE**\n[What you're offering]\n\n**6. MARKETING & SALES**\n[Marketing strategy]\n\n**7. FINANCIAL PROJECTIONS**\n[Revenue and expense forecasts]"
        }
        
        return templates.get(doc_type, templates["contract"])