import axios from 'axios';
import { Tweet } from 'app/schema/tweet';
import { User } from 'app/schema/user';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL;

export const fetchTweets = async (page: number, limit: number): Promise<Tweet[]> => {
  const url = `${API_BASE_URL}/tweets?page=${page}&limit=${limit}`;
  const response = await axios.get(url);
  return response.data as Tweet[];
};

export const fetchTweetById = async (tweetId: string): Promise<Tweet> => {
  const url = `${API_BASE_URL}/tweets/${tweetId}`;
  const response = await axios.get(url);
  return response.data as Tweet;
};

// HUMAN ASSISTANCE NEEDED
// This function might need additional error handling and input validation
export const generateResponse = async (tweetId: string): Promise<string> => {
  const url = `${API_BASE_URL}/generate-response`;
  const response = await axios.post(url, { tweetId });
  return response.data.generatedResponse;
};