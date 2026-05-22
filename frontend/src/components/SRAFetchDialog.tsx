'use client';

import { useState } from 'react';
import Modal from '@/components/Modal';
import { submitSRA } from '@/lib/api';

interface SRAFetchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onSubmit: () => void;
}

export default function SRAFetchDialog({ isOpen, onClose, projectId, onSubmit }: SRAFetchDialogProps) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function parseAccessions(input: string): string[] {
    const items = input
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    return Array.from(new Set(items));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const accessions = parseAccessions(text);
    if (accessions.length === 0) return;

    setSubmitting(true);
    setError(null);
    try {
      await submitSRA(projectId, accessions);
      setText('');
      onSubmit();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit SRA accessions');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Fetch from SRA">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        <div>
          <label className="block text-sm text-gray-400 mb-1">SRR Accessions</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            className="input w-full resize-none font-mono text-sm"
            placeholder={"SRR12345678\nSRR12345679\nSRR12345680"}
            autoFocus
          />
          <p className="text-xs text-gray-500 mt-1">
            Enter SRR accession numbers, one per line (e.g., SRR12345678)
          </p>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || parseAccessions(text).length === 0}
            className="btn-primary"
          >
            {submitting ? 'Submitting...' : `Fetch ${parseAccessions(text).length || ''} Accession${parseAccessions(text).length !== 1 ? 's' : ''}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
