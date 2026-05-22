'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Download, Upload, Check, X, Plus } from 'lucide-react';
import { getAllMetadata, uploadMetadataGlobal, updateMetadata } from '@/lib/api';
import type { MetadataRow } from '@/lib/api';

function EditableCell({
  value,
  onSave,
  placeholder,
}: {
  value: string | null;
  onSave: (val: string) => Promise<void>;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || '');
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function startEdit() {
    setDraft(value || '');
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function save() {
    if (draft === (value || '')) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } catch {
      // keep editing on error
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    setDraft(value || '');
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save();
            if (e.key === 'Escape') cancel();
          }}
          className="input text-xs py-0.5 px-1.5 w-full min-w-[80px]"
          disabled={saving}
          placeholder={placeholder}
        />
        <button onClick={save} disabled={saving} className="p-0.5 text-green-400 hover:text-green-300">
          <Check className="w-3.5 h-3.5" />
        </button>
        <button onClick={cancel} className="p-0.5 text-gray-500 hover:text-gray-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <span
      onClick={startEdit}
      className="cursor-pointer hover:bg-gray-800/50 rounded px-1 py-0.5 -mx-1 block min-h-[1.5em]"
      title="Click to edit"
    >
      {value || <span className="text-gray-600">&mdash;</span>}
    </span>
  );
}

export default function MetadataPage() {
  const [rows, setRows] = useState<MetadataRow[]>([]);
  const [customColumns, setCustomColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [addingColumn, setAddingColumn] = useState(false);
  const [newColumnName, setNewColumnName] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const newColRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    try {
      const data = await getAllMetadata();
      setRows(data.rows);
      setCustomColumns(data.custom_columns);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load metadata');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  function handleDownload() {
    const link = document.createElement('a');
    link.href = '/api/metadata/download';
    link.download = 'metadata.tsv';
    link.click();
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg(null);
    setError(null);
    try {
      const result = await uploadMetadataGlobal(file);
      const parts: string[] = [];
      if (result.created > 0) parts.push(`${result.created} created`);
      if (result.updated > 0) parts.push(`${result.updated} updated`);
      if (result.errors.length > 0) parts.push(`${result.errors.length} errors`);
      setUploadMsg(parts.join(', ') || 'No changes');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleCellSave(sampleId: string, field: string, value: string) {
    const fixedFields = ['source', 'collection_date', 'location', 'species'];
    try {
      if (fixedFields.includes(field)) {
        await updateMetadata(sampleId, { [field]: value || null } as any);
      } else {
        // Custom field — need to get current custom_fields and merge
        const row = rows.find((r) => r.sample_id === sampleId);
        const currentCustom: Record<string, string> = {};
        for (const col of customColumns) {
          const val = row?.[col];
          if (val) currentCustom[col] = val;
        }
        currentCustom[field] = value;
        await updateMetadata(sampleId, { custom_fields: currentCustom } as any);
      }
      // Update local state
      setRows((prev) =>
        prev.map((r) =>
          r.sample_id === sampleId ? { ...r, [field]: value || null } : r
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
      throw err;
    }
  }

  function handleAddColumn() {
    const name = newColumnName.trim().toLowerCase().replace(/\s+/g, '_');
    if (!name || customColumns.includes(name)) {
      setAddingColumn(false);
      setNewColumnName('');
      return;
    }
    setCustomColumns((prev) => [...prev, name]);
    setAddingColumn(false);
    setNewColumnName('');
  }

  const fixedColumns = ['source', 'collection_date', 'location'];
  const columnLabels: Record<string, string> = {
    source: 'Source',
    collection_date: 'Collection Date\n(YYYY-MM-DD)',
    location: 'Location',
  };

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
          <h1 className="text-2xl font-bold text-white">Metadata</h1>
          <p className="text-gray-400 text-sm mt-1">Click any cell to edit. Upload a TSV for bulk updates.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleDownload}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <Download className="w-4 h-4" />
            Download TSV
          </button>
          <label className={`btn-primary flex items-center gap-2 text-sm cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
            <Upload className="w-4 h-4" />
            {uploading ? 'Uploading...' : 'Upload TSV'}
            <input
              ref={fileRef}
              type="file"
              accept=".tsv,.csv,.txt,.xlsx,.xls"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">dismiss</button>
        </div>
      )}

      {uploadMsg && (
        <div className="mb-4 p-4 bg-green-600/20 border border-green-600/50 rounded-lg text-green-300 text-sm">
          {uploadMsg}
        </div>
      )}

      <div className="mb-4 text-sm text-gray-400">
        {rows.length} sample{rows.length !== 1 ? 's' : ''}
      </div>

      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-gray-500 border border-dashed border-gray-700 rounded-lg gap-2">
          <p>No samples yet. Upload files first, then add metadata here.</p>
        </div>
      ) : (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header text-center align-middle">Sample</th>
                  {fixedColumns.map((col) => (
                    <th key={col} className="table-header whitespace-pre-line text-center align-middle">
                      {columnLabels[col] || col}
                    </th>
                  ))}
                  {customColumns.map((col) => (
                    <th key={col} className="table-header text-center align-middle">
                      {col}
                    </th>
                  ))}
                  <th className="table-header w-10">
                    {addingColumn ? (
                      <div className="flex items-center gap-1">
                        <input
                          ref={newColRef}
                          type="text"
                          value={newColumnName}
                          onChange={(e) => setNewColumnName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleAddColumn();
                            if (e.key === 'Escape') { setAddingColumn(false); setNewColumnName(''); }
                          }}
                          placeholder="column name"
                          className="input text-xs py-0.5 px-1.5 w-24"
                          autoFocus
                        />
                        <button onClick={handleAddColumn} className="p-0.5 text-green-400"><Check className="w-3.5 h-3.5" /></button>
                        <button onClick={() => { setAddingColumn(false); setNewColumnName(''); }} className="p-0.5 text-gray-500"><X className="w-3.5 h-3.5" /></button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setAddingColumn(true)}
                        className="p-1 rounded hover:bg-gray-700 text-gray-500 hover:text-gray-300 transition-colors"
                        title="Add custom column"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    )}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.sample_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="table-cell">
                      <span className="text-gray-100 font-medium">{row.sample_name}</span>
                    </td>
                    {fixedColumns.map((col) => (
                      <td key={col} className="table-cell text-sm">
                        <EditableCell
                          value={row[col] || null}
                          onSave={(val) => handleCellSave(row.sample_id, col, val)}
                          placeholder={columnLabels[col] || col}
                        />
                      </td>
                    ))}
                    {customColumns.map((col) => (
                      <td key={col} className="table-cell text-sm">
                        <EditableCell
                          value={row[col] || null}
                          onSave={(val) => handleCellSave(row.sample_id, col, val)}
                          placeholder={col}
                        />
                      </td>
                    ))}
                    <td className="table-cell"></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
