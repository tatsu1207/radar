'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Upload, Trash2 } from 'lucide-react';
import { getAllAST, importAST, deleteAST, ASTRow } from '@/lib/api';

const SIR_STYLES: Record<string, string> = {
  R: 'bg-red-600/20 text-red-300',
  I: 'bg-yellow-600/20 text-yellow-300',
  S: 'bg-green-600/20 text-green-300',
};
const SIR_LABEL: Record<string, string> = { R: 'Resistant', I: 'Intermediate', S: 'Susceptible' };

export default function ASTPage() {
  const [rows, setRows] = useState<ASTRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setRows(await getAllAST());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load AST results.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setMsg(null);
    setError(null);
    try {
      const r = await importAST(file);
      setMsg(`Imported ${r.imported} result(s) across ${r.samples} sample(s)${r.skipped ? `, ${r.skipped} skipped` : ''}${r.errors?.length ? `. ${r.errors.length} issue(s): ${r.errors.slice(0, 3).join('; ')}${r.errors.length > 3 ? '…' : ''}` : ''}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDelete(sampleId: string, id: string) {
    try {
      await deleteAST(sampleId, id);
      setRows((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed.');
    }
  }

  const q = search.trim().toLowerCase();
  const filtered = q
    ? rows.filter((r) => r.sample_name.toLowerCase().includes(q) || r.antibiotic.toLowerCase().includes(q))
    : rows;

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-2">
        <h1 className="text-2xl font-bold text-white">AST (Antibiotic Susceptibility)</h1>
        <button onClick={() => fileRef.current?.click()} className="btn-primary flex items-center gap-1.5 text-sm shrink-0">
          <Upload className="w-4 h-4" />
          Import CSV
        </button>
        <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" className="hidden" onChange={handleImport} />
      </div>
      <p className="text-sm text-gray-400 mb-4">
        Lab-entered phenotypic susceptibility results across all samples. Import in bulk, or add/edit per sample in the sample&apos;s AST tab.
      </p>

      <details className="mb-4 text-xs text-gray-500">
        <summary className="cursor-pointer hover:text-gray-300">CSV/TSV format for bulk import</summary>
        <div className="mt-2 space-y-2 pl-2">
          <div>
            <span className="text-gray-400">Long format</span> — first column <code className="text-blue-400">SAMPLE</code>, then <code className="text-blue-400">antibiotic</code>, optional <code className="text-blue-400">method</code>/<code className="text-blue-400">mic</code>, and <code className="text-blue-400">sir</code> (S/I/R):
            <pre className="mt-1 p-2 bg-gray-900 rounded text-gray-400 overflow-x-auto">SAMPLE{'\t'}antibiotic{'\t'}method{'\t'}mic{'\t'}sir{'\n'}EC1{'\t'}Ciprofloxacin{'\t'}MIC{'\t'}0.25{'\t'}S{'\n'}EC1{'\t'}Ampicillin{'\t'}Disk{'\t'}-{'\t'}R</pre>
          </div>
          <div>
            <span className="text-gray-400">Wide format</span> — first column <code className="text-blue-400">SAMPLE</code>, one column per antibiotic (cells = S/I/R; blanks ignored):
            <pre className="mt-1 p-2 bg-gray-900 rounded text-gray-400 overflow-x-auto">SAMPLE{'\t'}Ciprofloxacin{'\t'}Ampicillin{'\n'}EC1{'\t'}S{'\t'}R</pre>
          </div>
          <div className="text-gray-500">SAMPLE must match the sample name. Existing (sample, antibiotic) entries are updated, not duplicated.</div>
        </div>
      </details>

      {msg && <div className="mb-3 p-2.5 bg-blue-600/15 border border-blue-600/40 rounded text-blue-200 text-sm">{msg}</div>}
      {error && <div className="mb-3 p-2.5 bg-red-600/20 border border-red-600/50 rounded text-red-300 text-sm">{error}</div>}

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Filter by sample or antibiotic…"
        className="mb-4 bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-72"
      />

      <div className="card">
        {loading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-gray-500">
            {rows.length === 0 ? 'No AST results yet. Import a CSV above, or add them in a sample’s AST tab.' : 'No matches.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Sample</th>
                  <th className="table-header">Antibiotic</th>
                  <th className="table-header">Method</th>
                  <th className="table-header">MIC</th>
                  <th className="table-header">Interpretation</th>
                  <th className="table-header"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-800/50">
                    <td className="table-cell font-medium text-gray-200">{r.sample_name}</td>
                    <td className="table-cell text-gray-200">{r.antibiotic}</td>
                    <td className="table-cell text-gray-400">{r.method || '—'}</td>
                    <td className="table-cell font-mono text-sm text-gray-300">{r.mic || '—'}</td>
                    <td className="table-cell">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${SIR_STYLES[r.sir] || 'bg-gray-700 text-gray-300'}`}>
                        {r.sir} — {SIR_LABEL[r.sir] || r.sir}
                      </span>
                    </td>
                    <td className="table-cell text-right">
                      <button onClick={() => handleDelete(r.sample_id, r.id)} className="text-gray-500 hover:text-red-400 transition-colors" title="Delete">
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
          <p className="text-xs text-gray-500 mt-3">{filtered.length} result{filtered.length === 1 ? '' : 's'}{q ? ` (filtered from ${rows.length})` : ''}</p>
        )}
      </div>
    </div>
  );
}
