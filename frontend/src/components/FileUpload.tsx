'use client';

import { useState, useCallback, useRef } from 'react';
import { Upload, X, FileText, CheckCircle, AlertCircle } from 'lucide-react';

interface FileUploadProps {
  onUpload: (files: File[]) => Promise<void>;
  acceptedTypes?: string[];
  maxSizeMB?: number;
}

interface FileItem {
  file: File;
  id: string;
  status: 'pending' | 'uploading' | 'done' | 'error';
  progress: number;
  error?: string;
}

const ALLOWED_EXTENSIONS = ['.fastq', '.fastq.gz', '.fq', '.fq.gz', '.fasta', '.fa', '.fna', '.gff', '.gbk', '.csv', '.tsv'];

export default function FileUpload({ onUpload, acceptedTypes, maxSizeMB = 500 }: FileUploadProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = useCallback(
    (file: File): string | null => {
      const maxBytes = maxSizeMB * 1024 * 1024;
      if (file.size > maxBytes) {
        return `File too large (max ${maxSizeMB}MB)`;
      }
      if (acceptedTypes && acceptedTypes.length > 0) {
        const ext = '.' + file.name.split('.').slice(1).join('.');
        if (!acceptedTypes.some((t) => file.name.endsWith(t))) {
          return `Unsupported file type (${ext})`;
        }
      }
      return null;
    },
    [acceptedTypes, maxSizeMB]
  );

  const addFiles = useCallback(
    (newFiles: FileList | File[]) => {
      const items: FileItem[] = Array.from(newFiles).map((file) => {
        const error = validateFile(file);
        return {
          file,
          id: `${file.name}-${Date.now()}-${Math.random()}`,
          status: error ? 'error' : 'pending',
          progress: 0,
          error: error || undefined,
        };
      });
      setFiles((prev) => [...prev, ...items]);
    },
    [validateFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles]
  );

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const handleUpload = async () => {
    const validFiles = files.filter((f) => f.status === 'pending').map((f) => f.file);
    if (validFiles.length === 0) return;

    setUploading(true);
    setFiles((prev) =>
      prev.map((f) => (f.status === 'pending' ? { ...f, status: 'uploading', progress: 50 } : f))
    );

    try {
      await onUpload(validFiles);
      setFiles((prev) =>
        prev.map((f) => (f.status === 'uploading' ? { ...f, status: 'done', progress: 100 } : f))
      );
    } catch (err) {
      setFiles((prev) =>
        prev.map((f) =>
          f.status === 'uploading'
            ? { ...f, status: 'error', error: err instanceof Error ? err.message : 'Upload failed' }
            : f
        )
      );
    } finally {
      setUploading(false);
    }
  };

  const pendingCount = files.filter((f) => f.status === 'pending').length;

  const getFileTypeLabel = (name: string): string => {
    if (name.match(/\.fastq(\.gz)?$|\.fq(\.gz)?$/)) return 'FASTQ';
    if (name.match(/\.fasta$|\.fa$|\.fna$/)) return 'FASTA';
    if (name.endsWith('.gff')) return 'GFF';
    if (name.endsWith('.gbk')) return 'GenBank';
    if (name.endsWith('.csv')) return 'CSV';
    if (name.endsWith('.tsv')) return 'TSV';
    return 'File';
  };

  return (
    <div>
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${
          dragOver
            ? 'border-blue-500 bg-blue-500/10'
            : 'border-gray-700 hover:border-gray-500 bg-gray-900/50'
        }`}
      >
        <Upload className="w-10 h-10 mx-auto mb-3 text-gray-500" />
        <p className="text-gray-300 font-medium mb-1">
          Drag and drop files here, or click to browse
        </p>
        <p className="text-xs text-gray-500">
          Supported: {ALLOWED_EXTENSIONS.join(', ')} (max {maxSizeMB}MB per file)
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-4 space-y-2">
          {files.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700"
            >
              <FileText className="w-5 h-5 text-gray-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-200 truncate">{item.file.name}</span>
                  <span className="text-xs text-gray-500 px-1.5 py-0.5 bg-gray-700 rounded">
                    {getFileTypeLabel(item.file.name)}
                  </span>
                  <span className="text-xs text-gray-500">
                    {(item.file.size / 1024 / 1024).toFixed(1)}MB
                  </span>
                </div>
                {item.status === 'uploading' && (
                  <div className="mt-1 w-full bg-gray-700 rounded-full h-1.5">
                    <div
                      className="bg-blue-500 h-1.5 rounded-full transition-all"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                )}
                {item.error && <p className="text-xs text-red-400 mt-1">{item.error}</p>}
              </div>
              <div className="flex-shrink-0">
                {item.status === 'done' && <CheckCircle className="w-5 h-5 text-green-500" />}
                {item.status === 'error' && <AlertCircle className="w-5 h-5 text-red-500" />}
                {(item.status === 'pending' || item.status === 'error') && (
                  <button
                    onClick={() => removeFile(item.id)}
                    className="p-1 hover:bg-gray-700 rounded transition-colors text-gray-400"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}

          <div className="flex items-center justify-between pt-2">
            <button
              onClick={() => setFiles([])}
              className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Clear all
            </button>
            <button
              onClick={handleUpload}
              disabled={pendingCount === 0 || uploading}
              className="btn-primary flex items-center gap-2"
            >
              <Upload className="w-4 h-4" />
              {uploading ? 'Uploading...' : `Upload ${pendingCount} file${pendingCount !== 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
