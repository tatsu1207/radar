import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import Sidebar from '@/components/Sidebar';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'RADAR - Resistome Analysis, Detection, Assessment & Risk',
  description: 'Bioinformatics web application for antibiotic resistance analysis',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-gray-950 text-gray-100`}>
        <Sidebar />
        <main className="lg:ml-64 min-h-screen">
          <div className="p-6 lg:p-8">{children}</div>
        </main>
      </body>
    </html>
  );
}
