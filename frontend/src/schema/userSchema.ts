import { z } from 'zod';

export interface User {
  user_id: string;
  username: string;
  display_name: string;
  followers_count: number;
  created_at: Date;
}

export const userSchema = z.object({
  user_id: z.string(),
  username: z.string(),
  display_name: z.string(),
  followers_count: z.number(),
  created_at: z.date()
});