'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Trash2, Upload, Wand2 } from 'lucide-react';
import {
  getAST, addAST, deleteAST, importAST, ASTResult,
  getBreakpointOrganisms, interpretMIC, OrganismPanel,
  getBreakpointStandards, resolveBreakpointOrganism, BreakpointStandard,
} from '@/lib/api';

const SIR_STYLES: Record<string, string> = {
  R: 'bg-red-600/20 text-red-300',
  I: 'bg-yellow-600/20 text-yellow-300',
  S: 'bg-green-600/20 text-green-300',
};
const SIR_LABEL: Record<string, string> = { R: 'Resistant', I: 'Intermediate', S: 'Susceptible' };
const METHODS = ['Sensititre', 'Vitek AST', 'Broth microdilution', 'Etest', 'Disk diffusion'];
const STANDARD_PREF = ['EUCAST', 'CLSI', 'APQA']; // preferred default order
const STANDARD_KEY = 'ast_breakpoint_standard';

// pick the panel whose organism matches the sample species (exact or prefix either way)
function matchOrganism(panels: OrganismPanel[], species: string): string {
  if (!species) return '';
  const s = species.trim().toLowerCase();
  const hit = panels.find((p) => s === p.organism.toLowerCase()
    || s.startsWith(p.organism.toLowerCase()) || p.organism.toLowerCase().startsWith(s));
  return hit?.organism || '';
}

