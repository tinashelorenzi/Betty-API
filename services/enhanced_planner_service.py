# services/enhanced_planner_service.py
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from models.planner_models import (
    TaskCreate, TaskResponse, TaskUpdate, TaskStatus, TaskPriority,
    NoteCreate, NoteResponse, NoteUpdate, NoteType,
    CalendarEvent, CalendarEventCreate, EventType,
    MeetingRecording, RecordingCreate, RecordingUpdate, RecordingStatus,
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
    # TASK OPERATIONS WITH CALENDAR SYNC
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
            if task.due_date and task.sync_to_calendar:
                try:
                    calendar_event = await self.create_calendar_event_for_task(
                        user_id, task_data
                    )
                    task_data["calendar_event_id"] = calendar_event.get("id")
                    await self.firebase_service.update_document("tasks", task_id, {
                        "calendar_event_id": calendar_event.get("id")
                    })
                except Exception as e:
                    print(f"Failed to sync task to calendar: {e}")
            
            return TaskResponse(**task_data)
            
        except Exception as e:
            raise Exception(f"Failed to create task: {e}")
    
    async def update_task(self, task_id: str, task_update: TaskUpdate, user_id: str) -> TaskResponse:
        """Update task with calendar sync"""
        try:
            # Verify ownership
            if not await self.firebase_service.verify_document_ownership("tasks", task_id, user_id):
                raise ValueError("Task not found or access denied")
            
            current_task = await self.firebase_service.get_document("tasks", task_id)
            
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
                if task_update.status == TaskStatus.COMPLETED:
                    update_data["completed_at"] = datetime.utcnow().isoformat()
                elif current_task.get("completed_at"):
                    update_data["completed_at"] = None
            if task_update.due_date is not None:
                update_data["due_date"] = task_update.due_date.isoformat()
            if task_update.tags is not None:
                update_data["tags"] = task_update.tags
            
            # Update task in Firebase
            await self.firebase_service.update_document("tasks", task_id, update_data)
            
            # Sync to calendar if needed
            if current_task.get("calendar_event_id") and (
                task_update.title or task_update.due_date or task_update.status
            ):
                await self.update_calendar_event_for_task(
                    user_id, task_id, current_task["calendar_event_id"], update_data
                )
            
            # Get updated task
            updated_task = await self.firebase_service.get_document("tasks", task_id)
            return TaskResponse(**updated_task)
            
        except Exception as e:
            raise Exception(f"Failed to update task: {e}")
    
    async def get_tasks(
    self, 
    user_id: str, 
    task_filter: Optional[TaskFilter] = None,  # ✅ Add this parameter
    completed: Optional[bool] = None,
    priority: Optional[TaskPriority] = None,
    due_date_range: Optional[tuple] = None,
    limit: Optional[int] = None
) -> List[TaskResponse]:
        """Get user tasks with filters"""
        try:
            filters = [("user_id", "==", user_id)]
            
            # Handle TaskFilter object if provided
            if task_filter:
                if task_filter.status:
                    # Convert status list to values
                    status_values = [status.value if hasattr(status, 'value') else status for status in task_filter.status]
                    if len(status_values) == 1:
                        filters.append(("status", "==", status_values[0]))
                    else:
                        filters.append(("status", "in", status_values))
                
                if task_filter.priority:
                    # Convert priority list to values
                    priority_values = [priority.value if hasattr(priority, 'value') else priority for priority in task_filter.priority]
                    if len(priority_values) == 1:
                        filters.append(("priority", "==", priority_values[0]))
                    else:
                        filters.append(("priority", "in", priority_values))
                
                # Handle date filtering from TaskFilter
                if task_filter.due_date_from and task_filter.due_date_to:
                    due_date_range = (task_filter.due_date_from, task_filter.due_date_to)
            
            # Legacy parameter handling (for backward compatibility)
            if completed is not None:
                if completed:
                    filters.append(("status", "==", TaskStatus.COMPLETED.value))
                else:
                    filters.append(("status", "in", [TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]))
            
            if priority:
                filters.append(("priority", "==", priority.value))
            
            # Order by created_at descending
            tasks = await self.firebase_service.query_documents(
                "tasks", 
                filters, 
                order_by=[("created_at", "desc")],
                limit=limit
            )
            
            # Filter by due date range if provided
            if due_date_range:
                start_date, end_date = due_date_range
                filtered_tasks = []
                for task in tasks:
                    if task.get("due_date"):
                        try:
                            task_due_date = datetime.fromisoformat(task["due_date"]).date()
                            if start_date <= task_due_date <= end_date:
                                filtered_tasks.append(task)
                        except ValueError:
                            # Skip tasks with invalid dates
                            continue
                    elif not task.get("due_date") and not due_date_range:
                        # Include tasks without due dates when no date filter is applied
                        filtered_tasks.append(task)
                tasks = filtered_tasks
            
            return [TaskResponse(**task) for task in tasks]
            
        except Exception as e:
            print(f"Error in get_tasks: {e}")  # Add logging
            raise Exception(f"Failed to get tasks: {e}")
    
    async def delete_task(self, task_id: str, user_id: str) -> bool:
        """Delete task and associated calendar event"""
        try:
            # Verify ownership and get task
            if not await self.firebase_service.verify_document_ownership("tasks", task_id, user_id):
                raise ValueError("Task not found or access denied")
            
            task = await self.firebase_service.get_document("tasks", task_id)
            
            # Delete associated calendar event if exists
            if task.get("calendar_event_id"):
                try:
                    await self.google_service.delete_calendar_event(
                        user_id, task["calendar_event_id"]
                    )
                except Exception as e:
                    print(f"Failed to delete calendar event: {e}")
            
            # Delete task from Firebase
            await self.firebase_service.delete_document("tasks", task_id)
            return True
            
        except Exception as e:
            raise Exception(f"Failed to delete task: {e}")
    
    # ========================================================================
    # CALENDAR INTEGRATION METHODS
    # ========================================================================
    
    async def create_calendar_event_for_task(self, user_id: str, task_data: Dict) -> Dict:
        """Create Google Calendar event for task"""
        try:
            # Check if user has Google connected
            user_profile = await self.firebase_service.get_user_profile(user_id)
            if not user_profile.get("google_connected"):
                raise ValueError("Google account not connected")
            
            # Prepare event data
            due_date = datetime.fromisoformat(task_data["due_date"])
            event_data = {
                "summary": f"📋 {task_data['title']}",
                "description": f"Task: {task_data.get('description', '')}\n\nCreated from Planner App",
                "start": {
                    "dateTime": due_date.isoformat(),
                    "timeZone": user_profile.get("timezone", "UTC")
                },
                "end": {
                    "dateTime": (due_date + timedelta(hours=1)).isoformat(),
                    "timeZone": user_profile.get("timezone", "UTC")
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email", "minutes": 24 * 60},  # 1 day before
                        {"method": "popup", "minutes": 30}        # 30 minutes before
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
                due_date = datetime.fromisoformat(task_update["due_date"])
                user_profile = await self.firebase_service.get_user_profile(user_id)
                timezone = user_profile.get("timezone", "UTC")
                
                event_update["start"] = {
                    "dateTime": due_date.isoformat(),
                    "timeZone": timezone
                }
                event_update["end"] = {
                    "dateTime": (due_date + timedelta(hours=1)).isoformat(),
                    "timeZone": timezone
                }
            
            if "status" in task_update:
                if task_update["status"] == TaskStatus.COMPLETED.value:
                    event_update["summary"] = f"✅ {event_update.get('summary', 'Task')}"
            
            return await self.google_service.update_calendar_event(
                user_id, event_id, event_update
            )
            
        except Exception as e:
            raise Exception(f"Failed to update calendar event for task: {e}")
    
    async def sync_calendar_tasks(self, user_id: str, start_date: date, end_date: date) -> Dict:
        """Sync tasks with Google Calendar events"""
        try:
            # Get calendar events from Google
            calendar_events = await self.google_service.get_calendar_events(
                user_id, start_date.isoformat(), end_date.isoformat()
            )
            
            # Get existing tasks in date range
            tasks = await self.get_tasks(
                user_id, 
                due_date_range=(start_date, end_date)
            )
            
            # Identify tasks that need calendar events
            tasks_without_events = [
                task for task in tasks 
                if task.due_date and not task.calendar_event_id
            ]
            
            created_events = []
            for task in tasks_without_events:
                try:
                    event = await self.create_calendar_event_for_task(
                        user_id, task.dict()
                    )
                    created_events.append(event)
                    
                    # Update task with calendar event ID
                    await self.firebase_service.update_document("tasks", task.id, {
                        "calendar_event_id": event["id"]
                    })
                except Exception as e:
                    print(f"Failed to create event for task {task.id}: {e}")
            
            return {
                "synced_events": len(created_events),
                "calendar_events": calendar_events,
                "tasks_synced": len(tasks_without_events)
            }
            
        except Exception as e:
            raise Exception(f"Failed to sync calendar tasks: {e}")
    
    # ========================================================================
    # DASHBOARD AND ANALYTICS
    # ========================================================================
    
    async def get_planner_dashboard(self, user_id: str) -> PlannerDashboard:
        """Get planner dashboard with stats and upcoming items"""
        try:
            # Get tasks stats - use the updated method signature
            all_tasks = await self.get_tasks(user_id, limit=1000)  # Get more tasks for accurate stats
            completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
            pending_tasks = [t for t in all_tasks if t.status != TaskStatus.COMPLETED]
            
            # Calculate overdue tasks safely
            overdue_tasks = []
            today = date.today()
            for task in pending_tasks:
                if task.due_date:
                    try:
                        # Handle both string and datetime objects
                        if isinstance(task.due_date, str):
                            task_due_date = datetime.fromisoformat(task.due_date).date()
                        else:
                            task_due_date = task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date
                        
                        if task_due_date < today:
                            overdue_tasks.append(task)
                    except (ValueError, AttributeError) as e:
                        print(f"Error parsing due date for task {task.id}: {e}")
                        continue
            
            # Get upcoming tasks (next 7 days) - use TaskFilter
            upcoming_end = today + timedelta(days=7)
            upcoming_task_filter = TaskFilter(
                due_date_from=today,
                due_date_to=upcoming_end,
                status=[TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            )
            upcoming_tasks = await self.get_tasks(user_id, task_filter=upcoming_task_filter)
            
            # Get recent notes safely
            try:
                recent_notes = await self.get_notes(user_id, limit=5)
            except Exception as e:
                print(f"Error getting notes: {e}")
                recent_notes = []
            
            # Get calendar events safely - handle Google API errors
            calendar_events = []
            try:
                if hasattr(self.google_service, 'get_calendar_events'):
                    calendar_events = await self.google_service.get_calendar_events(
                        user_id, 
                        today.isoformat(), 
                        upcoming_end.isoformat()
                    )
            except Exception as e:
                print(f"Error getting calendar events: {e}")
                # Continue without calendar events
            
            # Build stats
            stats = PlannerStats(
                total_tasks=len(all_tasks),
                completed_tasks=len(completed_tasks),
                pending_tasks=len(pending_tasks),
                overdue_tasks=len(overdue_tasks),
                completion_rate=round((len(completed_tasks) / len(all_tasks) * 100) if all_tasks else 0, 1),
                total_notes=len(recent_notes)
            )
            
            # Build dashboard response
            dashboard = PlannerDashboard(
                stats=stats,
                upcoming_tasks=upcoming_tasks[:5],  # Limit to 5 for dashboard
                recent_notes=recent_notes,
                calendar_events=calendar_events[:5] if calendar_events else []
            )
            
            return dashboard
            
        except Exception as e:
            print(f"Error in get_planner_dashboard: {e}")
            # Return a basic dashboard instead of failing completely
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
                calendar_events=[]
            )
    
    # ========================================================================
    # NOTE OPERATIONS (Enhanced from existing)
    # ========================================================================
    
    async def create_note(self, note: NoteCreate, user_id: str) -> NoteResponse:
        """Create a new note"""
        try:
            note_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": note.title,
                "content": note.content,
                "type": note.note_type.value if note.note_type else NoteType.TEXT.value,
                "tags": note.tags or [],
                "metadata": note.metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "google_keep_id": None
            }
            
            note_id = await self.firebase_service.create_document("notes", note_data)
            note_data["id"] = note_id
            
            return NoteResponse(**note_data)
            
        except Exception as e:
            raise Exception(f"Failed to create note: {e}")
    
    async def get_notes(self, user_id: str, limit: Optional[int] = None) -> List[NoteResponse]:
        """Get user notes"""
        try:
            filters = [("user_id", "==", user_id)]
            notes = await self.firebase_service.query_documents(
                "notes", 
                filters, 
                order_by=[("updated_at", "desc")],
                limit=limit
            )
            
            return [NoteResponse(**note) for note in notes]
            
        except Exception as e:
            raise Exception(f"Failed to get notes: {e}")