"""Google Calendar integration for Pensive.

This module provides CRUD operations for Google Calendar events.
Requires OAuth2 credentials from Google Cloud Console.

Setup:
1. Create a project in Google Cloud Console
2. Enable Google Calendar API
3. Create OAuth2 credentials (Desktop app)
4. Download credentials.json and place in project root
5. Set environment variables in .env:
   - GOOGLE_CALENDAR_CREDENTIALS_FILE=credentials.json
   - GOOGLE_CALENDAR_TOKEN_FILE=token.json
   - GOOGLE_CALENDAR_ID=primary (or specific calendar ID)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from config import (
    GOOGLE_CALENDAR_CREDENTIALS_FILE,
    GOOGLE_CALENDAR_TOKEN_FILE,
    GOOGLE_CALENDAR_ID,
)

logger = logging.getLogger(__name__)

# Flag to track if Google Calendar API is available
GOOGLE_CALENDAR_AVAILABLE = False

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import os.path
    
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    logger.warning(
        "Google Calendar dependencies not installed. "
        "Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
    )


# OAuth2 scopes for Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    id: Optional[str] = None
    summary: str = ""
    description: str = ""
    location: str = ""
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    all_day: bool = False
    attendees: list[str] = None
    reminders: list[dict] = None
    
    def __post_init__(self):
        if self.attendees is None:
            self.attendees = []
        if self.reminders is None:
            self.reminders = []


class GoogleCalendarService:
    """Service for interacting with Google Calendar API."""
    
    def __init__(self):
        self._service = None
        self._initialized = False
    
    def _get_credentials(self) -> Optional["Credentials"]:
        """Get or refresh OAuth2 credentials."""
        if not GOOGLE_CALENDAR_AVAILABLE:
            logger.error("Google Calendar API not available")
            return None
        
        creds = None
        
        # Load existing token
        if os.path.exists(GOOGLE_CALENDAR_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(
                GOOGLE_CALENDAR_TOKEN_FILE, SCOPES
            )
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(GOOGLE_CALENDAR_CREDENTIALS_FILE):
                    logger.error(
                        f"Credentials file not found: {GOOGLE_CALENDAR_CREDENTIALS_FILE}. "
                        "Download from Google Cloud Console."
                    )
                    return None
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        GOOGLE_CALENDAR_CREDENTIALS_FILE, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Failed to authenticate: {e}")
                    return None
            
            # Save credentials for next run
            if creds:
                with open(GOOGLE_CALENDAR_TOKEN_FILE, "w") as token:
                    token.write(creds.to_json())
        
        return creds
    
    def initialize(self) -> bool:
        """Initialize the Calendar service."""
        if self._initialized:
            return True
        
        if not GOOGLE_CALENDAR_AVAILABLE:
            return False
        
        creds = self._get_credentials()
        if not creds:
            return False
        
        try:
            self._service = build("calendar", "v3", credentials=creds)
            self._initialized = True
            logger.info("Google Calendar service initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to build Calendar service: {e}")
            return False
    
    @property
    def is_available(self) -> bool:
        """Check if the service is available."""
        return self._initialized and self._service is not None
    
    # ==================== CREATE ====================
    
    def create_event(self, event: CalendarEvent, calendar_id: str = None) -> Optional[str]:
        """Create a new calendar event.
        
        Args:
            event: CalendarEvent object with event details
            calendar_id: Calendar ID (defaults to GOOGLE_CALENDAR_ID)
            
        Returns:
            Event ID if successful, None otherwise
        """
        if not self.is_available:
            if not self.initialize():
                return None
        
        calendar_id = calendar_id or GOOGLE_CALENDAR_ID
        
        # Build event body
        event_body = {
            "summary": event.summary,
            "description": event.description,
            "location": event.location,
        }
        
        # Set start/end times
        if event.all_day:
            event_body["start"] = {"date": event.start_datetime.strftime("%Y-%m-%d")}
            event_body["end"] = {"date": event.end_datetime.strftime("%Y-%m-%d")}
        else:
            event_body["start"] = {
                "dateTime": event.start_datetime.isoformat(),
                "timeZone": "America/New_York",  # TODO: Make configurable
            }
            event_body["end"] = {
                "dateTime": event.end_datetime.isoformat(),
                "timeZone": "America/New_York",
            }
        
        # Add attendees
        if event.attendees:
            event_body["attendees"] = [{"email": email} for email in event.attendees]
        
        # Add reminders
        if event.reminders:
            event_body["reminders"] = {
                "useDefault": False,
                "overrides": event.reminders,
            }
        
        try:
            created_event = self._service.events().insert(
                calendarId=calendar_id,
                body=event_body,
            ).execute()
            
            logger.info(f"Created event: {created_event.get('id')}")
            return created_event.get("id")
        except HttpError as e:
            logger.error(f"Failed to create event: {e}")
            return None
    
    # ==================== READ ====================
    
    def get_event(self, event_id: str, calendar_id: str = None) -> Optional[CalendarEvent]:
        """Get a specific calendar event by ID.
        
        Args:
            event_id: The event ID
            calendar_id: Calendar ID (defaults to GOOGLE_CALENDAR_ID)
            
        Returns:
            CalendarEvent if found, None otherwise
        """
        if not self.is_available:
            if not self.initialize():
                return None
        
        calendar_id = calendar_id or GOOGLE_CALENDAR_ID
        
        try:
            event = self._service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
            
            return self._parse_event(event)
        except HttpError as e:
            logger.error(f"Failed to get event {event_id}: {e}")
            return None
    
    def list_events(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        max_results: int = 10,
        search_query: str = None,
        calendar_id: str = None,
    ) -> list[CalendarEvent]:
        """List calendar events within a time range.
        
        Args:
            start_date: Start of time range (defaults to now)
            end_date: End of time range (defaults to 7 days from now)
            max_results: Maximum number of events to return
            search_query: Optional text search query
            calendar_id: Calendar ID (defaults to GOOGLE_CALENDAR_ID)
            
        Returns:
            List of CalendarEvent objects
        """
        if not self.is_available:
            if not self.initialize():
                return []
        
        calendar_id = calendar_id or GOOGLE_CALENDAR_ID
        start_date = start_date or datetime.utcnow()
        end_date = end_date or (start_date + timedelta(days=7))
        
        try:
            events_result = self._service.events().list(
                calendarId=calendar_id,
                timeMin=start_date.isoformat() + "Z",
                timeMax=end_date.isoformat() + "Z",
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                q=search_query,
            ).execute()
            
            events = events_result.get("items", [])
            return [self._parse_event(e) for e in events]
        except HttpError as e:
            logger.error(f"Failed to list events: {e}")
            return []
    
    def get_upcoming_events(
        self,
        days: int = 7,
        max_results: int = 10,
        calendar_id: str = None,
    ) -> list[CalendarEvent]:
        """Get upcoming events for the next N days.
        
        Args:
            days: Number of days to look ahead
            max_results: Maximum number of events
            calendar_id: Calendar ID
            
        Returns:
            List of upcoming CalendarEvent objects
        """
        now = datetime.utcnow()
        end = now + timedelta(days=days)
        return self.list_events(
            start_date=now,
            end_date=end,
            max_results=max_results,
            calendar_id=calendar_id,
        )
    
    # ==================== UPDATE ====================
    
    def update_event(
        self,
        event_id: str,
        event: CalendarEvent,
        calendar_id: str = None,
    ) -> bool:
        """Update an existing calendar event.
        
        Args:
            event_id: The event ID to update
            event: CalendarEvent with updated details
            calendar_id: Calendar ID (defaults to GOOGLE_CALENDAR_ID)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available:
            if not self.initialize():
                return False
        
        calendar_id = calendar_id or GOOGLE_CALENDAR_ID
        
        # Build update body
        event_body = {}
        
        if event.summary:
            event_body["summary"] = event.summary
        if event.description:
            event_body["description"] = event.description
        if event.location:
            event_body["location"] = event.location
        
        if event.start_datetime and event.end_datetime:
            if event.all_day:
                event_body["start"] = {"date": event.start_datetime.strftime("%Y-%m-%d")}
                event_body["end"] = {"date": event.end_datetime.strftime("%Y-%m-%d")}
            else:
                event_body["start"] = {
                    "dateTime": event.start_datetime.isoformat(),
                    "timeZone": "America/New_York",
                }
                event_body["end"] = {
                    "dateTime": event.end_datetime.isoformat(),
                    "timeZone": "America/New_York",
                }
        
        if event.attendees:
            event_body["attendees"] = [{"email": email} for email in event.attendees]
        
        try:
            self._service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=event_body,
            ).execute()
            
            logger.info(f"Updated event: {event_id}")
            return True
        except HttpError as e:
            logger.error(f"Failed to update event {event_id}: {e}")
            return False
    
    # ==================== DELETE ====================
    
    def delete_event(self, event_id: str, calendar_id: str = None) -> bool:
        """Delete a calendar event.
        
        Args:
            event_id: The event ID to delete
            calendar_id: Calendar ID (defaults to GOOGLE_CALENDAR_ID)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available:
            if not self.initialize():
                return False
        
        calendar_id = calendar_id or GOOGLE_CALENDAR_ID
        
        try:
            self._service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
            
            logger.info(f"Deleted event: {event_id}")
            return True
        except HttpError as e:
            logger.error(f"Failed to delete event {event_id}: {e}")
            return False
    
    # ==================== HELPERS ====================
    
    def _parse_event(self, event_data: dict) -> CalendarEvent:
        """Parse Google Calendar API event data into CalendarEvent."""
        start = event_data.get("start", {})
        end = event_data.get("end", {})
        
        # Determine if all-day event
        all_day = "date" in start
        
        if all_day:
            start_dt = datetime.strptime(start["date"], "%Y-%m-%d")
            end_dt = datetime.strptime(end["date"], "%Y-%m-%d")
        else:
            start_str = start.get("dateTime", "")
            end_str = end.get("dateTime", "")
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")) if start_str else None
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else None
        
        attendees = [
            a.get("email") 
            for a in event_data.get("attendees", [])
            if a.get("email")
        ]
        
        return CalendarEvent(
            id=event_data.get("id"),
            summary=event_data.get("summary", ""),
            description=event_data.get("description", ""),
            location=event_data.get("location", ""),
            start_datetime=start_dt,
            end_datetime=end_dt,
            all_day=all_day,
            attendees=attendees,
        )
    
    def list_calendars(self) -> list[dict]:
        """List all calendars accessible by the user.
        
        Returns:
            List of calendar info dicts with 'id' and 'summary' keys
        """
        if not self.is_available:
            if not self.initialize():
                return []
        
        try:
            calendars_result = self._service.calendarList().list().execute()
            calendars = calendars_result.get("items", [])
            return [
                {"id": c.get("id"), "summary": c.get("summary")}
                for c in calendars
            ]
        except HttpError as e:
            logger.error(f"Failed to list calendars: {e}")
            return []


# Singleton instance
_calendar_service: Optional[GoogleCalendarService] = None


def get_calendar_service() -> GoogleCalendarService:
    """Get the singleton calendar service instance."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = GoogleCalendarService()
    return _calendar_service


