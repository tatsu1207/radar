'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Upload, Trash2, Grid3x3, ExternalLink, FileUp } from 'lucide-react';
import { getAllAST, importAST, deleteAST, importBreakpoints, ASTRow } from '@/lib/api';

// breakpoint standard applied to MIC values on import
const STANDARDS: { value: string; label: string }[] = [
  { value: 'EUCAST', label: 'EUCAST' },
  { value: 'CLSI', label: 'CLSI' },
  { value: 'self', label: 'Self-defined' },
];
const STANDARD_KEY = 'ast_import_standard';

// official guideline documents (include MIC + disk-content test protocols)
const REFERENCES: { standard: string; label: string; href: string }[] = [
  { standard: 'EUCAST', label: 'EUCAST clinical breakpoint tables', href: 'https://www.eucast.org/clinical_breakpoints' },
  { standard: 'EUCAST', label: 'EUCAST disk diffusion method & QC', href: 'https://www.eucast.org/ast_of_bacteria/disk_diffusion_methodology' },
  { standard: 'CLSI', label: 'CLSI M100 (free-access)', href: 'https://clsi.org/all-free-resources/' },
];

const SIR_STYLES: Record<string, string> = {
  R: 'bg-red-600/20 text-red-300',
  I: 'bg-yellow-600/20 text-yellow-300',
  S: 'bg-green-600/20 text-green-300',
};
const SIR_LABEL: Record<string, string> = { R: 'Resistant', I: 'Intermediate', S: 'Susceptible' };
const SIR_FILL: Record<string, string> = { R: '#ef4444', I: '#eab308', S: '#22c55e' };

interface Heatmap {
  samples: string[];                                      // y-axis (rows)
  antibiotics: string[];                                  // x-axis (cols), most-resistant first
  cells: Map<string, { sir: string; mic?: string | null }>;  // key `${sample}|||${antibiotic}`
}

const cellKey = (sample: string, antibiotic: string) => `${sample}|||${antibiotic}`;

// sample × antibiotic matrix of S/I/R calls. Antibiotics are ordered most-resistant
// first (by %R); samples are natural-sorted.
function buildHeatmap(rows: ASTRow[]): Heatmap {
  const counts = new Map<string, { S: number; I: number; R: number }>();
  const sampleSet = new Set<string>();
  const cells = new Map<string, { sir: string; mic?: string | null }>();
  for (const r of rows) {
    const sir = (r.sir || '').toUpperCase();
    if (sir !== 'S' && sir !== 'I' && sir !== 'R') continue;
    sampleSet.add(r.sample_name);
    cells.set(cellKey(r.sample_name, r.antibiotic), { sir, mic: r.mic });
    const c = counts.get(r.antibiotic) || { S: 0, I: 0, R: 0 };
    c[sir] += 1;
    counts.set(r.antibiotic, c);
  }
  const antibiotics = Array.from(counts.entries())
    .map(([a, c]) => ({ a, pctR: c.R / (c.S + c.I + c.R) }))
    .sort((x, y) => y.pctR - x.pctR || x.a.localeCompare(y.a))
    .map((x) => x.a);
  const samples = Array.from(sampleSet).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  return { samples, antibiotics, cells };
}

