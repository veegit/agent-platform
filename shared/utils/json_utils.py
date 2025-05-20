"""
JSON utilities for serialization and deserialization.
"""

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""
    
    def default(self, obj: Any) -> Any:
        """Convert datetime objects to ISO format strings.
        
        Args:
            obj: The object to encode.
            
        Returns:
            A JSON serializable object.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def dumps(obj: Any) -> str:
    """Dump an object to a JSON string, handling datetime objects.
    
    Args:
        obj: The object to serialize.
        
    Returns:
        A JSON string.
    """
    return json.dumps(obj, cls=DateTimeEncoder)

def loads(s: str) -> Any:
    """Load a JSON string to an object.
    
    Args:
        s: The JSON string to deserialize.
        
    Returns:
        The deserialized object.
    """
    return json.loads(s)
