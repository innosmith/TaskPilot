import { type ReactNode } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import { AppLayout } from './layouts/AppLayout';
import { LoginPage } from './pages/LoginPage';
import { CockpitPage } from './pages/CockpitPage';
import { PipelinePage } from './pages/PipelinePage';
import { ProjectBoardPage } from './pages/ProjectBoardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { AgentQueuePage } from './pages/AgentQueuePage';
import { SettingsPage } from './pages/SettingsPage';
import { InboxPage } from './pages/InboxPage';

import { SignalePage } from './pages/SignalePage';
import { FinancePage } from './pages/FinancePage';
import DebtorsPage from './pages/DebtorsPage';
import CreditorsPage from './pages/CreditorsPage';

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PublicRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/cockpit" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            <PublicRoute>
              <LoginPage />
            </PublicRoute>
          }
        />

        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/cockpit" element={<CockpitPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
          <Route path="/agenten" element={<AgentQueuePage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectBoardPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/signale" element={<SignalePage />} />
          <Route path="/finanzen" element={<FinancePage />} />
          <Route path="/debitoren" element={<DebtorsPage />} />
          <Route path="/kreditoren" element={<CreditorsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        {/* Redirects für alte Routen und Default */}
        <Route path="/agent-queue" element={<Navigate to="/agenten" replace />} />
        <Route path="/memory" element={<Navigate to="/settings?tab=memory" replace />} />
        <Route path="*" element={<Navigate to="/cockpit" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
