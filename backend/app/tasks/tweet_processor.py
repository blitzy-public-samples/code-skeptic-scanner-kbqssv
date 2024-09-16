from tweepy import StreamListener
from app.db.firestore import add_tweet
from app.schema.tweet import Tweet
from app.services.llm_service import LLMService
from app.core.config import Settings

settings = Settings()

class TweetStreamListener(StreamListener):
    llm_service: LLMService

    def __init__(self):
        super().__init__()
        self.llm_service = LLMService()

    # HUMAN ASSISTANCE NEEDED
    # The following function needs review for production readiness
    def on_status(self, status):
        # Extract relevant information from the status
        tweet_id = status.id_str
        text = status.text
        user = status.user.screen_name
        created_at = status.created_at
        retweet_count = status.retweet_count
        favorite_count = status.favorite_count

        # Check if tweet meets popularity threshold
        if retweet_count + favorite_count < settings.POPULARITY_THRESHOLD:
            return True

        # Calculate doubt rating using LLMService
        doubt_rating = self.llm_service.calculate_doubt_rating(text)

        # Create a Tweet object
        tweet = Tweet(
            id=tweet_id,
            text=text,
            user=user,
            created_at=created_at,
            retweet_count=retweet_count,
            favorite_count=favorite_count,
            doubt_rating=doubt_rating
        )

        # Add the tweet to the database
        add_tweet(tweet)

        return True

# HUMAN ASSISTANCE NEEDED
# The following function needs review for production readiness
def start_tweet_stream():
    import tweepy

    # Set up OAuth authentication using settings
    auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
    auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_ACCESS_TOKEN_SECRET)

    # Create tweepy API object
    api = tweepy.API(auth)

    # Initialize TweetStreamListener
    listener = TweetStreamListener()

    # Start streaming with specified filters
    stream = tweepy.Stream(auth=api.auth, listener=listener)
    stream.filter(track=settings.TWITTER_TRACK_KEYWORDS)