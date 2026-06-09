'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Check, AlertTriangle, Minus, Trash2, Upload, Download, X, Play, Square, CheckCircle, XCircle, Loader2, HardDrive, RotateCw } from 'lucide-react';
import {
  getAllFileManager,
  deleteFileManagerSample,
  globalUploadFiles,
  globalSubmitSRA,
  globalGetSRADownloads,
  cancelSRADownload,
  removeSRADownload,
  retrySRADownload,
  startPipeline,
  cancelJob,
} from '@/lib/api';
import type { FileManagerSample, SRADownload } from '@/lib/api';
import ServerPathDialog from '@/components/ServerPathDialog';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[i]}`;
}

function FileSlotCell({
  file,
  isMissingPair,
}: {
  file: { id: string; filename: string; size: number } | null;
  isMissingPair: boolean;
}) {
  if (file) {
    return (
      <div className="flex items-center gap-2">
        <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
        <span className="text-gray-300 truncate max-w-[120px]" title={file.filename}>
          {formatBytes(file.size)}
        </span>
      </div>
    );
  }
  if (isMissingPair) {
    return (
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
        <span className="text-yellow-400">missing</span>
      </div>
    );
  }
  return (
    <span className="text-gray-600">
      <Minus className="w-4 h-4" />
    </span>
  );
}

function SRAStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: 'bg-yellow-600/20 text-yellow-400 border-yellow-500/30',
    downloading: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
    complete: 'bg-green-600/20 text-green-400 border-green-500/30',
    failed: 'bg-red-600/20 text-red-400 border-red-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${styles[status] || styles.queued}`}>
      {status}
    </span>
  );
}

