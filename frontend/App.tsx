import { FC, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatInterface } from './components/ChatInterface';
import { Header } from './components/Header';
import { ChatState, AgentStatus } from './types';
import { AnimatePresence, motion } from 'framer-motion';

const App: FC = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  
  // Initial Welcome Message
  const [chatState, setChatState] = useState<ChatState>({
    messages: [
      {
        id: 'welcome-1',
        role: 'assistant',
        content: "Welcome to the WPI Business School Adviser Portal!\n\nI'm your academic advisor. Feel free to ask me about programs, courses, requirements, or upload your transcript for personalized guidance.",
        timestamp: new Date(),
      }
    ],
    isLoading: false,
    agentStatus: AgentStatus.IDLE
  });

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

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
      <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-full w-full relative transition-all duration-300">
        <Header toggleSidebar={toggleSidebar} />
        
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