const BASE = "/api";

// Called by the auth handler when a 401 is detected
let _onUnauthorized = null;
export const setUnauthorizedHandler = (fn) => { _onUnauthorized = fn; };

function getToken() {
  return localStorage.getItem("crm_token");
}

async function request(method, path, body) {
  const token = getToken();
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    if (_onUnauthorized) _onUnauthorized();
    throw new Error("Session expirée, veuillez vous reconnecter");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Erreur serveur");
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Apporteurs
  getApporteurs: () => request("GET", "/apporteurs/"),
  getApporteur: (id) => request("GET", `/apporteurs/${id}`),
  createApporteur: (data) => request("POST", "/apporteurs/", data),
  updateApporteur: (id, data) => request("PUT", `/apporteurs/${id}`, data),
  deleteApporteur: (id) => request("DELETE", `/apporteurs/${id}`),

  // Opportunites
  getOpportunites: () => request("GET", "/opportunites/"),
  getOpportunite: (id) => request("GET", `/opportunites/${id}`),
  createOpportunite: (data) => request("POST", "/opportunites/", data),
  updateOpportunite: (id, data) => request("PUT", `/opportunites/${id}`, data),
  deleteOpportunite: (id) => request("DELETE", `/opportunites/${id}`),

  // Commissions
  getCommissions: () => request("GET", "/commissions/"),
  marquerPaye: (id) => request("PUT", `/commissions/${id}/marquer-paye`),

  // Dashboard
  getDashboard: () => request("GET", "/dashboard/"),
};
