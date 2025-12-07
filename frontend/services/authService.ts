/**
 * Authentication Service
 * Handles WPI user authentication via Microsoft SSO and session management
 */

import { AccountInfo } from '@azure/msal-browser';
import { msalInstance, loginRequest, isMsalConfigured } from '../config/msalConfig';

export interface User {
  email: string;
  name: string;
  loginTime: Date;
  microsoftAccount?: AccountInfo;
}

const AUTH_STORAGE_KEY = 'wpi_adviser_auth';
const SESSION_DURATION = 24 * 60 * 60 * 1000; // 24 hours in milliseconds

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
      
      const user: User = {
        email: email,
        name: account.name || email.split('@')[0],
        loginTime: new Date(),
        microsoftAccount: account,
      };
      
      storeSession(user);
      return user;
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
 * Store user session in localStorage
 */
export function storeSession(user: User): void {
  const session = {
    email: user.email,
    name: user.name,
    loginTime: user.loginTime.toISOString(),
    expiresAt: new Date(Date.now() + SESSION_DURATION).toISOString(),
  };
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
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
 * Generate a unique session ID for this user session
 */
export function generateSessionId(email: string): string {
  const timestamp = Date.now().toString(36);
  const randomPart = Math.random().toString(36).substring(2, 10);
  const emailHash = email.split('@')[0].substring(0, 4);
  return `${emailHash}-${timestamp}-${randomPart}`;
}

/**
 * Check if MSAL is properly configured
 */
export { isMsalConfigured };
