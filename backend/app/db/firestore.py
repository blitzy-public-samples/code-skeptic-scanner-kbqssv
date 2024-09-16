from google.cloud.firestore import Client
from google.auth import default
from app.core.config import Settings

db = Client()

def get_db():
    credentials, project_id = default()
    settings = Settings()
    return Client(project=settings.PROJECT_ID)

def add_tweet(tweet_data: dict) -> str:
    # HUMAN ASSISTANCE NEEDED
    # This function needs review for production readiness
    client = get_db()
    doc_ref = client.collection('tweets').add(tweet_data)
    return doc_ref[1].id

def get_tweet(tweet_id: str) -> dict:
    client = get_db()
    doc_ref = client.collection('tweets').document(tweet_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        return None

def update_tweet(tweet_id: str, update_data: dict) -> bool:
    # HUMAN ASSISTANCE NEEDED
    # This function needs review for production readiness
    client = get_db()
    doc_ref = client.collection('tweets').document(tweet_id)
    try:
        doc_ref.update(update_data)
        return True
    except Exception:
        return False