import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./contexts/AuthContext";
import { setUnauthorizedHandler } from "./api";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Apporteurs from "./pages/Apporteurs";
import Opportunites from "./pages/Opportunites";
import Commissions from "./pages/Commissions";
import Login from "./pages/Login";

export default function App() {
  const { isAuthenticated, logout } = useAuth();

  // Wire API 401 → auto-logout
  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  if (!isAuthenticated) return <Login />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/apporteurs" element={<Apporteurs />} />
        <Route path="/opportunites" element={<Opportunites />} />
        <Route path="/commissions" element={<Commissions />} />
      </Routes>
    </Layout>
  );
}
