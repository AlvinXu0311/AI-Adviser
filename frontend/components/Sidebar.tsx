import { FC, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  X,
  Sparkles
} from 'lucide-react';
import { getSystemStatus, StatusComponent } from '../services/statusService';

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
}

interface StatusLight {
  label: string;
  state: string;
  color: string;
}

export const Sidebar: FC<SidebarProps> = ({ isOpen, toggleSidebar }) => {
  const [statusLights, setStatusLights] = useState<StatusLight[]>([
    { label: 'Vector DB', state: 'Loading', color: 'bg-gray-400' },
    { label: 'Gemini', state: 'Loading', color: 'bg-gray-400' },
    { label: 'Streaming', state: 'Loading', color: 'bg-gray-400' },
  ]);

  useEffect(() => {
    // Fetch initial status
    fetchStatus();

    // Poll status every 30 seconds
    const interval = setInterval(fetchStatus, 30000);

    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const status = await getSystemStatus();

      // Map components to status lights
      const newStatusLights: StatusLight[] = status.components.map((component: StatusComponent) => {
        const isOnline = component.status === 'online';

        // Determine color and state based on component key
        let color = isOnline ? 'bg-emerald-400' : 'bg-red-400';
        let state = isOnline ? 'Online' : 'Offline';

        if (component.key === 'gemini') {
          color = isOnline ? 'bg-sky-400' : 'bg-red-400';
          state = isOnline ? 'Ready' : 'Offline';
        } else if (component.key === 'streaming') {
          color = isOnline ? 'bg-amber-300' : 'bg-red-400';
          state = isOnline ? 'Live' : 'Offline';
        }

        return {
          label: component.label,
          state,
          color,
        };
      });

      setStatusLights(newStatusLights);
    } catch (error) {
      console.error('Failed to fetch system status:', error);
      // Set all to error state
      setStatusLights([
        { label: 'Vector DB', state: 'Error', color: 'bg-red-400' },
        { label: 'Gemini', state: 'Error', color: 'bg-red-400' },
        { label: 'Streaming', state: 'Error', color: 'bg-red-400' },
      ]);
    }
  };

  return (
    <motion.div
      initial={false}
      animate={{ 
        width: isOpen ? 360 : 0,
        x: isOpen ? 0 : -360 
      }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className={`fixed inset-y-0 left-0 z-30 lg:relative bg-wpi-darkGrey text-white flex flex-col h-full border-r border-gray-800 shadow-xl overflow-hidden whitespace-nowrap`}
    >
      <div className="p-6 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <div className="w-14 h-14 rounded-lg flex items-center justify-center shadow-lg overflow-hidden">
            <img src="/assets/WPI_ICON.jpg" alt="WPI Logo" className="w-full h-full object-cover" />
          </div>
          <div className="overflow-hidden">
            <h1 className="font-bold text-2xl leading-tight">WPI Business</h1>
            <span className="text-base text-gray-400 font-medium tracking-wider">DIGITAL ADVISER</span>
          </div>
        </div>
        <button onClick={toggleSidebar} className="lg:hidden p-2 hover:bg-white/10 rounded">
          <X className="w-7 h-7" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-6 px-6 space-y-6">
        <div className="bg-white/5 rounded-2xl border border-white/10 p-6 shadow-inner">
          <div className="flex items-center space-x-4 mb-3">
            <Sparkles className="text-wpi-red w-7 h-7" />
            <p className="text-lg font-semibold tracking-wide text-gray-200">Adviser Portal</p>
          </div>
        </div>

        <div className="bg-black/10 rounded-2xl border border-white/5 p-5">
          <p className="text-base uppercase tracking-[0.3em] text-gray-500 mb-4">Status</p>
          <div className="space-y-4">
            {statusLights.map(item => (
              <div key={item.label} className="flex items-center justify-between text-lg">
                <div className="flex items-center space-x-3 text-gray-300">
                  <span className={`inline-flex w-4 h-4 rounded-full ${item.color} shadow-[0_0_8px_rgba(255,255,255,0.5)]`}></span>
                  <span>{item.label}</span>
                </div>
                <span className="text-base uppercase tracking-wide text-gray-400">{item.state}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
};