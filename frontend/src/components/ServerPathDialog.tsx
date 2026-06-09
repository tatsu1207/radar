'use client';

import { useState, useEffect, useCallback } from 'react';
import { Folder, FileText, ChevronUp, Check } from 'lucide-react';
import Modal from '@/components/Modal';
import { browseServerFiles, registerServerPaths, globalRegisterServerPaths } from '@/lib/api';
import type { FileBrowserEntry } from '@/lib/api';

interface ServerPathDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId?: string;
  onSubmit: () => void;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

export default function ServerPathDialog({ isOpen, onClose, projectId, onSubmit }: ServerPathDialogProps) {
  const [currentPath, setCurrentPath] = useState<string>('');
  const [entries, setEntries] = useState<FileBrowserEntry[]>([]);
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const browse = useCallback(async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await browseServerFiles(path);
      setCurrentPath(data.current);
      setParentPath(data.parent);
      setEntries(data.entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to browse');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      browse();
      setSelected(new Set());
    }
  }, [isOpen, browse]);

  function toggleEntry(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  function selectAll() {
    const files = entries.filter((e) => !e.is_dir).map((e) => e.path);
    setSelected((prev) => {
      const allSelected = files.every((f) => prev.has(f));
      const next = new Set(prev);
      if (allSelected) {
        files.forEach((f) => next.delete(f));
      } else {
        files.forEach((f) => next.add(f));
      }
      return next;
    });
  }

  async function handleSubmit() {
    if (selected.size === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      if (projectId) {
        await registerServerPaths(projectId, Array.from(selected));
      } else {
        await globalRegisterServerPaths(Array.from(selected));
      }
      setSelected(new Set());
      onSubmit();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to register files');
    } finally {
      setSubmitting(false);
    }
  }

  const fileEntries = entries.filter((e) => !e.is_dir);
  const allSelected = fileEntries.length > 0 && fileEntries.every((e) => selected.has(e.path));

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Files from Server">
      <div className="space-y-3">
        {error && (
          <div className="p-3 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Current path */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-400 font-mono truncate flex-1" title={currentPath}>
            {currentPath}
          </span>
          {parentPath && (
            <button
              onClick={() => browse(parentPath)}
              className="btn-secondary flex items-center gap-1 text-xs px-2 py-1 shrink-0"
            >
              <ChevronUp className="w-3 h-3" />
              Up
            </button>
          )}
        </div>

        {/* File list */}
        <div className="border border-gray-700 rounded-lg overflow-hidden max-h-80 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
            </div>
          ) : entries.length === 0 ? (
            <div className="text-center py-8 text-gray-500 text-sm">Empty directory</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-800/50">
                  <th className="w-8 px-2 py-2 text-left">
                    {fileEntries.length > 0 && (
                      <button
                        onClick={selectAll}
                        className={`w-4 h-4 rounded border flex items-center justify-center ${
                          allSelected
                            ? 'bg-blue-500 border-blue-500'
                            : 'border-gray-600 hover:border-gray-400'
                        }`}
                      >
                        {allSelected && <Check className="w-3 h-3 text-white" />}
                      </button>
                    )}
                  </th>
                  <th className="px-2 py-2 text-left text-gray-400 font-medium">Name</th>
                  <th className="px-2 py-2 text-right text-gray-400 font-medium w-24">Size</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.path}
                    onClick={() => entry.is_dir ? browse(entry.path) : toggleEntry(entry.path)}
                    className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                      selected.has(entry.path)
                        ? 'bg-blue-600/10'
                        : 'hover:bg-gray-800/50'
                    }`}
                  >
                    <td className="px-2 py-1.5">
                      {!entry.is_dir && (
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleEntry(entry.path); }}
                          className={`w-4 h-4 rounded border flex items-center justify-center ${
                            selected.has(entry.path)
                              ? 'bg-blue-500 border-blue-500'
                              : 'border-gray-600'
                          }`}
                        >
                          {selected.has(entry.path) && <Check className="w-3 h-3 text-white" />}
                        </button>
                      )}
                    </td>
                    <td className="px-2 py-1.5 flex items-center gap-2">
                      {entry.is_dir ? (
                        <Folder className="w-4 h-4 text-yellow-400 shrink-0" />
                      ) : (
                        <FileText className="w-4 h-4 text-gray-500 shrink-0" />
                      )}
                      <span className={`truncate ${entry.is_dir ? 'text-yellow-300' : 'text-gray-300'}`}>
                        {entry.name}
                      </span>
                      {entry.is_dir && (
                        <span className="text-xs text-gray-600 ml-auto shrink-0">click to open</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right text-gray-500 text-xs">
                      {formatBytes(entry.size)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Selected count & actions */}
        <div className="flex items-center justify-between pt-2">
          <span className="text-sm text-gray-400">
            {selected.size > 0
              ? `${selected.size} file${selected.size !== 1 ? 's' : ''} selected`
              : 'No files selected'}
          </span>
          <div className="flex gap-3">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting || selected.size === 0}
              className="btn-primary"
            >
              {submitting ? 'Copying...' : `Add ${selected.size || ''} File${selected.size !== 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
