'use client';

import { useState, useEffect } from 'react';

export function getAuthHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('radar_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function authFetch(url: string): Promise<Response> {
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('radar_token');
    window.location.href = '/login';
  }
  return res;
}

export async function authPost(url: string, body: object): Promise<Response> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('radar_token');
    window.location.href = '/login';
    // Throw so callers don't try to parse the 401 body as data
    throw new Error('Session expired. Redirecting to login...');
  }
  return res;
}

export interface PickerSample {
  sample_id: string;
  name: string;
  species: string | null;
  st: string | null;
  project_name: string | null;
}

export function SamplePicker({
  samples, selected, onToggle, onSelectAll, onDeselectAll, loading,
}: {
  samples: PickerSample[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  loading: boolean;
}) {
  const [search, setSearch] = useState('');
  const [speciesFilter, setSpeciesFilter] = useState('');

  const species = Array.from(new Set(samples.map((s) => s.species).filter(Boolean) as string[])).sort();

  const filtered = samples.filter((s) => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (speciesFilter && s.species !== speciesFilter) return false;
    return true;
  });

  if (loading) return <div className="flex items-center justify-center h-20"><div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name..." className="input text-xs py-1.5 px-2 w-44" />
        {species.length > 1 && (
          <select value={speciesFilter} onChange={(e) => setSpeciesFilter(e.target.value)} className="input text-xs py-1.5 px-2">
            <option value="">All species</option>
            {species.map((sp) => <option key={sp} value={sp}>{sp}</option>)}
          </select>
        )}
        <button onClick={onSelectAll} className="text-xs text-blue-400 hover:text-blue-300">Select all ({filtered.length})</button>
        <button onClick={onDeselectAll} className="text-xs text-gray-500 hover:text-gray-300">Deselect all</button>
        <span className="text-xs text-gray-500 ml-auto">{selected.size} selected</span>
      </div>
      <div className="max-h-60 overflow-y-auto border border-gray-800 rounded-lg">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="border-b border-gray-800">
              <th className="w-8 px-2 py-1.5" />
              <th className="text-left px-2 py-1.5 text-gray-400 font-medium">Sample</th>
              <th className="text-left px-2 py-1.5 text-gray-400 font-medium">Species</th>
              <th className="text-left px-2 py-1.5 text-gray-400 font-medium">ST</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.sample_id} className={`cursor-pointer hover:bg-gray-800/50 ${selected.has(s.sample_id) ? 'bg-blue-600/10' : ''}`} onClick={() => onToggle(s.sample_id)}>
                <td className="px-2 py-1 text-center">
                  <input type="checkbox" checked={selected.has(s.sample_id)} onChange={() => onToggle(s.sample_id)} className="rounded border-gray-600" onClick={(e) => e.stopPropagation()} />
                </td>
                <td className="px-2 py-1 text-gray-200 font-medium">{s.name}</td>
                <td className="px-2 py-1 text-gray-400 italic">{s.species || '-'}</td>
                <td className="px-2 py-1 text-gray-400">{s.st ? `ST${s.st}` : '-'}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="text-center py-4 text-gray-600">No samples match filters</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function useSamplePicker() {
  const [allSamples, setAllSamples] = useState<PickerSample[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const r = await authFetch('/api/tools/samples');
          if (r.ok) {
            const d = await r.json();
            if (!cancelled && Array.isArray(d)) setAllSamples(d);
            return;
          }
          if (r.status === 401 && attempt < 2) {
            await new Promise((res) => setTimeout(res, 1000));
            continue;
          }
        } catch { /* ignore */ }
        break;
      }
    }
    load().finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const toggle = (id: string) => setSelected((prev) => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const selectAll = () => setSelected(new Set(allSamples.map((s) => s.sample_id)));
  const deselectAll = () => setSelected(new Set());

  return { allSamples, selected, toggle, selectAll, deselectAll, loading, selectedIds: Array.from(selected) };
}

/**
 * Hook for async tool jobs: submit → poll → get results.
 * Returns { submit, data, computing, error, jobStatus }.
 */
export function useToolJob<T>(toolEndpoint: string) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);

  // Poll for completion
  useEffect(() => {
    if (!jobId || jobStatus === 'complete' || jobStatus === 'failed') return;
    const interval = setInterval(async () => {
      try {
        const r = await authFetch(`/api/tools/job/${jobId}`);
        if (!r.ok) return;
        const d = await r.json();
        setJobStatus(d.status);
        if (d.status === 'complete' && d.data) {
          setData(d.data as T);
          setComputing(false);
        } else if (d.status === 'failed') {
          setError(d.error || 'Job failed');
          setComputing(false);
        }
      } catch { /* ignore poll errors */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [jobId, jobStatus]);

  async function submit(body: object) {
    setComputing(true);
    setError(null);
    setData(null);
    setJobId(null);
    setJobStatus(null);
    try {
      const res = await authPost(toolEndpoint, body);
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      setJobId(d.job_id);
      setJobStatus('pending');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit job');
      setComputing(false);
    }
  }

  return { submit, data, computing, error, jobStatus };
}
