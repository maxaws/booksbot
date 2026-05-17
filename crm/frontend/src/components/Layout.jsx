import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/dashboard",    icon: "📊", label: "Tableau de bord" },
  { to: "/apporteurs",   icon: "👥", label: "Apporteurs" },
  { to: "/opportunites", icon: "🎯", label: "Opportunités" },
  { to: "/commissions",  icon: "💰", label: "Commissions" },
];

export default function Layout({ children }) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="brand">One System</div>
          <div className="sub">CRM Apporteurs d'affaires</div>
        </div>
        <nav className="sidebar-nav">
          {NAV.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}
            >
              <span className="nav-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>
        <div style={{ padding: "16px 20px", fontSize: "11px", color: "#475569" }}>
          v1.0.0 — One System © 2025
        </div>
      </aside>
      <main className="main-content">
        <div className="page">{children}</div>
      </main>
    </div>
  );
}
