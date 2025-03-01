from __future__ import annotations
from typing import Optional

class Context:
    """Application context"""
    _instance: Optional[Context] = None
    
    def __init__(self):
        from datetime import datetime, timezone
        self.batch_time = datetime.now(timezone.utc)
        
    @classmethod
    def get(cls) -> Context:
        """Get or create the singleton instance"""
        if cls._instance is None:
            cls._instance = Context()
        return cls._instance
