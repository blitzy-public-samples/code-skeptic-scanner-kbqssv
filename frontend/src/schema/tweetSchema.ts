import { z } from 'zod';

export interface Tweet {
  tweet_id: string;
  content: string;
  user_id: string;
  timestamp: Date;
  likes_count: number;
  retweets_count: number;
  doubt_rating: number;
  ai_tools: string[];
  media_urls: string[];
  quoted_tweet_id: string | null;
}

export const tweetSchema = z.object({
  tweet_id: z.string(),
  content: z.string(),
  user_id: z.string(),
  timestamp: z.date(),
  likes_count: z.number(),
  retweets_count: z.number(),
  doubt_rating: z.number(),
  ai_tools: z.array(z.string()),
  media_urls: z.array(z.string()),
  quoted_tweet_id: z.string().nullable(),
});

// HUMAN ASSISTANCE NEEDED
// Please review the tweetSchema to ensure it meets all production requirements.
// Consider adding additional validation rules if necessary, such as:
// - Maximum length for content
// - Range for doubt_rating (e.g., 0 to 100)
// - Format validation for tweet_id and user_id if they follow specific patterns