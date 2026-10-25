/**
 * Fetch wrapper for authenticated backend calls.
 * Adds the bearer token and signs the user out when the backend rejects it (401).
 */

import { API_BASE_URL } from '../config/api';
import { clearSession, getAccessToken } from './authService';

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getAccessToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    // Token missing or expired: drop the local session and return to the login page
    clearSession();
    window.location.reload();
  }
  return res;
}
