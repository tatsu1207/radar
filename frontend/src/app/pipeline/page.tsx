'use client';

import { useState, useEffect, useCallback } from 'react';
import { Play, CheckCircle, XCircle, Loader2, Terminal, X, FileDown, Minus, Cpu } from 'lucide-react';
import { getPipelineStatus, startPipeline, getJob } from '@/lib/api';
import type { PipelineStatus } from '@/lib/api';

function StatusCell({ sample, onStart }: { sample: PipelineStatus; onStart: (id: string) => void }) {
  switch (sample.status) {
    case 'complete':
      return (
        <div className="flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-green-400" />
          <span className="text-sm text-green-400">Complete</span>
          <button
            onClick={() => onStart(sample.sample_id)}
            className="ml-2 px-2 py-0.5 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
          >
            Re-run
          </button>
        </div>
      );
    case 'running':
      return (
        <div className="flex items-center gap-2 text-blue-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">In Progress</span>
        </div>
      );
    case 'failed':
      return (
        <div className="flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-400" />
          <span className="text-sm text-red-400">Failed</span>
          <button
            onClick={() => onStart(sample.sample_id)}
            className="ml-2 px-2 py-0.5 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
          >
            Retry
          </button>
        </div>
      );
    default:
      return (
        <button
          onClick={() => onStart(sample.sample_id)}
          className="btn-primary text-xs flex items-center gap-1.5 py-1.5 px-3"
        >
          <Play className="w-3.5 h-3.5" />
          Start
        </button>
      );
  }
}

export default function PipelinePage() {
  const [samples, setSamples] = useState<PipelineStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [threads, setThreads] = useState(12);
  const [logModal, setLogModal] = useState<{ name: string; log: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await getPipelineStatus();
      setSamples(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pipeline status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Poll when any samples are running
  useEffect(() => {
    const hasActive = samples.some((s) => s.status === 'running');
    if (!hasActive) return;
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [samples, loadData]);

  async function handleStart(sampleId: string) {
    setStarting(sampleId);
    setError(null);
    try {
      await startPipeline(sampleId, threads);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start pipeline');
    } finally {
      setStarting(null);
    }
  }

  async function handleStartAll() {
    const toStart = samples.filter((s) => s.status === 'not_started' || s.status === 'failed');
    if (toStart.length === 0) return;
    setError(null);
    for (const s of toStart) {
      try {
        await startPipeline(s.sample_id, threads);
      } catch {
        // continue with others
      }
    }
    await loadData();
  }

  async function handleViewLog(sample: PipelineStatus) {
    if (!sample.job_id) return;
    try {
      const job = await getJob(sample.job_id);
      setLogModal({ name: sample.sample_name, log: job.log || 'No logs available.' });
    } catch {
      setLogModal({ name: sample.sample_name, log: sample.log || 'No logs available.' });
    }
  }

  const notStarted = samples.filter((s) => s.status === 'not_started' || s.status === 'failed').length;
  const running = samples.filter((s) => s.status === 'running').length;
  const complete = samples.filter((s) => s.status === 'complete').length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Pipeline</h1>
          <p className="text-sm text-gray-400 mt-1">
            QC (fastp + Chopper) and assembly (SPAdes / Flye)
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-400">
            <Cpu className="w-4 h-4" />
            <input
              type="number"
              min={1}
              max={128}
              value={threads}
              onChange={(e) => setThreads(Math.max(1, Math.min(128, parseInt(e.target.value) || 12)))}
              className="input w-20 text-center text-sm py-1"
            />
            threads
          </label>
          {notStarted > 0 && (
            <button onClick={handleStartAll} className="btn-primary flex items-center gap-2 text-sm">
              <Play className="w-4 h-4" />
              Start All ({notStarted})
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {running > 0 && (
        <div className="mb-4 p-3 bg-blue-600/10 border border-blue-500/30 rounded-lg text-blue-300 text-sm flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          {running} sample{running !== 1 ? 's' : ''} running &mdash; auto-refreshing
        </div>
      )}

      <div className="mb-4 text-sm text-gray-400">
        {samples.length} sample{samples.length !== 1 ? 's' : ''}
        {complete > 0 && <span className="text-green-400 ml-2">{complete} complete</span>}
        {running > 0 && <span className="text-blue-400 ml-2">{running} running</span>}
      </div>

      {samples.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-gray-500 border border-dashed border-gray-700 rounded-lg">
          <p>No samples yet. Upload files first.</p>
        </div>
      ) : (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Sample</th>
                  <th className="table-header">Pipeline Status</th>
                  <th className="table-header">QC</th>
                  <th className="table-header w-10"></th>
                </tr>
              </thead>
              <tbody>
                {samples.map((sample) => (
                  <tr key={sample.sample_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="table-cell">
                      <span className="text-gray-100 font-medium">{sample.sample_name}</span>
                    </td>
                    <td className="table-cell">
                      {starting === sample.sample_id ? (
                        <div className="flex items-center gap-2 text-gray-400">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span className="text-sm">Starting...</span>
                        </div>
                      ) : (
                        <StatusCell sample={sample} onStart={handleStart} />
                      )}
                    </td>
                    <td className="table-cell">
                      {sample.has_qc ? (
                        <button
                          onClick={() => {
                            const token = localStorage.getItem('radar_token');
                            fetch(`/api/pipeline/qc/${sample.sample_id}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
                              .then(r => r.blob())
                              .then(blob => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${sample.sample_name}_qc.txt`; a.click(); });
                          }}
                          className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 text-sm transition-colors"
                        >
                          <FileDown className="w-4 h-4" />
                          Report
                        </button>
                      ) : (
                        <span className="text-gray-600"><Minus className="w-4 h-4" /></span>
                      )}
                    </td>
                    <td className="table-cell">
                      {sample.job_id && (
                        <button
                          onClick={() => handleViewLog(sample)}
                          className="p-1.5 rounded-lg hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition-colors"
                          title="View log"
                        >
                          <Terminal className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Log Modal */}
      {logModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" onClick={() => setLogModal(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">{logModal.name} - Pipeline Log</h2>
              <button onClick={() => setLogModal(null)} className="text-gray-400 hover:text-gray-200">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="bg-gray-950 rounded-lg p-4 font-mono text-xs text-gray-300 overflow-y-auto whitespace-pre-wrap flex-1">
              {logModal.log}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
