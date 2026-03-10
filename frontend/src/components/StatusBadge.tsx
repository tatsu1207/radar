'use client';

import { clsx } from 'clsx';

interface StatusBadgeProps {
  status: string;
  type?: 'job' | 'risk';
}

const jobColors: Record<string, string> = {
  pending: 'bg-gray-600 text-gray-200',
  running: 'bg-blue-600 text-blue-100',
  complete: 'bg-green-600 text-green-100',
  failed: 'bg-red-600 text-red-100',
  cancelled: 'bg-yellow-600 text-yellow-100',
};

const riskColors: Record<string, string> = {
  low: 'bg-green-600 text-green-100',
  medium: 'bg-yellow-600 text-yellow-100',
  high: 'bg-orange-600 text-orange-100',
  critical: 'bg-red-600 text-red-100',
};

export default function StatusBadge({ status, type = 'job' }: StatusBadgeProps) {
  const colors = type === 'risk' ? riskColors : jobColors;
  const colorClass = colors[status] || 'bg-gray-600 text-gray-200';

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide',
        colorClass
      )}
    >
      {status}
    </span>
  );
}
