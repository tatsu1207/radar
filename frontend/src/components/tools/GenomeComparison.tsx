'use client';

import { useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { useToolJob, SamplePicker, useSamplePicker } from '@/components/tools/shared';

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

export default function GenomeComparisonTool() {
  const picker = useSamplePicker();
  const [subTab, setSubTab] = useState<'ani' | 'clusters'>('ani');
  const job = useToolJob<{ ani: ANIData; clusters: ClusterResult }>('/api/tools/ani');
  const [hoveredCell, setHoveredCell] = useState<{ i: number; j: number } | null>(null);

  const aniData = job.data?.ani ?? null;
  const clusterData = job.data?.clusters ?? null;
  const computing = job.computing;
  const error = job.error || (aniData?.message ?? null);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2) return;
    job.submit({ sample_ids: picker.selectedIds });
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

      {/* ANI Matrix view */}
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

      {/* Outbreak Clusters view */}
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