# ==================== TOOL FUNCTIONS ====================
# These functions are designed to be called by the AI agent

def calendar_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    all_day: bool = False,
) -> str:
    """Create a new calendar event.
    
    Args:
        summary: Event title/summary
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS) or date (YYYY-MM-DD for all-day)
        end_time: End time in ISO format or date
        description: Optional event description
        location: Optional event location
        all_day: Whether this is an all-day event
        
    Returns:
        Success message with event ID or error message
    """
    service = get_calendar_service()
    
    if not GOOGLE_CALENDAR_AVAILABLE:
        return "Google Calendar is not configured. Please install the required dependencies and set up credentials."
    
    try:
        if all_day:
            start_dt = datetime.strptime(start_time[:10], "%Y-%m-%d")
            end_dt = datetime.strptime(end_time[:10], "%Y-%m-%d")
        else:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
    except ValueError as e:
        return f"Invalid date/time format: {e}. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
    
    event = CalendarEvent(
        summary=summary,
        description=description,
        location=location,
        start_datetime=start_dt,
        end_datetime=end_dt,
        all_day=all_day,
    )
    
    event_id = service.create_event(event)
    
    if event_id:
        return f"✅ Created event '{summary}' (ID: {event_id})"
    else:
        return "❌ Failed to create event. Check logs for details."


