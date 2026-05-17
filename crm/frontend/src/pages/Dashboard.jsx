import { useEffect, useState } from "react";
import { api } from "../api";

const fmt = (n) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

function StatCard({ icon, label, value, color, sub }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${color}`}>{icon}</div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        {sub && <div className="text-muted text-sm" style={{ marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getDashboard()
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!stats) return <div className="spinner" />;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Tableau de bord</div>
          <div className="page-subtitle">Vue d'ensemble de l'activité des apporteurs</div>
        </div>
      </div>

      <div className="stat-grid">
        <StatCard
          icon="👥"
          color="blue"
          label="Apporteurs actifs"
          value={stats.total_apporteurs}
        />
        <StatCard
          icon="🎯"
          color="amber"
          label="Opportunités en cours"
          value={stats.opportunites_en_cours}
        />
        <StatCard
          icon="📈"
          color="green"
          label="CA gagné"
          value={fmt(stats.ca_gagne)}
        />
        <StatCard
          icon="💰"
          color="red"
          label="Commissions dues"
          value={fmt(stats.commissions_dues)}
        />
      </div>

      <div className="card">
        <div className="card-header">🏆 Top 5 apporteurs (CA gagné)</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Apporteur</th>
                <th>Affaires gagnées</th>
                <th>CA total</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_apporteurs.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-state">
                      <div className="icon">🎯</div>
                      <p>Aucune affaire gagnée pour l'instant</p>
                    </div>
                  </td>
                </tr>
              ) : (
                stats.top_apporteurs.map((a, i) => (
                  <tr key={a.id}>
                    <td>
                      <span style={{ fontWeight: 700, color: i === 0 ? "#f59e0b" : "inherit" }}>
                        {i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `${i + 1}.`}
                      </span>
                    </td>
                    <td className="fw-600">{a.prenom} {a.nom}</td>
                    <td>{a.nb_affaires}</td>
                    <td className="fw-600" style={{ color: "var(--success)" }}>{fmt(a.ca_total)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
