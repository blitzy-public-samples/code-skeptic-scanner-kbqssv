from pydantic import BaseModel
from datetime import datetime

class User(BaseModel):
    user_id: str
    username: str
    display_name: str
    followers_count: int
    created_at: datetime