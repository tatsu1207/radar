'use client';

import { useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';
import dynamic from 'next/dynamic';
import { authPost, SamplePicker, useSamplePicker } from '@/components/tools/shared';

const TemporalGeoMap = dynamic(() => import('@/components/ResistomeMapInner'), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-64"><div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" /></div>,
});

interface ResistomeCellData { present: number; genes: string[] }
interface GeoSample {
  sample_name: string;
  sample_id: string;
  latitude: number;
  longitude: number;
  location: string;
  source: string;
  host: string;
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
    counts?: Record<string, number[]>;
    sample_counts?: number[];
    locations?: string[];
    location_counts?: Record<string, Record<string, number[]>>;
    hosts?: string[];
    host_counts?: Record<string, Record<string, number[]>>;
    sts?: string[];
    st_counts?: Record<string, Record<string, number[]>>;
    yearly_time_points?: string[];
    yearly_counts?: Record<string, number[]>;
    yearly_sample_counts?: number[];
  };
  distance_matrix: number[][];
  mst?: {
    nodes: { id: number; sample_id: string; name: string; st: string; host: string; location: string; x: number; y: number }[];
    edges: { source: number; target: number; distance: number; shared_loci: number }[];
  } | null;
  geo?: GeoSample[];
  locations?: LocationStat[];
}

