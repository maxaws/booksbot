import { useEffect, useState } from "react";
import { api } from "../api";

const STATUTS = [
  { value: "nouveau",   label: "Nouveau",    cls: "badge-nouveau" },
  { value: "en_cours",  label: "En cours",   cls: "badge-en_cours" },
  { value: "gagne",     label: "Gagné",      cls: "badge-gagne" },
  { value: "perdu",     label: "Perdu",      cls: "badge-perdu" },
];

const fmt = (n) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);
const fmtDate = (d) => d ? new Date(d).toLocaleDateString("fr-FR") : "—";

function Badge({ statut }) {
  const s = STATUTS.find((s) => s.value === statut) || { label: statut, cls: "" };
  return <span className={`badge ${s.cls}`}>{s.label}</span>;
}

function OpportuniteModal({ opportunite, apporteurs, onClose, onSave }) {
  const isEdit = Boolean(opportunite?.id);
  const [form, setForm] = useState(
    isEdit
      ? { ...opportunite }
      : { apporteur_id: apporteurs[0]?.id || "", nom_prospect: "", societe_prospect: "", montant_estime: 0, statut: "nouveau", description: "" }
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload = { ...form, apporteur_id: Number(form.apporteur_id), montant_estime: Number(form.montant_estime) };
      isEdit ? await api.updateOpportunite(opportunite.id, payload) : await api.createOpportunite(payload);
      onSave();
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
          <div className="modal-title">{isEdit ? "Modifier l'opportunité" : "Nouvelle opportunité"}</div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {error && <div className="alert alert-danger">{error}</div>}
          <form onSubmit={submit}>
            <div className="form-group">
              <label className="form-label">Apporteur <span>*</span></label>
              <select className="form-control" value={form.apporteur_id} onChange={(e) => set("apporteur_id", e.target.value)} required>
                {apporteurs.map((a) => (
                  <option key={a.id} value={a.id}>{a.prenom} {a.nom}</option>
                ))}
              </select>
            </div>
            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Nom du prospect <span>*</span></label>
                <input className="form-control" value={form.nom_prospect} onChange={(e) => set("nom_prospect", e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">Société du prospect</label>
                <input className="form-control" value={form.societe_prospect || ""} onChange={(e) => set("societe_prospect", e.target.value)} />
              </div>
            </div>
            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Montant estimé (€) <span>*</span></label>
                <input
                  className="form-control"
                  type="number"
                  min="0" step="100"
                  value={form.montant_estime}
                  onChange={(e) => set("montant_estime", e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Statut <span>*</span></label>
                <select className="form-control" value={form.statut} onChange={(e) => set("statut", e.target.value)}>
                  {STATUTS.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Description / Notes</label>
              <textarea className="form-control" value={form.description || ""} onChange={(e) => set("description", e.target.value)} />
            </div>
            {isEdit && form.statut === "gagne" && (
              <div className="alert alert-success" style={{ marginBottom: 16 }}>
                ✅ Une commission sera automatiquement calculée à la sauvegarde.
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

export default function Opportunites() {
  const [opps, setOpps] = useState([]);
  const [apporteurs, setApporteurs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [filterStatut, setFilterStatut] = useState("");
  const [modal, setModal] = useState(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.getOpportunites(), api.getApporteurs()])
      .then(([o, a]) => { setOpps(o); setApporteurs(a); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleDelete = async (o) => {
    if (!confirm(`Supprimer l'opportunité "${o.nom_prospect}" ?`)) return;
    try { await api.deleteOpportunite(o.id); load(); }
    catch (e) { alert(e.message); }
  };

  const filtered = opps.filter((o) => {
    const q = search.toLowerCase();
    const matchText = `${o.nom_prospect} ${o.societe_prospect || ""} ${o.apporteur_nom} ${o.apporteur_prenom}`.toLowerCase().includes(q);
    const matchStatut = !filterStatut || o.statut === filterStatut;
    return matchText && matchStatut;
  });

  return (
    <>
      {modal !== null && (
        <OpportuniteModal
          opportunite={modal === "new" ? null : modal}
          apporteurs={apporteurs}
          onClose={() => setModal(null)}
          onSave={() => { setModal(null); load(); }}
        />
      )}

      <div className="page-header">
        <div>
          <div className="page-title">Opportunités</div>
          <div className="page-subtitle">{opps.length} opportunité{opps.length !== 1 ? "s" : ""}</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="search-bar">
            <span>🔍</span>
            <input placeholder="Rechercher…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select
            className="form-control"
            style={{ width: "auto" }}
            value={filterStatut}
            onChange={(e) => setFilterStatut(e.target.value)}
          >
            <option value="">Tous les statuts</option>
            {STATUTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <button className="btn btn-primary" onClick={() => setModal("new")} disabled={apporteurs.length === 0}>
            + Nouvelle opportunité
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {apporteurs.length === 0 && !loading && (
        <div className="alert alert-danger">Ajoutez d'abord un apporteur avant de créer une opportunité.</div>
      )}

      <div className="card">
        <div className="table-wrap">
          {loading ? (
            <div className="spinner" />
          ) : filtered.length === 0 ? (
            <div className="empty-state">
              <div className="icon">🎯</div>
              <p>{search || filterStatut ? "Aucun résultat" : "Aucune opportunité enregistrée"}</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Prospect</th>
                  <th>Apporteur</th>
                  <th>Montant estimé</th>
                  <th>Statut</th>
                  <th>Date création</th>
                  <th>Clôture</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <div className="fw-600">{o.nom_prospect}</div>
                      {o.societe_prospect && <div className="text-muted text-sm">{o.societe_prospect}</div>}
                    </td>
                    <td>{o.apporteur_prenom} {o.apporteur_nom}</td>
                    <td className="fw-600">{fmt(o.montant_estime)}</td>
                    <td><Badge statut={o.statut} /></td>
                    <td className="text-muted">{fmtDate(o.date_creation)}</td>
                    <td className="text-muted">{fmtDate(o.date_cloture)}</td>
                    <td>
                      <div className="flex gap-2">
                        <button className="btn btn-secondary btn-sm" onClick={() => setModal(o)}>Modifier</button>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(o)}>Suppr.</button>
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
