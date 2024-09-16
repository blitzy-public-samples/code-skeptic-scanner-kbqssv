from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Twitter Bot"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    TWITTER_API_KEY: str
    TWITTER_API_SECRET: str
    TWITTER_ACCESS_TOKEN: str
    TWITTER_ACCESS_TOKEN_SECRET: str
    OPENAI_API_KEY: str
    NOTION_API_KEY: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: str
    FIRESTORE_COLLECTION_TWEETS: str = "tweets"
    FIRESTORE_COLLECTION_USERS: str = "users"
    FIRESTORE_COLLECTION_RESPONSES: str = "responses"
    BIGQUERY_DATASET: str
    DOUBT_RATING_THRESHOLD: float = 0.7
    POPULARITY_THRESHOLD: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()