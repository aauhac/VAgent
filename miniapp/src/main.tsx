import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { getUserIdentity } from './lib/userIdentity';
import { loginWithTossApp } from './lib/tossAuth';
import { recoverPendingPurchases } from './lib/tossIap';
import './styles/app.css';

void (async () => {
  await getUserIdentity().catch(() => undefined);
  await loginWithTossApp().catch(() => undefined);
  await recoverPendingPurchases().catch(() => undefined);
})();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