export default function ASTPanel({ sampleId, defaultOrganism = '' }: { sampleId: string; defaultOrganism?: string }) {
  const [results, setResults] = useState<ASTResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [standards, setStandards] = useState<BreakpointStandard[]>([]);
  const [standard, setStandard] = useState('');
  const [panels, setPanels] = useState<OrganismPanel[]>([]);
  const [organism, setOrganism] = useState('');
  const [host, setHost] = useState('');

  const [antibiotic, setAntibiotic] = useState('');
  const [method, setMethod] = useState('Sensititre');
  const [mic, setMic] = useState('');
  const [sir, setSir] = useState<'S' | 'I' | 'R'>('S');
  const [autoNote, setAutoNote] = useState<string | null>(null); // feedback from auto-interpretation

  const fileRef = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setResults(await getAST(sampleId));
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [sampleId]);

  useEffect(() => { load(); }, [load]);

  // load available guideline standards once; default to a remembered or preferred one
  useEffect(() => {
    getBreakpointStandards().then((s) => {
      setStandards(s);
      const names = s.map((x) => x.standard);
      const saved = typeof window !== 'undefined' ? localStorage.getItem(STANDARD_KEY) : null;
      const pref = STANDARD_PREF.find((p) => names.includes(p));
      setStandard((cur) => cur || (saved && names.includes(saved) ? saved : (pref || names[0] || '')));
    }).catch(() => {});
  }, []);

  // (re)load the organism panels for the chosen standard, then preselect the sample's
  // organism — resolving it up its lineage server-side (species -> genus -> ... -> order),
  // since e.g. E. coli breakpoints may live under "Enterobacterales".
  useEffect(() => {
    if (!standard) return;
    let cancelled = false;
    setHost(''); // host options are standard-specific; clear any stale selection
    getBreakpointOrganisms(standard).then(async (p) => {
      if (cancelled) return;
      setPanels(p);
      const direct = matchOrganism(p, defaultOrganism);
      if (direct) { setOrganism(direct); return; }
      if (defaultOrganism) {
        try {
          const r = await resolveBreakpointOrganism(defaultOrganism, standard);
          if (!cancelled && r.organism) setOrganism(r.organism);
          else if (!cancelled) setOrganism('');
        } catch { if (!cancelled) setOrganism(''); }
      } else if (!cancelled) {
        setOrganism('');
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [standard, defaultOrganism]);

  const panel = panels.find((p) => p.organism === organism);
  const abxOptions = panel?.antibiotics || [];

  // auto-interpret MIC -> SIR whenever standard/organism/antibiotic/mic/host change
  useEffect(() => {
    if (!organism || !antibiotic.trim() || !mic.trim()) { setAutoNote(null); return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await interpretMIC({ organism, antibiotic: antibiotic.trim(), mic: mic.trim(), host: host || undefined, standard: standard || undefined });
        if (cancelled) return;
        if (r.sir) {
          setSir(r.sir);
          const parts = [
            r.matched_standard,
            r.susceptible_max != null ? `S ≤ ${r.susceptible_max}` : null,
            r.resistant_min != null ? `R ${r.matched_standard === 'EUCAST' ? '>' : '≥'} ${r.resistant_min}` : null,
            r.matched_organism, r.matched_host,
          ].filter(Boolean);
          setAutoNote(`Auto: ${r.sir} (${parts.join(' · ')})`);
        } else {
          setAutoNote('No matching breakpoint — set S/I/R manually.');
        }
      } catch { /* ignore */ }
    }, 350);
    return () => { cancelled = true; clearTimeout(t); };
  }, [standard, organism, antibiotic, mic, host]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!antibiotic.trim()) { setError('Antibiotic is required.'); return; }
    setSaving(true);
    setError(null);
    try {
      await addAST(sampleId, {
        antibiotic: antibiotic.trim(),
        method: method.trim() || undefined,
        mic: mic.trim() || undefined,
        sir,
        organism: organism || undefined,
        host: host || undefined,
      });
      setAntibiotic(''); setMic(''); setSir('S'); setAutoNote(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add AST result.');
    } finally {
      setSaving(false);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportMsg(null);
    setError(null);
    try {
      const r = await importAST(file);
      setImportMsg(`Imported ${r.imported} result(s) across ${r.samples} sample(s)${r.skipped ? `, ${r.skipped} skipped` : ''}${r.errors?.length ? `. ${r.errors.length} issue(s): ${r.errors.slice(0, 3).join('; ')}${r.errors.length > 3 ? '…' : ''}` : ''}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteAST(sampleId, id);
      setResults((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete.');
    }
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-4 gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">Antibiotic Susceptibility (AST)</h2>
          <p className="text-sm text-gray-400 mt-0.5">
            Enter an MIC and S/I/R is interpreted automatically against the chosen guideline standard (EUCAST / CLSI).
          </p>
        </div>
        <div className="shrink-0">
          <button onClick={() => fileRef.current?.click()} className="btn-secondary flex items-center gap-1.5 text-sm">
            <Upload className="w-4 h-4" />
            Import CSV
          </button>
          <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,.xlsx,.xls" className="hidden" onChange={handleImport} />
        </div>
      </div>

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

      {importMsg && (
        <div className="mb-3 p-2.5 bg-blue-600/15 border border-blue-600/40 rounded text-blue-200 text-sm">{importMsg}</div>
      )}

      {/* Add form */}
      <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-3 mb-5 p-3 bg-gray-800/40 border border-gray-700 rounded-lg">
        {standards.length > 0 && (
          <div className="flex flex-col">
            <label className="text-xs text-gray-400 mb-1">Standard</label>
            <div className="inline-flex rounded-md border border-gray-700 overflow-hidden">
              {standards.map((s) => (
                <button
                  key={s.standard}
                  type="button"
                  onClick={() => { setStandard(s.standard); try { localStorage.setItem(STANDARD_KEY, s.standard); } catch { /* ignore */ } }}
                  title={`${s.count} breakpoints`}
                  className={`px-2.5 py-1.5 text-sm border-r border-gray-700 last:border-r-0 transition-colors ${
                    standard === s.standard ? 'bg-blue-600 text-white' : 'bg-gray-900 text-gray-300 hover:bg-gray-800'
                  }`}
                >
                  {s.standard}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">Organism</label>
          <select
            value={organism}
            onChange={(e) => { setOrganism(e.target.value); setHost(''); }}
            className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-52"
          >
            <option value="">— select organism —</option>
            {panels.map((p) => <option key={p.organism} value={p.organism}>{p.organism}</option>)}
          </select>
        </div>
        {panel && panel.hosts.length > 0 && (
          <div className="flex flex-col">
            <label className="text-xs text-gray-400 mb-1">Host</label>
            <select
              value={host}
              onChange={(e) => setHost(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none"
            >
              <option value="">any</option>
              {panel.hosts.map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
          </div>
        )}
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">Antibiotic *</label>
          {abxOptions.length > 0 ? (
            <select
              value={antibiotic}
              onChange={(e) => setAntibiotic(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-56"
            >
              <option value="">— select antibiotic —</option>
              {abxOptions.map((a) => (
                <option key={a.antibiotic} value={a.antibiotic}>
                  {a.antibiotic}{a.abbreviation ? ` (${a.abbreviation})` : ''}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={antibiotic}
              onChange={(e) => setAntibiotic(e.target.value)}
              placeholder="e.g. Ciprofloxacin"
              className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-48"
            />
          )}
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">Method</label>
          <input
            list="ast-methods"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-40"
          />
          <datalist id="ast-methods">{METHODS.map((m) => <option key={m} value={m} />)}</datalist>
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">MIC (µg/mL)</label>
          <input
            value={mic}
            onChange={(e) => setMic(e.target.value)}
            placeholder="e.g. ≤0.5 or 32"
            className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none w-32"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-xs text-gray-400 mb-1">Interpretation *</label>
          <select
            value={sir}
            onChange={(e) => setSir(e.target.value as 'S' | 'I' | 'R')}
            className="bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 focus:border-blue-500 outline-none"
          >
            <option value="S">S — Susceptible</option>
            <option value="I">I — Intermediate</option>
            <option value="R">R — Resistant</option>
          </select>
        </div>
        <button type="submit" disabled={saving} className="btn-primary flex items-center gap-1.5 text-sm disabled:opacity-50">
          <Plus className="w-4 h-4" />
          {saving ? 'Adding…' : 'Add'}
        </button>
        {autoNote && (
          <div className="basis-full flex items-center gap-1.5 text-xs text-gray-400">
            <Wand2 className="w-3.5 h-3.5 text-blue-400" />
            {autoNote}
          </div>
        )}
      </form>

      {error && (
        <div className="mb-3 p-2.5 bg-red-600/20 border border-red-600/50 rounded text-red-300 text-sm">{error}</div>
      )}

      {/* Results table */}
      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : results.length === 0 ? (
        <p className="text-sm text-gray-500">No AST results entered yet. Add one above.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="table-header">Antibiotic</th>
                <th className="table-header">Method</th>
                <th className="table-header">MIC</th>
                <th className="table-header">Interpretation</th>
                <th className="table-header"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {results.map((r) => (
                <tr key={r.id} className="hover:bg-gray-800/50">
                  <td className="table-cell font-medium text-gray-200">{r.antibiotic}</td>
                  <td className="table-cell text-gray-400">{r.method || '—'}</td>
                  <td className="table-cell font-mono text-sm text-gray-300">{r.mic || '—'}</td>
                  <td className="table-cell">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${SIR_STYLES[r.sir] || 'bg-gray-700 text-gray-300'}`}>
                      {r.sir} — {SIR_LABEL[r.sir] || r.sir}
                    </span>
                  </td>
                  <td className="table-cell text-right">
                    <button
                      onClick={() => handleDelete(r.id)}
                      className="text-gray-500 hover:text-red-400 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
