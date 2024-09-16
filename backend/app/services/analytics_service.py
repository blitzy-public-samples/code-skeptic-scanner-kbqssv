from pandas import DataFrame
from app.db.bigquery import run_query
from app.core.config import Settings

settings = Settings()

# HUMAN ASSISTANCE NEEDED
# The following functions have a confidence level below 0.8 and may need refinement for production readiness.
# Please review and adjust as necessary.

def get_tweet_analytics(start_date: str, end_date: str) -> dict:
    # Prepare SQL query for tweet analytics
    query = f"""
    SELECT 
        DATE(created_at) as date,
        COUNT(*) as tweet_count,
        AVG(retweet_count) as avg_retweets,
        AVG(favorite_count) as avg_favorites
    FROM 
        `{settings.BIGQUERY_DATASET}.tweets`
    WHERE 
        DATE(created_at) BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY 
        DATE(created_at)
    ORDER BY 
        date
    """

    # Execute query using BigQuery
    results = run_query(query)

    # Process query results using pandas
    df = DataFrame(results)

    # Calculate relevant metrics
    analytics_data = {
        'total_tweets': int(df['tweet_count'].sum()),
        'avg_daily_tweets': float(df['tweet_count'].mean()),
        'avg_retweets': float(df['avg_retweets'].mean()),
        'avg_favorites': float(df['avg_favorites'].mean()),
        'daily_breakdown': df.to_dict('records')
    }

    # Return processed analytics data
    return analytics_data

def get_user_analytics(start_date: str, end_date: str) -> dict:
    # Prepare SQL query for user analytics
    query = f"""
    SELECT 
        DATE(created_at) as date,
        COUNT(DISTINCT user_id) as active_users,
        AVG(followers_count) as avg_followers,
        AVG(friends_count) as avg_friends
    FROM 
        `{settings.BIGQUERY_DATASET}.tweets`
    WHERE 
        DATE(created_at) BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY 
        DATE(created_at)
    ORDER BY 
        date
    """

    # Execute query using BigQuery
    results = run_query(query)

    # Process query results using pandas
    df = DataFrame(results)

    # Calculate relevant metrics
    analytics_data = {
        'total_active_users': int(df['active_users'].sum()),
        'avg_daily_active_users': float(df['active_users'].mean()),
        'avg_followers': float(df['avg_followers'].mean()),
        'avg_friends': float(df['avg_friends'].mean()),
        'daily_breakdown': df.to_dict('records')
    }

    # Return processed analytics data
    return analytics_data