def calendar_list_events(
    days: int = 7,
    search_query: str = None,
) -> str:
    """List upcoming calendar events.
    
    Args:
        days: Number of days to look ahead (default: 7)
        search_query: Optional text to search for in events
        
    Returns:
        Formatted list of events or error message
    """
    service = get_calendar_service()
    
    if not GOOGLE_CALENDAR_AVAILABLE:
        return "Google Calendar is not configured. Please install the required dependencies and set up credentials."
    
    now = datetime.utcnow()
    end = now + timedelta(days=days)
    
    events = service.list_events(
        start_date=now,
        end_date=end,
        max_results=20,
        search_query=search_query,
    )
    
    if not events:
        return f"No events found in the next {days} days."
    
    lines = [f"📅 **Upcoming Events (next {days} days):**\n"]
    
    for event in events:
        if event.all_day:
            time_str = event.start_datetime.strftime("%Y-%m-%d") + " (All day)"
        else:
            time_str = event.start_datetime.strftime("%Y-%m-%d %H:%M")
        
        lines.append(f"• **{event.summary}** - {time_str}")
        if event.location:
            lines.append(f"  📍 {event.location}")
        if event.description:
            desc_preview = event.description[:100] + "..." if len(event.description) > 100 else event.description
            lines.append(f"  {desc_preview}")
        lines.append("")
    
    return "\n".join(lines)


