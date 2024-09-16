import { fetchTweets, fetchTweetById } from 'app/services/api';

export interface Tweet {
  // Define the Tweet interface based on the actual structure
  id: string;
  text: string;
  // Add other properties as needed
}

export async function getLatestTweets(count: number): Promise<Tweet[]> {
  try {
    const tweets = await fetchTweets(count);
    return tweets;
  } catch (error) {
    console.error('Error fetching latest tweets:', error);
    throw error;
  }
}

export async function getTweetDetails(tweetId: string): Promise<Tweet> {
  try {
    const tweetDetails = await fetchTweetById(tweetId);
    return tweetDetails;
  } catch (error) {
    console.error('Error fetching tweet details:', error);
    throw error;
  }
}