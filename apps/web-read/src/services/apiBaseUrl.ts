export const API_BASE_URL = import.meta.env.VITE_API_READ_BASE_URL
  ?? (import.meta.env.DEV ? "http://127.0.0.1:5001" : "");
