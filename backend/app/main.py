from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import tweets, users, analytics, config
from app.core.config import Settings
from app.tasks.tweet_processor import start_tweet_stream
from app.db.firestore import get_db

app = FastAPI()
settings = Settings()

def configure_cors(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def include_routers(app: FastAPI):
    app.include_router(tweets.router)
    app.include_router(users.router)
    app.include_router(analytics.router)
    app.include_router(config.router)

@app.on_event("startup")
async def startup_event():
    # HUMAN ASSISTANCE NEEDED
    # The following code block has a confidence level below 0.8
    # Please review and adjust as necessary
    db = get_db()
    await db.connect()
    await start_tweet_stream()

@app.on_event("shutdown")
async def shutdown_event():
    db = get_db()
    await db.close()
    # Add any additional cleanup steps here if needed

configure_cors(app)
include_routers(app)