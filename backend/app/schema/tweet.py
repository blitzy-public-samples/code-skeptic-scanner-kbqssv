from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Tweet(BaseModel):
    tweet_id: str
    content: str
    user_id: str
    timestamp: datetime
    likes_count: int
    retweets_count: int
    doubt_rating: float
    ai_tools: List[str]
    media_urls: List[str]
    quoted_tweet_id: Optional[str] = None