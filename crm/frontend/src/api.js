const BASE = "/api";

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
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
