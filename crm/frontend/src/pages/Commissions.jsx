import { useEffect, useState } from "react";
import { api } from "../api";

const fmt = (n) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);
const fmtDate = (d) => d ? new Date(d).toLocaleDateString("fr-FR") : "—";

export default function Commissions() {
  const [commissions, setCommissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const [paying, setPaying] = useState(null);

  const load = () => {
    setLoading(true);
    api.getCommissions()
      .then(setCommissions)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handlePay = async (c) => {
    if (!confirm(`Marquer la commission de ${fmt(c.montant)} comme payée ?`)) return;
    setPaying(c.id);
    try {
      await api.marquerPaye(c.id);
      load();
    } catch (e) {
      alert(e.message);
    } finally {
      setPaying(null);
    }
  };

  const filtered = filter ? commissions.filter((c) => c.statut_paiement === filter) : commissions;

  const totalDues = commissions
    .filter((c) => c.statut_paiement === "en_attente")
    .reduce((s, c) => s + c.montant, 0);

  const totalPaye = commissions
    .filter((c) => c.statut_paiement === "paye")
    .reduce((s, c) => s + c.montant, 0);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Commissions</div>
          <div className="page-subtitle">Suivi des commissions dues aux apporteurs</div>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="form-control"
            style={{ width: "auto" }}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="">Toutes</option>
            <option value="en_attente">En attente</option>
            <option value="paye">Payées</option>
          </select>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-icon amber">💳</div>
          <div>
            <div className="stat-label">Commissions dues</div>
            <div className="stat-value" style={{ color: "var(--warning)" }}>{fmt(totalDues)}</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon green">✅</div>
          <div>
            <div className="stat-label">Commissions payées</div>
            <div className="stat-value" style={{ color: "var(--success)" }}>{fmt(totalPaye)}</div>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card">
        <div className="table-wrap">
          {loading ? (
            <div className="spinner" />
          ) : filtered.length === 0 ? (
            <div className="empty-state">
              <div className="icon">💰</div>
              <p>Aucune commission{filter ? " dans ce filtre" : " — les commissions apparaissent quand une opportunité est gagnée"}</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Apporteur</th>
                  <th>Prospect</th>
                  <th>Montant affaire</th>
                  <th>Commission</th>
                  <th>Statut</th>
                  <th>Calculée le</th>
                  <th>Payée le</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id}>
                    <td className="fw-600">{c.apporteur_prenom} {c.apporteur_nom}</td>
                    <td>
                      <div>{c.prospect_nom}</div>
                      {c.prospect_societe && <div className="text-muted text-sm">{c.prospect_societe}</div>}
                    </td>
                    <td>{fmt(c.montant_affaire)}</td>
                    <td className="fw-600" style={{ color: "var(--primary)" }}>{fmt(c.montant)}</td>
                    <td>
                      <span className={`badge badge-${c.statut_paiement}`}>
                        {c.statut_paiement === "paye" ? "Payée" : "En attente"}
                      </span>
                    </td>
                    <td className="text-muted">{fmtDate(c.date_calcul)}</td>
                    <td className="text-muted">{fmtDate(c.date_paiement)}</td>
                    <td>
                      {c.statut_paiement === "en_attente" && (
                        <button
                          className="btn btn-success btn-sm"
                          disabled={paying === c.id}
                          onClick={() => handlePay(c)}
                        >
                          {paying === c.id ? "…" : "Marquer payée"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}
