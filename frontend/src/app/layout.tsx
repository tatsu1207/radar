import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import 'cgview/dist/cgview.css';
import { AuthProvider } from '@/context/AuthContext';
import AuthGate from '@/components/AuthGate';
import ThemeProvider from '@/components/ThemeProvider';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'RADAR - Resistome Analysis, Detection, Assessment & Research',
  description: 'Bioinformatics web application for antibiotic resistance analysis',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={inter.className}>
        <AuthProvider>
          <ThemeProvider>
            <AuthGate>{children}</AuthGate>
          </ThemeProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
