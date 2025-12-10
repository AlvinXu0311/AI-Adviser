import { FC } from 'react';
import { Menu, LogOut, XCircle } from 'lucide-react';
import { User } from '../types';

interface HeaderProps {
  toggleSidebar: () => void;
  user?: User;
  onLogout?: () => void;
  onEndChat?: () => void;
}

// Get initials from name
const getInitials = (name: string): string => {
  return name
    .split(' ')
    .map(part => part.charAt(0).toUpperCase())
    .slice(0, 2)
    .join('');
};

export const Header: FC<HeaderProps> = ({ toggleSidebar, user, onLogout, onEndChat }) => {
  return (
    <header className="h-16 sm:h-20 bg-white border-b border-gray-200 flex items-center justify-between px-3 sm:px-6 lg:px-10 shadow-sm z-10">
      <div className="flex items-center">
        <button 
          onClick={toggleSidebar}
          className="p-2 sm:p-3 -ml-1 mr-2 rounded-md text-gray-600 hover:bg-gray-100 lg:hidden"
        >
          <Menu size={24} className="sm:w-8 sm:h-8" />
        </button>
        <h2 className="text-lg sm:text-2xl font-semibold text-wpi-darkGrey hidden sm:block">
          Student Advising Portal
        </h2>
        <h2 className="text-base font-semibold text-wpi-darkGrey sm:hidden">
          Adviser
        </h2>
      </div>

      <div className="flex items-center space-x-2 sm:space-x-4">
        {/* End Chat Button */}
        {onEndChat && (
          <button
            onClick={onEndChat}
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-4 py-1.5 sm:py-2 text-gray-600 hover:text-[#AC2B37] hover:bg-red-50 rounded-lg transition-colors border border-transparent hover:border-red-200"
            title="End chat and download summary"
          >
            <XCircle size={18} className="sm:w-5 sm:h-5" />
            <span className="hidden sm:inline text-sm font-medium">End Chat</span>
          </button>
        )}
        
        <div className="h-8 sm:h-10 w-px bg-gray-200 mx-1"></div>
        <div className="flex items-center space-x-2 sm:space-x-3 p-1.5 sm:p-2 rounded-full border border-gray-200">
          <div className="w-8 h-8 sm:w-12 sm:h-12 bg-gradient-to-br from-wpi-red to-red-800 rounded-full flex items-center justify-center text-white font-bold text-sm sm:text-lg">
            {user ? getInitials(user.name) : 'WP'}
          </div>
          <span className="text-sm sm:text-lg font-medium text-gray-700 pr-2 sm:pr-3 hidden md:block">
            {user?.name || 'WPI User'}
          </span>
        </div>
        {onLogout && (
          <button
            onClick={onLogout}
            className="p-2 sm:p-3 text-gray-500 hover:bg-red-50 hover:text-red-600 rounded-full transition-colors"
            title="Sign out"
          >
            <LogOut size={20} className="sm:w-6 sm:h-6" />
          </button>
        )}
      </div>
    </header>
  );
};