def calendar_update_event(
    event_id: str,
    summary: str = None,
    start_time: str = None,
    end_time: str = None,
    description: str = None,
    location: str = None,
) -> str:
    """Update an existing calendar event.
    
    Args:
        event_id: The ID of the event to update
        summary: New event title (optional)
        start_time: New start time in ISO format (optional)
        end_time: New end time in ISO format (optional)
        description: New description (optional)
        location: New location (optional)
        
    Returns:
        Success or error message
    """
    service = get_calendar_service()
    
    if not GOOGLE_CALENDAR_AVAILABLE:
        return "Google Calendar is not configured. Please install the required dependencies and set up credentials."
    
    start_dt = None
    end_dt = None
    
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
        except ValueError as e:
            return f"Invalid start time format: {e}"
    
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time)
        except ValueError as e:
            return f"Invalid end time format: {e}"
    
    event = CalendarEvent(
        summary=summary or "",
        description=description or "",
        location=location or "",
        start_datetime=start_dt,
        end_datetime=end_dt,
    )
    
    if service.update_event(event_id, event):
        return f"✅ Updated event {event_id}"
    else:
        return f"❌ Failed to update event {event_id}. Check if the ID is correct."


def calendar_delete_event(event_id: str) -> str:
    """Delete a calendar event.
    
    Args:
        event_id: The ID of the event to delete
        
    Returns:
        Success or error message
    """
    service = get_calendar_service()
    
    if not GOOGLE_CALENDAR_AVAILABLE:
        return "Google Calendar is not configured. Please install the required dependencies and set up credentials."
    
    if service.delete_event(event_id):
        return f"✅ Deleted event {event_id}"
    else:
        return f"❌ Failed to delete event {event_id}. Check if the ID is correct."


def calendar_get_event(event_id: str) -> str:
    """Get details of a specific calendar event.
    
    Args:
        event_id: The ID of the event
        
    Returns:
        Event details or error message
    """
    service = get_calendar_service()
    
    if not GOOGLE_CALENDAR_AVAILABLE:
        return "Google Calendar is not configured. Please install the required dependencies and set up credentials."
    
    event = service.get_event(event_id)
    
    if not event:
        return f"❌ Event {event_id} not found."
    
    lines = [f"📅 **{event.summary}**\n"]
    
    if event.all_day:
        lines.append(f"📆 {event.start_datetime.strftime('%Y-%m-%d')} (All day)")
    else:
        lines.append(f"🕐 {event.start_datetime.strftime('%Y-%m-%d %H:%M')} - {event.end_datetime.strftime('%H:%M')}")
    
    if event.location:
        lines.append(f"📍 {event.location}")
    
    if event.description:
        lines.append(f"\n{event.description}")
    
    if event.attendees:
        lines.append(f"\n👥 Attendees: {', '.join(event.attendees)}")
    
    lines.append(f"\n🔑 ID: {event.id}")
    
    return "\n".join(lines)






