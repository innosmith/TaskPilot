import { Component, Suspense, lazy, type ReactNode } from 'react';
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

const LazyChatPage = lazy(() =>
  import('./pages/ChatPage').then(m => ({ default: m.ChatPage })),
);

interface ErrorBoundaryState { error: Error | null }

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 dark:bg-gray-950">
          <div className="w-full max-w-md rounded-xl border border-red-200 bg-white p-6 shadow-lg dark:border-red-800 dark:bg-gray-900">
            <h1 className="mb-2 text-lg font-semibold text-red-700 dark:text-red-400">Fehler beim Laden</h1>
            <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
              Die Anwendung konnte nicht geladen werden. Bitte versuche es erneut.
            </p>
            <pre className="mb-4 max-h-32 overflow-auto rounded-lg bg-gray-100 p-3 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
              {this.state.error.message}
            </pre>
            <button
              onClick={() => { this.setState({ error: null }); window.location.reload(); }}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Seite neu laden
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function SuspenseFallback() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
    </div>
  );
}

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
    <ErrorBoundary>
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
            <Route path="/agenten/chat" element={<Suspense fallback={<SuspenseFallback />}><LazyChatPage /></Suspense>} />
            <Route path="/agenten/chat/:conversationId" element={<Suspense fallback={<SuspenseFallback />}><LazyChatPage /></Suspense>} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectBoardPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/signale" element={<SignalePage />} />
            <Route path="/finanzen" element={<FinancePage />} />
            <Route path="/debitoren" element={<DebtorsPage />} />
            <Route path="/kreditoren" element={<CreditorsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>

          {/* Redirects fuer alte Routen und Default */}
          <Route path="/agent-queue" element={<Navigate to="/agenten" replace />} />
          <Route path="/memory" element={<Navigate to="/settings?tab=memory" replace />} />
          <Route path="*" element={<Navigate to="/cockpit" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
