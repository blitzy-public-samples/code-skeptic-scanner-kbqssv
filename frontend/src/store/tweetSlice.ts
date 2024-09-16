import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';
import { Tweet } from '../schema/tweetSchema';
import { api } from '../services/api';

// HUMAN ASSISTANCE NEEDED
// The fetchTweets function has a confidence level of 0.7, which is below the threshold of 0.8.
// Please review and adjust the implementation as needed.
export const fetchTweets = createAsyncThunk<Tweet[]>(
  'tweets/fetchTweets',
  async (_, { rejectWithValue }) => {
    try {
      const response = await api.get('/tweets');
      return response.data;
    } catch (error) {
      return rejectWithValue('Failed to fetch tweets');
    }
  }
);

interface TweetState {
  tweets: Tweet[];
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: TweetState = {
  tweets: [],
  status: 'idle',
  error: null,
};

const tweetSlice = createSlice({
  name: 'tweets',
  initialState,
  reducers: {
    addTweet: (state, action: PayloadAction<Tweet>) => {
      state.tweets.push(action.payload);
    },
    updateTweet: (state, action: PayloadAction<Tweet>) => {
      const index = state.tweets.findIndex(tweet => tweet.id === action.payload.id);
      if (index !== -1) {
        state.tweets[index] = action.payload;
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchTweets.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchTweets.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.tweets = action.payload;
      })
      .addCase(fetchTweets.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string;
      });
  },
});

export const { addTweet, updateTweet } = tweetSlice.actions;
export default tweetSlice.reducer;