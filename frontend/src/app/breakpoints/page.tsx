'use client';

import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import {
  getBreakpoints, updateBreakpoint, createBreakpoint, deleteBreakpoint, Breakpoint,
} from '@/lib/api';

// one inline-editable numeric cutoff cell; commits on blur when changed
function NumCell({ value, onCommit }: { value: number | null | undefined; onCommit: (v: number | null) => void }) {
  const [v, setV] = useState(value ?? '');
  useEffect(() => { setV(value ?? ''); }, [value]);
  return (
    <input
      type="number"
      step="any"
      value={v}
      onChange={(e) => setV(e.target.value === '' ? '' : Number(e.target.value))}
      onBlur={() => {
        const nv = v === '' ? null : Number(v);
        if (nv !== (value ?? null)) onCommit(nv);
      }}
      className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-100 focus:border-blue-500 outline-none w-20"
    />
  );
}

export default function BreakpointsPage() {
  const [rows, setRows] = useState<Breakpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [organism, setOrganism] = useState('');

  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Partial<Breakpoint>>({ unit: 'µg/mL', source: 'manual' });

  const load = useCallback(async () => {
    try {
      setRows(await getBreakpoints());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load breakpoints.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const organisms = Array.from(new Set(rows.map((r) => r.organism))).sort();

  async function commit(id: string, patch: Partial<Breakpoint>) {
    try {
      const updated = await updateBreakpoint(id, patch);
      setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed.');
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.organism?.trim() || !draft.antibiotic?.trim()) {
      setError('Organism and antibiotic are required.');
      return;
    }
    try {
      const created = await createBreakpoint(draft);
      setRows((prev) => [...prev, created]);
      setDraft({ unit: 'µg/mL', source: 'manual' });
      setAdding(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed.');
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteBreakpoint(id);
      setRows((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed.');
    }
  }

  const q = search.trim().toLowerCase();
  const filtered = rows.filter((r) =>
    (!organism || r.organism === organism) &&
    (!q || r.antibiotic.toLowerCase().includes(q) || (r.abbreviation || '').toLowerCase().includes(q) || r.organism.toLowerCase().includes(q))
  );

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-2">
        <h1 className="text-2xl font-bold text-white">AST Breakpoints</h1>
        <button onClick={() => setAdding((a) => !a)} className="btn-primary flex items-center gap-1.5 text-sm shrink-0">
          <Plus className="w-4 h-4" />
          Add breakpoint
        </button>
      </div>
      <p className="text-sm text-gray-400 mb-4">
        Editable MIC interpretation cutoffs used to auto-call S/I/R. The panel supplies a resistant cutoff (MIC ≥ <span className="text-red-300">R≥</span> → R; below it → S).
        Fill in <span className="text-green-300">S≤</span> / <span className="text-yellow-300">I≥</span> for a full three-way call. Edits save on blur.
      </p>

      {error && <div className="mb-3 p-2.5 bg-red-600/20 border border-red-600/50 rounded text-red-300 text-sm">{error}</div>}

      {adding && (
        <form onSubmit={handleAdd} className="card mb-4 flex flex-wrap items-end gap-3">
          {(['organism', 'host', 'antibiotic', 'abbreviation', 'subclass'] as const).map((f) => (
            <div key={f} className="flex flex-col">
              <label className="text-xs text-gray-400 mb-1 capitalize">{f}{(f === 'organism' || f === 'antibiotic') ? ' *' : ''}</label>
              <input
                value={(draft[f] as string) || ''}
                onChange={(e) => setDraft((d) => ({ ...d, [f]: e.target.value }))}
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-100 focus:border-blue-500 outline-none w-36"
              />
            </div>
          ))}
          {(['susceptible_max', 'intermediate_min', 'resistant_min'] as const).map((f) => (
            <div key={f} className="flex flex-col">
              <label className="text-xs text-gray-400 mb-1">{f === 'susceptible_max' ? 'S≤' : f === 'intermediate_min' ? 'I≥' : 'R≥'}</label>
              <input
                type="number" step="any"
                value={(draft[f] as number) ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, [f]: e.target.value === '' ? null : Number(e.target.value) }))}
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-100 focus:border-blue-500 outline-none w-20"
              />
            </div>
          ))}
          <button type="submit" className="btn-primary text-sm">Save</button>
          <button type="button" onClick={() => setAdding(false)} className="btn-secondary text-sm">Cancel</button>
        </form>
      )}

      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={organism}
          onChange={(e) => setOrganism(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none"
        >
          <option value="">All organisms ({organisms.length})</option>
          {organisms.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by antibiotic or organism…"
          className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-72"
        />
      </div>

      <div className="card">
        {loading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-gray-500">No breakpoints match.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Organism</th>
                  <th className="table-header">Host</th>
                  <th className="table-header">Subclass</th>
                  <th className="table-header">Antibiotic</th>
                  <th className="table-header text-green-300">S ≤</th>
                  <th className="table-header text-yellow-300">I ≥</th>
                  <th className="table-header text-red-300">R ≥</th>
                  <th className="table-header">Notes</th>
                  <th className="table-header"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-800/50">
                    <td className="table-cell text-gray-300 italic">{r.organism}</td>
                    <td className="table-cell text-gray-400">{r.host || '—'}</td>
                    <td className="table-cell text-gray-500 text-xs">{r.subclass || '—'}</td>
                    <td className="table-cell font-medium text-gray-200">
                      {r.antibiotic}{r.abbreviation ? <span className="text-gray-500"> ({r.abbreviation})</span> : null}
                    </td>
                    <td className="table-cell"><NumCell value={r.susceptible_max} onCommit={(v) => commit(r.id, { susceptible_max: v })} /></td>
                    <td className="table-cell"><NumCell value={r.intermediate_min} onCommit={(v) => commit(r.id, { intermediate_min: v })} /></td>
                    <td className="table-cell"><NumCell value={r.resistant_min} onCommit={(v) => commit(r.id, { resistant_min: v })} /></td>
                    <td className="table-cell text-xs text-gray-500 max-w-[14rem] truncate" title={r.notes || ''}>{r.notes || '—'}</td>
                    <td className="table-cell text-right">
                      <button onClick={() => handleDelete(r.id)} className="text-gray-500 hover:text-red-400 transition-colors" title="Delete">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && filtered.length > 0 && (
          <p className="text-xs text-gray-500 mt-3">{filtered.length} breakpoint{filtered.length === 1 ? '' : 's'}{(q || organism) ? ` (filtered from ${rows.length})` : ''}</p>
        )}
      </div>
    </div>
  );
}
