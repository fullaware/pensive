# Intent Router
"""Intent router for detecting commands vs natural language queries."""
import re
from typing import Dict, Optional, List, Any
from pathlib import Path


class IntentRouter:
    """Router for detecting user intent from natural language queries."""

    def __init__(self):
        # Command patterns
        self.command_patterns = {
            "build_skill": [
                r"\bbuild\s+skill\b",
                r"\bcreate\s+skill\b",
                r"\bmake\s+a\s+skill\b",
                r"\badd\s+skill\b",
            ],
            "activate_skill": [
                r"\bactivate\s+skill\b",
                r"\benable\s+skill\b",
                r"\bturn\s+on\s+skill\b",
                r"\bskill\s+\w+\s+(activate|enable|on)\b",
            ],
            "deactivate_skill": [
                r"\bdeactivate\s+skill\b",
                r"\bdisable\s+skill\b",
                r"\bturn\s+off\s+skill\b",
                r"\bskill\s+\w+\s+(deactivate|disable|off)\b",
            ],
            "list_skills": [
                r"\blist\s+skills\b",
                r"\bwhat\s+skills\b",
                r"\bshow\s+skills\b",
                r"\bavailable\s+skills\b",
            ],
            "set_preference": [
                r"\bnever\s+use\s+emojis\b",
                r"\bno\s+emojis\b",
                r"\buse\s+short\s+responses\b",
                r"\buse\s+long\s+responses\b",
                r"\bchange\s+timezone\b",
                r"\bset\s+preference\b",
            ],
            "show_status": [
                r"\bstatus\b",
                r"\bagent\s+status\b",
                r"\bmemory\s+stats\b",
                r"\bwhat\s+skills\b",
                r"\bhow\s+many\s+skills\b",
            ],
            "run_dream": [
                r"\bdream\b",
                r"\bdream\s+mode\b",
                r"\borganize\s+memories\b",
                r"\bthink\s+about\b",
            ],
        }

        # Command trigger words (exact matches)
        self.command_triggers = {
            "/start": "start",
            "/help": "help",
            "/skill": "skill",
            "/status": "status",
            "/dream": "dream",
        }

    def detect_intent(self, query: str) -> Dict[str, Any]:
        """Detect intent from a user query."""
        query_lower = query.lower().strip()

        # Check for command triggers first
        for trigger, command in self.command_triggers.items():
            if query_lower.startswith(trigger):
                return {
                    "intent": "command",
                    "command": command,
                    "raw": query,
                    "confidence": 1.0,
                }

        # Check for skill-related commands
        for command_name, patterns in self.command_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    # Extract additional details
                    details = self._extract_details(command_name, query)
                    return {
                        "intent": "command",
                        "command": command_name,
                        "details": details,
                        "raw": query,
                        "confidence": 0.8,
                    }

        # Default to regular query
        return {
            "intent": "query",
            "query": query,
            "confidence": 0.5,
        }

    def _extract_details(self, command: str, query: str) -> Dict[str, Any]:
        """Extract additional details from command."""
        query_lower = query.lower()

        if command == "build_skill":
            # Extract skill description
            patterns = [
                r"build\s+skill\s+(that|for|to)?\s*(.+?)(?:\s*$)",
                r"create\s+skill\s+(that|for|to)?\s*(.+?)(?:\s*$)",
                r"make\s+a\s+skill\s+(that|for|to)?\s*(.+?)(?:\s*$)",
            ]
            for pattern in patterns:
                match = re.search(pattern, query_lower)
                if match:
                    return {"skill_description": match.group(2).strip()}

        elif command == "activate_skill" or command == "deactivate_skill":
            # Extract skill name
            patterns = [
                r"(?:activate|deactivate|enable|disable)\s+skill\s+(\w+)",
                r"(?:activate|deactivate|enable|disable)\s+(\w+)",
                r"skill\s+(\w+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, query_lower)
                if match:
                    return {"skill_name": match.group(1)}

        elif command == "set_preference":
            # Extract preference details
            preference = {}
            if "never use emojis" in query_lower or "no emojis" in query_lower:
                preference["use_emojis"] = False
            elif "use short responses" in query_lower:
                preference["communication_style"] = "short"
            elif "use long responses" in query_lower:
                preference["communication_style"] = "long"

            return {"preference": preference}

        return {}

    def is_command(self, query: str) -> bool:
        """Check if query is a command."""
        intent = self.detect_intent(query)
        return intent.get("intent") == "command"

    def get_command(self, query: str) -> Optional[str]:
        """Get command name from query."""
        intent = self.detect_intent(query)
        if intent.get("intent") == "command":
            return intent.get("command")
        return None


async def detect_intent(query: str) -> Dict[str, Any]:
    """Convenience function to detect intent."""
    router = IntentRouter()
    return router.detect_intent(query)