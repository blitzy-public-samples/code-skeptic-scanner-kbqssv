from app.db.firestore import get_tweet, add_response
from app.schema.tweet import Tweet
from app.services.llm_service import LLMService
from app.core.config import Settings

settings = Settings()
llm_service = LLMService()

# HUMAN ASSISTANCE NEEDED
# The following function may need additional error handling and optimization for production readiness
async def generate_response(tweet_id: str) -> str:
    tweet = await get_tweet(tweet_id)
    if not tweet:
        raise ValueError(f"Tweet with id {tweet_id} not found")
    
    response_content = await llm_service.generate_response(tweet.content)
    
    await add_response(tweet_id, response_content)
    
    return response_content

# HUMAN ASSISTANCE NEEDED
# The following function may need additional error handling, pagination, and optimization for production readiness
async def process_pending_responses() -> int:
    tweets_without_responses = await get_tweet(response_status="pending")
    
    response_count = 0
    for tweet in tweets_without_responses:
        await generate_response(tweet.id)
        response_count += 1
    
    return response_count