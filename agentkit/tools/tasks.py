"""CalDAV Tools for task management with tasks.org

This toolset provides integration with CalDAV-based task lists,
allowing agents to manage tasks across different lists.

Required environment variables:
- CALDAV_URL: CalDAV server URL (e.g., https://caldav.example.com)
- CALDAV_USERNAME: CalDAV username
- CALDAV_PASSWORD: CalDAV password
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import caldav
from caldav.elements import dav
from icalendar import Calendar, Todo

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)


class CalDAVTools(ToolSetHandler):
    """Tools for managing tasks via CalDAV protocol"""

    name = "tasks"

    def __init__(self):
        super().__init__(name="tasks")
        self._client: Optional[caldav.DAVClient] = None
        self._principal: Optional[caldav.Principal] = None
        self._url = os.getenv("CALDAV_URL")
        self._username = os.getenv("CALDAV_USERNAME")
        self._password = os.getenv("CALDAV_PASSWORD")

    async def initialize(self):
        """Initialize CalDAV connection"""
        await super().initialize()
        
        if not all([self._url, self._username, self._password]):
            raise ValueError(
                "CalDAV configuration incomplete. "
                "Set CALDAV_URL, CALDAV_USERNAME, and CALDAV_PASSWORD environment variables."
            )

        try:
            logger.info(f"Connecting to CalDAV server at {self._url}")
            self._client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password
            )
            self._principal = self._client.principal()
            logger.info("Successfully connected to CalDAV server")
        except Exception as e:
            logger.error(f"Failed to connect to CalDAV server: {e}", exc_info=True)
            raise

    async def cleanup(self):
        """Clean up CalDAV connection"""
        self._client = None
        self._principal = None
        logger.info("CalDAV connection cleaned up")

    @tool(
        description="Get all available task lists",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    async def get_task_lists(self) -> List[Dict[str, str]]:
        """Retrieve all task lists from the CalDAV server
        
        Returns:
            List of dictionaries containing list information (id, name, url)
        """
        if not self._principal:
            raise RuntimeError("CalDAV client not initialized")

        try:
            calendars = self._principal.calendars()
            
            task_lists = []
            for calendar in calendars:
                # Try to get the calendar name
                try:
                    display_name = calendar.get_properties([dav.DisplayName()])
                    name = display_name.get('{DAV:}displayname', 'Unnamed List')
                except Exception:
                    name = 'Unnamed List'
                
                task_lists.append({
                    "id": calendar.url.path.split('/')[-2] if '/' in calendar.url.path else str(calendar.url),
                    "name": name,
                    "url": str(calendar.url)
                })
            
            logger.info(f"Retrieved {len(task_lists)} task lists")
            return task_lists
            
        except Exception as e:
            logger.error(f"Error retrieving task lists: {e}", exc_info=True)
            raise

    @tool(
        description="List all tasks in a specific task list",
        parameters={
            "type": "object",
            "properties": {
                "list_url": {
                    "type": "string",
                    "description": "The URL of the task list (from get_task_lists)"
                },
                "include_completed": {
                    "type": "boolean",
                    "description": "Whether to include completed tasks",
                    "default": False
                }
            },
            "required": ["list_url"]
        }
    )
    async def list_tasks(
        self, 
        list_url: str, 
        include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """List all tasks in a specific task list
        
        Args:
            list_url: URL of the task list
            include_completed: Whether to include completed tasks
            
        Returns:
            List of task dictionaries with uid, summary, status, priority, etc.
        """
        if not self._client:
            raise RuntimeError("CalDAV client not initialized")

        try:
            calendar = caldav.Calendar(client=self._client, url=list_url)
            todos = calendar.todos(include_completed=include_completed)
            
            tasks = []
            for todo in todos:
                task_data = self._parse_todo(todo)
                if task_data:
                    tasks.append(task_data)
            
            logger.info(f"Retrieved {len(tasks)} tasks from list {list_url}")
            return tasks
            
        except Exception as e:
            logger.error(f"Error listing tasks: {e}", exc_info=True)
            raise

    @tool(
        description="Add a new task to a task list",
        parameters={
            "type": "object",
            "properties": {
                "list_url": {
                    "type": "string",
                    "description": "The URL of the task list"
                },
                "summary": {
                    "type": "string",
                    "description": "Task title/summary"
                },
                "description": {
                    "type": "string",
                    "description": "Optional task description/notes"
                },
                "priority": {
                    "type": "integer",
                    "description": "Task priority (1-9, where 1 is highest). 0 means undefined.",
                    "minimum": 0,
                    "maximum": 9
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date in ISO format (YYYY-MM-DD)"
                }
            },
            "required": ["list_url", "summary"]
        }
    )
    async def add_task(
        self,
        list_url: str,
        summary: str,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        due_date: Optional[str] = None
    ) -> Dict[str, str]:
        """Add a new task to a task list
        
        Args:
            list_url: URL of the task list
            summary: Task title
            description: Optional task description
            priority: Optional priority (1-9)
            due_date: Optional due date in ISO format
            
        Returns:
            Dictionary with created task information
        """
        if not self._client:
            raise RuntimeError("CalDAV client not initialized")

        try:
            calendar = caldav.Calendar(client=self._client, url=list_url)
            
            # Create iCalendar VTODO
            cal = Calendar()
            todo = Todo()
            
            # Required fields
            todo.add('summary', summary)
            todo.add('dtstamp', datetime.now(timezone.utc))
            todo.add('uid', f"{datetime.now(timezone.utc).timestamp()}@agentkit")
            
            # Optional fields
            if description:
                todo.add('description', description)
            
            if priority is not None and 0 <= priority <= 9:
                todo.add('priority', priority)
            
            if due_date:
                try:
                    # Parse ISO date and set as due date
                    from datetime import date
                    due = datetime.fromisoformat(due_date).date()
                    todo.add('due', due)
                except Exception as e:
                    logger.warning(f"Invalid due date format: {due_date}, ignoring. Error: {e}")
            
            # Add status
            todo.add('status', 'NEEDS-ACTION')
            
            cal.add_component(todo)
            
            # Save to CalDAV
            created_todo = calendar.save_todo(cal.to_ical().decode('utf-8'))
            
            logger.info(f"Created task '{summary}' in list {list_url}")
            
            return {
                "uid": str(todo.get('uid')),
                "summary": summary,
                "url": str(created_todo.url) if hasattr(created_todo, 'url') else "unknown"
            }
            
        except Exception as e:
            logger.error(f"Error adding task: {e}", exc_info=True)
            raise

    @tool(
        description="Mark a task as complete",
        parameters={
            "type": "object",
            "properties": {
                "list_url": {
                    "type": "string",
                    "description": "The URL of the task list"
                },
                "task_uid": {
                    "type": "string",
                    "description": "The UID of the task to complete"
                }
            },
            "required": ["list_url", "task_uid"]
        }
    )
    async def complete_task(self, list_url: str, task_uid: str) -> Dict[str, str]:
        """Mark a task as complete
        
        Args:
            list_url: URL of the task list
            task_uid: UID of the task to complete
            
        Returns:
            Dictionary with completion status
        """
        if not self._client:
            raise RuntimeError("CalDAV client not initialized")

        try:
            calendar = caldav.Calendar(client=self._client, url=list_url)
            
            # Get all todos and find the matching one
            todos = calendar.todos(include_completed=False)
            target_todo = None
            
            for todo in todos:
                try:
                    ical = Calendar.from_ical(todo.data)
                    for component in ical.walk('VTODO'):
                        if str(component.get('uid')) == task_uid:
                            target_todo = todo
                            break
                    if target_todo:
                        break
                except Exception as e:
                    logger.warning(f"Error parsing todo: {e}")
                    continue
            
            if not target_todo:
                raise ValueError(f"Task with UID {task_uid} not found in list")
            
            # Update the task to completed
            ical = Calendar.from_ical(target_todo.data)
            for component in ical.walk('VTODO'):
                if str(component.get('uid')) == task_uid:
                    component['status'] = 'COMPLETED'
                    component['completed'] = datetime.now(timezone.utc)
                    component['percent-complete'] = 100
            
            # Save the updated todo
            target_todo.data = ical.to_ical()
            target_todo.save()
            
            logger.info(f"Marked task {task_uid} as complete")
            
            return {
                "uid": task_uid,
                "status": "completed",
                "message": "Task marked as complete"
            }
            
        except Exception as e:
            logger.error(f"Error completing task: {e}", exc_info=True)
            raise

    def _parse_todo(self, todo) -> Optional[Dict[str, Any]]:
        """Parse a CalDAV todo into a dictionary
        
        Args:
            todo: CalDAV todo object
            
        Returns:
            Dictionary with task information or None if parsing fails
        """
        try:
            ical = Calendar.from_ical(todo.data)
            
            for component in ical.walk('VTODO'):
                task_data = {
                    "uid": str(component.get('uid', '')),
                    "summary": str(component.get('summary', 'Untitled')),
                    "status": str(component.get('status', 'NEEDS-ACTION')),
                    "url": str(todo.url) if hasattr(todo, 'url') else None
                }
                
                # Optional fields
                if component.get('description'):
                    task_data['description'] = str(component.get('description'))
                
                if component.get('priority'):
                    task_data['priority'] = int(component.get('priority'))
                
                if component.get('due'):
                    due = component.get('due')
                    if hasattr(due, 'dt'):
                        task_data['due'] = due.dt.isoformat()
                    else:
                        task_data['due'] = str(due)
                
                if component.get('completed'):
                    completed = component.get('completed')
                    if hasattr(completed, 'dt'):
                        task_data['completed'] = completed.dt.isoformat()
                    else:
                        task_data['completed'] = str(completed)
                
                if component.get('percent-complete'):
                    task_data['percent_complete'] = int(component.get('percent-complete'))
                
                return task_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing todo: {e}", exc_info=True)
            return None