import { FC } from 'react';
import { Menu, Bell, User } from 'lucide-react';

interface HeaderProps {
  toggleSidebar: () => void;
}

export const Header: FC<HeaderProps> = ({ toggleSidebar }) => {
  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-4 lg:px-8 shadow-sm z-10">
      <div className="flex items-center">
        <button 
          onClick={toggleSidebar}
          className="p-2 -ml-2 mr-2 rounded-md text-gray-600 hover:bg-gray-100 lg:hidden"
        >
          <Menu size={24} />
        </button>
        <h2 className="text-lg font-semibold text-wpi-darkGrey hidden sm:block">
          Student Advising Portal
        </h2>
      </div>

      <div className="flex items-center space-x-4">
        <button className="p-2 text-gray-500 hover:bg-gray-100 rounded-full relative transition-colors">
          <Bell size={20} />
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-wpi-red rounded-full border-2 border-white"></span>
        </button>
        <div className="h-8 w-px bg-gray-200 mx-2"></div>
        <button className="flex items-center space-x-2 p-1.5 rounded-full border border-gray-200 hover:border-wpi-red transition-all">
          <div className="w-8 h-8 bg-gradient-to-br from-wpi-red to-red-800 rounded-full flex items-center justify-center text-white font-bold text-xs">
            JS
          </div>
          <span className="text-sm font-medium text-gray-700 pr-2 hidden sm:block">John Smith</span>
        </button>
      </div>
    </header>
  );
};