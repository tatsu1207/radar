'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Check, AlertTriangle, Minus, Trash2, FolderKanban } from 'lucide-react';
import { getAllFileManager, deleteFileManagerSample, deleteFileManagerFile } from '@/lib/api';
import type { FileManagerSample } from '@/lib/api';

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

function SourceBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    upload: 'bg-blue-600/20 text-blue-400 border-blue-500/30',
    sra: 'bg-purple-600/20 text-purple-400 border-purple-500/30',
    'bv-brc': 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30',
  };
  const colorClass = colors[source.toLowerCase()] || 'bg-gray-600/20 text-gray-400 border-gray-500/30';
  const label = source.toLowerCase() === 'bv-brc' ? 'BV-BRC' : source.toLowerCase() === 'sra' ? 'SRA' : 'Upload';

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colorClass}`}>
      {label}
    </span>
  );
}

export default function GlobalFilesPage() {
  const [samples, setSamples] = useState<FileManagerSample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await getAllFileManager();
      setSamples(data.samples);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-6">All Files</h1>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="mb-4 text-sm text-gray-400">
        {samples.length} sample{samples.length !== 1 ? 's' : ''} across all projects
      </div>

      {samples.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-gray-500 border border-dashed border-gray-700 rounded-lg">
          <p>No samples yet. Add files via project File Manager pages.</p>
        </div>
      ) : (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Project</th>
                  <th className="table-header">Sample</th>
                  <th className="table-header">Illumina R1</th>
                  <th className="table-header">Illumina R2</th>
                  <th className="table-header">Long Read</th>
                  <th className="table-header">Source</th>
                  <th className="table-header">Metadata</th>
                  <th className="table-header w-10"></th>
                </tr>
              </thead>
              <tbody>
                {samples.map((sample) => {
                  const hasR1 = sample.illumina_r1 !== null;
                  const hasR2 = sample.illumina_r2 !== null;
                  const r2MissingPair = hasR1 && !hasR2;

                  return (
                    <tr key={sample.sample_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="table-cell">
                        {sample.project_id ? (
                          <Link
                            href={`/projects/${sample.project_id}`}
                            className="text-blue-400 hover:text-blue-300 flex items-center gap-1.5"
                          >
                            <FolderKanban className="w-3.5 h-3.5" />
                            {sample.project_name || 'Unknown'}
                          </Link>
                        ) : (
                          <span className="text-gray-500">—</span>
                        )}
                      </td>
                      <td className="table-cell">
                        <span className="text-gray-100 font-medium">{sample.name}</span>
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.illumina_r1} isMissingPair={false} />
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.illumina_r2} isMissingPair={r2MissingPair} />
                      </td>
                      <td className="table-cell">
                        <FileSlotCell file={sample.long_read} isMissingPair={false} />
                      </td>
                      <td className="table-cell">
                        <SourceBadge source={sample.source} />
                      </td>
                      <td className="table-cell">
                        {sample.has_metadata ? (
                          <Check className="w-4 h-4 text-green-400" />
                        ) : (
                          <span className="text-red-400 text-lg leading-none">&times;</span>
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
    </div>
  );
}
