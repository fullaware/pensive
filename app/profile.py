"""User profile utilities and storage helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from config import CONVERSATION_ID, logger
from database import agent_memory_collection

PROFILE_DOC_FILTER = {
    "type": "profile",
    "conversation_id": CONVERSATION_ID,
}


def normalize_profile_field(field_name: str) -> str:
    """Convert arbitrary field names into lowercase snake_case keys."""
    if not field_name:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", "_", field_name.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or field_name.strip().lower()


def ensure_profile_document() -> Optional[dict]:
    """Fetch the profile document, creating it if needed."""
    if agent_memory_collection is None:
        return None
    doc = agent_memory_collection.find_one(PROFILE_DOC_FILTER)
    if doc:
        return doc
    now = datetime.now(timezone.utc).isoformat()
    new_doc = {
        **PROFILE_DOC_FILTER,
        "profile": {},
        "updated_at": now,
    }
    agent_memory_collection.insert_one(new_doc)
    return new_doc


def get_profile_data() -> dict:
    """Return the stored profile data dictionary."""
    doc = agent_memory_collection.find_one(PROFILE_DOC_FILTER) if agent_memory_collection is not None else None
    if not doc:
        return {}
    return doc.get("profile", {}) or {}


def format_profile_text(max_fields: int | None = 10) -> str:
    """Turn the stored profile into human-readable lines."""
    profile = get_profile_data()
    if not profile:
        return ""
    items = list(profile.items())
    if max_fields is not None:
        items = items[:max_fields]
    lines = [f"{key.replace('_', ' ').title()}: {value}" for key, value in items]
    return "\n".join(lines)


def profile_snapshot_json() -> str:
    """Return profile data as JSON for prompts or logging."""
    profile = get_profile_data()
    if not profile:
        return "No profile data stored."
    return json.dumps(profile, indent=2)


def upsert_profile_field(field_name: str, field_value: str) -> str:
    """Persist a single profile field."""
    if agent_memory_collection is None:
        return "Database unavailable. Cannot store profile."
    normalized = normalize_profile_field(field_name)
    if not normalized:
        return "Invalid field name provided."
    ensure_profile_document()
    now = datetime.now(timezone.utc).isoformat()
    agent_memory_collection.update_one(
        PROFILE_DOC_FILTER,
        {
            "$set": {
                f"profile.{normalized}": field_value.strip(),
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return f"Stored profile.{normalized}"


def delete_profile_field(field_name: str) -> str:
    """Remove a profile field if it exists."""
    if agent_memory_collection is None:
        return "Database unavailable. Cannot delete profile data."
    normalized = normalize_profile_field(field_name)
    if not normalized:
        return "Invalid field name provided."
    ensure_profile_document()
    now = datetime.now(timezone.utc).isoformat()
    agent_memory_collection.update_one(
        PROFILE_DOC_FILTER,
        {
            "$unset": {f"profile.{normalized}": ""},
            "$set": {"updated_at": now},
        },
        upsert=True,
    )
    return f"Deleted profile.{normalized}"


def build_user_profile_context(max_fields: int = 10) -> str:
    """Render the stored user profile (identity + preferences)."""
    try:
        profile = get_profile_data()
        if not profile:
            return ""
        items = list(profile.items())
        if max_fields is not None:
            items = items[:max_fields]
        lines = [f"{key.replace('_', ' ').title()}: {value}" for key, value in items]
        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(f"Failed to build user profile context: {exc}")
        return ""


