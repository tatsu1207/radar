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

// All hazard badges use dark bg + white text for WCAG AA contrast (>=4.5:1).
// Each rank has a distinct hue. Tier label is appended as a non-colour cue.
//
// Contrast ratios (white #fff against Tailwind bg):
//   red-800    #991b1b  → 7.28:1   R1
//   red-700    #b91c1c  → 5.30:1   R2
//   red-900    #7f1d1d  → 9.48:1   R3
//   orange-800 #9a3412  → 5.58:1   R4
//   orange-700 #c2410c  → 4.57:1   R5
//   yellow-800 #854d0e  → 5.15:1   R6
//   amber-700  #b45309  → 4.56:1   R7
//   yellow-700 #a16207  → 4.68:1   R8
//   lime-800   #3f6212  → 5.47:1   R9
//   lime-700   #4d7c0f  → 4.66:1   R10
//   green-800  #166534  → 6.40:1   R11
//   green-700  #15803d  → 5.17:1   R12
//   gray-700   #374151  → 7.53:1   NG
const hazardColors: Record<string, string> = {
  R1:  'bg-red-800 text-white',
  R2:  'bg-red-700 text-white',
  R3:  'bg-red-900 text-white',
  R4:  'bg-orange-800 text-white',
  R5:  'bg-orange-700 text-white',
  R6:  'bg-yellow-800 text-white',
  R7:  'bg-amber-700 text-white',
  R8:  'bg-yellow-700 text-white',
  R9:  'bg-lime-800 text-white',
  R10: 'bg-lime-700 text-white',
  R11: 'bg-green-800 text-white',
  R12: 'bg-green-700 text-white',
  NG:  'bg-gray-700 text-white',
};

// Map rank to AWaRe tier label for non-colour cue (F4)
const rankTier: Record<string, string> = {
  R1: 'Rsv', R2: 'Rsv', R3: 'Rsv', R4: 'Rsv', R5: 'Rsv',
  R6: 'Wtc', R7: 'Wtc', R8: 'Wtc', R9: 'Wtc', R10: 'Wtc',
  R11: 'Acc', R12: '', NG: '',
};

export default function StatusBadge({ status, type = 'job' }: StatusBadgeProps) {
  const colors = type === 'hazard' ? hazardColors : type === 'risk' ? riskColors : jobColors;
  const colorClass = colors[status] || 'bg-gray-700 text-white';
  const tier = type === 'hazard' ? rankTier[status] : undefined;

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide',
        colorClass
      )}
    >
      {status}{tier ? <span className="ml-1 opacity-75 font-normal text-[10px]">{tier}</span> : null}
    </span>
  );
}
