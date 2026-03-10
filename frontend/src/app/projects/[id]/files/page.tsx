'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Upload, Download, Database, FileSpreadsheet, HardDrive } from 'lucide-react';
import {
  getProject,
  getFileManager,
  uploadFilesToProject,
  getSRADownloads,
  getBVBRCFetches,
  uploadMetadataTSV,
  deleteFileManagerFile,
  deleteFileManagerSample,
} from '@/lib/api';
import type { Project, FileManagerSample, SRADownload, BVBRCFetch } from '@/lib/api';
import FileManagerTable from '@/components/FileManagerTable';
import SRAFetchDialog from '@/components/SRAFetchDialog';
import BVBRCFetchDialog from '@/components/BVBRCFetchDialog';
import ServerPathDialog from '@/components/ServerPathDialog';

export default function FileManagerPage() {
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [samples, setSamples] = useState<FileManagerSample[]>([]);
  const [sraDownloads, setSraDownloads] = useState<SRADownload[]>([]);
  const [bvbrcFetches, setBvbrcFetches] = useState<BVBRCFetch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const [showSRA, setShowSRA] = useState(false);
  const [showBVBRC, setShowBVBRC] = useState(false);
  const [showServerPath, setShowServerPath] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const metadataInputRef = useRef<HTMLInputElement>(null);

  const loadFileManager = useCallback(async () => {
    try {
      const data = await getFileManager(projectId);
      setSamples(data.samples);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file manager data');
    }
  }, [projectId]);

  const loadDownloads = useCallback(async () => {
    try {
      const [sra, bvbrc] = await Promise.all([
        getSRADownloads(projectId),
        getBVBRCFetches(projectId),
      ]);
      setSraDownloads(sra);
      setBvbrcFetches(bvbrc);
    } catch {
      // Silently fail on polling
    }
  }, [projectId]);

  const loadAll = useCallback(async () => {
    try {
      const [proj] = await Promise.all([getProject(projectId)]);
      setProject(proj);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project');
    }
    await Promise.all([loadFileManager(), loadDownloads()]);
    setLoading(false);
  }, [projectId, loadFileManager, loadDownloads]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Poll SRA downloads if any are active
  useEffect(() => {
    const hasActive = sraDownloads.some(
      (d) => d.status === 'queued' || d.status === 'downloading'
    );
    if (!hasActive) return;

    const interval = setInterval(async () => {
      await loadDownloads();
      await loadFileManager();
    }, 5000);

    return () => clearInterval(interval);
  }, [sraDownloads, loadDownloads, loadFileManager]);

  async function handleFileUpload(files: FileList | File[]) {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    setUploading(true);
    setError(null);
    try {
      await uploadFilesToProject(projectId, fileArray);
      await loadFileManager();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  async function handleMetadataUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    try {
      const result = await uploadMetadataTSV(projectId, file);
      if (result.errors.length > 0) {
        setError(`Metadata imported with errors: ${result.errors.join('; ')}`);
      }
      await loadFileManager();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Metadata upload failed');
    }
    // Reset input so the same file can be re-uploaded
    if (metadataInputRef.current) metadataInputRef.current.value = '';
  }

  async function handleDeleteSample(sampleId: string) {
    try {
      await deleteFileManagerSample(projectId, sampleId);
      setSamples((prev) => prev.filter((s) => s.sample_id !== sampleId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete sample');
    }
  }

  async function handleDeleteFile(fileId: string) {
    try {
      await deleteFileManagerFile(projectId, fileId);
      await loadFileManager();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete file');
    }
  }

  function handleSRASubmit() {
    loadDownloads();
    loadFileManager();
  }

  function handleBVBRCSubmit() {
    loadDownloads();
    loadFileManager();
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files);
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      className="relative"
    >
      {/* Drag overlay */}
      {dragOver && (
        <div className="fixed inset-0 z-40 bg-blue-600/10 border-2 border-dashed border-blue-500 flex items-center justify-center pointer-events-none">
          <div className="bg-gray-900 border border-blue-500 rounded-xl px-8 py-6 text-center">
            <Upload className="w-12 h-12 text-blue-400 mx-auto mb-2" />
            <p className="text-blue-300 text-lg font-medium">Drop files to upload</p>
          </div>
        </div>
      )}

      <Link
        href={`/projects/${projectId}`}
        className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Project
      </Link>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      <h1 className="text-2xl font-bold text-white mb-6">
        {project?.name ?? 'Project'} - File Manager
      </h1>

      {/* Naming convention */}
      <div className="mb-6 p-4 bg-gray-800/50 border border-gray-700 rounded-lg text-sm text-gray-400">
        <span className="text-gray-300 font-medium">File naming: </span>
        <code className="text-blue-400">SAMPLE_R1.fastq.gz</code> / <code className="text-blue-400">SAMPLE_R2.fastq.gz</code> for Illumina paired-end,{' '}
        <code className="text-blue-400">SAMPLE.fastq.gz</code> for long reads (ONT/PacBio auto-detected)
      </div>

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="btn-primary flex items-center gap-2 text-sm"
        >
          <Upload className="w-4 h-4" />
          {uploading ? 'Uploading...' : 'Upload Files'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) handleFileUpload(e.target.files);
            e.target.value = '';
          }}
        />

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

        <button
          onClick={() => setShowBVBRC(true)}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <Database className="w-4 h-4" />
          Fetch from BV-BRC
        </button>

        <button
          onClick={() => metadataInputRef.current?.click()}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <FileSpreadsheet className="w-4 h-4" />
          Upload Metadata TSV
        </button>
        <input
          ref={metadataInputRef}
          type="file"
          accept=".tsv,.txt,.tab"
          className="hidden"
          onChange={handleMetadataUpload}
        />
      </div>

      {/* File Manager Table */}
      <div className="card mb-6">
        <FileManagerTable
          samples={samples}
          onDeleteSample={handleDeleteSample}
          onDeleteFile={handleDeleteFile}
        />
      </div>

      {/* SRA Downloads */}
      {sraDownloads.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">SRA Downloads</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Accession</th>
                  <th className="table-header">Status</th>
                  <th className="table-header">Error</th>
                </tr>
              </thead>
              <tbody>
                {sraDownloads.map((dl) => (
                  <tr key={dl.id} className="border-b border-gray-800/50">
                    <td className="table-cell font-mono">{dl.srr_accession}</td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <StatusBadge status={dl.status} />
                        {dl.status === 'downloading' && (
                          <div className="flex-1 max-w-[120px]">
                            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                                style={{ width: `${dl.progress}%` }}
                              />
                            </div>
                            <span className="text-xs text-gray-500">{dl.progress}%</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="table-cell text-red-400 text-xs">
                      {dl.error_message || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* BV-BRC Fetches */}
      {bvbrcFetches.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">BV-BRC Fetches</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Genome ID</th>
                  <th className="table-header">Status</th>
                  <th className="table-header">Error</th>
                </tr>
              </thead>
              <tbody>
                {bvbrcFetches.map((fetch) => (
                  <tr key={fetch.id} className="border-b border-gray-800/50">
                    <td className="table-cell font-mono">{fetch.genome_id}</td>
                    <td className="table-cell">
                      <StatusBadge status={fetch.status} />
                    </td>
                    <td className="table-cell text-red-400 text-xs">
                      {fetch.error_message || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Dialogs */}
      <SRAFetchDialog
        isOpen={showSRA}
        onClose={() => setShowSRA(false)}
        projectId={projectId}
        onSubmit={handleSRASubmit}
      />
      <BVBRCFetchDialog
        isOpen={showBVBRC}
        onClose={() => setShowBVBRC(false)}
        projectId={projectId}
        onSubmit={handleBVBRCSubmit}
      />
      <ServerPathDialog
        isOpen={showServerPath}
        onClose={() => setShowServerPath(false)}
        projectId={projectId}
        onSubmit={() => loadFileManager()}
      />
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: 'bg-gray-600/20 text-gray-400 border-gray-500/30',
    downloading: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
    complete: 'bg-green-600/20 text-green-400 border-green-500/30',
    failed: 'bg-red-600/20 text-red-400 border-red-500/30',
  };
  const colorClass = styles[status] || styles.queued;

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colorClass}`}>
      {status}
    </span>
  );
}
