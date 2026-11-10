'use client';

import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import type { SortDir } from '@/lib/sort';

/** Table header cell that sorts its column when clicked. */
export default function SortableHeader<K extends string>({
  label, column, sortKey, sortDir, onSort, className = '',
}: {
  label: string;
  column: K;
  sortKey: K;
  sortDir: SortDir;
  onSort: (column: K) => void;
  className?: string;
}) {
  const active = sortKey === column;
  const Icon = !active ? ArrowUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown;
  return (
    <th className={`table-header ${className}`} aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`inline-flex items-center gap-1 hover:text-gray-200 ${active ? 'text-gray-200' : ''}`}
      >
        {label}
        <Icon className={`w-3 h-3 ${active ? '' : 'opacity-40'}`} />
      </button>
    </th>
  );
}
