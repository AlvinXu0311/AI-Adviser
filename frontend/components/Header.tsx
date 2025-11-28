import { FC } from 'react';
import { Menu, Bell, User } from 'lucide-react';

interface HeaderProps {
  toggleSidebar: () => void;
}

export const Header: FC<HeaderProps> = ({ toggleSidebar }) => {
  return (
    <header className="h-20 bg-white border-b border-gray-200 flex items-center justify-between px-6 lg:px-10 shadow-sm z-10">
      <div className="flex items-center">
        <button 
          onClick={toggleSidebar}
          className="p-3 -ml-2 mr-3 rounded-md text-gray-600 hover:bg-gray-100 lg:hidden"
        >
          <Menu size={32} />
        </button>
        <h2 className="text-2xl font-semibold text-wpi-darkGrey hidden sm:block">
          Student Advising Portal
        </h2>
      </div>

      <div className="flex items-center space-x-6">
        <button className="p-3 text-gray-500 hover:bg-gray-100 rounded-full relative transition-colors">
          <Bell size={28} />
          <span className="absolute top-1 right-1 w-3 h-3 bg-wpi-red rounded-full border-2 border-white"></span>
        </button>
        <div className="h-10 w-px bg-gray-200 mx-3"></div>
        <button className="flex items-center space-x-3 p-2 rounded-full border border-gray-200 hover:border-wpi-red transition-all">
          <div className="w-12 h-12 bg-gradient-to-br from-wpi-red to-red-800 rounded-full flex items-center justify-center text-white font-bold text-lg">
            JS
          </div>
          <span className="text-lg font-medium text-gray-700 pr-3 hidden sm:block">John Smith</span>
        </button>
      </div>
    </header>
  );
};