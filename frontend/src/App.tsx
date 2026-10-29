// src/App.tsx — routes. Every page reads the FastAPI backend through src/lib/api.ts.
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { setUnauthorizedHandler } from './lib/api';
import Layout from './components/Layout';
import SignIn from './pages/SignIn';
import Overview from './pages/Overview';
import LiveMonitor from './pages/LiveMonitor';
import Devices from './pages/Devices';
import Alerts from './pages/Alerts';
import DecisionLab from './pages/DecisionLab';
import ModelData from './pages/ModelData';
import Audit from './pages/Audit';
import SystemInfo from './pages/SystemInfo';
import Admin from './pages/Admin';
import Project from './pages/Project';
import Trace from './pages/Trace';
import MultiCloud from './pages/MultiCloud';

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 3_000 } } });

function RequireAuth({ children, roles }: { children: ReactNode; roles?: string[] }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function SessionWatcher() {
  const { logout } = useAuth();
  const nav = useNavigate();
  useEffect(() => setUnauthorizedHandler(() => { logout(); nav('/login'); }), [logout, nav]);
  return null;
}

function AppRoutes() {
  const { user } = useAuth();
  return (
    <>
      <SessionWatcher />
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <SignIn />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Overview />} />
          <Route path="project" element={<Project />} />
          <Route path="events" element={<LiveMonitor />} />
          <Route path="trace" element={<Trace />} />
          <Route path="trace/:id" element={<Trace />} />
          <Route path="multi-cloud" element={<MultiCloud />} />
          <Route path="devices" element={<Devices />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="decision-lab" element={<DecisionLab />} />
          <Route path="model" element={<ModelData />} />
          <Route path="audit" element={<RequireAuth roles={['admin', 'auditor']}><Audit /></RequireAuth>} />
          <Route path="system" element={<SystemInfo />} />
          <Route path="admin" element={<RequireAuth roles={['admin']}><Admin /></RequireAuth>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider><BrowserRouter><AppRoutes /></BrowserRouter></AuthProvider>
    </QueryClientProvider>
  );
}
