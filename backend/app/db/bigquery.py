from google.cloud.bigquery import Client
from app.core.config import Settings

bq_client = Client()

def get_bq_client():
    return Client(project=Settings.GOOGLE_CLOUD_PROJECT)

# HUMAN ASSISTANCE NEEDED
# This function needs review for production readiness and error handling
def run_query(query: str) -> list:
    client = get_bq_client()
    query_job = client.query(query)
    results = query_job.result()
    return [dict(row) for row in results]

# HUMAN ASSISTANCE NEEDED
# This function needs review for production readiness, error handling, and data validation
def insert_tweet_analytics(analytics_data: dict) -> bool:
    client = get_bq_client()
    table_id = f"{Settings.GOOGLE_CLOUD_PROJECT}.tweet_analytics.tweets"
    
    errors = client.insert_rows_json(table_id, [analytics_data])
    
    if errors:
        print(f"Errors occurred while inserting rows: {errors}")
        return False
    return True