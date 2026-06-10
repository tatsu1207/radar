'use client';

import { useState, useEffect, useMemo } from 'react';
import { Search, CheckSquare, Square, FileBarChart, X, Download } from 'lucide-react';
import Link from 'next/link';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { getAllFileManager, getSampleSummary } from '@/lib/api';
import type { FileManagerSample, SampleSummary } from '@/lib/api';

export default function ResultsPage() {
  const [allSamples, setAllSamples] = useState<FileManagerSample[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [showQC, setShowQC] = useState(false);

  // Per-sample summary cache
  const [summaries, setSummaries] = useState<Record<string, SampleSummary>>({});

  useEffect(() => {
    getAllFileManager()
      .then((res) => {
        setAllSamples(res.samples);
        const completed = new Set(
          res.samples.filter((s) => s.status === 'complete').map((s) => s.sample_id)
        );
        setSelected(completed);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load summaries for completed samples that are selected
  useEffect(() => {
    const toLoad = Array.from(selected).filter(
      (id) => !summaries[id] && allSamples.find((s) => s.sample_id === id)?.status === 'complete'
    );
    if (toLoad.length === 0) return;

    toLoad.forEach((id) => {
      getSampleSummary(id)
        .then((summary) => {
          setSummaries((prev) => ({ ...prev, [id]: summary }));
        })
        .catch(() => {});
    });
  }, [selected, allSamples, summaries]);

  const filtered = useMemo(() => {
    return allSamples.filter((s) => {
      if (s.status !== 'complete') return false;
      const matchesText = !filter || s.name.toLowerCase().includes(filter.toLowerCase());
      return matchesText;
    });
  }, [allSamples, filter]);

  const selectedCompleted = allSamples.filter(
    (s) => selected.has(s.sample_id) && s.status === 'complete'
  );

  // QC chart data
  const quastData = useMemo(() => {
    return selectedCompleted
      .filter((s) => summaries[s.sample_id]?.quast)
      .map((s) => {
        const q = summaries[s.sample_id].quast!;
        return {
          name: s.name,
          'N50 (kbp)': q.n50 ? Math.round(q.n50 / 1000) : 0,
          'Total Length (Mbp)': q.total_length ? +(q.total_length / 1e6).toFixed(2) : 0,
          'Contigs': q.num_contigs || 0,
        };
      });
  }, [selectedCompleted, summaries]);

  const buscoData = useMemo(() => {
    return selectedCompleted
      .filter((s) => summaries[s.sample_id]?.busco)
      .map((s) => {
        const b = summaries[s.sample_id].busco!;
        return {
          name: s.name,
          'Complete': b.complete || 0,
          'Fragmented': b.fragmented || 0,
          'Missing': b.missing || 0,
        };
      });
  }, [selectedCompleted, summaries]);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    const filteredIds = filtered.map((s) => s.sample_id);
    const allSelected = filteredIds.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      if (allSelected) filteredIds.forEach((id) => next.delete(id));
      else filteredIds.forEach((id) => next.add(id));
      return next;
    });
  }

  function formatSpecies(summary: SampleSummary | undefined): React.ReactNode {
    if (!summary?.species) return <span className="text-gray-600">-</span>;
    const parts: string[] = [summary.species];
    if (summary.mlst_st) parts.push(`ST${summary.mlst_st}`);
    if (summary.serotype) parts.push(summary.serotype);
    return (
      <span>
        <span className="italic text-gray-300">{summary.species}</span>
        {(summary.mlst_st || summary.serotype) && (
          <span className="text-gray-500 text-xs ml-1">
            ({[summary.mlst_st ? `ST${summary.mlst_st}` : '', summary.serotype].filter(Boolean).join(', ')})
          </span>
        )}
      </span>
    );
  }

  function formatPlasmids(summary: SampleSummary | undefined): React.ReactNode {
    if (!summary || summary.plasmids.length === 0) return <span className="text-gray-600">-</span>;
    const counts: Record<string, number> = {};
    for (const p of summary.plasmids) {
      const mob = p.mobility || 'non-mobilizable';
      counts[mob] = (counts[mob] || 0) + 1;
    }
    const parts: string[] = [];
    if (counts['conjugative']) parts.push(`${counts['conjugative']} conj`);
    if (counts['mobilizable']) parts.push(`${counts['mobilizable']} mob`);
    if (counts['non-mobilizable']) parts.push(`${counts['non-mobilizable']} non-mob`);
    return <span className="text-gray-300">{parts.join(', ')}</span>;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  const allFilteredSelected = filtered.length > 0 && filtered.every((s) => selected.has(s.sample_id));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Annotation</h1>
          <p className="text-gray-400 text-sm mt-1">
            Select samples to view results. Click sample name for full details.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              const ids = selectedCompleted.map((s) => s.sample_id).join(',');
              if (ids) window.location.href = `/api/export/annotations?sample_ids=${encodeURIComponent(ids)}`;
            }}
            disabled={selectedCompleted.length === 0}
            className="btn-secondary flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Download ({selectedCompleted.length})
          </button>
          <button
            onClick={() => setShowQC(true)}
            disabled={selectedCompleted.length === 0}
            className="btn-primary flex items-center gap-2"
          >
            <FileBarChart className="w-4 h-4" />
            QC Report ({selectedCompleted.length})
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by sample name..."
              className="input w-full pl-10"
            />
          </div>
          <span className="text-sm text-gray-400">
            {filtered.length} completed sample{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Sample table */}
      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="table-header w-10">
                  <button onClick={toggleAll} className="text-gray-400 hover:text-gray-200">
                    {allFilteredSelected ? <CheckSquare className="w-4 h-4 text-blue-400" /> : <Square className="w-4 h-4" />}
                  </button>
                </th>
                <th className="table-header">Sample</th>
                <th className="table-header">Species</th>
                <th className="table-header">Resistance Profile</th>
                <th className="table-header">VFs</th>
                <th className="table-header">Plasmids</th>
                <th className="table-header">Biocide/Metal</th>
                <th className="table-header text-center">Export</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {filtered.map((s) => {
                const isSelected = selected.has(s.sample_id);
                const summary = summaries[s.sample_id];
                return (
                  <tr
                    key={s.sample_id}
                    className={`transition-colors cursor-pointer ${isSelected ? 'bg-blue-600/5' : 'hover:bg-gray-800/50'}`}
                    onClick={() => toggleSelect(s.sample_id)}
                  >
                    <td className="table-cell">
                      {isSelected ? <CheckSquare className="w-4 h-4 text-blue-400" /> : <Square className="w-4 h-4 text-gray-600" />}
                    </td>
                    <td className="table-cell">
                      <Link
                        href={`/samples/${s.sample_id}`}
                        className="font-medium text-blue-400 hover:text-blue-300"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {s.name}
                      </Link>
                    </td>
                    <td className="table-cell text-sm">
                      {summary ? formatSpecies(summary) : <span className="text-gray-600 text-xs">loading...</span>}
                    </td>
                    <td className="table-cell text-sm">
                      {summary ? (
                        summary.drug_resistance.length > 0 ? (
                          <span className="text-red-400">{summary.drug_resistance.join(', ')}</span>
                        ) : <span className="text-gray-500">none detected</span>
                      ) : <span className="text-gray-600 text-xs">...</span>}
                    </td>
                    <td className="table-cell text-sm">
                      {summary ? (
                        summary.vf_genes.length > 0 ? (
                          <span className="text-gray-300 text-xs">{summary.vf_genes.join(', ')}</span>
                        ) : <span className="text-gray-600">-</span>
                      ) : <span className="text-gray-600 text-xs">...</span>}
                    </td>
                    <td className="table-cell text-sm">
                      {summary && summary.plasmids.length > 0 ? (
                        formatPlasmids(summary)
                      ) : summary ? (
                        <span className="text-gray-600">-</span>
                      ) : (
                        <span className="text-gray-600 text-xs">...</span>
                      )}
                    </td>
                    <td className="table-cell text-sm">
                      {summary ? (
                        summary.bacmet && summary.bacmet.length > 0 ? (() => {
                          const compounds = Array.from(new Set(summary.bacmet.map((b) => b.compound).filter(Boolean)));
                          // Show specific compounds first, then count generic efflux
                          const specific = compounds.filter((c) => !c.toLowerCase().includes('efflux') && !c.toLowerCase().includes('stress'));
                          const nEfflux = compounds.length - specific.length;
                          const display = [...specific, ...(nEfflux > 0 ? [`${nEfflux} efflux`] : [])];
                          return <span className="text-gray-300 text-xs">{display.join(', ') || `${summary.bacmet.length} genes`}</span>;
                        })() : <span className="text-gray-600">-</span>
                      ) : <span className="text-gray-600 text-xs">...</span>}
                    </td>
                    <td className="table-cell text-center" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => window.location.href = `/api/samples/${s.sample_id}/export-all`}
                        className="p-1 rounded hover:bg-blue-600/20 text-gray-500 hover:text-blue-400 transition-colors"
                        title="Download all annotations (TSV)"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              {allSamples.length === 0 ? 'No completed samples yet.' : 'No samples match the filter.'}
            </div>
          )}
        </div>
      </div>

      {/* QC Report Modal */}
      {showQC && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowQC(false)}>
          <div
            className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-[90vw] max-w-5xl max-h-[85vh] overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-white">
                QC Report ({selectedCompleted.length} samples)
              </h2>
              <button onClick={() => setShowQC(false)} className="text-gray-400 hover:text-gray-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* QUAST chart */}
            {quastData.length > 0 ? (
              <div className="mb-8">
                <h3 className="text-lg font-semibold text-gray-100 mb-4">Assembly Quality (QUAST)</h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* N50 bar chart */}
                  <div>
                    <h4 className="text-sm text-gray-400 mb-2">N50 (kbp)</h4>
                    <ResponsiveContainer width="100%" height={Math.max(200, quastData.length * 35 + 40)}>
                      <BarChart data={quastData} layout="vertical" margin={{ left: 80, right: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
                        <YAxis type="category" dataKey="name" stroke="#9CA3AF" tick={{ fontSize: 11 }} width={75} />
                        <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }} />
                        <Bar dataKey="N50 (kbp)" fill="#3B82F6" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  {/* Contigs bar chart */}
                  <div>
                    <h4 className="text-sm text-gray-400 mb-2">Number of Contigs</h4>
                    <ResponsiveContainer width="100%" height={Math.max(200, quastData.length * 35 + 40)}>
                      <BarChart data={quastData} layout="vertical" margin={{ left: 80, right: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
                        <YAxis type="category" dataKey="name" stroke="#9CA3AF" tick={{ fontSize: 11 }} width={75} />
                        <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }} />
                        <Bar dataKey="Contigs" fill="#F59E0B" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mb-8 p-6 bg-gray-800/50 rounded-lg text-center text-gray-500">
                No QUAST data available for selected samples.
              </div>
            )}

            {/* BUSCO chart */}
            {buscoData.length > 0 ? (
              <div>
                <h3 className="text-lg font-semibold text-gray-100 mb-4">Genome Completeness (BUSCO)</h3>
                <ResponsiveContainer width="100%" height={Math.max(200, buscoData.length * 35 + 60)}>
                  <BarChart data={buscoData} layout="vertical" margin={{ left: 80, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis type="number" domain={[0, 100]} unit="%" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
                    <YAxis type="category" dataKey="name" stroke="#9CA3AF" tick={{ fontSize: 11 }} width={75} />
                    <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: '8px' }} />
                    <Legend />
                    <Bar dataKey="Complete" stackId="a" fill="#22C55E" />
                    <Bar dataKey="Fragmented" stackId="a" fill="#F59E0B" />
                    <Bar dataKey="Missing" stackId="a" fill="#EF4444" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="p-6 bg-gray-800/50 rounded-lg text-center text-gray-500">
                No BUSCO data available for selected samples.
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
