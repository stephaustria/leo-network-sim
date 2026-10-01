const explicit = import.meta.env.VITE_API_URL;

// 1) explicit override, 2) same-origin /api in production builds (nginx proxies it),
// 3) the local backend during `npm run dev`
export const API_URL = explicit
  ? explicit
  : import.meta.env.PROD
    ? `${window.location.origin}/api`
    : "http://127.0.0.1:8000";

export const WS_URL = API_URL.replace(/^http/, "ws");