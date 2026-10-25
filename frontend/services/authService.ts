/**
 * Authentication Service
 * Handles WPI user authentication via Microsoft SSO and session management
 */

import { AccountInfo } from '@azure/msal-browser';
import { msalInstance, loginRequest, isMsalConfigured } from '../config/msalConfig';
import { API_BASE_URL } from '../config/api';

export interface User {
  email: string;
  name: string;
  loginTime: Date;
  microsoftAccount?: AccountInfo;
}

const AUTH_STORAGE_KEY = 'wpi_adviser_auth';

// Backend sign-in response (POST /api/auth/demo-login, /api/auth/microsoft); the token itself
// arrives as an HttpOnly cookie and is never visible to this code
interface TokenResponse {
  expires_in: number;
  email: string;
  name: string;
}

export interface AuthConfig {
  demo_login: boolean;
  microsoft_login: boolean;
}

/**
 * Which sign-in methods the backend has enabled
 */
export async function getAuthConfig(): Promise<AuthConfig> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/config`);
    if (res.ok) return res.json();
  } catch (error) {
    console.error('[Auth] Failed to load auth config:', error);
  }
  return { demo_login: false, microsoft_login: false };
}

async function exchangeForSession(path: string, body: object, microsoftAccount?: AccountInfo): Promise<User> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
    body: JSON.stringify(body),
    credentials: 'include',
  });
  if (!res.ok) {
    const detail = await res.json().then((d) => d.detail).catch(() => '');
    throw new Error(detail || `Sign-in failed (${res.status})`);
  }
  const token: TokenResponse = await res.json();
  const user: User = { email: token.email, name: token.name, loginTime: new Date(), microsoftAccount };
  storeSession(user, token.expires_in);
  return user;
}

/**
 * Login with the demo account (only works when the backend has DEMO_LOGIN_ENABLED=true)
 */
export async function loginWithDemo(email: string, password: string): Promise<User> {
  return exchangeForSession('/api/auth/demo-login', { email, password });
}

/**
 * Login with Microsoft SSO (popup method)
 */
export async function loginWithMicrosoft(): Promise<User | null> {
  try {
    const response = await msalInstance.loginPopup(loginRequest);
    
    if (response && response.account) {
      const account = response.account;
      
      // Validate WPI email domain
      const email = account.username?.toLowerCase() || '';
      if (!isValidWPIEmail(email)) {
        // Sign out if not a WPI email
        await msalInstance.logoutPopup();
        throw new Error('Please use your WPI email address (@wpi.edu or @alumni.wpi.edu)');
      }
      
      // The backend verifies the ID token itself and issues its own access token
      return await exchangeForSession('/api/auth/microsoft', { id_token: response.idToken }, account);
    }
    return null;
  } catch (error) {
    console.error('[Auth] Microsoft login error:', error);
    throw error;
  }
}

/**
 * Login with Microsoft SSO (redirect method - alternative)
 */
export async function loginWithMicrosoftRedirect(): Promise<void> {
  try {
    await msalInstance.loginRedirect(loginRequest);
  } catch (error) {
    console.error('[Auth] Microsoft redirect login error:', error);
    throw error;
  }
}

/**
 * Logout from Microsoft SSO
 */
export async function logoutFromMicrosoft(): Promise<void> {
  try {
    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      await msalInstance.logoutPopup({
        account: accounts[0],
        postLogoutRedirectUri: window.location.origin,
      });
    }
    clearSession();
  } catch (error) {
    console.error('[Auth] Microsoft logout error:', error);
    clearSession();
  }
}

/**
 * Get current Microsoft account
 */
export function getMicrosoftAccount(): AccountInfo | null {
  const accounts = msalInstance.getAllAccounts();
  return accounts.length > 0 ? accounts[0] : null;
}

/**
 * Check if user is authenticated with Microsoft
 */
export function isMicrosoftAuthenticated(): boolean {
  return msalInstance.getAllAccounts().length > 0;
}

/**
 * Store the signed-in user's display profile (not a credential) in localStorage
 */
export function storeSession(user: User, expiresInSeconds: number): void {
  const session = {
    email: user.email,
    name: user.name,
    loginTime: user.loginTime.toISOString(),
    expiresAt: new Date(Date.now() + expiresInSeconds * 1000).toISOString(),
  };
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

/**
 * Ask the backend whether the session cookie is still valid (it may have been revoked)
 */
export async function verifySession(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, { credentials: 'include' });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Revoke the session server-side and clear the cookie
 */
export async function logoutFromBackend(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: { 'X-Requested-With': 'fetch' },
      credentials: 'include',
    });
  } catch (error) {
    console.error('[Auth] Backend logout failed:', error);
  }
}

/**
 * Get stored user session
 * Returns null if no valid session exists
 */
export function getStoredSession(): User | null {
  try {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!stored) return null;

    const session = JSON.parse(stored);
    const expiresAt = new Date(session.expiresAt);

    // Check if session has expired
    if (expiresAt < new Date()) {
      clearSession();
      return null;
    }

    // Also check if Microsoft account still exists
    const msAccount = getMicrosoftAccount();
    
    return {
      email: session.email,
      name: session.name,
      loginTime: new Date(session.loginTime),
      microsoftAccount: msAccount || undefined,
    };
  } catch {
    clearSession();
    return null;
  }
}

/**
 * Clear user session
 */
export function clearSession(): void {
  localStorage.removeItem(AUTH_STORAGE_KEY);
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return getStoredSession() !== null;
}

/**
 * Validate WPI email domain
 */
export function isValidWPIEmail(email: string): boolean {
  const wpiDomains = ['@wpi.edu', '@alumni.wpi.edu'];
  return wpiDomains.some(domain => email.toLowerCase().endsWith(domain));
}

/**
 * Check if MSAL is properly configured
 */
export { isMsalConfigured };
