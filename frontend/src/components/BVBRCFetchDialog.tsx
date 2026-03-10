'use client';

import { useState } from 'react';
import Modal from '@/components/Modal';
import { submitBVBRC } from '@/lib/api';

interface BVBRCFetchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onSubmit: () => void;
}

export default function BVBRCFetchDialog({ isOpen, onClose, projectId, onSubmit }: BVBRCFetchDialogProps) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function parseGenomeIds(input: string): string[] {
    const items = input
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    return [...new Set(items)];
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const genomeIds = parseGenomeIds(text);
    if (genomeIds.length === 0) return;

    setSubmitting(true);
    setError(null);
    try {
      await submitBVBRC(projectId, genomeIds);
      setText('');
      onSubmit();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit BV-BRC genome IDs');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Fetch from BV-BRC">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        <div>
          <label className="block text-sm text-gray-400 mb-1">BV-BRC Genome IDs</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            className="input w-full resize-none font-mono text-sm"
            placeholder={"83332.12\n83332.111\n83332.222"}
            autoFocus
          />
          <p className="text-xs text-gray-500 mt-1">
            Enter BV-BRC genome IDs, one per line (e.g., 83332.12)
          </p>
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || parseGenomeIds(text).length === 0}
            className="btn-primary"
          >
            {submitting ? 'Submitting...' : `Fetch ${parseGenomeIds(text).length || ''} Genome${parseGenomeIds(text).length !== 1 ? 's' : ''}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