export default function ASTPage() {
  const [rows, setRows] = useState<ASTRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showChart, setShowChart] = useState(true);
  const [standard, setStandard] = useState('EUCAST');
  const fileRef = useRef<HTMLInputElement>(null);
  const cutoffRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem(STANDARD_KEY) : null;
    if (saved && STANDARDS.some((s) => s.value === saved)) setStandard(saved);
  }, []);

  function pickStandard(v: string) {
    setStandard(v);
    try { localStorage.setItem(STANDARD_KEY, v); } catch { /* ignore */ }
  }

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
      const r = await importAST(file, standard);
      const auto = r.auto_interpreted ? `, ${r.auto_interpreted} auto-called from MIC (${r.standard})` : '';
      setMsg(`Imported ${r.imported} result(s) across ${r.samples} sample(s)${auto}${r.skipped ? `, ${r.skipped} skipped` : ''}${r.errors?.length ? `. ${r.errors.length} issue(s): ${r.errors.slice(0, 3).join('; ')}${r.errors.length > 3 ? '…' : ''}` : ''}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleCutoffs(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setMsg(null);
    setError(null);
    try {
      const r = await importBreakpoints(file);
      setMsg(`Custom cutoffs: ${r.created} added, ${r.updated} updated${r.skipped ? `, ${r.skipped} skipped` : ''}. These apply to MIC-only rows under Self-defined.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cutoff import failed.');
    } finally {
      if (cutoffRef.current) cutoffRef.current.value = '';
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

  const heatmap = useMemo(() => buildHeatmap(filtered), [filtered]);

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-2">
        <h1 className="text-2xl font-bold text-white">AST (Antibiotic Susceptibility)</h1>
        <div className="flex items-center gap-2 shrink-0">
          {standard === 'self' && (
            <>
              <button onClick={() => cutoffRef.current?.click()} className="btn-secondary flex items-center gap-1.5 text-sm" title="Upload your own MIC cutoffs (organism, antibiotic, S, R)">
                <FileUp className="w-4 h-4" />
                Custom cutoffs
              </button>
              <input ref={cutoffRef} type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" className="hidden" onChange={handleCutoffs} />
            </>
          )}
          <button onClick={() => fileRef.current?.click()} className="btn-primary flex items-center gap-1.5 text-sm">
            <Upload className="w-4 h-4" />
            Import AST
          </button>
          <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" className="hidden" onChange={handleImport} />
        </div>
      </div>
      <p className="text-sm text-gray-400 mb-3">
        Lab-entered phenotypic susceptibility results across all samples. On import, RADAR applies the selected breakpoint standard to any <code className="text-gray-300">mic</code> values to auto-call S/I/R per the sample&apos;s species. Or add/edit per sample in the sample&apos;s AST tab.
      </p>

      {/* breakpoint standard selector + official references */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">Breakpoint standard</span>
          <div className="inline-flex rounded-md border border-gray-700 overflow-hidden">
            {STANDARDS.map((s) => (
              <button
                key={s.value}
                onClick={() => pickStandard(s.value)}
                className={`px-2.5 py-1.5 text-sm border-r border-gray-700 last:border-r-0 transition-colors ${
                  standard === s.value ? 'bg-blue-600 text-white' : 'bg-gray-900 text-gray-300 hover:bg-gray-800'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-gray-500">Reference & test protocols:</span>
          {REFERENCES.filter((r) => standard !== 'self' ? r.standard === standard : true).map((r) => (
            <a key={r.href} href={r.href} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center gap-1 text-blue-400 hover:underline">
              {r.label} <ExternalLink className="w-3 h-3" />
            </a>
          ))}
        </div>
      </div>
      {standard === 'self' && (
        <p className="text-xs text-gray-500 mb-4 -mt-2">
          Self-defined: an <code>sir</code> value in your file is kept as-is; MIC-only rows are interpreted against your uploaded custom cutoffs (if any).
        </p>
      )}

      <details className="mb-4 text-xs text-gray-500">
        <summary className="cursor-pointer hover:text-gray-300">CSV/TSV format for bulk import</summary>
        <div className="mt-2 space-y-2 pl-2">
          <div>
            <span className="text-gray-400">Long format</span> — first column <code className="text-blue-400">SAMPLE</code>, then <code className="text-blue-400">antibiotic</code>, optional <code className="text-blue-400">method</code>, <code className="text-blue-400">mic</code>, and <code className="text-blue-400">sir</code>. Under EUCAST/CLSI, the <code className="text-blue-400">mic</code> is interpreted automatically (no <code>sir</code> needed); a disk-only row without a MIC needs an <code>sir</code>:
            <pre className="mt-1 p-2 bg-gray-900 rounded text-gray-400 overflow-x-auto">SAMPLE{'\t'}antibiotic{'\t'}method{'\t'}mic{'\n'}EC1{'\t'}Ciprofloxacin{'\t'}MIC{'\t'}0.25{'\n'}EC1{'\t'}Meropenem{'\t'}MIC{'\t'}8</pre>
          </div>
          <div>
            <span className="text-gray-400">Wide format</span> — first column <code className="text-blue-400">SAMPLE</code>, one column per antibiotic (cells = S/I/R; blanks ignored). Taken as-is regardless of standard:
            <pre className="mt-1 p-2 bg-gray-900 rounded text-gray-400 overflow-x-auto">SAMPLE{'\t'}Ciprofloxacin{'\t'}Ampicillin{'\n'}EC1{'\t'}S{'\t'}R</pre>
          </div>
          <div className="text-gray-500">SAMPLE must match the sample name. Existing (sample, antibiotic) entries are updated, not duplicated. MIC auto-interpretation needs the sample&apos;s species (from the pipeline or metadata).</div>
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

      {heatmap.samples.length > 0 && (
        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Grid3x3 className="w-4 h-4 text-blue-400" />
              <h2 className="text-sm font-semibold text-gray-100">Antibiogram heatmap</h2>
              <span className="text-xs text-gray-500">
                {heatmap.samples.length} sample{heatmap.samples.length === 1 ? '' : 's'} × {heatmap.antibiotics.length} antibiotic{heatmap.antibiotics.length === 1 ? '' : 's'}{q ? ' (filtered)' : ''}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-3 text-xs text-gray-400">
                {(['S', 'I', 'R'] as const).map((k) => (
                  <span key={k} className="flex items-center gap-1">
                    <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: SIR_FILL[k] }} />
                    {SIR_LABEL[k]}
                  </span>
                ))}
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2.5 h-2.5 rounded-sm border border-gray-700 bg-gray-900" />
                  n/t
                </span>
              </div>
              <button onClick={() => setShowChart((v) => !v)} className="text-xs text-gray-400 hover:text-gray-200">
                {showChart ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>
          {showChart && (
            <div className="overflow-auto max-h-[70vh]">
              <table className="border-separate" style={{ borderSpacing: 2 }}>
                <thead>
                  <tr>
                    <th className="sticky left-0 top-0 z-20 bg-gray-900" />
                    {heatmap.antibiotics.map((a) => (
                      <th key={a} className="sticky top-0 z-10 bg-gray-900 align-bottom p-0.5" title={a}>
                        <div className="text-[11px] text-gray-400 font-normal mx-auto whitespace-nowrap"
                             style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxHeight: 150 }}>
                          {a}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {heatmap.samples.map((s) => (
                    <tr key={s}>
                      <th className="sticky left-0 z-10 bg-gray-900 text-right pr-2 text-xs font-medium text-gray-300 whitespace-nowrap">
                        {s}
                      </th>
                      {heatmap.antibiotics.map((a) => {
                        const c = heatmap.cells.get(cellKey(s, a));
                        return (
                          <td key={a} className="p-0">
                            <div
                              className="w-7 h-6 rounded-sm flex items-center justify-center text-[10px] font-semibold"
                              style={c ? { background: SIR_FILL[c.sir], color: '#111827' }
                                       : { background: '#111827', border: '1px solid #1f2937' }}
                              title={c ? `${s} · ${a}: ${SIR_LABEL[c.sir]}${c.mic ? ` (MIC ${c.mic})` : ''}` : `${s} · ${a}: not tested`}
                            >
                              {c ? c.sir : ''}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

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
