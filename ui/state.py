"""State management stub for backward compatibility.

This module is kept for backward compatibility with backend modules that reference it.
The Gradio app uses its own SessionState class instead.
"""


class AppState:
    """Stub AppState class for backward compatibility."""
    
    def get_user(self):
        """Stub - returns None."""
        return None
    
    def set_user(self, user):
        """Stub - no-op."""
        pass
    
    def clear_user(self):
        """Stub - no-op."""
        pass
    
    def is_authenticated(self):
        """Stub - returns False."""
        return False
    
    def get_client_id(self):
        """Stub - returns empty string."""
        return ""
    
    def refresh_session(self):
        """Stub - no-op."""
        pass
    
    def get_session_info(self):
        """Stub - returns empty dict."""
        return {}
    
    def add_tool_usage(self, tool_name, details=""):
        """Stub - no-op."""
        pass
    
    def get_tool_usage(self):
        """Stub - returns empty list."""
        return []
    
    def get_messages(self):
        """Stub - returns empty list."""
        return []
    
    def add_message(self, message):
        """Stub - no-op."""
        pass
    
    def get_greeting(self):
        """Stub - returns None."""
        return None
    
    def set_greeting(self, greeting):
        """Stub - no-op."""
        pass
    
    def get_chat_session_id(self):
        """Stub - returns None."""
        return None
    
    def set_chat_session_id(self, session_id):
        """Stub - no-op."""
        pass
    
    def increment_maintenance_count(self):
        """Stub - returns 0."""
        return 0
    
    def reset_maintenance_count(self):
        """Stub - no-op."""
        pass
    
    def set_message_history(self, history):
        """Stub - no-op."""
        pass


# Global app_state instance for backward compatibility
app_state = AppState()




