import { generateResponse } from 'app/services/api';

export const generateTweetResponse = async (tweetId: string): Promise<string> => {
  try {
    const response = await generateResponse(tweetId);
    return response;
  } catch (error) {
    // HUMAN ASSISTANCE NEEDED
    // Error handling strategy needs to be defined. 
    // Consider logging the error and returning a default message or re-throwing the error.
    console.error('Error generating tweet response:', error);
    throw new Error('Failed to generate tweet response');
  }
};