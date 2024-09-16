import { configureStore } from '@reduxjs/toolkit';
import { tweetReducer } from './tweetSlice';
import { configReducer } from './configSlice';

export const setupStore = () => {
  return configureStore({
    reducer: {
      tweets: tweetReducer,
      config: configReducer,
    },
    // Add any middleware or enhancers here if needed
  });
};

export const store = setupStore();

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;