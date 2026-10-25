import { FC, FormEvent, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { loginWithMicrosoft, loginWithDemo, getAuthConfig, isMsalConfigured } from '../services/authService';
import { User } from '../types';

interface LoginPageProps {
  onLogin: (user: User) => void;
}

export const LoginPage: FC<LoginPageProps> = ({ onLogin }) => {
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const [demoEmail, setDemoEmail] = useState('');
  const [demoPassword, setDemoPassword] = useState('');
  // Demo login exists only when the backend enables it (DEMO_LOGIN_ENABLED=true)
  const [demoEnabled, setDemoEnabled] = useState(false);

  // Check if Microsoft SSO is configured
  const msalConfigured = isMsalConfigured();
  // Default to WPI email form if MSAL not configured
  const [showMicrosoftLogin, setShowMicrosoftLogin] = useState(msalConfigured);

  useEffect(() => {
    getAuthConfig().then((config) => setDemoEnabled(config.demo_login));
  }, []);

  // Handle Microsoft SSO Login
  const handleMicrosoftLogin = async () => {
    setError('');
    setIsLoading(true);

    try {
      const user = await loginWithMicrosoft();
      if (user) {
        onLogin({
          email: user.email,
          name: user.name,
          loginTime: user.loginTime,
        });
      }
    } catch (err: any) {
      const errorMessage = err?.message || 'Authentication failed. Please try again.';
      
      // Check for specific error types
      if (errorMessage.includes('popup_window_error')) {
        setError('Popup was blocked. Please allow popups for this site.');
      } else if (errorMessage.includes('user_cancelled')) {
        setError('Login was cancelled.');
      } else if (errorMessage.includes('WPI email')) {
        setError(errorMessage);
      } else if (errorMessage.includes('AADSTS700016') || errorMessage.includes('not found in the directory')) {
        setError('App not registered in Azure AD. Please contact WPI IT or use demo login.');
      } else if (errorMessage.includes('AADSTS50011')) {
        setError('Redirect URI not configured. Please contact the administrator.');
      } else {
        setError('Authentication failed. Please try again or use demo login.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Demo account login - credentials are checked by the backend
  const handleDemoLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const user: User = await loginWithDemo(demoEmail.trim(), demoPassword);
      onLogin(user);
    } catch (err: any) {
      setError(err?.message || 'Demo sign-in failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#AC2B37] via-[#8B1C26] to-[#6B0F18] flex flex-col justify-center items-center p-4">
      {/* Background Pattern */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute inset-0" style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
        }} />
      </div>

      {/* Login Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-md"
      >
        {/* Logo and Header */}
        <div className="text-center mb-8">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
            className="inline-block"
          >
            <img 
              src="/assets/WPI_ICON.jpg" 
              alt="WPI Logo" 
              className="w-24 h-24 mx-auto rounded-full shadow-2xl border-4 border-white/30"
            />
          </motion.div>
          <h1 className="mt-6 text-3xl font-bold text-white">
            WPI Business School
          </h1>
          <p className="mt-2 text-lg text-white/80">
            Digital Academic Adviser
          </p>
        </div>

        {/* Login Card */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="bg-white/95 backdrop-blur-lg rounded-2xl shadow-2xl p-8"
        >
          <h2 className="text-2xl font-semibold text-gray-800 text-center mb-6">
            Sign In
          </h2>

          {/* Microsoft SSO Button - only show if configured */}
          {showMicrosoftLogin && (
            <div className="space-y-4">
              <button
                onClick={handleMicrosoftLogin}
                disabled={isLoading}
                className="w-full py-3 px-4 bg-white border-2 border-gray-200 hover:border-[#0078D4] hover:bg-[#0078D4]/5 text-gray-700 font-medium rounded-lg shadow-sm hover:shadow-md transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin w-5 h-5 text-[#0078D4]" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Signing in...</span>
                  </>
                ) : (
                  <>
                    {/* Microsoft Logo */}
                    <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none">
                      <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
                      <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
                      <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
                      <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
                    </svg>
                    <span>Sign in with Microsoft</span>
                  </>
                )}
              </button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-4 bg-white text-gray-500">WPI Account</span>
                </div>
              </div>

              <p className="text-center text-sm text-gray-500">
                Use your <strong>@wpi.edu</strong> account with Microsoft Authenticator or your WPI credentials.
              </p>
            </div>
          )}

          {/* Demo account - email + password, verified by the backend */}
          {!showMicrosoftLogin && !demoEnabled && (
            <p className="text-center text-sm text-gray-500">
              Demo login is disabled on this server.
            </p>
          )}

          {!showMicrosoftLogin && demoEnabled && (
            <form className="space-y-4" onSubmit={handleDemoLogin}>
              <div>
                <label htmlFor="demo-email" className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  id="demo-email"
                  type="email"
                  autoComplete="username"
                  required
                  value={demoEmail}
                  onChange={(e) => setDemoEmail(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#AC2B37]/40 focus:border-[#AC2B37]"
                />
              </div>
              <div>
                <label htmlFor="demo-password" className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  id="demo-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={demoPassword}
                  onChange={(e) => setDemoPassword(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#AC2B37]/40 focus:border-[#AC2B37]"
                />
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 bg-[#AC2B37] hover:bg-[#8B1C26] text-white font-semibold rounded-lg shadow-lg hover:shadow-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Signing in...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                    <span>Sign in to Demo</span>
                  </>
                )}
              </button>

              {msalConfigured && (
                <button
                  type="button"
                  onClick={() => setShowMicrosoftLogin(true)}
                  className="w-full text-sm text-gray-500 hover:text-gray-700"
                >
                  ← Back to Microsoft Sign In
                </button>
              )}
            </form>
          )}

          {/* Error Message */}
          {error && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="mt-4 flex items-center gap-2 text-red-600 text-sm bg-red-50 px-4 py-3 rounded-lg"
            >
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
            </motion.div>
          )}

          {/* Demo Mode Toggle - show switch to demo when Microsoft login is showing */}
          {showMicrosoftLogin && demoEnabled && (
            <div className="mt-6 pt-4 border-t border-gray-200">
              <button
                onClick={() => setShowMicrosoftLogin(false)}
                className="w-full text-sm text-gray-500 hover:text-[#AC2B37] transition-colors"
              >
                Use demo login instead →
              </button>
              {!msalConfigured && (
                <p className="mt-2 text-xs text-center text-gray-400">
                  Microsoft SSO not configured. Demo mode available.
                </p>
              )}
            </div>
          )}
        </motion.div>

        {/* Help Link */}
        <div className="mt-6 text-center">
          <a 
            href="https://www.wpi.edu/offices/information-technology/services/accounts"
            target="_blank"
            rel="noopener noreferrer"
            className="text-white/80 hover:text-white text-sm underline underline-offset-2 transition-colors"
          >
            Need help with your WPI account?
          </a>
        </div>
      </motion.div>

      {/* Footer */}
      <div className="absolute bottom-4 text-center text-white/60 text-sm">
        <p>© {new Date().getFullYear()} Worcester Polytechnic Institute</p>
      </div>
    </div>
  );
};
