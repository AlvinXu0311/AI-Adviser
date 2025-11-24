import { FC } from 'react';
import { motion } from 'framer-motion';
import { 
  GraduationCap, 
  X,
  Sparkles
} from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
}

export const Sidebar: FC<SidebarProps> = ({ isOpen, toggleSidebar }) => {
  const statusLights = [
    { label: 'Vector DB', state: 'Online', color: 'bg-emerald-400' },
    { label: 'Gemini', state: 'Ready', color: 'bg-sky-400' },
    { label: 'Streaming', state: 'Live', color: 'bg-amber-300' },
  ];

  return (
    <motion.div
      initial={false}
      animate={{ 
        width: isOpen ? 280 : 0,
        x: isOpen ? 0 : -280 
      }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className={`fixed inset-y-0 left-0 z-30 lg:relative bg-wpi-darkGrey text-white flex flex-col h-full border-r border-gray-800 shadow-xl overflow-hidden whitespace-nowrap`}
    >
      <div className="p-6 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-wpi-red rounded-lg flex items-center justify-center shadow-lg">
            <GraduationCap className="text-white w-6 h-6" />
          </div>
          <div className="overflow-hidden">
            <h1 className="font-bold text-lg leading-tight">WPI Business</h1>
            <span className="text-xs text-gray-400 font-medium tracking-wider">DIGITAL ADVISER</span>
          </div>
        </div>
        <button onClick={toggleSidebar} className="lg:hidden p-1 hover:bg-white/10 rounded">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-6 px-6 space-y-6">
        <div className="bg-white/5 rounded-2xl border border-white/10 p-5 shadow-inner">
          <div className="flex items-center space-x-3 mb-3">
            <Sparkles className="text-wpi-red w-5 h-5" />
            <p className="text-sm font-semibold tracking-wide text-gray-200">Adviser Portal</p>
          </div>
        </div>

        <div className="bg-black/10 rounded-2xl border border-white/5 p-4">
          <p className="text-xs uppercase tracking-[0.3em] text-gray-500 mb-2">Status</p>
          <div className="space-y-3">
            {statusLights.map(item => (
              <div key={item.label} className="flex items-center justify-between text-sm">
                <div className="flex items-center space-x-2 text-gray-300">
                  <span className={`inline-flex w-2.5 h-2.5 rounded-full ${item.color} shadow-[0_0_8px_rgba(255,255,255,0.5)]`}></span>
                  <span>{item.label}</span>
                </div>
                <span className="text-xs uppercase tracking-wide text-gray-400">{item.state}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
};