from tweepy import StreamListener, OAuthHandler, API
from app.core.config import Settings
from app.db.firestore import add_tweet
from app.schema.tweet import Tweet

settings = Settings()

class TwitterStreamListener(StreamListener):
    def __init__(self):
        super().__init__()
        # Initialize any necessary attributes

    # HUMAN ASSISTANCE NEEDED
    # The confidence level for this function is below 0.8. Please review and adjust as needed.
    def on_status(self, status):
        # Extract relevant information from the status
        tweet_data = {
            'id': status.id_str,
            'text': status.text,
            'user': status.user.screen_name,
            'created_at': status.created_at
        }
        
        # Create a Tweet object
        tweet = Tweet(**tweet_data)
        
        # Add the tweet to the database
        add_tweet(tweet)
        
        # Return True to continue processing
        return True

# HUMAN ASSISTANCE NEEDED
# The confidence level for this function is below 0.8. Please review and adjust as needed.
def start_twitter_stream():
    # Set up OAuth authentication
    auth = OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
    auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_ACCESS_TOKEN_SECRET)
    
    # Create API object
    api = API(auth)
    
    # Initialize TwitterStreamListener
    listener = TwitterStreamListener()
    
    # Start streaming with specified filters
    stream = tweepy.Stream(auth=api.auth, listener=listener)
    stream.filter(track=settings.TWITTER_TRACK_KEYWORDS)