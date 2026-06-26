'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Radar } from 'lucide-react';

export default function VerifyPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [message, setMessage] = useState('Verifying...');
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    if (!token) {
      setMessage('Missing verification token.');
      setIsError(true);
      return;
    }

    fetch(`/api/auth/verify?token=${encodeURIComponent(token)}`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Verification failed');
        setMessage(data.message);
      })
      .catch((err) => {
        setMessage(err.message);
        setIsError(true);
      });
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="w-full max-w-sm mx-auto text-center">
        <div className="flex items-center justify-center gap-3 mb-8">
          <Radar className="w-10 h-10 text-blue-500" />
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">RADAR</h1>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <p className={isError ? 'text-red-400' : 'text-green-400'}>{message}</p>
          <Link
            href="/login"
            className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            Go to Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
