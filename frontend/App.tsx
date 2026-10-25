import { FC, useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatInterface } from './components/ChatInterface';
import { Header } from './components/Header';
import { LoginPage } from './components/LoginPage';
import { EndChatModal } from './components/EndChatModal';
import { ChatState, AgentStatus, User } from './types';
import { getStoredSession, clearSession, logoutFromMicrosoft, logoutFromBackend, verifySession } from './services/authService';
import { initializeMsal } from './config/msalConfig';
import { AnimatePresence, motion } from 'framer-motion';

const App: FC = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [showEndChatModal, setShowEndChatModal] = useState(false);
  
  // Initialize MSAL and check for existing session on mount
  useEffect(() => {
    const init = async () => {
      try {
        // Initialize MSAL first
        await initializeMsal();
        
        // Then check for stored session, and that the backend still accepts its cookie
        const storedUser = getStoredSession();
        if (storedUser && await verifySession()) {
          setUser(storedUser);
        } else if (storedUser) {
          clearSession();
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
            content: `Welcome, ${firstName}! I'm your WPI Business School Digital Adviser. How can I help you today?`,
            timestamp: new Date(),
          }
        ],
        isLoading: false,
        agentStatus: AgentStatus.IDLE
      });
    }
  }, [user]);

  // The login flows store the profile themselves; the session token is an HttpOnly cookie
  const handleLogin = (loginUser: User) => {
    setUser({
      ...loginUser,
      loginTime: loginUser.loginTime || new Date()
    });
  };

  const handleLogout = async () => {
    try {
      // Logout from Microsoft SSO
      await logoutFromMicrosoft();
    } catch (error) {
      console.error('[App] Logout error:', error);
    }
    // Revoke the token server-side, not just locally
    await logoutFromBackend();
    clearSession();
    setUser(null);
    setChatState({
      messages: [],
      isLoading: false,
      agentStatus: AgentStatus.IDLE
    });
  };

  // End chat session and clear messages
  const handleEndChat = () => {
    setShowEndChatModal(false);
    // Reset chat to initial welcome message
    const firstName = user?.name.split(' ')[0] || 'there';
    setChatState({
      messages: [
        {
          id: `welcome-${Date.now()}`,
          role: 'assistant',
          content: `Welcome back, ${firstName}! 👋\n\nYour previous session has ended. How can I help you today?`,
          timestamp: new Date(),
        }
      ],
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
        <Header 
          toggleSidebar={toggleSidebar} 
          user={user}
          onEndChat={() => setShowEndChatModal(true)}
        />
        
        <main className="flex-1 overflow-hidden relative flex flex-col">
          <ChatInterface 
            chatState={chatState} 
            setChatState={setChatState}
          />
        </main>
      </div>

      {/* End Chat Modal */}
      <EndChatModal
        isOpen={showEndChatModal}
        onClose={() => setShowEndChatModal(false)}
        onConfirmEnd={handleEndChat}
        messages={chatState.messages}
        userName={user?.name || 'User'}
      />
    </div>
  );
};

export default App;