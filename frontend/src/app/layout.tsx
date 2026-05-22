import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import 'cgview/dist/cgview.css';
import Sidebar from '@/components/Sidebar';
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
        <ThemeProvider>
          <Sidebar />
          <main className="lg:ml-64 min-h-screen">
            <div className="p-6 lg:p-8">{children}</div>
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
