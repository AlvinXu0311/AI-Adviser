import { FC, useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatInterface } from './components/ChatInterface';
import { Header } from './components/Header';
import { LoginPage } from './components/LoginPage';
import { ChatState, AgentStatus, User } from './types';
import { getStoredSession, storeSession, clearSession, generateSessionId, logoutFromMicrosoft } from './services/authService';
import { initializeMsal } from './config/msalConfig';
import { AnimatePresence, motion } from 'framer-motion';

const App: FC = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  
  // Initialize MSAL and check for existing session on mount
  useEffect(() => {
    const init = async () => {
      try {
        // Initialize MSAL first
        await initializeMsal();
        
        // Then check for stored session
        const storedUser = getStoredSession();
        if (storedUser) {
          setUser(storedUser);
        }
      } catch (error) {
        console.error('[App] MSAL initialization error:', error);
      } finally {
        setIsCheckingAuth(false);
      }
    };
    
    init();
  }, []);
  
  // Initial Welcome Message - personalized if logged in
  const [chatState, setChatState] = useState<ChatState>({
    messages: [],
    isLoading: false,
    agentStatus: AgentStatus.IDLE
  });

  // Update welcome message when user logs in
  useEffect(() => {
    if (user && chatState.messages.length === 0) {
      const firstName = user.name.split(' ')[0];
      setChatState({
        messages: [
          {
            id: 'welcome-1',
            role: 'assistant',
            content: `Welcome, ${firstName}! 👋\n\nI'm your WPI Business School Academic Adviser. I can help you with:\n\n• **Program Information** - MSIT, MSBA, MSM requirements\n• **Course Selection** - Prerequisites and recommendations\n• **Progress Tracking** - Upload your transcript for personalized advice\n\nHow can I assist you today?`,
            timestamp: new Date(),
          }
        ],
        isLoading: false,
        agentStatus: AgentStatus.IDLE
      });
    }
  }, [user]);

  const handleLogin = (loginUser: User) => {
    const newUser: User = {
      ...loginUser,
      loginTime: loginUser.loginTime || new Date()
    };
    storeSession(newUser);
    setUser(newUser);
    
    // Store session ID for chat API calls
    const sessionId = generateSessionId(loginUser.email);
    sessionStorage.setItem('chat_session_id', sessionId);
  };

  const handleLogout = async () => {
    try {
      // Logout from Microsoft SSO
      await logoutFromMicrosoft();
    } catch (error) {
      console.error('[App] Logout error:', error);
    }
    clearSession();
    setUser(null);
    sessionStorage.removeItem('chat_session_id');
    setChatState({
      messages: [],
      isLoading: false,
      agentStatus: AgentStatus.IDLE
    });
  };

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  // Show loading state while checking auth
  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#AC2B37] via-[#8B1C26] to-[#6B0F18] flex items-center justify-center">
        <div className="animate-spin w-12 h-12 border-4 border-white/30 border-t-white rounded-full" />
      </div>
    );
  }

  // Show login page if not authenticated
  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden text-gray-800">
      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {isSidebarOpen && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-20 lg:hidden"
            onClick={toggleSidebar}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <Sidebar 
        isOpen={isSidebarOpen} 
        toggleSidebar={toggleSidebar}
        user={user}
        onLogout={handleLogout}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-full w-full relative transition-all duration-300">
        <Header toggleSidebar={toggleSidebar} user={user} />
        
        <main className="flex-1 overflow-hidden relative flex flex-col">
          <ChatInterface 
            chatState={chatState} 
            setChatState={setChatState}
          />
        </main>
      </div>
    </div>
  );
};

export default App;