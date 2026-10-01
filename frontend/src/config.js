export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
export const WS_URL = API_URL.replace(/^http/, "ws");