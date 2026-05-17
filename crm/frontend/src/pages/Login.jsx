import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const body = new URLSearchParams({ username, password });
      const res = await fetch("/api/auth/login", { method: "POST", body });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Identifiants incorrects");
      }
      const data = await res.json();
      login(data.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}>
      <div style={{ width: "100%", maxWidth: 400, padding: "0 16px" }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>💼</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>One System CRM</div>
          <div style={{ color: "var(--text-muted)", marginTop: 4, fontSize: 13 }}>
            Connectez-vous pour accéder au CRM
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            {error && <div className="alert alert-danger">{error}</div>}
            <form onSubmit={submit}>
              <div className="form-group">
                <label className="form-label">Identifiant</label>
                <input
                  className="form-control"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label className="form-label">Mot de passe</label>
                <input
                  className="form-control"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
                disabled={loading}
              >
                {loading ? "Connexion…" : "Se connecter"}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
