'use client';

import { clsx } from 'clsx';

interface StatusBadgeProps {
  status: string;
  type?: 'job' | 'risk' | 'hazard';
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

const hazardColors: Record<string, string> = {
  R1: 'bg-red-700 text-red-100',
  R2: 'bg-red-600 text-red-100',
  R3: 'bg-red-500 text-red-100',
  R4: 'bg-orange-600 text-orange-100',
  R5: 'bg-orange-500 text-orange-100',
  R6: 'bg-yellow-600 text-yellow-100',
  R7: 'bg-yellow-500 text-yellow-100',
  R8: 'bg-yellow-500 text-yellow-100',
  R9: 'bg-lime-600 text-lime-100',
  R10: 'bg-lime-500 text-lime-100',
  R11: 'bg-green-600 text-green-100',
  R12: 'bg-green-500 text-green-100',
  NG: 'bg-gray-600 text-gray-200',
};

export default function StatusBadge({ status, type = 'job' }: StatusBadgeProps) {
  const colors = type === 'hazard' ? hazardColors : type === 'risk' ? riskColors : jobColors;
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
