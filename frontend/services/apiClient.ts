/**
 * Fetch wrapper for authenticated backend calls.
 * The session token is an HttpOnly cookie the browser sends itself (scripts can't read it);
 * every call also carries the CSRF header the backend requires for cookie-authenticated writes.
 * Signs the user out when the backend rejects the session (401).
 */

import { API_BASE_URL } from '../config/api';
import { clearSession } from './authService';

export const CSRF_HEADERS = { 'X-Requested-With': 'fetch' };

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json');
  }
  Object.entries(CSRF_HEADERS).forEach(([k, v]) => headers.set(k, v));

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: 'include' });

  if (res.status === 401) {
    // Session missing, expired or revoked: drop the local profile and return to the login page
    clearSession();
    window.location.reload();
  }
  return res;
}
