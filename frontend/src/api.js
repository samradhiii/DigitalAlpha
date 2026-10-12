const TOKEN_KEY = "recon_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Turns DRF error bodies ({detail}, {field: [msgs]}) into one readable message.
function errorMessage(body, status) {
  if (!body) return `Request failed (${status}).`;
  if (typeof body.detail === "string") return body.detail;
  const parts = Object.entries(body).map(([field, msgs]) => {
    const text = Array.isArray(msgs) ? msgs.join(" ") : String(msgs);
    return field === "non_field_errors" ? text : `${field}: ${text}`;
  });
  return parts.join(" ") || `Request failed (${status}).`;
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export async function request(path, { method = "GET", json, formData } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (formData) {
    body = formData;
  }

  let response;
  try {
    response = await fetch(`/api${path}`, { method, headers, body });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0);
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    throw new ApiError(errorMessage(data, response.status), response.status);
  }
  return data;
}

export const api = {
  login: (username, password) => request("/auth/login/", { method: "POST", json: { username, password } }),
  logout: () => request("/auth/logout/", { method: "POST" }),
  me: () => request("/me/"),
  investors: () => request("/investors/"),
  capitalCalls: () => request("/capital-calls/"),
  imports: () => request("/imports/"),
  importDetail: (id) => request(`/imports/${id}/`),
  uploadStatement: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/imports/", { method: "POST", formData });
  },
  transactions: (params = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return request(`/transactions/${query ? `?${query}` : ""}`);
  },
  act: (id, action, payload = {}) => request(`/transactions/${id}/${action}/`, { method: "POST", json: payload }),
};
