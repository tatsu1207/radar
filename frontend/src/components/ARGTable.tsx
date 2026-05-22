'use client';

import { useState, useMemo } from 'react';
import { Download, Filter } from 'lucide-react';
import type { ARGResult } from '@/lib/api';

interface ARGTableProps {
  results: ARGResult[];
}

type SortKey = keyof ARGResult;
type SortDir = 'asc' | 'desc';

export default function ARGTable({ results }: ARGTableProps) {
  const [drugClassFilter, setDrugClassFilter] = useState('');
  const [databaseFilter, setDatabaseFilter] = useState('');
  const [minIdentity, setMinIdentity] = useState(0);
  const [plasmidOnly, setPlasmidOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('gene');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [showFilters, setShowFilters] = useState(false);

  const drugClasses = useMemo(() => Array.from(new Set(results.map((r) => r.drug_class))).sort(), [results]);
  const databases = useMemo(() => Array.from(new Set(results.map((r) => r.database))).sort(), [results]);

  const filtered = useMemo(() => {
    let data = [...results];
    if (drugClassFilter) data = data.filter((r) => r.drug_class === drugClassFilter);
    if (databaseFilter) data = data.filter((r) => r.database === databaseFilter);
    if (minIdentity > 0) data = data.filter((r) => r.identity >= minIdentity);
    if (plasmidOnly) data = data.filter((r) => r.on_plasmid);

    data.sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal == null || bVal == null) return 0;
      const cmp = typeof aVal === 'string' ? aVal.localeCompare(bVal as string) : (aVal as number) - (bVal as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return data;
  }, [results, drugClassFilter, databaseFilter, minIdentity, plasmidOnly, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const exportCSV = () => {
    const headers = ['Gene', 'Drug Class', 'Mechanism', 'Identity%', 'Coverage%', 'Contig', 'Database', 'On Plasmid'];
    const rows = filtered.map((r) => [
      r.gene,
      r.drug_class,
      r.mechanism,
      r.identity,
      r.coverage,
      r.contig,
      r.database,
      r.on_plasmid ? 'Yes' : 'No',
    ]);
    const csv = [headers, ...rows].map((row) => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'arg_results.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const SortableHeader = ({ label, field }: { label: string; field: SortKey }) => (
    <th
      className="table-header cursor-pointer hover:text-gray-200 select-none"
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {label}
        {sortKey === field && <span>{sortDir === 'asc' ? '\u2191' : '\u2193'}</span>}
      </span>
    </th>
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <Filter className="w-4 h-4" />
          Filters
          {(drugClassFilter || databaseFilter || minIdentity > 0 || plasmidOnly) && (
            <span className="bg-blue-600 text-white text-xs rounded-full px-1.5">!</span>
          )}
        </button>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{filtered.length} results</span>
          <button onClick={exportCSV} className="btn-secondary flex items-center gap-2 text-sm">
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Drug Class</label>
            <select
              value={drugClassFilter}
              onChange={(e) => setDrugClassFilter(e.target.value)}
              className="input w-full text-sm"
            >
              <option value="">All</option>
              {drugClasses.map((dc) => (
                <option key={dc} value={dc}>{dc}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Database</label>
            <select
              value={databaseFilter}
              onChange={(e) => setDatabaseFilter(e.target.value)}
              className="input w-full text-sm"
            >
              <option value="">All</option>
              {databases.map((db) => (
                <option key={db} value={db}>{db}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Min Identity: {minIdentity}%</label>
            <input
              type="range"
              min={0}
              max={100}
              value={minIdentity}
              onChange={(e) => setMinIdentity(Number(e.target.value))}
              className="w-full accent-blue-500"
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={plasmidOnly}
                onChange={(e) => setPlasmidOnly(e.target.checked)}
                className="rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-300">Plasmid-borne only</span>
            </label>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <SortableHeader label="Gene" field="gene" />
              <SortableHeader label="Drug Class" field="drug_class" />
              <SortableHeader label="Mechanism" field="mechanism" />
              <SortableHeader label="Identity%" field="identity" />
              <SortableHeader label="Coverage%" field="coverage" />
              <SortableHeader label="Contig" field="contig" />
              <SortableHeader label="Database" field="database" />
              <th className="table-header">On Plasmid</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="table-cell text-center text-gray-500 py-8">
                  No ARG results found
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.id} className="hover:bg-gray-800/50 transition-colors">
                  <td className="table-cell font-medium text-gray-200">{r.gene}</td>
                  <td className="table-cell">{r.drug_class}</td>
                  <td className="table-cell">{r.mechanism}</td>
                  <td className="table-cell">
                    <span
                      className={
                        r.identity >= 99
                          ? 'text-green-400'
                          : r.identity >= 90
                          ? 'text-yellow-400'
                          : 'text-red-400'
                      }
                    >
                      {r.identity.toFixed(1)}%
                    </span>
                  </td>
                  <td className="table-cell">{r.coverage.toFixed(1)}%</td>
                  <td className="table-cell font-mono text-xs">{r.contig}</td>
                  <td className="table-cell">{r.database}</td>
                  <td className="table-cell">
                    {r.on_plasmid ? (
                      <span className="text-orange-400 font-medium">Yes</span>
                    ) : (
                      <span className="text-gray-500">No</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
