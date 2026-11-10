// Thin client for the FastAPI backend. The token is kept in localStorage on this device.
const TOKEN_KEY = "hr_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", json, form } = {}) {
  const headers = { Authorization: `Bearer ${getToken()}` };
  let body;
  if (json) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  let res;
  try {
    res = await fetch(`/api${path}`, { method, headers, body });
  } catch {
    throw new ApiError(0, "אין חיבור לשרת. בדקו את האינטרנט ונסו שוב.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : null;
    throw new ApiError(res.status, translateError(res.status, detail));
  }
  return data;
}

// Backend messages are in English; show the user Hebrew.
function translateError(status, detail) {
  if (status === 401) return "קוד הכניסה שגוי.";
  if (status === 413) return "הקובץ גדול מדי (עד 20MB).";
  if (detail?.includes("Unsupported file type"))
    return "סוג הקובץ לא נתמך. אפשר PDF, Word או תמונה.";
  if (detail?.includes("private or internal")) return "אי אפשר להוסיף את הקישור הזה.";
  if (detail?.includes("Could not find")) return "האתר לא נמצא. בדקו שהקישור נכון.";
  if (detail?.includes("http")) return "יש להדביק קישור שמתחיל ב-https://";
  if (status === 422) return "הקישור לא תקין. העתיקו אותו שוב מהדפדפן.";
  return "משהו השתבש. נסו שוב.";
}

export const api = {
  health: () => request("/health"),
  list: () => request("/articles"),
  usage: () => request("/usage"),
  addUrl: (url) => request("/articles/url", { method: "POST", json: { url } }),
  addFile: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/articles/file", { method: "POST", form });
  },
  update: (id, fields) => request(`/articles/${id}`, { method: "PATCH", json: fields }),
  remove: (id) => request(`/articles/${id}`, { method: "DELETE" }),
  // <audio> can't send headers, so the token goes in the query string.
  audioUrl: (id) => `/api/articles/${id}/audio?token=${encodeURIComponent(getToken())}`,
};