export default function GlobalFilesPage() {
  const [samples, setSamples] = useState<FileManagerSample[]>([]);
  const [sraDownloads, setSraDownloads] = useState<SRADownload[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [showSRA, setShowSRA] = useState(false);
  const [showServerPath, setShowServerPath] = useState(false);

  const [sraInput, setSraInput] = useState('');
  const [sraSubmitting, setSraSubmitting] = useState(false);
  const [pipelineStarting, setPipelineStarting] = useState<string | null>(null);
  const [pipelineCancelling, setPipelineCancelling] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    try {
      const [fileData, sraData] = await Promise.all([
        getAllFileManager(),
        globalGetSRADownloads().catch(() => [] as SRADownload[]),
      ]);
      setSamples(fileData.samples);
      setSraDownloads(sraData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Poll when any pipelines are running
  useEffect(() => {
    const hasRunning = samples.some((s) => s.pipeline_status === 'running');
    if (!hasRunning) return;
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [samples, loadData]);

  // Poll SRA downloads if any are in progress
  useEffect(() => {
    const hasActive = sraDownloads.some((d) => d.status === 'queued' || d.status === 'downloading');
    if (!hasActive) return;
    const interval = setInterval(async () => {
      try {
        const [fileData, sraData] = await Promise.all([
          getAllFileManager(),
          globalGetSRADownloads(),
        ]);
        setSamples(fileData.samples);
        setSraDownloads(sraData);
      } catch {}
    }, 5000);
    return () => clearInterval(interval);
  }, [sraDownloads]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    setUploading(true);
    setUploadProgress(0);
    setError(null);
    try {
      const data = await globalUploadFiles(Array.from(fileList), (percent) => {
        setUploadProgress(percent);
      });
      setSamples(data.samples);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleSRASubmit() {
    const accessions = sraInput
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (accessions.length === 0) return;
    setSraSubmitting(true);
    setError(null);
    try {
      const newDownloads = await globalSubmitSRA(accessions);
      setSraDownloads((prev) => [...newDownloads, ...prev]);
      setSraInput('');
      setShowSRA(false);
      // Reload files
      const fileData = await getAllFileManager();
      setSamples(fileData.samples);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SRA submission failed');
    } finally {
      setSraSubmitting(false);
    }
  }

  async function handleDeleteSample(sampleId: string) {
    const sample = samples.find((s) => s.sample_id === sampleId);
    if (!sample?.project_id) return;
    try {
      await deleteFileManagerSample(sample.project_id, sampleId);
      setSamples((prev) => prev.filter((s) => s.sample_id !== sampleId));
      setDeleteConfirm(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete sample');
    }
  }

  async function handleStartPipeline(sampleId: string) {
    setPipelineStarting(sampleId);
    setError(null);
    try {
      await startPipeline(sampleId, 12);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start pipeline');
    } finally {
      setPipelineStarting(null);
    }
  }

  async function handleCancelPipeline(jobId: string) {
    setPipelineCancelling(jobId);
    try {
      await cancelJob(jobId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel pipeline');
    } finally {
      setPipelineCancelling(null);
    }
  }

  async function handleCancelSRA(downloadId: string) {
    try {
      await cancelSRADownload(downloadId);
      setSraDownloads((prev) =>
        prev.map((d) => (d.id === downloadId ? { ...d, status: 'failed' as const, error_message: 'Cancelled by user' } : d))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel download');
    }
  }

  async function handleRemoveSRA(downloadId: string) {
    try {
      await removeSRADownload(downloadId);
      setSraDownloads((prev) => prev.filter((d) => d.id !== downloadId));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove download');
    }
  }

  async function handleRetrySRA(downloadId: string) {
    try {
      await retrySRADownload(downloadId);
      setSraDownloads((prev) =>
        prev.map((d) => (d.id === downloadId ? { ...d, status: 'queued' as const, progress: 0, error_message: null } : d))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry download');
    }
  }

  const activeSRA = sraDownloads.filter((d) => d.status === 'queued' || d.status === 'downloading');

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
        <h1 className="text-2xl font-bold text-white">Files</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowServerPath(true)}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <HardDrive className="w-4 h-4" />
            Add from Server
          </button>
          <button
            onClick={() => setShowSRA(true)}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Download className="w-4 h-4" />
            Fetch from SRA
          </button>
          <label className={`btn-primary flex items-center gap-2 text-sm cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
            <Upload className="w-4 h-4" />
            {uploading ? `Uploading ${uploadProgress}%` : 'Upload Files'}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".fastq,.fq,.fasta,.fa,.fna,.gz"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {uploading && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-sm text-gray-400 mb-1.5">
            <span>Uploading...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* SRA Download Dialog */}
      {showSRA && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" onClick={() => setShowSRA(false)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Fetch from NCBI SRA</h2>
              <button onClick={() => setShowSRA(false)} className="text-gray-400 hover:text-gray-200">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-gray-400 mb-4">
              Enter one or more SRR accession numbers (separated by commas, spaces, or newlines).
            </p>
            <textarea
              value={sraInput}
              onChange={(e) => setSraInput(e.target.value)}
              placeholder="SRR1234567, SRR1234568..."
              rows={4}
              className="input w-full resize-none mb-4"
              autoFocus
            />
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowSRA(false)} className="btn-secondary text-sm">
                Cancel
              </button>
              <button
                onClick={handleSRASubmit}
                disabled={sraSubmitting || sraInput.trim().length === 0}
                className="btn-primary text-sm"
              >
                {sraSubmitting ? 'Submitting...' : 'Fetch'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SRA Downloads */}
      {sraDownloads.length > 0 && (
        <div className="mb-4 card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">SRA Downloads</h3>
          <div className="space-y-2">
            {sraDownloads.map((dl) => (
              <div key={dl.id} className="flex items-center justify-between text-sm">
                <span className="text-gray-200 font-mono">{dl.srr_accession}</span>
                <div className="flex items-center gap-3">
                  {dl.status === 'downloading' && (
                    <div className="w-24 bg-gray-800 rounded-full h-1.5">
                      <div
                        className="bg-blue-500 h-1.5 rounded-full transition-all"
                        style={{ width: `${dl.progress}%` }}
                      />
                    </div>
                  )}
                  <SRAStatusBadge status={dl.status} />
                  {(dl.status === 'queued' || dl.status === 'downloading') && (
                    <button
                      onClick={() => handleCancelSRA(dl.id)}
                      className="p-1 rounded hover:bg-red-600/20 text-gray-400 hover:text-red-400 transition-colors"
                      title="Stop download"
                    >
                      <Square className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {dl.status === 'failed' && (
                    <button
                      onClick={() => handleRetrySRA(dl.id)}
                      className="p-1 rounded hover:bg-blue-600/20 text-gray-400 hover:text-blue-400 transition-colors"
                      title="Retry download"
                    >
                      <RotateCw className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => handleRemoveSRA(dl.id)}
                    className="p-1 rounded hover:bg-red-600/20 text-gray-400 hover:text-red-400 transition-colors"
                    title="Remove"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mb-4 text-sm text-gray-400">
        {samples.length} sample{samples.length !== 1 ? 's' : ''}
      </div>

      {samples.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-gray-500 border border-dashed border-gray-700 rounded-lg">
          <p>No samples yet. Upload files or fetch from SRA to get started.</p>
        </div>
      ) : (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Sample</th>
                  <th className="table-header">Type</th>
                  <th className="table-header">R1</th>
                  <th className="table-header">R2</th>
                  <th className="table-header">ONT</th>
                  <th className="table-header">PacBio</th>
                  <th className="table-header">Pipeline</th>
                  <th className="table-header">Completeness</th>
                  <th className="table-header w-10"></th>
                </tr>
              </thead>
              <tbody>
                {samples.map((sample) => {
                  const hasR1 = sample.illumina_r1 !== null;
                  const hasR2 = sample.illumina_r2 !== null;
                  const r2MissingPair = hasR1 && !hasR2;
                  const sraInProgress = sraDownloads.some(
                    (d) => d.sample_id === sample.sample_id && (d.status === 'queued' || d.status === 'downloading')
                  );

                  return (
                    <tr key={sample.sample_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="table-cell">
                        <span className="text-gray-100 font-medium">{sample.name}</span>
                      </td>
                      <td className="table-cell">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          sample.input_type === 'fasta' ? 'bg-cyan-600/20 text-cyan-300' : 'bg-blue-600/20 text-blue-300'
                        }`}>{sample.input_type === 'fasta' ? 'FASTA' : 'FASTQ'}</span>
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.illumina_r1} isMissingPair={false} />
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.illumina_r2} isMissingPair={r2MissingPair} />
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.long_read_platform !== 'pacbio' ? sample.long_read : null} isMissingPair={false} />
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.long_read_platform === 'pacbio' ? sample.long_read : null} isMissingPair={false} />
                      </td>
                      <td className="table-cell">
                        {sraInProgress ? (
                          <div className="flex items-center gap-1.5">
                            <Download className="w-4 h-4 text-yellow-400 animate-pulse" />
                            <span className="text-xs text-yellow-400">Downloading...</span>
                          </div>
                        ) : sample.pipeline_status === 'complete' ? (
                          <div className="flex items-center gap-1.5">
                            <CheckCircle className="w-4 h-4 text-green-400" />
                            <button
                              onClick={() => handleStartPipeline(sample.sample_id)}
                              disabled={pipelineStarting === sample.sample_id}
                              className="px-2 py-0.5 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
                            >
                              Re-start
                            </button>
                          </div>
                        ) : sample.pipeline_status === 'running' ? (
                          <div className="flex items-center gap-1.5">
                            <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
                            <span className="text-xs text-blue-400 font-mono">{sample.pipeline_progress}%</span>
                            {sample.pipeline_job_id && (
                              <button
                                onClick={() => handleCancelPipeline(sample.pipeline_job_id!)}
                                disabled={pipelineCancelling === sample.pipeline_job_id}
                                className="px-2 py-0.5 text-xs rounded bg-red-900/40 hover:bg-red-900/70 text-red-300 transition-colors"
                              >
                                Stop
                              </button>
                            )}
                          </div>
                        ) : sample.pipeline_status === 'failed' ? (
                          <div className="flex items-center gap-1.5">
                            <XCircle className="w-4 h-4 text-red-400" />
                            <button
                              onClick={() => handleStartPipeline(sample.sample_id)}
                              disabled={pipelineStarting === sample.sample_id}
                              className="px-2 py-0.5 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
                            >
                              Start
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => handleStartPipeline(sample.sample_id)}
                            disabled={pipelineStarting === sample.sample_id}
                            className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white transition-colors"
                          >
                            {pipelineStarting === sample.sample_id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Play className="w-3.5 h-3.5" />
                            )}
                            Start
                          </button>
                        )}
                      </td>
                      <td className="table-cell text-center">
                        {sample.busco_complete != null ? (
                          <span className={`text-xs font-medium ${
                            sample.busco_complete >= 95 ? 'text-green-400' :
                            sample.busco_complete >= 80 ? 'text-yellow-400' :
                            'text-red-400'
                          }`}>
                            {sample.busco_complete.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-gray-600">&mdash;</span>
                        )}
                      </td>
                      <td className="table-cell">
                        {deleteConfirm === sample.sample_id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleDeleteSample(sample.sample_id)}
                              className="px-2 py-0.5 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setDeleteConfirm(null)}
                              className="px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded hover:bg-gray-600"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDeleteConfirm(sample.sample_id)}
                            className="p-1.5 rounded-lg hover:bg-red-600/20 text-gray-400 hover:text-red-400 transition-colors"
                            title="Delete sample"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ServerPathDialog
        isOpen={showServerPath}
        onClose={() => setShowServerPath(false)}
        onSubmit={() => loadData()}
      />
    </div>
  );
}
