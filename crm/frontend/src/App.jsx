import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Apporteurs from "./pages/Apporteurs";
import Opportunites from "./pages/Opportunites";
import Commissions from "./pages/Commissions";

export default function App() {
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
