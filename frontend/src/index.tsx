import React from 'react';
import ReactDOM from 'react-dom';
import { Provider } from 'react-redux';
import App from '@/app';
import { store } from '@/store';
import { setupInterceptors } from '@/services/api';

const rootElement = document.getElementById('root');

const renderApp = () => {
  setupInterceptors();

  ReactDOM.render(
    <React.StrictMode>
      <Provider store={store}>
        <App />
      </Provider>
    </React.StrictMode>,
    rootElement
  );
};

renderApp();