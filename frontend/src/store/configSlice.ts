import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Config } from '../schema/configSchema';

interface ConfigState {
  config: Config;
  status: string;
  error: string | null;
}

const initialState: ConfigState = {
  config: {} as Config,
  status: 'idle',
  error: null,
};

const configSlice = createSlice({
  name: 'config',
  initialState,
  reducers: {
    updateConfig: (state, action: PayloadAction<Partial<Config>>) => {
      state.config = { ...state.config, ...action.payload };
      state.status = 'updated';
      state.error = null;
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.status = 'error';
    },
  },
});

export const { updateConfig, setError } = configSlice.actions;
export default configSlice.reducer;

// HUMAN ASSISTANCE NEEDED
// Consider adding additional actions or thunks for async operations
// related to fetching or saving configuration data if required.