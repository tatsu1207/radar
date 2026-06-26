'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import {
  Info,
  Files,
  Table2,
  Workflow,
  BarChart3,
  Wrench,
  Menu,
  X,
  Radar,
  Sun,
  Moon,
  LogOut,
  User,
} from 'lucide-react';
import { useTheme } from '@/components/ThemeProvider';
import { useAuth } from '@/context/AuthContext';

const navItems = [
  { href: '/files', label: 'Files', icon: Files },
  { href: '/metadata', label: 'Metadata', icon: Table2 },
  { href: '/results', label: 'Annotation', icon: BarChart3 },
  { href: '/tools', label: 'Tools', icon: Wrench },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  const navContent = (
    <>
      <div className="px-4 py-6 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <Radar className="w-8 h-8 text-blue-500" />
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">RADAR</h1>
            <p className="text-[10px] text-gray-500 leading-tight">
              Resistome Analysis, Detection,
              <br />
              Assessment &amp; Research
            </p>
          </div>
        </div>
        <button
          onClick={toggle}
          className="flex items-center gap-2 mt-4 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors duration-200 w-full"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 flex-shrink-0" /> : <Moon className="w-4 h-4 flex-shrink-0" />}
          {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </button>
        <Link
          href="/"
          onClick={() => setMobileOpen(false)}
          className={clsx(
            'flex items-center gap-2 mt-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-200 w-full',
            isActive('/')
              ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
              : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
          )}
        >
          <Info className="w-4 h-4 flex-shrink-0" />
          Introduction
        </Link>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-200',
                isActive(item.href)
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              )}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="px-4 py-4 border-t border-gray-800 space-y-2">
        {user && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <User className="w-3.5 h-3.5" />
              {user.username}
            </div>
            <button
              onClick={logout}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-400 transition-colors"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
        <p className="text-xs text-gray-600">RADAR v0.1.0</p>
      </div>
    </>
  );

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-gray-900 border border-gray-700 lg:hidden"
      >
        {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed top-0 left-0 z-40 h-full w-64 bg-gray-950 border-r border-gray-800 flex flex-col transition-transform duration-300 lg:translate-x-0',
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {navContent}
      </aside>
    </>
  );
}