export default function ResistomeTrackerTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<ResistomeData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subTab, setSubTab] = useState<'matrix' | 'temporal' | 'distance' | 'mst'>('matrix');
  const [regionFilter, setRegionFilter] = useState('all');
  const [hostFilter, setHostFilter] = useState('all');
  const [stFilter, setStFilter] = useState('all');
  const [timeGranularity, setTimeGranularity] = useState<'month' | 'year'>('month');
  const [mstColorBy, setMstColorBy] = useState<'st' | 'host' | 'region'>('st');
  const [mstHoveredNode, setMstHoveredNode] = useState<number | null>(null);
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
          {data!.mst && (
            <button onClick={() => setSubTab('mst')} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${subTab === 'mst' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              MST
            </button>
          )}
        </div>
      )}

      {/* Resistance Matrix */}
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

      {/* Temporal Trends (with geographic map) */}
      {subTab === 'temporal' && hasTemporal && data && (
        <div className="space-y-4">
          {/* Geographic view with time filter */}
          {data.geo && data.geo.length > 0 && (
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-100 mb-4">Geographic AMR Distribution Over Time</h2>
              <TemporalGeoMap geo={data.geo} locations={data.locations || []} />
            </div>
          )}

          {/* Bar chart */}
          {data.temporal.time_points.length > 0 && data.temporal.counts && (() => {
            const colors = ['#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6', '#EC4899', '#F97316', '#06B6D4', '#84CC16', '#A855F7', '#14B8A6', '#E11D48'];
            const locations = data.temporal.locations || [];
            // Select time points and counts based on granularity
            const isYearly = timeGranularity === 'year';
            const timePoints = isYearly
              ? (data.temporal.yearly_time_points || data.temporal.time_points)
              : data.temporal.time_points;
            let countsSource = isYearly
              ? (data.temporal.yearly_counts || data.temporal.counts!)
              : data.temporal.counts!;

            // Apply filters (only for monthly — yearly doesn't have per-filter breakdown)
            if (!isYearly) {
              if (regionFilter !== 'all' && data.temporal.location_counts?.[regionFilter]) {
                countsSource = data.temporal.location_counts[regionFilter];
              } else if (hostFilter !== 'all' && data.temporal.host_counts?.[hostFilter]) {
                countsSource = data.temporal.host_counts[hostFilter];
              } else if (stFilter !== 'all' && data.temporal.st_counts?.[stFilter]) {
                countsSource = data.temporal.st_counts[stFilter];
              }
            }

            const chartData = timePoints.map((tp, idx) => {
              const point: Record<string, string | number> = { date: tp };
              for (const dc of data.temporal.drug_classes) {
                point[dc] = countsSource[dc]?.[idx] ?? 0;
              }
              return point;
            });

            const downloadChart = () => {
              const headers = ['Date', ...data.temporal.drug_classes];
              const rows = chartData.map((d) => [d.date, ...data.temporal.drug_classes.map((dc) => d[dc])]);
              const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
              const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
              const a = document.createElement('a');
              a.href = URL.createObjectURL(blob);
              a.download = `resistome_over_time${regionFilter !== 'all' ? '_' + regionFilter : ''}.tsv`;
              a.click();
              URL.revokeObjectURL(a.href);
            };

            return (
              <div className="card">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-semibold text-gray-100">Resistant Isolate Count Over Time</h2>
                  <button onClick={downloadChart} className="btn-secondary text-xs flex items-center gap-1.5">
                    <Download className="w-3.5 h-3.5" />
                    Download TSV
                  </button>
                </div>

                {/* Filters */}
                <div className="flex flex-wrap items-center gap-4 mb-4">
                  {/* Time granularity */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">View:</span>
                    <button onClick={() => setTimeGranularity('month')} className={`px-2 py-1 rounded text-xs ${timeGranularity === 'month' ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>Monthly</button>
                    <button onClick={() => setTimeGranularity('year')} className={`px-2 py-1 rounded text-xs ${timeGranularity === 'year' ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>Yearly</button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-4 mb-4">
                  {/* Host filter */}
                  {(data.temporal.hosts?.length ?? 0) > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">Host:</span>
                      <button onClick={() => { setHostFilter('all'); setRegionFilter('all'); setStFilter('all'); }} className={`px-2 py-1 rounded text-xs ${hostFilter === 'all' ? 'bg-green-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>All</button>
                      {data.temporal.hosts!.map((h) => (
                        <button key={h} onClick={() => { setHostFilter(h); setRegionFilter('all'); setStFilter('all'); }} className={`px-2 py-1 rounded text-xs ${hostFilter === h ? 'bg-green-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                          {h}
                        </button>
                      ))}
                    </div>
                  )}
                  {/* Region filter */}
                  {locations.length > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">Region:</span>
                      <button onClick={() => { setRegionFilter('all'); setHostFilter('all'); setStFilter('all'); }} className={`px-2 py-1 rounded text-xs ${regionFilter === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>All</button>
                      {locations.map((loc) => (
                        <button key={loc} onClick={() => { setRegionFilter(loc); setHostFilter('all'); setStFilter('all'); }} className={`px-2 py-1 rounded text-xs ${regionFilter === loc ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                          {loc}
                        </button>
                      ))}
                    </div>
                  )}
                  {/* ST filter */}
                  {(data.temporal.sts?.length ?? 0) > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">ST:</span>
                      <button onClick={() => { setStFilter('all'); setHostFilter('all'); setRegionFilter('all'); }} className={`px-2 py-1 rounded text-xs ${stFilter === 'all' ? 'bg-orange-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>All</button>
                      {data.temporal.sts!.map((st) => (
                        <button key={st} onClick={() => { setStFilter(st); setHostFilter('all'); setRegionFilter('all'); }} className={`px-2 py-1 rounded text-xs ${stFilter === st ? 'bg-orange-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                          {st}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="date" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} allowDecimals={false} label={{ value: 'Isolates', angle: -90, position: 'insideLeft', fill: '#6B7280', fontSize: 11 }} />
                    <RechartsTooltip contentStyle={{ background: '#1F2937', border: '1px solid #374151', borderRadius: '8px', fontSize: 11 }} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    {data.temporal.drug_classes.map((dc, i) => (
                      <Bar key={dc} dataKey={dc} fill={colors[i % colors.length]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-2 text-xs text-gray-600">
                  Stacked bars. Y-axis = number of isolates carrying resistance.
                  {regionFilter !== 'all' && ` Region: ${regionFilter}.`}
                  {hostFilter !== 'all' && ` Host: ${hostFilter}.`}
                  {stFilter !== 'all' && ` ST: ${stFilter}.`}
                </p>
              </div>
            );
          })()}
        </div>
      )}

      {/* Similarity (Jaccard distance) */}
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

      {/* MST visualization */}
      {subTab === 'mst' && data?.mst && (() => {
        const mst = data.mst!;
        const [colorBy, setColorBy] = [mstColorBy, setMstColorBy];
        const [hoveredNode, setHoveredNode] = [mstHoveredNode, setMstHoveredNode];

        // Color palettes
        const stColors: Record<string, string> = {};
        const palette = ['#EF4444', '#F59E0B', '#10B981', '#3B82F6', '#8B5CF6', '#EC4899', '#F97316', '#06B6D4', '#84CC16', '#A855F7'];
        const uniqueSTs = Array.from(new Set(mst.nodes.map((n) => n.st))).sort();
        uniqueSTs.forEach((st, i) => { stColors[st] = st === 'Unknown' ? '#6B7280' : palette[i % palette.length]; });

        const hostColors: Record<string, string> = { Chicken: '#F59E0B', Pig: '#EC4899', Cattle: '#8B5CF6', Duck: '#06B6D4', Human: '#EF4444', Unknown: '#6B7280' };
        const regionColors: Record<string, string> = {};
        const uniqueRegions = Array.from(new Set(mst.nodes.map((n) => n.location))).sort();
        uniqueRegions.forEach((r, i) => { regionColors[r] = r === 'Unknown' ? '#6B7280' : palette[i % palette.length]; });

        function nodeColor(node: typeof mst.nodes[0]): string {
          if (colorBy === 'host') return hostColors[node.host] || '#6B7280';
          if (colorBy === 'region') return regionColors[node.location] || '#6B7280';
          return stColors[node.st] || '#6B7280';
        }

        function edgeColor(dist: number): string {
          if (dist <= 5) return '#EF4444';
          if (dist <= 10) return '#F87171';
          if (dist <= 50) return '#9CA3AF';
          return '#4B5563';
        }

        const colorItems = colorBy === 'st' ? uniqueSTs.map((s) => [s, stColors[s]]) :
          colorBy === 'host' ? Object.entries(hostColors).filter(([k]) => mst.nodes.some((n) => n.host === k)) :
          uniqueRegions.map((r) => [r, regionColors[r]]);

        return (
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-100">Minimum Spanning Tree (cgMLST)</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">Color by:</span>
                <button onClick={() => setMstColorBy('st')} className={`px-2 py-1 rounded text-xs ${colorBy === 'st' ? 'bg-orange-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>ST</button>
                <button onClick={() => setMstColorBy('host')} className={`px-2 py-1 rounded text-xs ${colorBy === 'host' ? 'bg-green-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>Host</button>
                <button onClick={() => setMstColorBy('region')} className={`px-2 py-1 rounded text-xs ${colorBy === 'region' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>Region</button>
              </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap items-center gap-3 mb-3 text-xs text-gray-400">
              {(colorItems as [string, string][]).map(([label, color]) => (
                <span key={label} className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ background: color }} />{label}</span>
              ))}
              <span className="ml-2 text-gray-600">|</span>
              <span className="flex items-center gap-1"><span className="w-4 h-0.5" style={{ background: '#EF4444' }} /> ≤5 alleles</span>
              <span className="flex items-center gap-1"><span className="w-4 h-0.5" style={{ background: '#F87171' }} /> 6-10</span>
              <span className="flex items-center gap-1"><span className="w-4 h-0.5" style={{ background: '#9CA3AF' }} /> 11-50</span>
            </div>

            <div className="overflow-auto">
              <svg width={600} height={500} className="rounded-lg" style={{ background: '#0F172A' }}>
                {/* Edges */}
                {mst.edges.map((e, i) => {
                  const src = mst.nodes[e.source];
                  const tgt = mst.nodes[e.target];
                  const mx = (src.x + tgt.x) / 2;
                  const my = (src.y + tgt.y) / 2;
                  return (
                    <g key={`e${i}`}>
                      <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                        stroke={edgeColor(e.distance)} strokeWidth={e.distance <= 5 ? 2.5 : e.distance <= 10 ? 1.5 : 1} opacity={0.8} />
                      <text x={mx} y={my - 4} textAnchor="middle" fill="#94A3B8" fontSize="9">{e.distance}</text>
                    </g>
                  );
                })}
                {/* Nodes */}
                {mst.nodes.map((node) => (
                  <g key={node.id}
                    onMouseEnter={() => setMstHoveredNode(node.id)}
                    onMouseLeave={() => setMstHoveredNode(null)}
                    style={{ cursor: 'pointer' }}>
                    <circle cx={node.x} cy={node.y} r={hoveredNode === node.id ? 14 : 10}
                      fill={nodeColor(node)} stroke={hoveredNode === node.id ? '#FFFFFF' : '#1E293B'} strokeWidth={hoveredNode === node.id ? 2 : 1.5} />
                    <text x={node.x} y={node.y + 22} textAnchor="middle" fill="#CBD5E1" fontSize="9" fontWeight="500">{node.name}</text>
                  </g>
                ))}
              </svg>
            </div>

            {/* Hover detail */}
            {hoveredNode !== null && (() => {
              const node = mst.nodes.find((n) => n.id === hoveredNode);
              if (!node) return null;
              return (
                <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
                  <span className="text-gray-200 font-medium">{node.name}</span>
                  <span className="text-orange-400 ml-3">{node.st}</span>
                  <span className="text-green-400 ml-3">{node.host}</span>
                  <span className="text-blue-400 ml-3">{node.location}</span>
                </div>
              );
            })()}
          </div>
        );
      })()}

      {picker.selectedIds.length > 0 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Show Resistome&quot; to view resistance profiles.</div>
      )}
    </div>
  );
}
