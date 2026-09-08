'use client';

import { useState, useEffect } from 'react';
import { Download, AlertTriangle, Info, RefreshCw } from 'lucide-react';
import dynamic from 'next/dynamic';

const TemporalGeoMap = dynamic(() => import('@/components/ResistomeMapInner'), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-64"><div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" /></div>,
});

function getAuthHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('radar_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function authFetch(url: string): Promise<Response> {
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('radar_token');
    window.location.href = '/login';
  }
  return res;
}

async function authPost(url: string, body: object): Promise<Response> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (res.status === 401 && typeof window !== 'undefined') {
    localStorage.removeItem('radar_token');
    window.location.href = '/login';
  }
  return res;
}

// ─── Shared Sample Picker ───
interface PickerSample {
  sample_id: string;
  name: string;
  species: string | null;
  st: string | null;
  project_name: string | null;
}

function SamplePicker({
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

function useSamplePicker() {
  const [allSamples, setAllSamples] = useState<PickerSample[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authFetch('/api/tools/samples')
      .then((r) => r.json())
      .then((d) => setAllSamples(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const toggle = (id: string) => setSelected((prev) => { const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const selectAll = () => setSelected(new Set(allSamples.map((s) => s.sample_id)));
  const deselectAll = () => setSelected(new Set());

  return { allSamples, selected, toggle, selectAll, deselectAll, loading, selectedIds: Array.from(selected) };
}

// ─── Main Page ───
export default function ToolsPage() {
  const [toolTab, setToolTab] = useState<'phenotype' | 'hazard' | 'comparison' | 'syntracker' | 'easyfig' | 'resistome' | 'sra'>('phenotype');

  const tabs = [
    { key: 'phenotype' as const, label: 'Phenotype Prediction' },
    { key: 'hazard' as const, label: 'Hazard Ranking' },
    { key: 'comparison' as const, label: 'ANI' },
    { key: 'syntracker' as const, label: 'SynTracker' },
    { key: 'easyfig' as const, label: 'EasyFig' },
    { key: 'resistome' as const, label: 'Resistome Tracker' },
    { key: 'sra' as const, label: 'SRA Submission' },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-2">Tools</h1>
      <div className="border-b border-gray-800 mb-6">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setToolTab(t.key)} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === t.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {toolTab === 'phenotype' && <PhenotypePredictionTool />}
      {toolTab === 'hazard' && <HazardRankingTool />}
      {toolTab === 'comparison' && <GenomeComparisonTool />}
      {toolTab === 'syntracker' && <SynTrackerTool />}
      {toolTab === 'easyfig' && <EasyFigTool />}
      {toolTab === 'resistome' && <ResistomeTrackerTool />}
      {toolTab === 'sra' && <SRASubmissionTool />}
    </div>
  );
}

// ─── Phenotype Prediction Tool ───
interface ModelQuality {
  n_samples: number;
  r_percent: number;
  cv_f1: number;
}

interface MLPrediction {
  id: string;
  antibiotic: string;
  drug_class: string;
  prediction: string;
  probability: number;
  confidence: string;
  key_genes: string[];
  key_mutations: string[];
  model_quality: ModelQuality | null;
}

interface MLPredictionResponse {
  species: string | null;
  mlst_st: string | null;
  n_antibiotics: number;
  n_resistant: number;
  n_susceptible: number;
  predictions: MLPrediction[];
}

function PhenotypePredictionTool() {
  const [samples, setSamples] = useState<{ id: string; name: string; status: string }[]>([]);
  const [selectedSample, setSelectedSample] = useState('');
  const [data, setData] = useState<MLPredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [predLoading, setPredLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'resistant' | 'susceptible'>('all');
  const [drugClassFilter, setDrugClassFilter] = useState<Set<string>>(new Set());
  const [confidenceFilter, setConfidenceFilter] = useState<Set<string>>(new Set());
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    authFetch('/api/pipeline/status')
      .then((r) => r.json())
      .then((d: { sample_id: string; sample_name: string; status: string }[]) => {
        const completed = d.filter((s) => s.status === 'complete');
        setSamples(completed.map((s) => ({ id: s.sample_id, name: s.sample_name, status: s.status })));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function loadPredictions(sampleId: string) {
    setSelectedSample(sampleId);
    setData(null);
    setError(null);
    if (!sampleId) return;
    setPredLoading(true);
    try {
      const res = await authFetch(`/api/samples/${sampleId}/ml-predictions`);
      if (!res.ok) throw new Error(await res.text());
      const d: MLPredictionResponse = await res.json();
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load predictions');
    } finally {
      setPredLoading(false);
    }
  }

  const drugClasses = Array.from(new Set(data?.predictions.map((p) => p.drug_class).filter(Boolean) || [])).sort();

  function downloadPredictions() {
    if (!data || !filtered.length) return;
    const sampleName = samples.find((s) => s.id === selectedSample)?.name || 'sample';
    const headers = ['Antibiotic', 'Drug Class', 'Prediction', 'P(Resistant)', 'Confidence', 'Key Genes', 'Key Mutations'];
    const rows = filtered.map((p) => [
      p.antibiotic, p.drug_class, p.prediction,
      p.probability.toFixed(3), p.confidence,
      p.key_genes.join('; '), p.key_mutations.join('; '),
    ]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${sampleName}_phenotype_prediction.tsv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const filtered = data?.predictions.filter((p) => {
    if (filter === 'resistant' && p.prediction !== 'Resistant') return false;
    if (filter === 'susceptible' && p.prediction !== 'Susceptible') return false;
    if (drugClassFilter.size > 0 && !drugClassFilter.has(p.drug_class)) return false;
    if (confidenceFilter.size > 0 && !confidenceFilter.has(p.confidence)) return false;
    if (searchText && !p.antibiotic.toLowerCase().includes(searchText.toLowerCase()) && !p.drug_class.toLowerCase().includes(searchText.toLowerCase())) return false;
    return true;
  }) || [];

  if (loading) return <div className="flex items-center justify-center h-32"><div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        ML-based phenotype prediction using pre-trained Random Forest models. Select a completed sample to view per-antibiotic resistance predictions.
      </p>

      <div className="card">
        <div className="flex items-center gap-4">
          <label className="text-sm text-gray-300 font-medium whitespace-nowrap">Sample:</label>
          <select
            value={selectedSample}
            onChange={(e) => loadPredictions(e.target.value)}
            className="input flex-1 text-sm"
          >
            <option value="">Select a completed sample...</option>
            {samples.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      </div>

      {predLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {data && data.predictions.length === 0 && (
        <div className="card text-center py-8 text-gray-500">
          No predictions available. This species may not be supported (Salmonella, E. coli, Klebsiella, S. aureus, A. baumannii), or the pipeline may not have completed annotation.
        </div>
      )}

      {data && data.predictions.length > 0 && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="card text-center">
              <p className="text-xs text-gray-400">Species</p>
              <p className="text-sm font-medium text-gray-100 mt-1">{data.species || 'Unknown'}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400">MLST</p>
              <p className="text-sm font-medium text-gray-100 mt-1">ST{data.mlst_st || '?'}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400">Resistant</p>
              <p className="text-2xl font-bold text-red-400 mt-1">{data.n_resistant}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400">Susceptible</p>
              <p className="text-2xl font-bold text-green-400 mt-1">{data.n_susceptible}</p>
            </div>
          </div>

          {/* Filters */}
          <div className="card space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {/* R/S filter */}
              <div className="flex gap-1">
                {(['all', 'resistant', 'susceptible'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      filter === f ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {f === 'all' ? `All (${data.predictions.length})` : f === 'resistant' ? `R (${data.n_resistant})` : `S (${data.n_susceptible})`}
                  </button>
                ))}
              </div>
              {/* Confidence */}
              <div className="flex gap-1">
                {(['High', 'Moderate', 'Low'] as const).map((c) => (
                  <button
                    key={c}
                    onClick={() => setConfidenceFilter((prev) => { const next = new Set(prev); next.has(c) ? next.delete(c) : next.add(c); return next; })}
                    className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      confidenceFilter.has(c)
                        ? c === 'High' ? 'bg-green-600/30 text-green-300 border border-green-500/40'
                        : c === 'Moderate' ? 'bg-yellow-600/30 text-yellow-300 border border-yellow-500/40'
                        : 'bg-gray-600/30 text-gray-300 border border-gray-500/40'
                        : 'bg-gray-800 text-gray-500 hover:bg-gray-700'
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
              {/* Search */}
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search antibiotic..."
                className="input text-xs py-1.5 px-2 w-40"
              />
              {/* Clear all */}
              {(drugClassFilter.size > 0 || confidenceFilter.size > 0 || searchText || filter !== 'all') && (
                <button
                  onClick={() => { setFilter('all'); setDrugClassFilter(new Set()); setConfidenceFilter(new Set()); setSearchText(''); }}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >Clear all</button>
              )}
              {/* Result count + download */}
              <span className="text-xs text-gray-500 ml-auto">{filtered.length} of {data.predictions.length}</span>
              <button
                onClick={downloadPredictions}
                className="btn-secondary text-xs flex items-center gap-1.5"
                title="Download predictions as TSV"
              >
                <Download className="w-3.5 h-3.5" />
                Download TSV
              </button>
            </div>
            {/* Drug class chips */}
            {drugClasses.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <span className="text-xs text-gray-500 py-1">Drug class:</span>
                {drugClasses.map((dc) => (
                  <button
                    key={dc}
                    onClick={() => setDrugClassFilter((prev) => { const next = new Set(prev); next.has(dc) ? next.delete(dc) : next.add(dc); return next; })}
                    className={`px-2 py-1 rounded text-xs transition-colors ${
                      drugClassFilter.has(dc)
                        ? 'bg-blue-600/30 text-blue-300 border border-blue-500/40'
                        : 'bg-gray-800 text-gray-500 hover:bg-gray-700 hover:text-gray-300'
                    }`}
                  >
                    {dc}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Predictions table */}
          <div className="card">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Antibiotic</th>
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Drug Class</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium">Prediction</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium" title="Probability of resistance (0-100%)">P(Resistant)</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium">Confidence</th>
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Key Genes</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium" title="Model quality: F1, training size, R%">Model</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {filtered.map((p) => {
                    const q = p.model_quality;
                    const lowF1 = q && q.cv_f1 < 0.70;
                    const highRBias = q && q.r_percent >= 70;
                    const rowClass = lowF1
                      ? 'opacity-40 hover:opacity-70'
                      : 'hover:bg-gray-800/30';

                    return (
                      <tr key={p.id} className={rowClass}>
                        <td className="py-2 px-3 font-medium text-gray-200 capitalize">
                          <div className="flex items-center gap-1.5">
                            {p.antibiotic.replace(/_/g, ' ')}
                            {lowF1 && (
                              <span className="text-red-400" title={`Low model performance (F1=${q!.cv_f1.toFixed(2)}). Prediction unreliable.`}>
                                <AlertTriangle className="w-3.5 h-3.5" />
                              </span>
                            )}
                            {!lowF1 && highRBias && (
                              <span className="text-yellow-400" title={`Training data bias: ${q!.r_percent}% resistant. May over-predict resistance.`}>
                                <AlertTriangle className="w-3.5 h-3.5" />
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-2 px-3 text-gray-400 text-xs">{p.drug_class}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            lowF1
                              ? 'bg-gray-700/30 text-gray-500 border border-gray-600/30'
                              : p.prediction === 'Resistant'
                              ? 'bg-red-600/20 text-red-400 border border-red-500/30'
                              : 'bg-green-600/20 text-green-400 border border-green-500/30'
                          }`}>
                            {p.prediction === 'Resistant' ? 'R' : 'S'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <div className="w-16 bg-gray-800 rounded-full h-1.5">
                              <div
                                className={`h-1.5 rounded-full ${lowF1 ? 'bg-gray-600' : p.prediction === 'Resistant' ? 'bg-red-500' : 'bg-green-500'}`}
                                style={{ width: `${Math.round(p.probability * 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-gray-400 font-mono w-10">
                              {(p.probability * 100).toFixed(0)}%
                            </span>
                          </div>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <span className={`text-xs ${
                            lowF1 ? 'text-gray-600' :
                            p.confidence === 'High' ? 'text-green-400' : p.confidence === 'Moderate' ? 'text-yellow-400' : 'text-gray-500'
                          }`}>
                            {p.confidence}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex flex-wrap gap-1">
                            {p.key_genes.map((g, i) => (
                              <span key={i} className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300 font-mono">{g}</span>
                            ))}
                            {p.key_mutations.map((m, i) => (
                              <span key={`m${i}`} className="px-1.5 py-0.5 bg-orange-900/30 rounded text-xs text-orange-300 font-mono">{m}</span>
                            ))}
                          </div>
                        </td>
                        <td className="py-2 px-3 text-center">
                          {q ? (
                            <div className="group relative inline-flex items-center gap-1">
                              <span className={`text-xs font-mono ${
                                lowF1 ? 'text-red-400' : q.cv_f1 >= 0.90 ? 'text-green-400' : q.cv_f1 >= 0.80 ? 'text-yellow-400' : 'text-gray-400'
                              }`}>
                                {q.cv_f1.toFixed(2)}
                              </span>
                              <Info className="w-3 h-3 text-gray-600" />
                              <div className="absolute bottom-full right-0 mb-1 hidden group-hover:block z-10 w-48 p-2 bg-gray-900 border border-gray-700 rounded-lg shadow-lg text-xs">
                                <div className="text-gray-300 mb-1 font-medium">Model Info</div>
                                <div className="text-gray-400">F1 score: <span className="text-gray-200">{q.cv_f1.toFixed(3)}</span></div>
                                <div className="text-gray-400">Training: <span className="text-gray-200">n={q.n_samples.toLocaleString()}</span></div>
                                <div className="text-gray-400">R% in training: <span className={q.r_percent >= 70 ? 'text-yellow-400' : 'text-gray-200'}>{q.r_percent}%</span></div>
                                {lowF1 && <div className="text-red-400 mt-1">Unreliable — low F1</div>}
                                {!lowF1 && highRBias && <div className="text-yellow-400 mt-1">R-biased training data</div>}
                              </div>
                            </div>
                          ) : (
                            <span className="text-gray-600 text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Hazard Ranking Tool ───

const RANK_DESCRIPTIONS: Record<string, string> = {
  R1: 'Reserve + conjugative plasmid (broad host range)',
  R2: 'Reserve + conjugative plasmid (narrow) or ICE-borne',
  R3: 'Reserve + mobilizable plasmid (with conjugative helper)',
  R4: 'Reserve + mobilizable plasmid (no helper)',
  R5: 'Reserve + chromosomal (non-mobile)',
  R6: 'Watch + conjugative plasmid (broad host range)',
  R7: 'Watch + conjugative plasmid (narrow) or ICE-borne',
  R8: 'Watch + mobilizable plasmid (with conjugative helper)',
  R9: 'Watch + mobilizable plasmid (no helper)',
  R10: 'Watch + chromosomal (non-mobile)',
  R11: 'Access-tier ARG only',
  R12: 'No AMR gene detected',
  NG: 'Not graded (intrinsic/untypeable only)',
};

const RANK_COLORS: Record<string, string> = {
  R1: 'bg-red-900 text-white', R2: 'bg-red-800 text-white', R3: 'bg-red-700 text-white',
  R4: 'bg-red-600 text-white', R5: 'bg-red-500 text-white',
  R6: 'bg-amber-700 text-white', R7: 'bg-amber-600 text-white',
  R8: 'bg-yellow-700 text-white', R9: 'bg-yellow-600 text-white', R10: 'bg-yellow-500 text-gray-900',
  R11: 'bg-green-700 text-white', R12: 'bg-gray-700 text-white', NG: 'bg-gray-600 text-white',
};

interface HazardScore {
  sample_id: string;
  sample_name: string;
  hazard_rank: string | null;
  aware_tier: string | null;
  transmissibility_level: number | null;
  worst_case_arg: string | null;
  worst_case_drug_class: string | null;
  worst_case_location: string | null;
  mdr_flag: boolean | null;
  drug_class_count: number | null;
  vf_category_count: number | null;
}

function HazardRankingTool() {
  const picker = useSamplePicker();
  const [scores, setScores] = useState<HazardScore[]>([]);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSample, setExpandedSample] = useState<string | null>(null);

  async function handleCalculate() {
    if (picker.selectedIds.length === 0) return;
    setCalculating(true);
    setError(null);
    try {
      const res = await authPost('/api/tools/risk', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      setScores(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to calculate risk');
    } finally {
      setCalculating(false);
    }
  }

  function buildExplanation(s: HazardScore): string {
    const rank = s.hazard_rank || 'NG';
    const parts: string[] = [];

    if (rank === 'R12') {
      parts.push('No AMR genes were detected in this isolate.');
      return parts.join(' ');
    }
    if (rank === 'NG') {
      parts.push('AMR genes were detected but none mapped to a WHO AWaRe tier. These may be intrinsic species-core genes that were excluded from ranking.');
      return parts.join(' ');
    }

    // AWaRe tier explanation
    if (s.aware_tier && s.worst_case_arg) {
      parts.push(`The worst-case ARG is ${s.worst_case_arg} (${s.worst_case_drug_class || 'unknown class'}), which maps to the WHO AWaRe "${s.aware_tier}" tier.`);
    }

    // Transmissibility explanation
    if (s.worst_case_location) {
      const loc = s.worst_case_location;
      if (loc.includes('conjugative-broad')) {
        parts.push(`This gene is carried on a conjugative plasmid with broad host range (transmissibility level 5), meaning it can transfer across genera.`);
      } else if (loc.includes('conjugative-narrow')) {
        parts.push(`This gene is on a conjugative plasmid with narrow host range (level 4), transferable within the same genus.`);
      } else if (loc.includes('ICE')) {
        parts.push(`This gene is within an integrative conjugative element (ICE) (level 4), which can excise and transfer chromosomally.`);
      } else if (loc.includes('mobilizable+helper')) {
        parts.push(`This gene is on a mobilizable plasmid with a conjugative helper plasmid present (level 3), enabling indirect transfer.`);
      } else if (loc.includes('mobilizable')) {
        parts.push(`This gene is on a mobilizable plasmid without a helper (level 2), with limited transfer potential.`);
      } else if (loc === 'chromosome') {
        parts.push(`This gene is chromosomal (level 1), with no detected mobile element context.`);
      }
    }

    // MDR
    if (s.mdr_flag) {
      parts.push(`This isolate is MDR (multi-drug resistant), with resistance genes spanning ${s.drug_class_count} distinct antimicrobial classes.`);
    }

    // VF
    if (s.vf_category_count && s.vf_category_count > 0) {
      parts.push(`${s.vf_category_count} virulence factor categor${s.vf_category_count === 1 ? 'y was' : 'ies were'} detected.`);
    }

    return parts.join(' ');
  }

  const highRisk = scores.filter((r) => r.hazard_rank && ['R1', 'R2', 'R3'].includes(r.hazard_rank)).length;
  const mdrCount = scores.filter((r) => r.mdr_flag).length;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Assess isolate-level AMR hazard based on the WHO AWaRe classification and ARG transmissibility context.
        Ranks R1 (highest risk) through R12 (no ARGs detected). Select isolates to score.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={handleCalculate} disabled={picker.selectedIds.length === 0 || calculating} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${calculating ? 'animate-spin' : ''}`} />
        {calculating ? 'Loading...' : `Show Risk (${picker.selectedIds.length})`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {/* Summary cards */}
      {scores.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="card text-center">
            <p className="text-2xl font-bold text-white">{scores.length}</p>
            <p className="text-xs text-gray-400">Total Samples</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-red-400">{highRisk}</p>
            <p className="text-xs text-gray-400">Critical (R1-R3)</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-yellow-400">{mdrCount}</p>
            <p className="text-xs text-gray-400">MDR</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-blue-400">{scores.length > 0 ? ((highRisk / scores.length) * 100).toFixed(0) : '0'}%</p>
            <p className="text-xs text-gray-400">Critical Rate</p>
          </div>
        </div>
      )}

      {/* Results */}
      {scores.length > 0 && (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-400 text-xs uppercase tracking-wider">
                  <th className="px-3 py-2">Sample</th>
                  <th className="px-3 py-2">Rank</th>
                  <th className="px-3 py-2">AWaRe Tier</th>
                  <th className="px-3 py-2">Worst-Case ARG</th>
                  <th className="px-3 py-2">Drug Class</th>
                  <th className="px-3 py-2">Location</th>
                  <th className="px-3 py-2">MDR</th>
                </tr>
              </thead>
              <tbody>
                {scores
                  .sort((a, b) => {
                    const aKey = a.hazard_rank === 'NG' ? 13 : parseInt((a.hazard_rank || 'R99').replace('R', ''), 10);
                    const bKey = b.hazard_rank === 'NG' ? 13 : parseInt((b.hazard_rank || 'R99').replace('R', ''), 10);
                    return aKey - bKey;
                  })
                  .map((s) => {
                    const rank = s.hazard_rank || 'NG';
                    const isExpanded = expandedSample === s.sample_id;
                    return (
                      <tr key={s.sample_id} className="border-b border-gray-800/50 cursor-pointer hover:bg-gray-800/30" onClick={() => setExpandedSample(isExpanded ? null : s.sample_id)}>
                        <td className="px-3 py-2.5 font-medium text-gray-200">{s.sample_name}</td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${RANK_COLORS[rank] || 'bg-gray-700 text-white'}`}>
                            {rank}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={s.aware_tier === 'Reserve' ? 'text-red-400 font-semibold' : s.aware_tier === 'Watch' ? 'text-yellow-400' : s.aware_tier === 'Access' ? 'text-green-400' : 'text-gray-500'}>
                            {s.aware_tier || '-'}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-gray-300 text-xs">{s.worst_case_arg || '-'}</td>
                        <td className="px-3 py-2.5 text-gray-400 text-xs">{s.worst_case_drug_class || '-'}</td>
                        <td className="px-3 py-2.5 text-gray-400 text-xs">{s.worst_case_location || '-'}</td>
                        <td className="px-3 py-2.5">
                          {s.mdr_flag ? <span className="text-orange-400 font-semibold">MDR ({s.drug_class_count})</span> : <span className="text-gray-600">-</span>}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>

          {/* Expanded explanation panel */}
          {expandedSample && (() => {
            const s = scores.find((sc) => sc.sample_id === expandedSample);
            if (!s) return null;
            const rank = s.hazard_rank || 'NG';
            return (
              <div className="mt-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded text-sm font-bold ${RANK_COLORS[rank] || 'bg-gray-700 text-white'}`}>{rank}</span>
                  <span className="text-gray-200 font-medium">{s.sample_name}</span>
                  <span className="text-gray-500 text-xs">{RANK_DESCRIPTIONS[rank]}</span>
                </div>
                <p className="text-sm text-gray-300 leading-relaxed">{buildExplanation(s)}</p>
              </div>
            );
          })()}

          {/* Legend */}
          <div className="mt-4 pt-4 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-2 font-semibold">Rank Legend (click a row for explanation)</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5 text-xs text-gray-500">
              {Object.entries(RANK_DESCRIPTIONS).map(([rank, desc]) => (
                <div key={rank} className="flex items-center gap-2">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${RANK_COLORS[rank] || 'bg-gray-700 text-white'}`}>{rank}</span>
                  <span>{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {scores.length === 0 && picker.selectedIds.length > 0 && !calculating && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Show Risk&quot; to view hazard ranks for selected isolates.</div>
      )}
    </div>
  );
}

// ─── Genome Comparison Tool ───

interface ANIData {
  samples: string[];
  sample_ids: string[];
  ani_matrix: number[][];
  af_matrix: number[][];
  message?: string;
}

interface ClusterSample { name: string; sample_id: string; species: string | null; st: string | null }
interface ClusterData {
  id: number;
  samples: ClusterSample[];
  size: number;
  method: string;
  max_distance: number;
  min_distance: number;
  mean_distance: number;
  shared_args: string[];
  shared_drug_classes: string[];
  shared_replicons: string[];
  date_range: { earliest: string; latest: string } | null;
  locations: string[];
}
interface ClusterResult {
  clusters: ClusterData[];
  total_samples: number;
  clustered_samples: number;
  threshold_used: number;
  species: string | null;
}

function GenomeComparisonTool() {
  const picker = useSamplePicker();
  const [subTab, setSubTab] = useState<'ani' | 'clusters'>('ani');
  const [aniData, setAniData] = useState<ANIData | null>(null);
  const [clusterData, setClusterData] = useState<ClusterResult | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCell, setHoveredCell] = useState<{ i: number; j: number } | null>(null);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2) return;
    setComputing(true);
    setError(null);
    setAniData(null);
    setClusterData(null);
    try {
      const body = { sample_ids: picker.selectedIds };
      const [aniRes, clusterRes] = await Promise.all([
        authPost('/api/tools/ani', body),
        authPost('/api/tools/clusters', body),
      ]);
      if (!aniRes.ok) throw new Error(await aniRes.text());
      if (!clusterRes.ok) throw new Error(await clusterRes.text());
      const ani: ANIData = await aniRes.json();
      const clusters: ClusterResult = await clusterRes.json();
      if (ani.message) setError(ani.message);
      setAniData(ani);
      setClusterData(clusters);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setComputing(false);
    }
  }

  function aniColor(val: number): string {
    if (val >= 99.95) return 'bg-green-600/80 text-white';
    if (val >= 99.0) return 'bg-green-600/40 text-green-200';
    if (val >= 97.0) return 'bg-yellow-600/40 text-yellow-200';
    if (val >= 95.0) return 'bg-orange-600/40 text-orange-200';
    return 'bg-red-600/40 text-red-200';
  }

  function downloadANI() {
    if (!aniData) return;
    const { samples, ani_matrix } = aniData;
    const headers = ['', ...samples];
    const rows = samples.map((s, i) => [s, ...ani_matrix[i].map((v) => v.toFixed(2))]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'ani_matrix.tsv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function downloadClusters() {
    if (!clusterData) return;
    const headers = ['Cluster', 'Size', 'Method', 'Samples', 'Species', 'STs', 'Mean Distance', 'Shared ARGs', 'Shared Drug Classes', 'Shared Replicons', 'Date Range', 'Locations'];
    const rows = clusterData.clusters.map((c) => [
      c.id, c.size, c.method,
      c.samples.map((s) => s.name).join('; '),
      c.samples.map((s) => s.species || '').filter(Boolean).join('; '),
      c.samples.map((s) => s.st ? `ST${s.st}` : '').filter(Boolean).join('; '),
      c.mean_distance,
      c.shared_args.join('; '),
      c.shared_drug_classes.join('; '),
      c.shared_replicons.join('; '),
      c.date_range ? `${c.date_range.earliest} to ${c.date_range.latest}` : '',
      c.locations.join('; '),
    ]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'outbreak_clusters.tsv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const hasResults = aniData || clusterData;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Compare genomes: ANI pairwise identity and outbreak cluster detection using cgMLST distances + ANI thresholds. Select 2 or more isolates.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={runAnalysis} disabled={picker.selectedIds.length < 2 || computing} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${computing ? 'animate-spin' : ''}`} />
        {computing ? 'Analyzing...' : `Analyze (${picker.selectedIds.length} selected)`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {/* Sub-tabs */}
      {hasResults && (
        <div className="flex gap-1">
          <button onClick={() => setSubTab('ani')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${subTab === 'ani' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            ANI Matrix
          </button>
          <button onClick={() => setSubTab('clusters')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${subTab === 'clusters' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            Outbreak Clusters {clusterData && clusterData.clusters.length > 0 && <span className="ml-1 px-1.5 py-0.5 rounded-full bg-red-600 text-white text-[10px]">{clusterData.clusters.length}</span>}
          </button>
        </div>
      )}

      {/* ── ANI Matrix view ── */}
      {subTab === 'ani' && aniData && aniData.ani_matrix.length > 1 && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-100">ANI Pairwise Matrix ({aniData.samples.length} samples)</h2>
            <button onClick={downloadANI} className="btn-secondary text-xs flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" />
              Download TSV
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3 mb-4 text-xs text-gray-400">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-600/80" /> &ge;99.95% (likely clonal)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-600/40" /> 99.0-99.95%</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-yellow-600/40" /> 97.0-99.0%</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-orange-600/40" /> 95.0-97.0%</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-600/40" /> &lt;95% (different species)</span>
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1.5 text-left text-gray-400 font-medium sticky left-0 bg-gray-900 z-10" />
                  {aniData.samples.map((s, j) => (
                    <th key={j} className="px-2 py-1.5 text-gray-400 font-medium whitespace-nowrap" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxWidth: '2rem' }}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {aniData.samples.map((rowName, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 text-gray-300 font-medium whitespace-nowrap sticky left-0 bg-gray-900 z-10">{rowName}</td>
                    {aniData.ani_matrix[i].map((val, j) => {
                      const isHovered = hoveredCell?.i === i && hoveredCell?.j === j;
                      const isDiag = i === j;
                      return (
                        <td key={j}
                          className={`px-2 py-1 text-center font-mono cursor-default transition-all ${isDiag ? 'bg-gray-800/50 text-gray-600' : aniColor(val)} ${isHovered ? 'ring-2 ring-blue-400' : ''}`}
                          onMouseEnter={() => setHoveredCell({ i, j })}
                          onMouseLeave={() => setHoveredCell(null)}
                          title={isDiag ? '' : `${rowName} vs ${aniData.samples[j]}\nANI: ${val.toFixed(2)}%\nAlign fraction: ${(aniData.af_matrix[i][j] * 100).toFixed(1)}%`}
                        >{isDiag ? '-' : val.toFixed(1)}</td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hoveredCell && hoveredCell.i !== hoveredCell.j && (
            <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
              <span className="text-gray-200 font-medium">{aniData.samples[hoveredCell.i]}</span>
              <span className="text-gray-500"> vs </span>
              <span className="text-gray-200 font-medium">{aniData.samples[hoveredCell.j]}</span>
              <span className="text-gray-400 ml-3">ANI: <span className="text-white font-mono">{aniData.ani_matrix[hoveredCell.i][hoveredCell.j].toFixed(4)}%</span></span>
              <span className="text-gray-400 ml-3">Align fraction: <span className="text-white font-mono">{(aniData.af_matrix[hoveredCell.i][hoveredCell.j] * 100).toFixed(1)}%</span></span>
              {aniData.ani_matrix[hoveredCell.i][hoveredCell.j] >= 99.95 && (
                <span className="ml-3 px-2 py-0.5 bg-green-600/30 text-green-300 rounded text-xs">Likely clonal</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Outbreak Clusters view ── */}
      {subTab === 'clusters' && clusterData && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="card text-center">
              <p className="text-2xl font-bold text-white">{clusterData.total_samples}</p>
              <p className="text-xs text-gray-400">Total Samples</p>
            </div>
            <div className="card text-center">
              <p className="text-2xl font-bold text-red-400">{clusterData.clusters.length}</p>
              <p className="text-xs text-gray-400">Clusters Detected</p>
            </div>
            <div className="card text-center">
              <p className="text-2xl font-bold text-orange-400">{clusterData.clustered_samples}</p>
              <p className="text-xs text-gray-400">Samples in Clusters</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400 mb-1">Threshold</p>
              <p className="text-sm text-gray-200">&le;{clusterData.threshold_used} allelic diffs</p>
              <p className="text-xs text-gray-500">{clusterData.species || 'unknown'}</p>
            </div>
          </div>

          {clusterData.clusters.length === 0 ? (
            <div className="card text-center py-8 text-gray-500">
              No outbreak clusters detected. All samples are genetically distinct based on the threshold (&le;{clusterData.threshold_used} cgMLST allelic differences or ANI &ge;99.98%).
            </div>
          ) : (
            <>
              <div className="flex justify-end">
                <button onClick={downloadClusters} className="btn-secondary text-xs flex items-center gap-1.5">
                  <Download className="w-3.5 h-3.5" />
                  Download Report
                </button>
              </div>

              {clusterData.clusters.map((cluster) => (
                <div key={cluster.id} className="card border-l-4 border-l-red-500">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-100">
                        Cluster {cluster.id}
                        <span className="ml-2 text-xs font-normal text-gray-400">({cluster.size} samples, {cluster.method})</span>
                      </h3>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Distance: {cluster.min_distance === cluster.max_distance ? cluster.min_distance : `${cluster.min_distance}-${cluster.max_distance}`} allelic diffs (mean {cluster.mean_distance})
                      </p>
                    </div>
                    {cluster.date_range && (
                      <div className="text-right text-xs text-gray-400">
                        <p>{cluster.date_range.earliest} — {cluster.date_range.latest}</p>
                        {cluster.locations.length > 0 && <p className="text-gray-500">{cluster.locations.join(', ')}</p>}
                      </div>
                    )}
                  </div>

                  {/* Member samples */}
                  <div className="mb-3">
                    <p className="text-xs text-gray-400 mb-1.5">Samples:</p>
                    <div className="flex flex-wrap gap-2">
                      {cluster.samples.map((s) => (
                        <div key={s.sample_id} className="px-2.5 py-1 bg-gray-800 rounded text-xs">
                          <span className="text-gray-200 font-medium">{s.name}</span>
                          {s.st && <span className="text-gray-500 ml-1">ST{s.st}</span>}
                          {s.species && <span className="text-gray-600 ml-1 italic">{s.species}</span>}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Shared resistance */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    {cluster.shared_args.length > 0 && (
                      <div>
                        <p className="text-gray-400 mb-1">Shared ARGs ({cluster.shared_args.length}):</p>
                        <div className="flex flex-wrap gap-1">
                          {cluster.shared_args.slice(0, 10).map((g) => (
                            <span key={g} className="px-1.5 py-0.5 bg-red-900/30 rounded text-red-300 font-mono">{g}</span>
                          ))}
                          {cluster.shared_args.length > 10 && <span className="text-gray-500">+{cluster.shared_args.length - 10} more</span>}
                        </div>
                      </div>
                    )}
                    {cluster.shared_drug_classes.length > 0 && (
                      <div>
                        <p className="text-gray-400 mb-1">Shared drug classes:</p>
                        <div className="flex flex-wrap gap-1">
                          {cluster.shared_drug_classes.map((c) => (
                            <span key={c} className="px-1.5 py-0.5 bg-orange-900/30 rounded text-orange-300">{c}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {cluster.shared_replicons.length > 0 && (
                      <div>
                        <p className="text-gray-400 mb-1">Shared plasmid replicons:</p>
                        <div className="flex flex-wrap gap-1">
                          {cluster.shared_replicons.map((r) => (
                            <span key={r} className="px-1.5 py-0.5 bg-blue-900/30 rounded text-blue-300">{r}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {cluster.shared_args.length === 0 && cluster.shared_drug_classes.length === 0 && cluster.shared_replicons.length === 0 && (
                    <p className="text-xs text-gray-600 mt-1">No shared resistance genes, drug classes, or plasmid replicons detected.</p>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {!hasResults && picker.selectedIds.length >= 2 && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Analyze&quot; to compute ANI matrix and detect outbreak clusters.</div>
      )}
    </div>
  );
}

// ─── SynTracker Tool ───

interface SyntenyData {
  samples: string[];
  sample_ids: string[];
  synteny_matrix: number[][];
  shared_genes_matrix: number[][];
  message?: string;
}

function SynTrackerTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<SyntenyData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCell, setHoveredCell] = useState<{ i: number; j: number } | null>(null);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2) return;
    setComputing(true);
    setError(null);
    setData(null);
    try {
      const res = await authPost('/api/tools/syntracker', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      const d: SyntenyData = await res.json();
      if (d.message) setError(d.message);
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setComputing(false);
    }
  }

  function syntenyColor(val: number): string {
    if (val >= 0.95) return 'bg-green-600/80 text-white';
    if (val >= 0.85) return 'bg-green-600/40 text-green-200';
    if (val >= 0.7) return 'bg-yellow-600/40 text-yellow-200';
    if (val >= 0.5) return 'bg-orange-600/40 text-orange-200';
    return 'bg-red-600/40 text-red-200';
  }

  function downloadSynteny() {
    if (!data) return;
    const { samples, synteny_matrix, shared_genes_matrix } = data;
    const headers = ['', ...samples];
    const rows = samples.map((s, i) => [s, ...synteny_matrix[i].map((v) => v.toFixed(4))]);
    const sharedRows = samples.map((s, i) => [s, ...shared_genes_matrix[i].map(String)]);
    const tsv = '# Synteny scores\n' + [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n')
      + '\n\n# Shared genes\n' + [headers.join('\t'), ...sharedRows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'synteny_matrix.tsv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const hasMatrix = data && data.synteny_matrix.length > 1;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Synteny conservation analysis using Prodigal protein hashing. Measures gene-order preservation between genomes.
        High synteny + high ANI = clonal; high ANI + low synteny = recombination or rearrangement.
        Select 2+ isolates for all-vs-all comparison. Typically completes in seconds.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={runAnalysis} disabled={picker.selectedIds.length < 2 || computing} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${computing ? 'animate-spin' : ''}`} />
        {computing ? 'Computing...' : `Compute Synteny (${picker.selectedIds.length} selected)`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {hasMatrix && data && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-100">Synteny Conservation Matrix ({data.samples.length} samples)</h2>
            <button onClick={downloadSynteny} className="btn-secondary text-xs flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" />
              Download TSV
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3 mb-4 text-xs text-gray-400">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-600/80" /> &ge;0.95 (high conservation)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-600/40" /> 0.85-0.95</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-yellow-600/40" /> 0.7-0.85</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-orange-600/40" /> 0.5-0.7</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-600/40" /> &lt;0.5 (major rearrangement)</span>
          </div>

          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1.5 text-left text-gray-400 font-medium sticky left-0 bg-gray-900 z-10" />
                  {data.samples.map((s, j) => (
                    <th key={j} className="px-2 py-1.5 text-gray-400 font-medium whitespace-nowrap" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxWidth: '2rem' }}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.samples.map((rowName, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 text-gray-300 font-medium whitespace-nowrap sticky left-0 bg-gray-900 z-10">{rowName}</td>
                    {data.synteny_matrix[i].map((val, j) => {
                      const isHovered = hoveredCell?.i === i && hoveredCell?.j === j;
                      const isDiag = i === j;
                      return (
                        <td key={j}
                          className={`px-2 py-1 text-center font-mono cursor-default transition-all ${isDiag ? 'bg-gray-800/50 text-gray-600' : syntenyColor(val)} ${isHovered ? 'ring-2 ring-blue-400' : ''}`}
                          onMouseEnter={() => setHoveredCell({ i, j })}
                          onMouseLeave={() => setHoveredCell(null)}
                          title={isDiag ? '' : `${rowName} vs ${data.samples[j]}\nSynteny: ${val.toFixed(4)}\nShared genes: ${data.shared_genes_matrix[i][j]}`}
                        >{isDiag ? '-' : val.toFixed(3)}</td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {hoveredCell && hoveredCell.i !== hoveredCell.j && (
            <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
              <span className="text-gray-200 font-medium">{data.samples[hoveredCell.i]}</span>
              <span className="text-gray-500"> vs </span>
              <span className="text-gray-200 font-medium">{data.samples[hoveredCell.j]}</span>
              <span className="text-gray-400 ml-3">Synteny: <span className="text-white font-mono">{data.synteny_matrix[hoveredCell.i][hoveredCell.j].toFixed(4)}</span></span>
              <span className="text-gray-400 ml-3">Shared genes: <span className="text-white font-mono">{data.shared_genes_matrix[hoveredCell.i][hoveredCell.j]}</span></span>
              {data.synteny_matrix[hoveredCell.i][hoveredCell.j] >= 0.95 && (
                <span className="ml-3 px-2 py-0.5 bg-green-600/30 text-green-300 rounded text-xs">High conservation</span>
              )}
            </div>
          )}
        </div>
      )}

      {picker.selectedIds.length >= 2 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Compute Synteny&quot; to analyze gene-order conservation.</div>
      )}
    </div>
  );
}

// ─── EasyFig Tool ───

interface EasyFigContig { name: string; length: number }
interface EasyFigGenome { sample_name: string; sample_id: string; contigs: EasyFigContig[]; total_length: number }
interface EasyFigBlock { query_contig: string; subject_contig: string; identity: number; length: number; query_start: number; query_end: number; subject_start: number; subject_end: number; inverted: boolean }
interface EasyFigAlignment { query_idx: number; subject_idx: number; blocks: EasyFigBlock[] }
interface EasyFigData { genomes: EasyFigGenome[]; alignments: EasyFigAlignment[]; message?: string }

function blockColor(identity: number, inverted: boolean): string {
  if (inverted) {
    if (identity >= 99) return 'rgba(239,68,68,0.5)';
    if (identity >= 95) return 'rgba(239,68,68,0.35)';
    if (identity >= 90) return 'rgba(239,68,68,0.2)';
    return 'rgba(239,68,68,0.1)';
  }
  if (identity >= 99) return 'rgba(59,130,246,0.5)';
  if (identity >= 95) return 'rgba(59,130,246,0.35)';
  if (identity >= 90) return 'rgba(59,130,246,0.2)';
  return 'rgba(59,130,246,0.1)';
}

function EasyFigTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<EasyFigData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredBlock, setHoveredBlock] = useState<EasyFigBlock | null>(null);
  const [minLength, setMinLength] = useState(1000);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2 || picker.selectedIds.length > 4) return;
    setComputing(true);
    setError(null);
    setData(null);
    try {
      const res = await authPost('/api/tools/easyfig', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      const d: EasyFigData = await res.json();
      if (d.message) setError(d.message);
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setComputing(false);
    }
  }

  const svgWidth = 900;
  const genomeHeight = 20;
  const gapHeight = 80;
  const marginLeft = 100;
  const marginRight = 20;
  const drawWidth = svgWidth - marginLeft - marginRight;

  function renderDiagram() {
    if (!data || data.genomes.length < 2) return null;

    const maxLen = Math.max(...data.genomes.map((g) => g.total_length));
    const scale = (pos: number) => (pos / maxLen) * drawWidth;

    const totalHeight = data.genomes.length * genomeHeight + (data.genomes.length - 1) * gapHeight + 60;

    return (
      <svg width={svgWidth} height={totalHeight} className="bg-gray-900 rounded-lg">
        {data.genomes.map((genome, gIdx) => {
          const y = 30 + gIdx * (genomeHeight + gapHeight);
          let offset = 0;
          return (
            <g key={gIdx}>
              {/* Label */}
              <text x={5} y={y + genomeHeight / 2 + 4} className="fill-gray-300 text-xs" fontSize="11">{genome.sample_name}</text>
              {/* Genome bar (contigs) */}
              {genome.contigs.map((contig, cIdx) => {
                const x = marginLeft + scale(offset);
                const w = Math.max(1, scale(contig.length));
                offset += contig.length;
                return (
                  <rect key={cIdx} x={x} y={y} width={w} height={genomeHeight} fill="#374151" stroke="#4B5563" strokeWidth={0.5} rx={2}>
                    <title>{contig.name}: {(contig.length / 1000).toFixed(0)} kb</title>
                  </rect>
                );
              })}
              {/* Length label */}
              <text x={marginLeft + scale(genome.total_length) + 5} y={y + genomeHeight / 2 + 4} className="fill-gray-500 text-xs" fontSize="9">
                {(genome.total_length / 1e6).toFixed(2)} Mb
              </text>
            </g>
          );
        })}

        {/* Alignment ribbons */}
        {data.alignments.map((aln, aIdx) => {
          const y1 = 30 + aln.query_idx * (genomeHeight + gapHeight) + genomeHeight;
          const y2 = 30 + aln.subject_idx * (genomeHeight + gapHeight);

          // Build contig offset maps
          const queryOffsets: Record<string, number> = {};
          let off = 0;
          for (const c of data.genomes[aln.query_idx].contigs) { queryOffsets[c.name] = off; off += c.length; }
          const subjectOffsets: Record<string, number> = {};
          off = 0;
          for (const c of data.genomes[aln.subject_idx].contigs) { subjectOffsets[c.name] = off; off += c.length; }

          return aln.blocks
            .filter((b) => b.length >= minLength)
            .map((block, bIdx) => {
              const qOff = queryOffsets[block.query_contig] ?? 0;
              const sOff = subjectOffsets[block.subject_contig] ?? 0;
              const qx1 = marginLeft + scale(qOff + block.query_start);
              const qx2 = marginLeft + scale(qOff + block.query_end);
              const sx1 = marginLeft + scale(sOff + block.subject_start);
              const sx2 = marginLeft + scale(sOff + block.subject_end);
              const color = blockColor(block.identity, block.inverted);
              const isHovered = hoveredBlock === block;

              return (
                <polygon
                  key={`${aIdx}-${bIdx}`}
                  points={`${qx1},${y1} ${qx2},${y1} ${sx2},${y2} ${sx1},${y2}`}
                  fill={color}
                  stroke={isHovered ? '#60A5FA' : 'none'}
                  strokeWidth={isHovered ? 1.5 : 0}
                  opacity={isHovered ? 1 : 0.8}
                  onMouseEnter={() => setHoveredBlock(block)}
                  onMouseLeave={() => setHoveredBlock(null)}
                  style={{ cursor: 'pointer' }}
                >
                  <title>{`${block.identity}% identity, ${(block.length / 1000).toFixed(1)} kb${block.inverted ? ' (inverted)' : ''}`}</title>
                </polygon>
              );
            });
        })}
      </svg>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        EasyFig-style synteny visualization. BLASTn alignments between genomes shown as colored ribbons.
        Blue = forward alignment, red = inverted. Darker = higher identity.
        Select 2-4 isolates.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={runAnalysis} disabled={picker.selectedIds.length < 2 || picker.selectedIds.length > 4 || computing} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${computing ? 'animate-spin' : ''}`} />
        {computing ? 'Computing...' : `Run EasyFig (${picker.selectedIds.length} selected, max 4)`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {data && data.genomes.length >= 2 && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-100">Synteny Diagram</h2>
            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-400">Min block: </label>
              <select value={minLength} onChange={(e) => setMinLength(Number(e.target.value))} className="input text-xs py-1 px-2">
                <option value={500}>500 bp</option>
                <option value={1000}>1 kb</option>
                <option value={5000}>5 kb</option>
                <option value={10000}>10 kb</option>
                <option value={50000}>50 kb</option>
              </select>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-4 mb-4 text-xs text-gray-400">
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(59,130,246,0.5)' }} /> Forward (&ge;99%)</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(59,130,246,0.25)' }} /> Forward (90-99%)</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(239,68,68,0.5)' }} /> Inverted (&ge;99%)</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(239,68,68,0.25)' }} /> Inverted (90-99%)</span>
          </div>

          <div className="overflow-x-auto">
            {renderDiagram()}
          </div>

          {hoveredBlock && (
            <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
              <span className="text-gray-400">Identity: </span>
              <span className="text-white font-mono">{hoveredBlock.identity}%</span>
              <span className="text-gray-400 ml-3">Length: </span>
              <span className="text-white font-mono">{(hoveredBlock.length / 1000).toFixed(1)} kb</span>
              <span className="text-gray-400 ml-3">Query: </span>
              <span className="text-gray-300">{hoveredBlock.query_contig}:{hoveredBlock.query_start}-{hoveredBlock.query_end}</span>
              <span className="text-gray-400 ml-3">Subject: </span>
              <span className="text-gray-300">{hoveredBlock.subject_contig}:{hoveredBlock.subject_start}-{hoveredBlock.subject_end}</span>
              {hoveredBlock.inverted && <span className="ml-3 px-2 py-0.5 bg-red-600/30 text-red-300 rounded text-xs">Inverted</span>}
            </div>
          )}

          {/* Stats */}
          <div className="mt-4 pt-3 border-t border-gray-800 text-xs text-gray-500">
            {data.alignments.map((aln, i) => {
              const filtered = aln.blocks.filter((b) => b.length >= minLength);
              const totalAligned = filtered.reduce((sum, b) => sum + b.length, 0);
              const inverted = filtered.filter((b) => b.inverted).length;
              return (
                <p key={i}>
                  {data.genomes[aln.query_idx].sample_name} vs {data.genomes[aln.subject_idx].sample_name}: {filtered.length} blocks, {(totalAligned / 1e6).toFixed(2)} Mb aligned, {inverted} inverted
                </p>
              );
            })}
          </div>
        </div>
      )}

      {picker.selectedIds.length >= 2 && picker.selectedIds.length <= 4 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Run EasyFig&quot; to generate synteny diagram.</div>
      )}
      {picker.selectedIds.length > 4 && (
        <div className="p-4 bg-yellow-600/20 border border-yellow-600/50 rounded-lg text-yellow-300 text-sm">Maximum 4 isolates for EasyFig visualization. Please deselect some.</div>
      )}
    </div>
  );
}

// ─── Resistome Tracker Tool ───

interface ResistomeCellData { present: number; genes: string[] }
interface GeoSample {
  sample_name: string;
  sample_id: string;
  latitude: number;
  longitude: number;
  location: string;
  source: string;
  collection_date: string | null;
  drug_class_count: number;
  drug_classes: string[];
  hazard_rank: string | null;
  mdr_flag: boolean;
}
interface LocationStat {
  location: string;
  sample_count: number;
  mdr_count: number;
  top_drug_classes: [string, number][];
}
interface ResistomeData {
  matrix: {
    sample_names: string[];
    drug_classes: string[];
    data: ResistomeCellData[][];
  };
  temporal: {
    time_points: string[];
    drug_classes: string[];
    series: Record<string, number[]>;
  };
  distance_matrix: number[][];
  geo?: GeoSample[];
  locations?: LocationStat[];
}

function ResistomeTrackerTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<ResistomeData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subTab, setSubTab] = useState<'matrix' | 'temporal' | 'distance'>('matrix');
  const [hoveredCell, setHoveredCell] = useState<{ i: number; j: number } | null>(null);

  async function runAnalysis() {
    if (picker.selectedIds.length === 0) return;
    setComputing(true);
    setError(null);
    setData(null);
    try {
      const res = await authPost('/api/tools/resistome', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      setData(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setComputing(false);
    }
  }

  function downloadMatrix() {
    if (!data?.matrix) return;
    const { sample_names, drug_classes, data: mdata } = data.matrix;
    const headers = ['Sample', ...drug_classes];
    const rows = sample_names.map((name, i) => [name, ...mdata[i].map((c) => c.present ? c.genes.join('; ') || '1' : '0')]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'resistome_matrix.tsv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const hasData = data && data.matrix.sample_names.length > 0;
  const hasTemporal = data && (data.temporal.time_points.length > 0 || (data.geo && data.geo.length > 0));

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Track resistance gene profiles across isolates. Shows drug class presence/absence matrix,
        temporal resistance trends (if collection dates available), and resistome similarity distances.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={runAnalysis} disabled={picker.selectedIds.length === 0 || computing} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${computing ? 'animate-spin' : ''}`} />
        {computing ? 'Loading...' : `Show Resistome (${picker.selectedIds.length})`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {/* Sub-tabs */}
      {hasData && (
        <div className="flex gap-1">
          <button onClick={() => setSubTab('matrix')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${subTab === 'matrix' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            Resistance Matrix
          </button>
          {hasTemporal && (
            <button onClick={() => setSubTab('temporal')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${subTab === 'temporal' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              Temporal Trends
            </button>
          )}
          {data!.matrix.sample_names.length >= 2 && (
            <button onClick={() => setSubTab('distance')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${subTab === 'distance' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              Similarity
            </button>
          )}
        </div>
      )}

      {/* ── Resistance Matrix ── */}
      {subTab === 'matrix' && hasData && data && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-100">
              Drug Class Resistance ({data.matrix.sample_names.length} samples × {data.matrix.drug_classes.length} classes)
            </h2>
            <button onClick={downloadMatrix} className="btn-secondary text-xs flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" />
              Download TSV
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1.5 text-left text-gray-400 font-medium sticky left-0 bg-gray-900 z-10" />
                  {data.matrix.drug_classes.map((dc, j) => (
                    <th key={j} className="px-1 py-1.5 text-gray-400 font-medium whitespace-nowrap" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxWidth: '1.5rem' }}>
                      {dc}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.matrix.sample_names.map((name, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 text-gray-300 font-medium whitespace-nowrap sticky left-0 bg-gray-900 z-10">{name}</td>
                    {data.matrix.data[i].map((cell, j) => (
                      <td
                        key={j}
                        className={`px-1 py-1 text-center cursor-default ${cell.present ? 'bg-red-600/40' : 'bg-gray-800/30'}`}
                        onMouseEnter={() => setHoveredCell({ i, j })}
                        onMouseLeave={() => setHoveredCell(null)}
                        title={cell.present ? `${name}: ${data.matrix.drug_classes[j]}\nGenes: ${cell.genes.join(', ')}` : ''}
                      >
                        {cell.present ? <span className="text-red-300 font-bold">+</span> : <span className="text-gray-700">·</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hoveredCell && data.matrix.data[hoveredCell.i][hoveredCell.j].present > 0 && (
            <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
              <span className="text-gray-200 font-medium">{data.matrix.sample_names[hoveredCell.i]}</span>
              <span className="text-gray-500"> — </span>
              <span className="text-orange-400">{data.matrix.drug_classes[hoveredCell.j]}</span>
              <span className="text-gray-400 ml-3">Genes: </span>
              <span className="text-gray-200 font-mono">{data.matrix.data[hoveredCell.i][hoveredCell.j].genes.join(', ')}</span>
            </div>
          )}
          {/* Summary row */}
          <div className="mt-3 pt-3 border-t border-gray-800 text-xs text-gray-500">
            {data.matrix.sample_names.map((name, i) => {
              const count = data.matrix.data[i].filter((c) => c.present).length;
              return <span key={i} className="mr-4">{name}: <span className="text-gray-300">{count}/{data.matrix.drug_classes.length}</span> classes</span>;
            })}
          </div>
        </div>
      )}

      {/* ── Temporal Trends (with geographic map) ── */}
      {subTab === 'temporal' && hasTemporal && data && (
        <div className="space-y-4">
          {/* Geographic view with time filter */}
          {data.geo && data.geo.length > 0 && (
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-100 mb-4">Geographic AMR Distribution Over Time</h2>
              <TemporalGeoMap geo={data.geo} locations={data.locations || []} />
            </div>
          )}

          {/* Prevalence table */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-4">Resistance Prevalence Over Time</h2>
            <div className="overflow-x-auto">
              <table className="text-xs w-full">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="px-2 py-1.5 text-left text-gray-400 font-medium sticky left-0 bg-gray-900">Drug Class</th>
                    {data.temporal.time_points.map((tp) => (
                      <th key={tp} className="px-2 py-1.5 text-gray-400 font-medium text-center">{tp}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.temporal.drug_classes.map((dc) => {
                    const values = data.temporal.series[dc] || [];
                    const hasChange = values.length > 1 && values[0] !== values[values.length - 1];
                    return (
                      <tr key={dc} className="border-b border-gray-800/30">
                        <td className="px-2 py-1 text-gray-300 font-medium whitespace-nowrap sticky left-0 bg-gray-900">
                          {dc}
                          {hasChange && (
                            <span className={`ml-1 text-[10px] ${values[values.length - 1] > values[0] ? 'text-red-400' : 'text-green-400'}`}>
                              {values[values.length - 1] > values[0] ? '↑' : '↓'}
                            </span>
                          )}
                        </td>
                        {values.map((v, idx) => (
                          <td key={idx} className="px-2 py-1 text-center">
                            <span className={`font-mono ${v >= 0.5 ? 'text-red-400' : v > 0 ? 'text-yellow-400' : 'text-gray-600'}`}>
                              {(v * 100).toFixed(0)}%
                            </span>
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-gray-600">Prevalence = fraction of samples at each time point carrying resistance. ↑ increasing ↓ decreasing trend.</p>
          </div>
        </div>
      )}

      {/* ── Similarity (Jaccard distance) ── */}
      {subTab === 'distance' && hasData && data && data.distance_matrix.length >= 2 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-100 mb-4">Resistome Similarity (Jaccard Distance)</h2>
          <div className="flex flex-wrap items-center gap-3 mb-4 text-xs text-gray-400">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-600/80" /> 0.0 (identical)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-yellow-600/40" /> 0.3-0.5</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-600/40" /> &ge;0.7 (very different)</span>
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1.5 text-left text-gray-400 font-medium sticky left-0 bg-gray-900 z-10" />
                  {data.matrix.sample_names.map((s, j) => (
                    <th key={j} className="px-2 py-1.5 text-gray-400 font-medium whitespace-nowrap" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxWidth: '2rem' }}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.matrix.sample_names.map((name, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 text-gray-300 font-medium whitespace-nowrap sticky left-0 bg-gray-900 z-10">{name}</td>
                    {data.distance_matrix[i].map((val, j) => {
                      const isDiag = i === j;
                      const color = isDiag ? 'bg-gray-800/50 text-gray-600'
                        : val <= 0.1 ? 'bg-green-600/80 text-white'
                        : val <= 0.3 ? 'bg-green-600/40 text-green-200'
                        : val <= 0.5 ? 'bg-yellow-600/40 text-yellow-200'
                        : val <= 0.7 ? 'bg-orange-600/40 text-orange-200'
                        : 'bg-red-600/40 text-red-200';
                      return (
                        <td key={j} className={`px-2 py-1 text-center font-mono ${color}`}
                          title={isDiag ? '' : `${name} vs ${data.matrix.sample_names[j]}: Jaccard distance ${val.toFixed(4)}`}
                        >{isDiag ? '-' : val.toFixed(2)}</td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-gray-600">Jaccard distance: 0 = identical drug class profiles, 1 = completely different.</p>
        </div>
      )}

      {picker.selectedIds.length > 0 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Show Resistome&quot; to view resistance profiles.</div>
      )}
    </div>
  );
}

// ─── SRA Submission Preparation Tool ───
interface SRASample {
  sample_id: string;
  sample_name: string;
  organism: string;
  collection_date: string;
  geo_loc_name: string;
  isolation_source: string;
  library_strategy: string;
  library_source: string;
  library_selection: string;
  library_layout: string;
  platform: string;
  instrument_model: string;
  filetype: string;
  filenames: string[];
  filename1: string;
  filename2: string;
}

const INSTRUMENT_OPTIONS: Record<string, string[]> = {
  ILLUMINA: ['Illumina MiSeq', 'Illumina HiSeq 2500', 'Illumina HiSeq 4000', 'Illumina NovaSeq 6000', 'NextSeq 500', 'NextSeq 2000', 'Illumina iSeq 100'],
  OXFORD_NANOPORE: ['MinION', 'GridION', 'PromethION', 'Flongle'],
  PACBIO_SMRT: ['PacBio RS II', 'Sequel', 'Sequel II', 'Sequel IIe', 'Revio'],
};

function SRASubmissionTool() {
  const [samples, setSamples] = useState<SRASample[]>([]);
  const [loading, setLoading] = useState(true);
  const [bioproject, setBioproject] = useState('');
  const [edited, setEdited] = useState<Record<string, Partial<SRASample>>>({});

  useEffect(() => {
    authFetch('/api/sra-submission')
      .then((r) => r.json())
      .then((d) => { setSamples(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const getVal = (s: SRASample, field: keyof SRASample): string => {
    const override = edited[s.sample_id]?.[field];
    if (override !== undefined) return String(override);
    return String(s[field] || '');
  };

  const setVal = (sampleId: string, field: keyof SRASample, value: string) => {
    setEdited((prev) => ({
      ...prev,
      [sampleId]: { ...prev[sampleId], [field]: value },
    }));
  };

  const downloadBioSampleTSV = () => {
    const headers = ['sample_name', 'organism', 'collection_date', 'geo_loc_name', 'isolation_source', 'sample_type'];
    const rows = samples.map((s) => [
      getVal(s, 'sample_name'),
      getVal(s, 'organism'),
      getVal(s, 'collection_date') || 'missing',
      getVal(s, 'geo_loc_name') || 'missing',
      getVal(s, 'isolation_source') || 'missing',
      'whole genome sequencing',
    ]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'biosample_attributes.tsv'; a.click();
  };

  const downloadSRAMetadataTSV = () => {
    const headers = ['bioproject_accession', 'biosample_accession', 'library_ID', 'title',
      'library_strategy', 'library_source', 'library_selection', 'library_layout',
      'platform', 'instrument_model', 'design_description', 'filetype', 'filename', 'filename2'];
    const rows = samples.map((s) => {
      const org = getVal(s, 'organism');
      const layout = getVal(s, 'library_layout');
      return [
        bioproject,
        '',  // biosample_accession — filled after BioSample submission
        getVal(s, 'sample_name'),
        `Whole genome sequencing of ${org || 'bacterial isolate'} ${getVal(s, 'sample_name')}`,
        getVal(s, 'library_strategy'),
        getVal(s, 'library_source'),
        getVal(s, 'library_selection'),
        layout,
        getVal(s, 'platform'),
        getVal(s, 'instrument_model'),
        `${org || 'Bacterial'} genomic DNA library`,
        getVal(s, 'filetype'),
        getVal(s, 'filename1'),
        layout === 'paired' ? getVal(s, 'filename2') : '',
      ];
    });
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'sra_metadata.tsv'; a.click();
  };

  if (loading) return <div className="flex items-center justify-center h-32"><div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Prepare BioSample and SRA metadata files for NCBI submission. Edit fields below, then download the TSV templates.
      </p>

      {samples.length === 0 ? (
        <div className="card text-center py-8 text-gray-500">No samples with FASTQ files found. Upload sequencing data first.</div>
      ) : (
        <>
          {/* BioProject */}
          <div className="card">
            <div className="flex items-center gap-4">
              <label className="text-sm text-gray-300 font-medium whitespace-nowrap">BioProject Accession:</label>
              <input type="text" value={bioproject} onChange={(e) => setBioproject(e.target.value)}
                placeholder="PRJNA000000 (leave blank if creating new)" className="input flex-1 text-sm" />
            </div>
          </div>

          {/* Download buttons */}
          <div className="flex gap-3">
            <button onClick={downloadBioSampleTSV} className="btn-primary flex items-center gap-2 text-sm">
              <Download className="w-4 h-4" />
              Download BioSample TSV
            </button>
            <button onClick={downloadSRAMetadataTSV} className="btn-primary flex items-center gap-2 text-sm">
              <Download className="w-4 h-4" />
              Download SRA Metadata TSV
            </button>
          </div>

          {/* Editable table */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-3">Sample Metadata ({samples.length} samples)</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Sample</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Organism</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Collection Date</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Location</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Isolation Source</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Layout</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Platform</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Instrument</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Files</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {samples.map((s) => {
                    const plat = getVal(s, 'platform');
                    return (
                      <tr key={s.sample_id} className="hover:bg-gray-800/20">
                        <td className="py-2 px-2 font-medium text-gray-200 whitespace-nowrap">{s.sample_name}</td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'organism')} onChange={(e) => setVal(s.sample_id, 'organism', e.target.value)}
                            className="input text-xs w-40 py-1 px-2" placeholder="Organism" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'collection_date')} onChange={(e) => setVal(s.sample_id, 'collection_date', e.target.value)}
                            className="input text-xs w-28 py-1 px-2" placeholder="YYYY-MM-DD" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'geo_loc_name')} onChange={(e) => setVal(s.sample_id, 'geo_loc_name', e.target.value)}
                            className="input text-xs w-32 py-1 px-2" placeholder="Country: Region" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'isolation_source')} onChange={(e) => setVal(s.sample_id, 'isolation_source', e.target.value)}
                            className="input text-xs w-28 py-1 px-2" placeholder="e.g. blood" />
                        </td>
                        <td className="py-2 px-2">
                          <select value={getVal(s, 'library_layout')} onChange={(e) => setVal(s.sample_id, 'library_layout', e.target.value)}
                            className="input text-xs py-1 px-2">
                            <option value="paired">paired</option>
                            <option value="single">single</option>
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select value={plat} onChange={(e) => setVal(s.sample_id, 'platform', e.target.value)}
                            className="input text-xs py-1 px-2">
                            <option value="ILLUMINA">ILLUMINA</option>
                            <option value="OXFORD_NANOPORE">OXFORD_NANOPORE</option>
                            <option value="PACBIO_SMRT">PACBIO_SMRT</option>
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select value={getVal(s, 'instrument_model')} onChange={(e) => setVal(s.sample_id, 'instrument_model', e.target.value)}
                            className="input text-xs py-1 px-2">
                            {(INSTRUMENT_OPTIONS[plat] || INSTRUMENT_OPTIONS.ILLUMINA).map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-2 text-gray-400 whitespace-nowrap">
                          {s.filenames.slice(0, 2).map((f, i) => (
                            <div key={i} className="truncate max-w-[150px]" title={f}>{f}</div>
                          ))}
                          {s.filenames.length > 2 && <div className="text-gray-600">+{s.filenames.length - 2} more</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Instructions */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-3">SRA Submission Steps</h2>
            <ol className="list-decimal list-inside space-y-2 text-sm text-gray-400">
              <li>Create a <strong className="text-gray-200">BioProject</strong> at <a href="https://submit.ncbi.nlm.nih.gov/" target="_blank" className="text-blue-400 hover:text-blue-300">NCBI Submission Portal</a> (if you don't have one)</li>
              <li>Download and submit the <strong className="text-gray-200">BioSample TSV</strong> — this registers your samples and gives you BioSample accessions</li>
              <li>Enter your BioProject accession above, then download the <strong className="text-gray-200">SRA Metadata TSV</strong></li>
              <li>Fill in the BioSample accessions in the SRA metadata file</li>
              <li>Upload your FASTQ files and the SRA metadata to the <a href="https://submit.ncbi.nlm.nih.gov/" target="_blank" className="text-blue-400 hover:text-blue-300">SRA submission wizard</a></li>
            </ol>
          </div>
        </>
      )}
    </div>
  );
}
