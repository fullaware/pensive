# Pushover notification utilities
"""Pushover notification sender."""
import httpx
from typing import Optional
from memory_system.config import Config


class PushoverClient:
    """Client for sending Pushover notifications."""

    def __init__(self):
        self.token = Config.PUSHOVER_TOKEN
        self.user = Config.PUSHOVER_USER
        self._client = httpx.AsyncClient(timeout=30.0)

    async def send(
        self,
        message: str,
        title: Optional[str] = None,
        priority: int = 0,
        sound: Optional[str] = None,
    ) -> bool:
        """Send a Pushover notification.

        Args:
            message: The notification message
            title: Optional notification title
            priority: Priority level (-2 to 2)
            sound: Optional sound name

        Returns:
            True if successful, False otherwise
        """
        if not self.token or not self.user:
            print("Pushover credentials not configured")
            return False

        try:
            payload = {
                "token": self.token,
                "user": self.user,
                "message": message,
            }

            if title:
                payload["title"] = title
            if priority:
                payload["priority"] = priority
            if sound:
                payload["sound"] = sound

            response = await self._client.post(
                "https://api.pushover.net/1/messages.json",
                data=payload,
            )
            response.raise_for_status()

            result = response.json()
            return result.get("status") == 1

        except Exception as e:
            print(f"Error sending Pushover notification: {e}")
            return False

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


# Convenience function
async def send_pushover_notification(
    message: str,
    title: Optional[str] = None,
    priority: int = 0,
) -> bool:
    """Convenience function to send a Pushover notification."""
    client = PushoverClient()
    try:
        return await client.send(message, title, priority)
    finally:
        await client.close()