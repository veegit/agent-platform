"""
User models for the API service.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    """Model for a user."""
    
    user_id: str = Field(..., description="Unique identifier for the user")
    username: str = Field(..., description="Username")
    email: Optional[EmailStr] = Field(default=None, description="Email address")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


# For MVP, we'll use a simple request model without auth
class SimpleUserRequest(BaseModel):
    """Simple request model for a user, used for MVP without full auth."""
    
    user_id: str = Field(..., description="Unique identifier for the user")