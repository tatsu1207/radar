'use client';

import { useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { authPost, SamplePicker, useSamplePicker } from '@/components/tools/shared';

interface RegionGene { start: number; end: number; strand: number; type: string; name: string | null; hash: string }
interface Region { contig: string; region_start: number; region_end: number; length: number; genes: RegionGene[] }
interface RegionDiagram { name: string; sample_id: string; regions: Region[] }

interface MobileARG {
  gene: string;
  drug_class: string;
  mge_names: string[];
  min_distance: number;
  on_plasmid: boolean;
  replicons: string[];
  same_plasmid_family: boolean;
  strain_replicons: Record<string, string>;
  strain_count: number;
  strains: string[];
  present_in: Record<string, boolean>;
}
interface MobileARGsTable {
  sample_names: string[];
  genes: MobileARG[];
  flanking: number;
  total_mobile_args: number;
  shared_count: number;
}

interface SyntenyData {
  samples: string[];
  sample_ids: string[];
  synteny_matrix: number[][];
  shared_genes_matrix: number[][];
  mode?: string;
  flanking?: number | null;
  message?: string;
  region_diagrams?: RegionDiagram[] | null;
  mobile_args?: MobileARGsTable | null;
}

export default function SynTrackerTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<SyntenyData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredCell, setHoveredCell] = useState<{ i: number; j: number } | null>(null);
  const [synMode, setSynMode] = useState<'full' | 'regions'>('full');
  const [flanking, setFlanking] = useState(20000);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2) return;
    setComputing(true);
    setError(null);
    setData(null);
    try {
      const res = await authPost('/api/tools/syntracker', {
        sample_ids: picker.selectedIds,
        mode: synMode,
        flanking,
      });
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

      {/* Mode selection */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-gray-400">Compare:</span>
        <button onClick={() => setSynMode('full')} className={`px-3 py-1.5 rounded-lg text-xs font-medium ${synMode === 'full' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
          Full genome
        </button>
        <button onClick={() => setSynMode('regions')} className={`px-3 py-1.5 rounded-lg text-xs font-medium ${synMode === 'regions' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
          ARG + mobilome regions
        </button>
        {synMode === 'regions' && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500">Flanking:</span>
            <select value={flanking} onChange={(e) => setFlanking(Number(e.target.value))} className="input text-xs py-1 px-2">
              <option value={5000}>5 kb</option>
              <option value={10000}>10 kb</option>
              <option value={20000}>20 kb</option>
              <option value={50000}>50 kb</option>
            </select>
          </div>
        )}
      </div>

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

      {/* Mobile ARGs table */}
      {data?.mobile_args && data.mobile_args.genes.length > 0 && (() => {
        const ma = data.mobile_args!;
        const downloadMobileArgs = () => {
          const headers = ['Gene', 'Drug Class', 'Associated MGE', 'Distance (bp)', 'Plasmid', 'Replicon', 'Same Plasmid Family', 'Strain Count', ...ma.sample_names];
          const rows = ma.genes.map((g) => [
            g.gene, g.drug_class, g.mge_names.join('; '), g.min_distance, g.on_plasmid ? 'Yes' : 'No',
            g.replicons.join('; '), g.same_plasmid_family ? 'Yes' : 'No', g.strain_count,
            ...ma.sample_names.map((s) => g.present_in[s] ? '1' : '0'),
          ]);
          const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
          const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `mobile_args_${(ma.flanking / 1000).toFixed(0)}kb.tsv`;
          a.click();
          URL.revokeObjectURL(a.href);
        };

        return (
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-semibold text-gray-100">Mobile ARGs (within {(ma.flanking / 1000).toFixed(0)} kb of MGE)</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {ma.total_mobile_args} mobile ARGs found, {ma.shared_count} shared across 2+ strains
                </p>
              </div>
              <button onClick={downloadMobileArgs} className="btn-secondary text-xs flex items-center gap-1.5">
                <Download className="w-3.5 h-3.5" />
                Download TSV
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left px-2 py-1.5 text-gray-400 font-medium sticky left-0 bg-gray-900 z-10">Gene</th>
                    <th className="text-left px-2 py-1.5 text-gray-400 font-medium">Drug Class</th>
                    <th className="text-left px-2 py-1.5 text-gray-400 font-medium">Associated MGE</th>
                    <th className="text-center px-2 py-1.5 text-gray-400 font-medium">Distance</th>
                    <th className="text-center px-2 py-1.5 text-gray-400 font-medium">Plasmid</th>
                    <th className="text-left px-2 py-1.5 text-gray-400 font-medium">Replicon</th>
                    {ma.sample_names.map((s) => (
                      <th key={s} className="text-center px-2 py-1.5 text-gray-400 font-medium whitespace-nowrap">{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ma.genes.map((g) => (
                    <tr key={g.gene} className={`border-b border-gray-800/30 ${g.strain_count > 1 ? 'bg-red-900/10' : ''}`}>
                      <td className="px-2 py-1.5 text-red-400 font-mono font-medium sticky left-0 bg-gray-900 z-10">{g.gene}</td>
                      <td className="px-2 py-1.5 text-gray-300">{g.drug_class.split(';')[0]}</td>
                      <td className="px-2 py-1.5">
                        {g.mge_names.map((m) => (
                          <span key={m} className="inline-block mr-1 px-1.5 py-0.5 bg-purple-900/30 rounded text-purple-300 text-[10px]">{m}</span>
                        ))}
                      </td>
                      <td className="px-2 py-1.5 text-center text-gray-400 font-mono">{g.min_distance === 0 ? 'overlap' : `${(g.min_distance / 1000).toFixed(1)}kb`}</td>
                      <td className="px-2 py-1.5 text-center">{g.on_plasmid ? <span className="text-orange-400">Yes</span> : <span className="text-gray-600">No</span>}</td>
                      <td className="px-2 py-1.5">
                        {g.replicons.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {g.replicons.map((r) => (
                              <span key={r} className="px-1.5 py-0.5 bg-blue-900/30 rounded text-blue-300 text-[10px]">{r}</span>
                            ))}
                            {g.same_plasmid_family && (
                              <span className="px-1.5 py-0.5 bg-red-900/40 rounded text-red-300 text-[10px] font-bold" title="Same plasmid replicon found in multiple strains — likely plasmid-mediated transfer">SHARED</span>
                            )}
                          </div>
                        ) : <span className="text-gray-700">—</span>}
                      </td>
                      {ma.sample_names.map((s) => (
                        <td key={s} className="px-2 py-1.5 text-center">
                          {g.present_in[s] ? <span className="text-red-400 font-bold">+</span> : <span className="text-gray-700">·</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}

      {data?.mobile_args && data.mobile_args.genes.length === 0 && data.mode === 'regions' && (
        <div className="card text-center py-6 text-gray-500 text-sm">
          No ARGs found within {((data.flanking || 20000) / 1000).toFixed(0)} kb of mobile elements.
        </div>
      )}


      {picker.selectedIds.length >= 2 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Compute Synteny&quot; to analyze gene-order conservation.</div>
      )}
    </div>
  );
}
