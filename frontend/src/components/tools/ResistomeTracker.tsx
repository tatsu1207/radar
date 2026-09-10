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
    yearly_time_points?: string[];
    yearly_counts?: Record<string, number[]>;
    yearly_sample_counts?: number[];
  };
  distance_matrix: number[][];
  geo?: GeoSample[];
  locations?: LocationStat[];
}

export default function ResistomeTrackerTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<ResistomeData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subTab, setSubTab] = useState<'matrix' | 'temporal' | 'distance'>('matrix');
  const [regionFilter, setRegionFilter] = useState('all');
  const [hostFilter, setHostFilter] = useState('all');
  const [timeGranularity, setTimeGranularity] = useState<'month' | 'year'>('month');
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

            // Apply filters (only for monthly — yearly doesn't have per-location/host breakdown)
            if (!isYearly) {
              if (regionFilter !== 'all' && data.temporal.location_counts?.[regionFilter]) {
                countsSource = data.temporal.location_counts[regionFilter];
              } else if (hostFilter !== 'all' && data.temporal.host_counts?.[hostFilter]) {
                countsSource = data.temporal.host_counts[hostFilter];
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
                      <button onClick={() => { setHostFilter('all'); setRegionFilter('all'); }} className={`px-2 py-1 rounded text-xs ${hostFilter === 'all' ? 'bg-green-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>All</button>
                      {data.temporal.hosts!.map((h) => (
                        <button key={h} onClick={() => { setHostFilter(h); setRegionFilter('all'); }} className={`px-2 py-1 rounded text-xs ${hostFilter === h ? 'bg-green-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                          {h}
                        </button>
                      ))}
                    </div>
                  )}
                  {/* Region filter */}
                  {locations.length > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">Region:</span>
                      <button onClick={() => { setRegionFilter('all'); setHostFilter('all'); }} className={`px-2 py-1 rounded text-xs ${regionFilter === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>All</button>
                      {locations.map((loc) => (
                        <button key={loc} onClick={() => { setRegionFilter(loc); setHostFilter('all'); }} className={`px-2 py-1 rounded text-xs ${regionFilter === loc ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                          {loc}
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

      {picker.selectedIds.length > 0 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Show Resistome&quot; to view resistance profiles.</div>
      )}
    </div>
  );
}
