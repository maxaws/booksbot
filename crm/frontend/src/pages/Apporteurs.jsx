import { useEffect, useState } from "react";
import { api } from "../api";

const fmt = (n) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

function ApporteurModal({ apporteur, onClose, onSave }) {
  const isEdit = Boolean(apporteur?.id);
  const [form, setForm] = useState(
    apporteur?.id
      ? { ...apporteur }
      : { nom: "", prenom: "", email: "", telephone: "", societe: "", taux_commission: 10, actif: true }
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const saved = isEdit
        ? await api.updateApporteur(apporteur.id, form)
        : await api.createApporteur(form);
      onSave(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">{isEdit ? "Modifier l'apporteur" : "Nouvel apporteur"}</div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {error && <div className="alert alert-danger">{error}</div>}
          <form onSubmit={submit}>
            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Prénom <span>*</span></label>
                <input className="form-control" value={form.prenom} onChange={(e) => set("prenom", e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">Nom <span>*</span></label>
                <input className="form-control" value={form.nom} onChange={(e) => set("nom", e.target.value)} required />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Email <span>*</span></label>
              <input className="form-control" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} required />
            </div>
            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Téléphone</label>
                <input className="form-control" value={form.telephone || ""} onChange={(e) => set("telephone", e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Société</label>
                <input className="form-control" value={form.societe || ""} onChange={(e) => set("societe", e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Taux de commission (%) <span>*</span></label>
              <input
                className="form-control"
                type="number"
                min="0" max="100" step="0.5"
                value={form.taux_commission}
                onChange={(e) => set("taux_commission", parseFloat(e.target.value))}
                required
              />
            </div>
            {isEdit && (
              <div className="form-group">
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                  <input type="checkbox" checked={form.actif} onChange={(e) => set("actif", e.target.checked)} />
                  Apporteur actif
                </label>
              </div>
            )}
            <div className="form-actions">
              <button type="button" className="btn btn-secondary" onClick={onClose}>Annuler</button>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "Enregistrement…" : "Enregistrer"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function Apporteurs() {
  const [apporteurs, setApporteurs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(null); // null | "new" | apporteur obj

  const load = () => {
    setLoading(true);
    api.getApporteurs()
      .then(setApporteurs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleSave = () => { setModal(null); load(); };

  const handleDelete = async (a) => {
    if (!confirm(`Supprimer ${a.prenom} ${a.nom} ?`)) return;
    try {
      await api.deleteApporteur(a.id);
      load();
    } catch (e) {
      alert(e.message);
    }
  };

  const filtered = apporteurs.filter((a) =>
    `${a.prenom} ${a.nom} ${a.email} ${a.societe || ""}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      {modal !== null && (
        <ApporteurModal
          apporteur={modal === "new" ? null : modal}
          onClose={() => setModal(null)}
          onSave={handleSave}
        />
      )}

      <div className="page-header">
        <div>
          <div className="page-title">Apporteurs d'affaires</div>
          <div className="page-subtitle">{apporteurs.length} apporteur{apporteurs.length !== 1 ? "s" : ""} enregistré{apporteurs.length !== 1 ? "s" : ""}</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="search-bar">
            <span>🔍</span>
            <input placeholder="Rechercher…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={() => setModal("new")}>+ Nouvel apporteur</button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card">
        <div className="table-wrap">
          {loading ? (
            <div className="spinner" />
          ) : filtered.length === 0 ? (
            <div className="empty-state">
              <div className="icon">👥</div>
              <p>{search ? "Aucun résultat" : "Ajoutez votre premier apporteur"}</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Société</th>
                  <th>Contact</th>
                  <th>Commission</th>
                  <th>CA généré</th>
                  <th>Opportunités</th>
                  <th>Statut</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="fw-600">{a.prenom} {a.nom}</div>
                    </td>
                    <td className="text-muted">{a.societe || "—"}</td>
                    <td>
                      <div>{a.email}</div>
                      {a.telephone && <div className="text-muted text-sm">{a.telephone}</div>}
                    </td>
                    <td className="fw-600">{a.taux_commission}%</td>
                    <td className="fw-600" style={{ color: "var(--success)" }}>{fmt(a.ca_total)}</td>
                    <td>{a.nombre_opportunites}</td>
                    <td>
                      <span className={`badge ${a.actif ? "badge-gagne" : "badge-perdu"}`}>
                        {a.actif ? "Actif" : "Inactif"}
                      </span>
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <button className="btn btn-secondary btn-sm" onClick={() => setModal(a)}>Modifier</button>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(a)}>Suppr.</button>
                      </div>
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
