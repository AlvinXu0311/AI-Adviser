/**
 * Microsoft Authentication Library (MSAL) Configuration for WPI
 * 
 * WPI is a Microsoft 365 Education organization. To enable SSO:
 * 
 * 1. Register this app in WPI's Azure AD:
 *    - Go to Azure Portal > Azure Active Directory > App registrations
 *    - Create new registration: "WPI Digital Adviser"
 *    - Set redirect URI: http://localhost:5173 (dev) or production URL
 *    - Select "Accounts in this organizational directory only (WPI only)"
 *    - Under Authentication, check "Access tokens" and "ID tokens"
 *    
 * 2. Configure environment variables:
 *    VITE_MSAL_CLIENT_ID=<Application (client) ID>
 *    VITE_MSAL_TENANT_ID=wpi.edu
 * 
 * Users will authenticate via Microsoft Authenticator or their WPI credentials.
 */

import { Configuration, LogLevel, PublicClientApplication } from '@azure/msal-browser';

// MSAL configuration - WPI Azure AD
const MSAL_CLIENT_ID = import.meta.env.VITE_MSAL_CLIENT_ID || 'YOUR_CLIENT_ID_HERE';
// Use 'wpi.edu' for WPI-only login, or specific tenant ID
const MSAL_TENANT_ID = import.meta.env.VITE_MSAL_TENANT_ID || 'wpi.edu';

// Determine redirect URI based on environment
const getRedirectUri = (): string => {
  if (typeof window !== 'undefined') {
    return window.location.origin;
  }
  return 'http://localhost:5173';
};

export const msalConfig: Configuration = {
  auth: {
    clientId: MSAL_CLIENT_ID,
    // WPI-only access - uses WPI's Azure AD tenant
    authority: `https://login.microsoftonline.com/${MSAL_TENANT_ID}`,
    redirectUri: getRedirectUri(),
    postLogoutRedirectUri: getRedirectUri(),
    navigateToLoginRequestUrl: true,
  },
  cache: {
    cacheLocation: 'localStorage', // or 'sessionStorage'
    storeAuthStateInCookie: false, // Set to true for IE11 or Edge
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        switch (level) {
          case LogLevel.Error:
            console.error('[MSAL]', message);
            break;
          case LogLevel.Warning:
            console.warn('[MSAL]', message);
            break;
          case LogLevel.Info:
            // console.info('[MSAL]', message);
            break;
          case LogLevel.Verbose:
            // console.debug('[MSAL]', message);
            break;
        }
      },
      logLevel: LogLevel.Warning,
    },
  },
};

// Scopes for login - basic profile info
export const loginRequest = {
  scopes: ['User.Read', 'openid', 'profile', 'email'],
};

// Optional: Scopes for accessing Microsoft Graph API
export const graphConfig = {
  graphMeEndpoint: 'https://graph.microsoft.com/v1.0/me',
};

// Create MSAL instance
export const msalInstance = new PublicClientApplication(msalConfig);

// Initialize MSAL
export const initializeMsal = async (): Promise<void> => {
  try {
    await msalInstance.initialize();
    
    // Handle redirect response if returning from login
    const response = await msalInstance.handleRedirectPromise();
    if (response) {
      console.log('[MSAL] Login redirect successful');
    }
  } catch (error) {
    console.error('[MSAL] Initialization error:', error);
  }
};

// Check if MSAL is configured (client ID is set)
export const isMsalConfigured = (): boolean => {
  return MSAL_CLIENT_ID !== 'YOUR_CLIENT_ID_HERE' && MSAL_CLIENT_ID.length > 10;
};
