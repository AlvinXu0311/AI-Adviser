// Use empty string for Docker (nginx proxy), or localhost for local dev
// VITE_BACKEND_URL="" means use relative paths (nginx will proxy /api to backend)
export const API_BASE_URL = (import.meta.env.VITE_BACKEND_URL !== undefined
  ? import.meta.env.VITE_BACKEND_URL
  : 'http://localhost:8000').replace(/\/$/, '');
