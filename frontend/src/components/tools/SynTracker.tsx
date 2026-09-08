'use client';

import { useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { authPost, SamplePicker, useSamplePicker } from '@/components/tools/shared';

interface RegionGene { start: number; end: number; strand: number; type: string; name: string | null; hash: string }
interface Region { contig: string; region_start: number; region_end: number; length: number; genes: RegionGene[] }
interface RegionDiagram { name: string; sample_id: string; regions: Region[] }

interface SyntenyData {
  samples: string[];
  sample_ids: string[];
  synteny_matrix: number[][];
  shared_genes_matrix: number[][];
  mode?: string;
  flanking?: number | null;
  message?: string;
  region_diagrams?: RegionDiagram[] | null;
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

      {/* Region diagrams (EasyFig-style linear view for ARG+mobilome regions) */}
      {data?.region_diagrams && data.region_diagrams.length >= 2 && (() => {
        const diagrams = data.region_diagrams!;
        // Find common regions across samples (by contig name match)
        const regionKeys = new Set<string>();
        for (const d of diagrams) {
          for (const r of d.regions) {
            regionKeys.add(r.contig);
          }
        }

        const geneColor: Record<string, string> = { arg: '#EF4444', mge: '#A855F7', cds: '#4B5563' };
        const svgWidth = 800;
        const barHeight = 16;
        const gapHeight = 40;
        const marginLeft = 100;
        const marginRight = 20;
        const drawWidth = svgWidth - marginLeft - marginRight;

        return (
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-2">Region Synteny Diagrams</h2>
            <p className="text-xs text-gray-500 mb-4">
              Linear gene maps around ARG/mobilome anchors. Shared genes (same protein hash) connected by gray lines.
              <span className="text-red-400 ml-1">Red</span> = ARG, <span className="text-purple-400 ml-1">Purple</span> = MGE, <span className="text-gray-400 ml-1">Gray</span> = CDS.
            </p>
            {Array.from(regionKeys).map((contigKey) => {
              // Get regions from each sample for this contig
              const sampleRegions = diagrams.map((d) => ({
                name: d.name,
                region: d.regions.find((r) => r.contig === contigKey),
              })).filter((x) => x.region);

              if (sampleRegions.length < 2) return null;
              const maxLen = Math.max(...sampleRegions.map((sr) => sr.region!.length));
              const scale = (pos: number) => (pos / maxLen) * drawWidth;
              const totalHeight = sampleRegions.length * barHeight + (sampleRegions.length - 1) * gapHeight + 30;

              // Build hash→position maps for connecting shared genes
              const hashMaps = sampleRegions.map((sr) => {
                const map: Record<string, { x: number; w: number }> = {};
                for (const g of sr.region!.genes) {
                  if (!map[g.hash]) {
                    map[g.hash] = { x: marginLeft + scale(g.start), w: Math.max(3, scale(g.end - g.start)) };
                  }
                }
                return map;
              });

              return (
                <div key={contigKey} className="mb-4">
                  <p className="text-xs text-gray-400 mb-1">{contigKey} ({(maxLen / 1000).toFixed(1)} kb region)</p>
                  <svg width={svgWidth} height={totalHeight} className="rounded" style={{ background: '#0F172A' }}>
                    {sampleRegions.map((sr, sIdx) => {
                      const y = 15 + sIdx * (barHeight + gapHeight);
                      return (
                        <g key={sr.name}>
                          <text x={5} y={y + barHeight / 2 + 4} fill="#D1D5DB" fontSize="10">{sr.name}</text>
                          <rect x={marginLeft} y={y} width={scale(sr.region!.length)} height={barHeight} fill="#1E293B" stroke="#334155" strokeWidth={0.5} rx={2} />
                          {sr.region!.genes.map((g, gIdx) => (
                            <rect key={gIdx} x={marginLeft + scale(g.start)} y={y} width={Math.max(3, scale(g.end - g.start))} height={barHeight}
                              fill={geneColor[g.type] || geneColor.cds} opacity={0.9} rx={1}>
                              <title>{g.name || g.type} ({g.type})</title>
                            </rect>
                          ))}
                        </g>
                      );
                    })}
                    {/* Connect shared genes between adjacent samples */}
                    {sampleRegions.slice(0, -1).map((_, sIdx) => {
                      const y1 = 15 + sIdx * (barHeight + gapHeight) + barHeight;
                      const y2 = 15 + (sIdx + 1) * (barHeight + gapHeight);
                      const map1 = hashMaps[sIdx];
                      const map2 = hashMaps[sIdx + 1];
                      return Object.keys(map1).filter((h) => map2[h]).map((h) => {
                        const g1 = map1[h];
                        const g2 = map2[h];
                        const cx1 = g1.x + g1.w / 2;
                        const cx2 = g2.x + g2.w / 2;
                        return (
                          <line key={`${sIdx}-${h}`} x1={cx1} y1={y1} x2={cx2} y2={y2}
                            stroke="#475569" strokeWidth={0.5} opacity={0.5} />
                        );
                      });
                    })}
                  </svg>
                </div>
              );
            })}
          </div>
        );
      })()}

      {picker.selectedIds.length >= 2 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Compute Synteny&quot; to analyze gene-order conservation.</div>
      )}
    </div>
  );
}
