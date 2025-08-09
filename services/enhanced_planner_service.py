# services/enhanced_planner_service.py - COMPLETE WITH MISSING METHODS

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta, timezone
from models.planner_models import (
    TaskCreate, TaskResponse, TaskUpdate, TaskStatus, TaskPriority,
    NoteCreate, NoteResponse, NoteUpdate, NoteType,
    CalendarEvent, CalendarEventCreate, EventType,
    PlannerDashboard, PlannerStats, TaskFilter
)
from services.firebase_service import FirebaseService
from services.google_service import GoogleService
import uuid

class EnhancedPlannerService:
    """Enhanced service for planner operations with Google integration"""
    
    def __init__(self, firebase_service: FirebaseService, google_service: GoogleService):
        self.firebase_service = firebase_service
        self.google_service = google_service
    
    # ========================================================================
    # TASK OPERATIONS - COMPLETE IMPLEMENTATION
    # ========================================================================
    
    async def create_task(self, task: TaskCreate, user_id: str) -> TaskResponse:
        """Create a new task with optional calendar event"""
        try:
            task_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": task.title,
                "description": task.description or "",
                "priority": task.priority.value if task.priority else TaskPriority.MEDIUM.value,
                "status": TaskStatus.TODO.value,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "tags": task.tags or [],
                "metadata": task.metadata or {},
                "completed_at": None,
                "calendar_event_id": None,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Create task in Firebase
            task_id = await self.firebase_service.create_document("tasks", task_data)
            task_data["id"] = task_id
            
            # If task has due date and user wants calendar sync, create calendar event
            if task.due_date and getattr(task, 'sync_to_calendar', False):
                try:
                    calendar_event = await self.create_calendar_event_for_task(
                        user_id, task_data
                    )
                    task_data["calendar_event_id"] = calendar_event.get("id")
                    await self.firebase_service.update_document("tasks", task_id, {
                        "calendar_event_id": task_data["calendar_event_id"]
                    })
                except Exception as e:
                    print(f"⚠️ Failed to create calendar event for task {task_id}: {e}")
            
            return TaskResponse(**task_data)
            
        except Exception as e:
            raise Exception(f"Failed to create task: {e}")
    
    # ✅ ADD MISSING get_task METHOD
    async def get_task(self, task_id: str, user_id: str) -> TaskResponse:
        """Get a single task by ID"""
        try:
            task_doc = await self.firebase_service.get_document("tasks", task_id)
            
            if not task_doc:
                raise ValueError(f"Task {task_id} not found")
            
            if task_doc.get("user_id") != user_id:
                raise ValueError(f"Task {task_id} not found")
            
            return TaskResponse(**task_doc)
            
        except ValueError:
            raise
        except Exception as e:
            raise Exception(f"Failed to get task: {e}")
    
    async def get_tasks(
        self, 
        user_id: str, 
        task_filter: Optional[TaskFilter] = None,
        completed: Optional[bool] = None,
        limit: int = 50
    ) -> List[TaskResponse]:
        """Get user tasks with filtering"""
        try:
            # Build query constraints
            constraints = [("user_id", "==", user_id)]
            
            # Apply filters
            if task_filter:
                if task_filter.status:
                    status_values = [status.value for status in task_filter.status]
                    constraints.append(("status", "in", status_values))
                
                if task_filter.priority:
                    priority_values = [priority.value for priority in task_filter.priority]
                    constraints.append(("priority", "in", priority_values))
            
            # Apply completed filter
            if completed is not None:
                if completed:
                    constraints.append(("status", "==", TaskStatus.COMPLETED.value))
                else:
                    constraints.append(("status", "!=", TaskStatus.COMPLETED.value))
            
            # Get tasks from Firebase
            tasks_data = await self.firebase_service.query_documents(
                "tasks", constraints, limit=limit, order_by="created_at"
            )
            
            tasks = [TaskResponse(**task) for task in tasks_data]
            
            # Apply additional filters that can't be done in Firebase query
            if task_filter:
                if task_filter.due_date_from or task_filter.due_date_to:
                    filtered_tasks = []
                    for task in tasks:
                        if task.due_date:
                            try:
                                if isinstance(task.due_date, str):
                                    task_due = datetime.fromisoformat(task.due_date).date()
                                else:
                                    task_due = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
                                
                                include_task = True
                                if task_filter.due_date_from and task_due < task_filter.due_date_from:
                                    include_task = False
                                if task_filter.due_date_to and task_due > task_filter.due_date_to:
                                    include_task = False
                                
                                if include_task:
                                    filtered_tasks.append(task)
                            except (ValueError, AttributeError):
                                continue
                    tasks = filtered_tasks
                
                if task_filter.search_term:
                    search_term = task_filter.search.lower()
                    tasks = [
                        task for task in tasks 
                        if search_term in task.title.lower() or 
                           (task.description and search_term in task.description.lower())
                    ]
            
            return tasks
            
        except Exception as e:
            raise Exception(f"Failed to get tasks: {e}")
    
    async def update_task(self, task_id: str, task_update: TaskUpdate, user_id: str) -> TaskResponse:
        """Update an existing task"""
        try:
            # Get current task first
            current_task = await self.get_task(task_id, user_id)
            
            # Prepare update data
            update_data = {
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Update fields if provided
            if task_update.title is not None:
                update_data["title"] = task_update.title
            if task_update.description is not None:
                update_data["description"] = task_update.description
            if task_update.priority is not None:
                update_data["priority"] = task_update.priority.value
            if task_update.status is not None:
                update_data["status"] = task_update.status.value
                
                # Set completed_at when marking as completed
                if task_update.status == TaskStatus.COMPLETED:
                    update_data["completed_at"] = datetime.utcnow().isoformat()
                elif current_task.status == TaskStatus.COMPLETED:
                    # Clearing completion
                    update_data["completed_at"] = None
            
            if task_update.due_date is not None:
                update_data["due_date"] = task_update.due_date.isoformat() if task_update.due_date else None
            if task_update.tags is not None:
                update_data["tags"] = task_update.tags
            if task_update.metadata is not None:
                update_data["metadata"] = task_update.metadata
            
            # Update task in Firebase
            await self.firebase_service.update_document("tasks", task_id, update_data)
            
            # Update calendar event if task has one
            if current_task.calendar_event_id and (task_update.title or task_update.due_date):
                try:
                    await self.update_calendar_event_for_task(
                        user_id, task_id, current_task.calendar_event_id, update_data
                    )
                except Exception as e:
                    print(f"⚠️ Failed to update calendar event: {e}")
            
            # Return updated task
            return await self.get_task(task_id, user_id)
            
        except ValueError:
            raise
        except Exception as e:
            raise Exception(f"Failed to update task: {e}")
    
    async def delete_task(self, task_id: str, user_id: str) -> bool:
        """Delete a task and its associated calendar event"""
        try:
            # Get task first to check calendar event
            task = await self.get_task(task_id, user_id)
            
            # Delete calendar event if it exists
            if task.calendar_event_id:
                try:
                    await self.google_service.delete_calendar_event(user_id, task.calendar_event_id)
                except Exception as e:
                    print(f"⚠️ Failed to delete calendar event: {e}")
            
            # Delete task from Firebase
            await self.firebase_service.delete_document("tasks", task_id)
            return True
            
        except ValueError:
            raise
        except Exception as e:
            raise Exception(f"Failed to delete task: {e}")
    
    # ========================================================================
    # CALENDAR INTEGRATION - FIXED
    # ========================================================================
    
    async def create_calendar_event_for_task(
        self, user_id: str, task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create Google Calendar event for task with proper date handling"""
        try:
            # Check if user has Google connected
            user_profile = await self.firebase_service.get_user_profile(user_id)
            if not user_profile or not user_profile.get("google_connected"):
                raise ValueError("Google account not connected")
            
            # Handle due_date properly
            due_date_input = task_data.get("due_date")
            if not due_date_input:
                raise ValueError("Task must have a due_date to create calendar event")
            
            # Parse due_date
            if isinstance(due_date_input, str):
                try:
                    due_date = datetime.fromisoformat(due_date_input.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    try:
                        due_date = datetime.strptime(due_date_input, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        due_date = datetime.strptime(due_date_input, "%Y-%m-%d")
            elif isinstance(due_date_input, datetime):
                due_date = due_date_input
            else:
                raise ValueError(f"Invalid due_date format: {due_date_input}")
            
            # Ensure timezone awareness
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=timezone.utc)
            
            # Get user timezone
            user_timezone = user_profile.get("timezone", "UTC")
            
            # Prepare event data
            event_data = {
                "summary": f"📋 {task_data['title']}",
                "description": f"Task: {task_data.get('description', '')}\n\nCreated from Planner App",
                "start": {
                    "dateTime": due_date.isoformat(),
                    "timeZone": user_timezone
                },
                "end": {
                    "dateTime": (due_date + timedelta(hours=1)).isoformat(),
                    "timeZone": user_timezone
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email", "minutes": 24 * 60},
                        {"method": "popup", "minutes": 30}
                    ]
                }
            }
            
            return await self.google_service.create_calendar_event(user_id, event_data)
            
        except Exception as e:
            raise Exception(f"Failed to create calendar event for task: {e}")
    
    async def update_calendar_event_for_task(
        self, user_id: str, task_id: str, event_id: str, task_update: Dict
    ) -> Dict:
        """Update Google Calendar event for task"""
        try:
            event_update = {}
            
            if "title" in task_update:
                event_update["summary"] = f"📋 {task_update['title']}"
            
            if "due_date" in task_update:
                due_date_input = task_update["due_date"]
                
                if isinstance(due_date_input, str):
                    try:
                        due_date = datetime.fromisoformat(due_date_input.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        try:
                            due_date = datetime.strptime(due_date_input, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            due_date = datetime.strptime(due_date_input, "%Y-%m-%d")
                elif isinstance(due_date_input, datetime):
                    due_date = due_date_input
                else:
                    raise ValueError(f"Invalid due_date format: {due_date_input}")
                
                if due_date.tzinfo is None:
                    due_date = due_date.replace(tzinfo=timezone.utc)
                
                user_profile = await self.firebase_service.get_user_profile(user_id)
                timezone_str = user_profile.get("timezone", "UTC")
                
                event_update["start"] = {
                    "dateTime": due_date.isoformat(),
                    "timeZone": timezone_str
                }
                event_update["end"] = {
                    "dateTime": (due_date + timedelta(hours=1)).isoformat(),
                    "timeZone": timezone_str
                }
            
            if "status" in task_update:
                if task_update["status"] == TaskStatus.COMPLETED.value:
                    event_update["summary"] = f"✅ {event_update.get('summary', 'Task')}"
            
            return await self.google_service.update_calendar_event(
                user_id, event_id, event_update
            )
            
        except Exception as e:
            raise Exception(f"Failed to update calendar event for task: {e}")
    
    async def sync_calendar_tasks(self, user_id: str, start_date, end_date) -> Dict:
        """Sync tasks with Google Calendar events"""
        try:
            print(f"🔄 Starting calendar sync for user {user_id}")
            
            # Check if user has Google credentials
            has_credentials = await self.google_service._check_google_credentials(user_id)
            if not has_credentials:
                return {
                    "synced_events": 0,
                    "calendar_events": [],
                    "tasks_synced": 0,
                    "message": "Google account not connected"
                }
            
            # Convert dates to strings
            if hasattr(start_date, 'isoformat'):
                start_date_str = start_date.isoformat()
            else:
                start_date_str = str(start_date)
                
            if hasattr(end_date, 'isoformat'):
                end_date_str = end_date.isoformat()
            else:
                end_date_str = str(end_date)
            
            # Get calendar events from Google
            calendar_events = await self.google_service.get_calendar_events(
                user_id, start_date_str, end_date_str
            )
            
            # Get existing tasks in date range
            tasks = await self.get_tasks(user_id, limit=1000)
            
            # Filter tasks that need calendar events
            tasks_without_events = []
            for task in tasks:
                if (task.due_date and 
                    not hasattr(task, 'calendar_event_id') or not task.calendar_event_id):
                    
                    try:
                        if isinstance(task.due_date, str):
                            task_due = datetime.fromisoformat(task.due_date.replace('Z', '+00:00'))
                        else:
                            task_due = task.due_date
                            
                        if isinstance(start_date, str):
                            range_start = datetime.fromisoformat(start_date)
                        else:
                            range_start = datetime.combine(start_date, datetime.min.time())
                            
                        if isinstance(end_date, str):
                            range_end = datetime.fromisoformat(end_date)
                        else:
                            range_end = datetime.combine(end_date, datetime.max.time())
                        
                        # Ensure timezone awareness
                        if task_due.tzinfo is None:
                            task_due = task_due.replace(tzinfo=timezone.utc)
                        if range_start.tzinfo is None:
                            range_start = range_start.replace(tzinfo=timezone.utc)
                        if range_end.tzinfo is None:
                            range_end = range_end.replace(tzinfo=timezone.utc)
                            
                        if range_start <= task_due <= range_end:
                            tasks_without_events.append(task)
                            
                    except Exception as e:
                        print(f"⚠️ Error checking task date range for task {task.id}: {e}")
                        continue
            
            created_events = []
            for task in tasks_without_events:
                try:
                    event = await self.create_calendar_event_for_task(
                        user_id, task.dict()
                    )
                    created_events.append(event)
                    
                    # Update task with calendar event ID
                    await self.firebase_service.update_document("tasks", task.id, {
                        "calendar_event_id": event.get("id") or event.get("google_event_id")
                    })
                    print(f"✅ Created calendar event for task {task.id}")
                    
                except Exception as e:
                    print(f"Failed to create event for task {task.id}: {e}")
                    continue
            
            return {
                "synced_events": len(created_events),
                "calendar_events": calendar_events,
                "tasks_synced": len(tasks_without_events),
                "message": f"Successfully synced {len(created_events)} tasks to calendar"
            }
            
        except Exception as e:
            error_message = f"Failed to sync calendar tasks: {e}"
            print(f"❌ {error_message}")
            return {
                "synced_events": 0,
                "calendar_events": [],
                "tasks_synced": 0,
                "error": error_message
            }
    
    # ========================================================================
    # NOTES OPERATIONS
    # ========================================================================
    
    async def create_note(self, note: NoteCreate, user_id: str) -> NoteResponse:
        """Create a new note"""
        try:
            note_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": note.title,
                "content": note.content,
                "note_type": note.note_type.value if note.note_type else NoteType.GENERAL.value,
                "tags": note.tags or [],
                "metadata": note.metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            note_id = await self.firebase_service.create_document("notes", note_data)
            note_data["id"] = note_id
            
            return NoteResponse(**note_data)
            
        except Exception as e:
            raise Exception(f"Failed to create note: {e}")
    
    async def get_notes(self, user_id: str, limit: int = 20) -> List[NoteResponse]:
        """Get user notes"""
        try:
            constraints = [("user_id", "==", user_id)]
            notes_data = await self.firebase_service.query_documents(
                "notes", constraints, limit=limit, order_by="created_at"
            )
            
            return [NoteResponse(**note) for note in notes_data]
            
        except Exception as e:
            raise Exception(f"Failed to get notes: {e}")
    
    # ========================================================================
    # DASHBOARD AND ANALYTICS
    # ========================================================================
    
    async def get_planner_dashboard(self, user_id: str) -> PlannerDashboard:
        """Get planner dashboard with stats and upcoming items"""
        try:
            # Get all tasks for stats
            all_tasks = await self.get_tasks(user_id, limit=1000)
            
            # Calculate stats
            completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
            pending_tasks = [t for t in all_tasks if t.status != TaskStatus.COMPLETED]
            
            # Calculate overdue tasks
            overdue_tasks = []
            today = date.today()
            for task in pending_tasks:
                if task.due_date:
                    try:
                        if isinstance(task.due_date, str):
                            task_due_date = datetime.fromisoformat(task.due_date).date()
                        else:
                            task_due_date = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
                        
                        if task_due_date < today:
                            overdue_tasks.append(task)
                    except (ValueError, AttributeError) as e:
                        print(f"Error parsing due date for task {task.id}: {e}")
                        continue
            
            # Get upcoming tasks
            upcoming_end = today + timedelta(days=7)
            upcoming_task_filter = TaskFilter(
                due_date_from=today,
                due_date_to=upcoming_end,
                status=[TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            )
            upcoming_tasks = await self.get_tasks(user_id, task_filter=upcoming_task_filter)
            
            # Get recent notes
            try:
                recent_notes = await self.get_notes(user_id, limit=5)
            except Exception as e:
                print(f"Error getting notes: {e}")
                recent_notes = []
            
            # ✅ GET CALENDAR EVENTS - Fixed implementation
            calendar_events = []
            try:
                # Check if user has Google credentials
                has_credentials = await self.google_service._check_google_credentials(user_id)
                if has_credentials:
                    calendar_events = await self.google_service.get_calendar_events(
                        user_id, 
                        today.isoformat(), 
                        upcoming_end.isoformat()
                    )
                    print(f"✅ Retrieved {len(calendar_events)} calendar events for dashboard")
                else:
                    print("⚠️ No Google credentials, skipping calendar events")
            except Exception as e:
                print(f"❌ Error getting calendar events for dashboard: {e}")
            
            # Build stats
            completion_rate = (len(completed_tasks) / len(all_tasks) * 100) if all_tasks else 0
            
            stats = PlannerStats(
                total_tasks=len(all_tasks),
                completed_tasks=len(completed_tasks),
                pending_tasks=len(pending_tasks),
                overdue_tasks=len(overdue_tasks),
                completion_rate=round(completion_rate, 1),
                total_notes=len(recent_notes)
            )
            
            return PlannerDashboard(
                stats=stats,
                upcoming_tasks=upcoming_tasks[:10],  # Limit to 10
                recent_notes=recent_notes,
                calendar_events=calendar_events,  # ✅ Now properly populated
                overdue_tasks=overdue_tasks[:5]   # Limit to 5
            )
            
        except Exception as e:
            print(f"❌ Error getting planner dashboard: {e}")
            # Return safe defaults
            return PlannerDashboard(
                stats=PlannerStats(
                    total_tasks=0,
                    completed_tasks=0,
                    pending_tasks=0,
                    overdue_tasks=0,
                    completion_rate=0,
                    total_notes=0
                ),
                upcoming_tasks=[],
                recent_notes=[],
                calendar_events=[],
                overdue_tasks=[]
            )