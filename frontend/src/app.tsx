import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Provider } from 'react-redux';
import Dashboard from '@/components/Dashboard';
import TweetManagement from '@/components/TweetManagement';
import Analytics from '@/components/Analytics';
import Configuration from '@/components/Configuration';
import { store } from '@/store';
import { setupInterceptors } from '@/services/api';

const App: React.FC = () => {
  useEffect(() => {
    setupInterceptors();
  }, []);

  return (
    <Provider store={store}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/tweets" element={<TweetManagement />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/configuration" element={<Configuration />} />
        </Routes>
      </BrowserRouter>
    </Provider>
  );
};

export default App;