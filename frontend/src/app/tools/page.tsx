'use client';

import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';

// ─── Main Page ───
export default function ToolsPage() {
  const [toolTab, setToolTab] = useState<'phenotype' | 'sra'>('phenotype');

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-2">Tools</h1>
      <div className="border-b border-gray-800 mb-6">
        <div className="flex gap-1">
          <button onClick={() => setToolTab('phenotype')} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === 'phenotype' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
            Phenotype Prediction
          </button>
          <button onClick={() => setToolTab('sra')} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === 'sra' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
            SRA Submission
          </button>
        </div>
      </div>

      {toolTab === 'phenotype' && <PhenotypePredictionTool />}
      {toolTab === 'sra' && <SRASubmissionTool />}
    </div>
  );
}

// ─── Phenotype Prediction Tool ───
interface MLPrediction {
  id: string;
  antibiotic: string;
  drug_class: string;
  prediction: string;
  probability: number;
  confidence: string;
  key_genes: string[];
  key_mutations: string[];
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
    fetch('/api/pipeline/status')
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
      const res = await fetch(`/api/samples/${sampleId}/ml-predictions`);
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
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {filtered.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-800/30">
                      <td className="py-2 px-3 font-medium text-gray-200 capitalize">
                        {p.antibiotic.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2 px-3 text-gray-400 text-xs">{p.drug_class}</td>
                      <td className="py-2 px-3 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          p.prediction === 'Resistant'
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
                              className={`h-1.5 rounded-full ${p.prediction === 'Resistant' ? 'bg-red-500' : 'bg-green-500'}`}
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
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
    fetch('/api/sra-submission')
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
